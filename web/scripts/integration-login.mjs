/**
 * Real login integration against dev-auth-migration / neondb.
 *
 * Exercises what the unit tests stub: real bcrypt against real stored hashes,
 * real Postgres case-sensitivity on username, the real verification gate, and
 * real session rows.
 *
 * Two safety rules, both learned the hard way on 2026-08-12:
 *
 *  1. **The legacy accounts are never mutated.** An earlier version set a known
 *     password on ids 1 and 2 so it could test username login, intending to
 *     restore the originals afterwards. Cleanup threw, the restore never ran,
 *     and both hashes were left overwritten. Case-sensitive username login is
 *     now tested with purpose-made accounts whose usernames differ only in
 *     case, so the real rows are read but never written.
 *
 *  2. **Cleanup runs in a finally, children before parents.** Only
 *     `email_verifications` and `user_settings` cascade from `users`; every
 *     other foreign key is ON DELETE NO ACTION, so deleting a user with a live
 *     session fails. That is what threw.
 *
 * NEVER point this at production.
 */
import bcrypt from "bcryptjs";
import { createHash } from "node:crypto";

import { createAccount } from "../lib/auth/signup.ts";
import { query } from "../lib/db/client.ts";
import { normalizeEmail } from "../lib/auth/contract.ts";
import {
  attemptLogin,
  openWebsiteSession,
  resolveWebsiteSession,
  revokeWebsiteSession,
} from "../lib/auth/login.ts";
import { consumeVerification, issueVerification } from "../lib/auth/verification.ts";

const TAG = `${Date.now()}`.slice(-8);
const address = (n) => `login+il${TAG}${n}@example.invalid`;
const PASSWORD = "Correct-Horse-Battery-9!";
const BASE = {
  password: PASSWORD,
  fullName: "Login Person",
  birthday: "1994-02-17",
  referralSource: "Reddit",
  referralOther: null,
};

let failures = 0;
const createdUserIds = [];

function check(label, ok, detail = "") {
  if (!ok) failures += 1;
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${label}${detail ? `  -> ${detail}` : ""}`);
}

async function counts() {
  const [r] = await query(
    `SELECT (SELECT count(*) FROM users) AS users,
            (SELECT count(*) FROM auth_sessions) AS sessions,
            (SELECT count(*) FROM email_verifications) AS verifications,
            (SELECT count(*) FROM auth_attempts) AS attempts`,
  );
  return {
    users: +r.users,
    sessions: +r.sessions,
    verifications: +r.verifications,
    attempts: +r.attempts,
  };
}

/** Children first: only email_verifications cascades from users. */
async function cleanup(before) {
  if (createdUserIds.length === 0) return;
  await query("DELETE FROM auth_sessions WHERE user_id = ANY($1)", [createdUserIds]);
  await query("DELETE FROM auth_handoffs WHERE user_id = ANY($1)", [createdUserIds]);
  await query("DELETE FROM email_verifications WHERE user_id = ANY($1)", [createdUserIds]);
  const gone = await query("DELETE FROM users WHERE id = ANY($1) RETURNING id", [createdUserIds]);
  await query("DELETE FROM auth_attempts");
  console.log(`\n  cleanup: deleted ${gone.length} test account(s) and their auth rows`);

  const after = await counts();
  console.log(`  post-test: users=${after.users} sessions=${after.sessions} verifications=${after.verifications} attempts=${after.attempts}`);
  check("users back to pre-test count", after.users === before.users, `${before.users} -> ${after.users}`);
  check("sessions back to pre-test count", after.sessions === before.sessions);
  check("verifications back to pre-test count", after.verifications === before.verifications);

  const rows = await query("SELECT id, username FROM users ORDER BY id");
  check(
    "the two legacy accounts are present and untouched",
    rows.length === 2 && rows[0].username === "ayoub" && rows[1].username === "Ayoub",
    JSON.stringify(rows.map((r) => r.username)),
  );
}

async function run() {
  // --- case-sensitive username login, on accounts we own ------------------
  // Two usernames differing only in case, mirroring ayoub/Ayoub without
  // touching them.
  const emailLower = normalizeEmail(address("a"));
  const emailUpper = normalizeEmail(address("b"));
  const lowerAcct = await createAccount({ ...BASE, email: emailLower });
  const upperAcct = await createAccount({ ...BASE, email: emailUpper });
  createdUserIds.push(lowerAcct.userId, upperAcct.userId);

  const nameLower = `tl${TAG}x`;
  const nameUpper = `tl${TAG}X`;
  await query("UPDATE users SET username = $2 WHERE id = $1", [lowerAcct.userId, nameLower]);
  await query("UPDATE users SET username = $2 WHERE id = $1", [upperAcct.userId, nameUpper]);
  // Verify both so the username path is not blocked by the verification gate.
  for (const [id, email] of [[lowerAcct.userId, emailLower], [upperAcct.userId, emailUpper]]) {
    const t = await issueVerification(id, email);
    await consumeVerification(t.token);
  }

  const a = await attemptLogin(nameLower, PASSWORD);
  const b = await attemptLogin(nameUpper, PASSWORD);
  check("lowercase username authenticates", a.ok === true && a.userId === lowerAcct.userId);
  check("uppercase variant authenticates as a DIFFERENT account",
    b.ok === true && b.userId === upperAcct.userId);
  check("username matching is exact and case-sensitive", a.userId !== b.userId,
    `${a.userId} vs ${b.userId}`);
  check("a case variant matching no row is rejected",
    (await attemptLogin(nameLower.toUpperCase(), PASSWORD)).ok === false);

  // --- legacy accounts: read-only assertions only -------------------------
  const legacy = await query(
    "SELECT id, username, email, email_verification_required FROM users WHERE id IN (1,2) ORDER BY id");
  check("legacy accounts still have no email", legacy.every((r) => r.email === null));
  check("legacy accounts remain exempt from verification",
    legacy.every((r) => r.email_verification_required === false));
  check("a wrong password against a legacy username is rejected",
    (await attemptLogin("ayoub", "definitely-not-the-password")).ok === false);
  check("an unknown username is rejected",
    (await attemptLogin("nobody_at_all", PASSWORD)).ok === false);

  // --- new account: unverified is refused ---------------------------------
  const email1 = normalizeEmail(address(1));
  const acct = await createAccount({ ...BASE, email: email1 });
  createdUserIds.push(acct.userId);

  const unverified = await attemptLogin(email1, PASSWORD);
  check("unverified new account is refused", unverified.ok === false);
  check("reason is email_unverified, not bad credentials",
    unverified.reason === "email_unverified", unverified.reason);

  // --- verified email authenticates ---------------------------------------
  const issued = await issueVerification(acct.userId, email1);
  check("verification consumed", (await consumeVerification(issued.token)).status === "verified");
  const verified = await attemptLogin(email1, PASSWORD);
  check("verified email + password authenticates", verified.ok === true && verified.userId === acct.userId);
  check("wrong password still rejected", (await attemptLogin(email1, "wrong-password-here")).ok === false);
  check("email lookup normalizes case", (await attemptLogin(email1.toUpperCase(), PASSWORD)).ok === true);
  check("an @ identifier never falls through to a username lookup",
    (await attemptLogin("ayoub@nope.invalid", PASSWORD)).ok === false);

  // --- inactive account ----------------------------------------------------
  await query("UPDATE users SET is_active = 0 WHERE id = $1", [acct.userId]);
  const inactive = await attemptLogin(email1, PASSWORD);
  check("inactive account refused", inactive.ok === false && inactive.reason === "inactive", inactive.reason);
  await query("UPDATE users SET is_active = 1 WHERE id = $1", [acct.userId]);

  // --- website session lifecycle ------------------------------------------
  const { token, expiresAt } = await openWebsiteSession(acct.userId);
  const [row] = await query("SELECT token_hash FROM auth_sessions WHERE user_id = $1", [acct.userId]);
  check("only the session hash is stored",
    row.token_hash === createHash("sha256").update(token).digest("hex") && row.token_hash !== token);
  check("absolute expiry is 12h", Math.round((expiresAt - Date.now()) / 3600000) === 12);
  check("session resolves to its user", (await resolveWebsiteSession(token)) === acct.userId);
  check("unknown session rejected", (await resolveWebsiteSession("nope")) === null);
  check("revocation ends it", (await revokeWebsiteSession(token)) === true);
  check("revoked session no longer resolves", (await resolveWebsiteSession(token)) === null);
  check("a second revoke reports nothing ended", (await revokeWebsiteSession(token)) === false);

  // --- bcrypt: the stored hash is real -------------------------------------
  const [stored] = await query("SELECT password_hash FROM users WHERE id = $1", [acct.userId]);
  check("password stored as bcrypt cost 12", stored.password_hash.startsWith("$2b$12$"));
  check("stored hash verifies", bcrypt.compareSync(PASSWORD, stored.password_hash));
  check("plaintext never stored", !stored.password_hash.includes(PASSWORD));
}

async function main() {
  console.log("=== dev Neon login integration ===");
  const before = await counts();
  console.log(`  pre-test: users=${before.users} sessions=${before.sessions} verifications=${before.verifications} attempts=${before.attempts}`);

  const names = (await query("SELECT username FROM users ORDER BY id")).map((r) => r.username);
  if (names.length !== 2 || names[0] !== "ayoub" || names[1] !== "Ayoub") {
    console.error(`  REFUSING: expected the two dev accounts, found ${JSON.stringify(names)}`);
    process.exit(2);
  }

  try {
    await run(before);
  } catch (error) {
    failures += 1;
    console.log(`  [FAIL] run threw: ${error.message}`);
  } finally {
    // Always runs, so a mid-test failure cannot leave rows behind.
    try {
      await cleanup(before);
    } catch (error) {
      failures += 1;
      console.log(`  [FAIL] cleanup threw: ${error.message}`);
    }
  }

  console.log(failures === 0 ? "\nINTEGRATION PASSED" : `\n${failures} CHECK(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("integration error:", e.message);
  process.exit(1);
});
