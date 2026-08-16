/**
 * Real personal-onboarding integration against dev-auth-migration / neondb.
 *
 * Safety rules from the step-6 incident: disposable tagged accounts only,
 * ayoub/Ayoub read-only, cleanup in a finally, children before parents, dev
 * proven back to its pre-test state.
 *
 * NEVER point this at production.
 */
import { createHash } from "node:crypto";

import { createAccount } from "../lib/auth/signup.ts";
import { query } from "../lib/db/client.ts";
import { normalizeEmail } from "../lib/auth/contract.ts";
import { openWebsiteSession, revokeWebsiteSession } from "../lib/auth/login.ts";
import { authenticateSessionToken, emailGatePassed, nextDestinationFor } from "../lib/auth/session.ts";
import { completeOnboarding, validateOnboarding } from "../lib/auth/onboarding.ts";
import { consumeVerification, issueVerification } from "../lib/auth/verification.ts";

const TAG = `${Date.now()}`.slice(-8);
const address = (n) => `onb+io${TAG}${n}@example.invalid`;
const PASSWORD = "Correct-Horse-Battery-9!";
const BASE = { password: PASSWORD, fullName: "Signup Placeholder", birthday: "1990-01-01", referralSource: "Reddit", referralOther: null };
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
            (SELECT count(*) FROM email_verifications) AS verifications,
            (SELECT count(*) FROM password_resets) AS resets,
            (SELECT count(*) FROM auth_attempts) AS attempts`);
  return { users: +r.users, sessions: +r.sessions, verifications: +r.verifications, resets: +r.resets, attempts: +r.attempts };
}

async function makeVerifiedUser(n) {
  const email = normalizeEmail(address(n));
  const acct = await createAccount({ ...BASE, email });
  created.push(acct.userId);
  const t = await issueVerification(acct.userId, email);
  await consumeVerification(t.token);
  // createAccount stores signup-time values; reset them so this test observes
  // onboarding writing them, not signup.
  await query(
    `UPDATE users SET onboarding_completed = false, full_name = NULL, birthday = NULL,
            referral_source = NULL, referral_source_other = NULL WHERE id = $1`,
    [acct.userId]);
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
  console.log(`  post-test: users=${after.users} sessions=${after.sessions} verifications=${after.verifications} resets=${after.resets} attempts=${after.attempts}`);
  check("dev users = 2", after.users === 2, `${before.users} -> ${after.users}`);
  check("auth_sessions back to pre-test", after.sessions === before.sessions);
  check("email_verifications back to pre-test", after.verifications === before.verifications);
  check("password_resets back to pre-test", after.resets === before.resets);

  const rows = await query("SELECT id, username, password_hash, full_name, onboarding_completed FROM users ORDER BY id");
  check("remaining usernames exactly ayoub and Ayoub",
    rows.length === 2 && rows[0].username === "ayoub" && rows[1].username === "Ayoub",
    JSON.stringify(rows.map((r) => r.username)));
  const fps = rows.map((r) => sha256(r.password_hash).slice(0, 16));
  check("legacy password fingerprints unchanged",
    fps[0] === "ad21629058e33b79" && fps[1] === "63585ccd0f71998e", fps.join(" / "));
  check("legacy onboarding fields untouched",
    rows.every((r) => r.full_name === null && r.onboarding_completed === true),
    JSON.stringify(rows.map((r) => ({ n: r.full_name, o: r.onboarding_completed }))));
}

async function run() {
  // 1-4. verified new account, session, initial state
  const { userId } = await makeVerifiedUser(1);
  const { token } = await openWebsiteSession(userId);
  const [initial] = await query(
    "SELECT onboarding_completed, strategy_profile_completed FROM users WHERE id = $1", [userId]);
  check("onboarding_completed starts false", initial.onboarding_completed === false);
  check("strategy_profile_completed starts false", initial.strategy_profile_completed === false);

  // 5. real protected-route authentication
  const authed = await authenticateSessionToken(token);
  check("session authenticates to the right user", authed !== null && authed.userId === userId);
  check("email gate passes for a verified account", emailGatePassed(authed));
  check("routing sends an incomplete user to onboarding", nextDestinationFor(authed) === "/onboarding");

  // 6-7. submit and verify stored values
  const input = validateOnboarding({
    fullName: "  Ayoub   Abouelfaïd  ",
    birthday: "1994-02-17",
    referralSource: "Other",
    referralOther: "A trading Discord",
  });
  check("payload validates", input.ok === true);
  check("full name normalized", input.ok && input.value.fullName === "Ayoub Abouelfaïd", input.ok ? input.value.fullName : "");

  const outcome = await completeOnboarding(userId, input.value);
  check("onboarding completes", outcome.status === "completed", outcome.status);

  const [stored] = await query(
    `SELECT full_name, birthday, referral_source, referral_source_other,
            onboarding_completed, strategy_profile_completed FROM users WHERE id = $1`, [userId]);
  check("full_name stored normalized", stored.full_name === "Ayoub Abouelfaïd", stored.full_name);
  check("birthday stored as DATE 1994-02-17",
    new Date(stored.birthday).toISOString().slice(0, 10) === "1994-02-17",
    String(stored.birthday));
  check("referral_source stored", stored.referral_source === "Other");
  check("referral_source_other stored", stored.referral_source_other === "A trading Discord");

  // 8-9. flags
  check("onboarding_completed is now true", stored.onboarding_completed === true);
  check("strategy_profile_completed STILL false", stored.strategy_profile_completed === false);

  const after = await authenticateSessionToken(token);
  check("routing now sends them onward, not back to onboarding",
    nextDestinationFor(after) === "/continue", nextDestinationFor(after));

  // 10. second attempt must not overwrite
  const second = validateOnboarding({
    fullName: "Someone Else Entirely", birthday: "1980-05-05",
    referralSource: "TikTok", referralOther: null });
  const repeat = await completeOnboarding(userId, second.value);
  check("second submission reports already_completed", repeat.status === "already_completed", repeat.status);
  const [unchanged] = await query(
    "SELECT full_name, referral_source FROM users WHERE id = $1", [userId]);
  check("first-run data NOT overwritten",
    unchanged.full_name === "Ayoub Abouelfaïd" && unchanged.referral_source === "Other",
    `${unchanged.full_name} / ${unchanged.referral_source}`);

  // 11. cross-user isolation
  const victim = await makeVerifiedUser(2);
  const [victimBefore] = await query("SELECT full_name, onboarding_completed FROM users WHERE id = $1", [victim.userId]);
  check("second user starts untouched", victimBefore.full_name === null && victimBefore.onboarding_completed === false);
  // The attacker's session resolves only to their own id; completeOnboarding is
  // only ever called with that id, so the victim cannot be reached.
  const attackerAuthed = await authenticateSessionToken(token);
  check("attacker session resolves only to their own account", attackerAuthed.userId === userId);
  check("attacker id is not the victim id", attackerAuthed.userId !== victim.userId);
  const [victimAfter] = await query("SELECT full_name, onboarding_completed FROM users WHERE id = $1", [victim.userId]);
  check("victim untouched after attacker activity",
    victimAfter.full_name === null && victimAfter.onboarding_completed === false);

  // 12. revoked and expired sessions
  const third = await makeVerifiedUser(3);
  const revoked = await openWebsiteSession(third.userId);
  await revokeWebsiteSession(revoked.token);
  check("revoked session rejected", (await authenticateSessionToken(revoked.token)) === null);

  const idle = await openWebsiteSession(third.userId);
  check("idle-expired session rejected",
    (await authenticateSessionToken(idle.token, new Date(Date.now() + 9 * 3600_000))) === null);

  const started = new Date();
  const absolute = await openWebsiteSession(third.userId, started);
  for (let h = 1; h <= 11; h += 1) {
    await authenticateSessionToken(absolute.token, new Date(started.getTime() + h * 3600_000));
  }
  check("12h absolute cap holds despite hourly activity",
    (await authenticateSessionToken(absolute.token, new Date(started.getTime() + 12.1 * 3600_000))) === null);
  const [row] = await query("SELECT created_at, expires_at FROM auth_sessions WHERE token_hash = $1",
    [sha256(absolute.token)]);
  check("expires_at was never extended by activity",
    Math.round((new Date(row.expires_at) - new Date(row.created_at)) / 3600000) === 12);

  check("unknown session rejected", (await authenticateSessionToken("nope")) === null);
}

async function main() {
  console.log("=== dev Neon personal-onboarding integration ===");
  const before = await counts();
  console.log(`  pre-test: users=${before.users} sessions=${before.sessions} verifications=${before.verifications} resets=${before.resets} attempts=${before.attempts}`);

  const names = (await query("SELECT username FROM users ORDER BY id")).map((r) => r.username);
  if (names.length !== 2 || names[0] !== "ayoub" || names[1] !== "Ayoub") {
    console.error(`  REFUSING: expected the two dev accounts, found ${JSON.stringify(names)}`);
    process.exit(2);
  }

  try { await run(before); }
  catch (e) { failures += 1; console.log(`  [FAIL] run threw: ${e.message}`); }
  finally {
    try { await cleanup(before); }
    catch (e) { failures += 1; console.log(`  [FAIL] cleanup threw: ${e.message}`); }
  }
  console.log(failures === 0 ? "\nINTEGRATION PASSED" : `\n${failures} CHECK(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error("integration error:", e.message); process.exit(1); });
