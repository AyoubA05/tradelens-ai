/**
 * Real password-reset integration against dev-auth-migration / neondb.
 *
 * Safety rules carried over from the step-6 incident:
 *   - disposable, per-run-tagged accounts only
 *   - ayoub and Ayoub are read-only invariants; never written to
 *   - cleanup runs in a finally, children before parents
 *   - dev proven back to 2 users with unchanged fingerprints
 *
 * NEVER point this at production.
 */
import bcrypt from "bcryptjs";
import { createHash, randomBytes } from "node:crypto";

import { createAccount } from "../lib/auth/signup.ts";
import { query } from "../lib/db/client.ts";
import { normalizeEmail } from "../lib/auth/contract.ts";
import { attemptLogin, openWebsiteSession, resolveWebsiteSession } from "../lib/auth/login.ts";
import { consumeVerification, issueVerification } from "../lib/auth/verification.ts";
import {
  completeReset,
  hashNewPassword,
  inspectReset,
  issueReset,
  resetEligibility,
  resetUrl,
} from "../lib/auth/password-reset.ts";
import { CaptureTransport } from "../lib/mail/transport.ts";

/**
 * Test fixture, not the real handoff issuer — that is step 9 and is not being
 * built early just to satisfy this test. Inserts a row shaped exactly like the
 * Python issuer produces, so the reset's void-outstanding-handoffs behaviour can
 * be exercised against real data.
 */
async function seedHandoff(userId) {
  const token = randomBytes(32).toString("base64url");
  const now = new Date();
  await query(
    `INSERT INTO auth_handoffs (token_hash, user_id, created_at, expires_at)
     VALUES ($1, $2, $3, $4)`,
    [createHash("sha256").update(token, "utf8").digest("hex"), userId, now,
     new Date(now.getTime() + 120_000)],
  );
  return token;
}

const TAG = `${Date.now()}`.slice(-8);
const address = (n) => `reset+ir${TAG}${n}@example.invalid`;
const OLD_PASSWORD = "Correct-Horse-Battery-9!";
const NEW_PASSWORD = "Entirely-Different-Pass-7@";
const BASE = { password: OLD_PASSWORD, fullName: "Reset Person", birthday: "1994-02-17", referralSource: "Reddit", referralOther: null };
const sha256 = (v) => createHash("sha256").update(v, "utf8").digest("hex");

let failures = 0;
const created = [];
function check(label, ok, detail = "") {
  if (!ok) failures += 1;
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${label}${detail ? `  -> ${detail}` : ""}`);
}

async function counts() {
  const [r] = await query(
    `SELECT (SELECT count(*) FROM users) AS users,
            (SELECT count(*) FROM auth_sessions) AS sessions,
            (SELECT count(*) FROM password_resets) AS resets,
            (SELECT count(*) FROM auth_handoffs) AS handoffs,
            (SELECT count(*) FROM auth_attempts) AS attempts`);
  return { users: +r.users, sessions: +r.sessions, resets: +r.resets, handoffs: +r.handoffs, attempts: +r.attempts };
}

async function makeVerifiedUser(n) {
  const email = normalizeEmail(address(n));
  const acct = await createAccount({ ...BASE, email });
  created.push(acct.userId);
  const t = await issueVerification(acct.userId, email);
  await consumeVerification(t.token);
  return { userId: acct.userId, email };
}

async function cleanup(before) {
  if (created.length) {
    await query("DELETE FROM auth_sessions WHERE user_id = ANY($1)", [created]);
    await query("DELETE FROM auth_handoffs WHERE user_id = ANY($1)", [created]);
    await query("DELETE FROM password_resets WHERE user_id = ANY($1)", [created]);
    await query("DELETE FROM email_verifications WHERE user_id = ANY($1)", [created]);
    const gone = await query("DELETE FROM users WHERE id = ANY($1) RETURNING id", [created]);
    console.log(`\n  cleanup: deleted ${gone.length} test account(s) and their auth rows`);
  }
  await query("DELETE FROM auth_attempts");

  const after = await counts();
  console.log(`  post-test: users=${after.users} sessions=${after.sessions} resets=${after.resets} handoffs=${after.handoffs} attempts=${after.attempts}`);
  check("users back to 2", after.users === before.users && after.users === 2, `${before.users} -> ${after.users}`);
  check("password_resets back to pre-test", after.resets === before.resets);
  check("auth_sessions back to pre-test", after.sessions === before.sessions);
  check("auth_handoffs back to pre-test", after.handoffs === before.handoffs);

  const rows = await query("SELECT id, username, password_hash FROM users ORDER BY id");
  check("remaining usernames are exactly ayoub and Ayoub",
    rows.length === 2 && rows[0].username === "ayoub" && rows[1].username === "Ayoub",
    JSON.stringify(rows.map((r) => r.username)));
  const fps = rows.map((r) => sha256(r.password_hash).slice(0, 16));
  check("legacy password fingerprints unchanged",
    fps[0] === "ad21629058e33b79" && fps[1] === "63585ccd0f71998e", fps.join(" / "));
}

async function run() {
  // --- eligibility ---------------------------------------------------------
  const legacy = await resetEligibility("nobody@example.invalid");
  check("unknown address is not eligible", legacy.eligible === false);

  const unverifiedEmail = normalizeEmail(address("u"));
  const unverifiedAcct = await createAccount({ ...BASE, email: unverifiedEmail });
  created.push(unverifiedAcct.userId);
  check("unverified account is not eligible",
    (await resetEligibility(unverifiedEmail)).eligible === false);

  const { userId, email } = await makeVerifiedUser(1);
  const eligible = await resetEligibility(email);
  check("verified account is eligible", eligible.eligible === true && eligible.userId === userId);

  // --- issuance, capture, hash-only storage --------------------------------
  const capture = new CaptureTransport();
  const [{ password_hash: hashAtIssue }] = await query(
    "SELECT password_hash FROM users WHERE id = $1", [userId]);
  const issued = await issueReset(userId, email, hashAtIssue);
  const link = resetUrl("https://site.test", issued.token);
  await capture.send({ to: email, subject: "reset", text: `here: ${link}` });
  check("reset link captured via CaptureTransport", capture.last().text.includes(link));

  const [row] = await query("SELECT * FROM password_resets WHERE user_id = $1", [userId]);
  check("only the token hash is stored", row.token_hash === sha256(issued.token));
  check("raw token absent from the row", !JSON.stringify(row).includes(issued.token));
  check("bcrypt hash never copied into the row", !JSON.stringify(row).includes(hashAtIssue));
  check("fingerprint is sha256 of the hash", row.password_hash_fingerprint === sha256(hashAtIssue));
  check("email snapshot is the normalized address", row.email === email);
  const ttl = (new Date(row.expires_at) - new Date(row.created_at)) / 60000;
  check("TTL is 30 minutes", Math.round(ttl) === 30, `${ttl}m`);

  // --- scanner-safe GET ----------------------------------------------------
  check("inspect reports valid", (await inspectReset(issued.token)).status === "valid");
  const [afterInspect] = await query("SELECT consumed_at, superseded_at FROM password_resets WHERE id = $1", [row.id]);
  check("inspect consumed nothing", afterInspect.consumed_at === null && afterInspect.superseded_at === null);

  // --- sessions + handoff that must die on reset ---------------------------
  const s1 = await openWebsiteSession(userId);
  const s2 = await openWebsiteSession(userId);
  const other = await makeVerifiedUser(2);
  const otherSession = await openWebsiteSession(other.userId);
  const handoff = await seedHandoff(userId);
  check("two sessions live before reset",
    (await resolveWebsiteSession(s1.token)) === userId && (await resolveWebsiteSession(s2.token)) === userId);

  // --- the reset -----------------------------------------------------------
  const newHash = await hashNewPassword(NEW_PASSWORD);
  const outcome = await completeReset(issued.token, newHash);
  check("reset succeeds", outcome.status === "reset" && outcome.userId === userId, JSON.stringify(outcome));
  check("both sessions revoked", outcome.sessionsRevoked === 2, String(outcome.sessionsRevoked));
  check("outstanding handoff voided", outcome.handoffsVoided === 1, String(outcome.handoffsVoided));

  check("old password no longer works", (await attemptLogin(email, OLD_PASSWORD)).ok === false);
  const withNew = await attemptLogin(email, NEW_PASSWORD);
  check("new password works", withNew.ok === true && withNew.userId === userId);

  const [stored] = await query("SELECT password_hash FROM users WHERE id = $1", [userId]);
  check("stored hash is bcrypt cost 12", stored.password_hash.startsWith("$2b$12$"));
  check("stored hash verifies the new password", bcrypt.compareSync(NEW_PASSWORD, stored.password_hash));

  check("session 1 revoked", (await resolveWebsiteSession(s1.token)) === null);
  check("session 2 revoked", (await resolveWebsiteSession(s2.token)) === null);
  check("another user's session is untouched",
    (await resolveWebsiteSession(otherSession.token)) === other.userId);

  const [voided] = await query("SELECT consumed_at FROM auth_handoffs WHERE token_hash = $1", [sha256(handoff)]);
  check("handoff is no longer redeemable", voided.consumed_at !== null);

  // --- replay + staleness ---------------------------------------------------
  check("replay rejected", (await completeReset(issued.token, newHash)).status === "rejected");
  check("inspect after consume rejects", (await inspectReset(issued.token)).status === "rejected");

  // fingerprint staleness: issue, change password by another route, then try
  const third = await makeVerifiedUser(3);
  const [{ password_hash: h3 }] = await query("SELECT password_hash FROM users WHERE id = $1", [third.userId]);
  const stale = await issueReset(third.userId, third.email, h3);
  await query("UPDATE users SET password_hash = $2 WHERE id = $1",
    [third.userId, await hashNewPassword("Some-Other-Password-5#")]);
  check("token is stale once the password changed by another route",
    (await completeReset(stale.token, newHash)).status === "rejected");
  check("inspect agrees the stale token is dead", (await inspectReset(stale.token)).status === "rejected");

  // email-change binding
  const fourth = await makeVerifiedUser(4);
  const [{ password_hash: h4 }] = await query("SELECT password_hash FROM users WHERE id = $1", [fourth.userId]);
  const boundToOld = await issueReset(fourth.userId, fourth.email, h4);
  await query("UPDATE users SET email = $2 WHERE id = $1", [fourth.userId, normalizeEmail(address("4b"))]);
  check("token issued for the old address cannot reset the new one",
    (await completeReset(boundToOld.token, newHash)).status === "rejected");

  // supersession
  const fifth = await makeVerifiedUser(5);
  const [{ password_hash: h5 }] = await query("SELECT password_hash FROM users WHERE id = $1", [fifth.userId]);
  const first = await issueReset(fifth.userId, fifth.email, h5);
  const second = await issueReset(fifth.userId, fifth.email, h5);
  check("superseded token rejected", (await completeReset(first.token, newHash)).status === "rejected");
  check("newest token works", (await completeReset(second.token, newHash)).status === "reset");

  // concurrency
  const sixth = await makeVerifiedUser(6);
  const [{ password_hash: h6 }] = await query("SELECT password_hash FROM users WHERE id = $1", [sixth.userId]);
  const racer = await issueReset(sixth.userId, sixth.email, h6);
  const results = await Promise.all(
    Array.from({ length: 8 }, () => completeReset(racer.token, newHash)));
  const wins = results.filter((r) => r.status === "reset").length;
  check("8 concurrent resets -> exactly one wins", wins === 1, `winners=${wins}`);
}

async function main() {
  console.log("=== dev Neon password-reset integration ===");
  const before = await counts();
  console.log(`  pre-test: users=${before.users} sessions=${before.sessions} resets=${before.resets} handoffs=${before.handoffs} attempts=${before.attempts}`);

  const names = (await query("SELECT username FROM users ORDER BY id")).map((r) => r.username);
  if (names.length !== 2 || names[0] !== "ayoub" || names[1] !== "Ayoub") {
    console.error(`  REFUSING: expected the two dev accounts, found ${JSON.stringify(names)}`);
    process.exit(2);
  }

  try {
    await run();
  } catch (error) {
    failures += 1;
    console.log(`  [FAIL] run threw: ${error.message}`);
  } finally {
    try { await cleanup(before); }
    catch (error) { failures += 1; console.log(`  [FAIL] cleanup threw: ${error.message}`); }
  }
  console.log(failures === 0 ? "\nINTEGRATION PASSED" : `\n${failures} CHECK(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error("integration error:", e.message); process.exit(1); });
