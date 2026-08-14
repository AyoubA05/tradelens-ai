/**
 * Real email-verification integration against dev-auth-migration / neondb.
 *
 * Exercises the paths the unit tests stub: the actual conditional UPDATE, the
 * actual unique index, real concurrency, and the real email-change binding.
 *
 * Refuses to run unless the target holds exactly the two known dev accounts,
 * records pre-test counts, and deletes only rows carrying its own run tag.
 * NEVER point this at production.
 */
import { createHash } from "node:crypto";

import { createAccount } from "../lib/auth/signup.ts";
import { query } from "../lib/db/client.ts";
import { normalizeEmail } from "../lib/auth/contract.ts";
import {
  consumeVerification,
  inspectVerification,
  issueVerification,
  verificationUrl,
} from "../lib/auth/verification.ts";
import { verificationMessage } from "../lib/mail/messages.ts";
import { CaptureTransport } from "../lib/mail/transport.ts";

const TAG = `iv${Date.now()}`;
const address = (n) => `verify+${TAG}${n}@example.invalid`;
const sha256 = (v) => createHash("sha256").update(v, "utf8").digest("hex");

let failures = 0;
function check(label, ok, detail = "") {
  if (!ok) failures += 1;
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${label}${detail ? `  -> ${detail}` : ""}`);
}

async function counts() {
  const [r] = await query(
    `SELECT (SELECT count(*) FROM users) AS users,
            (SELECT count(*) FROM email_verifications) AS verifications,
            (SELECT count(*) FROM auth_attempts) AS attempts`,
  );
  return { users: +r.users, verifications: +r.verifications, attempts: +r.attempts };
}

const BASE = {
  password: "Correct-Horse-Battery-9!",
  fullName: "Verify Person",
  birthday: "1994-02-17",
  referralSource: "Reddit",
  referralOther: null,
};

async function main() {
  console.log("=== dev Neon email-verification integration ===");
  const before = await counts();
  console.log(`  pre-test: users=${before.users} verifications=${before.verifications} attempts=${before.attempts}`);

  const existing = await query("SELECT username FROM users ORDER BY id");
  const names = existing.map((r) => r.username);
  if (names.length !== 2 || names[0] !== "ayoub" || names[1] !== "Ayoub") {
    console.error(`  REFUSING: expected the two dev accounts, found ${JSON.stringify(names)}`);
    process.exit(2);
  }

  const capture = new CaptureTransport();

  // --- 1. signup -> issue -> capture the emailed link ---------------------
  const email1 = normalizeEmail(address(1));
  const created = await createAccount({ ...BASE, email: email1 });
  check("account created", created.status === "created");

  const issued = await issueVerification(created.userId, email1);
  const url = verificationUrl("https://site.test", issued.token);
  await capture.send(verificationMessage(email1, url));
  const capturedUrl = capture.lastVerificationUrl();
  check("verification link captured by the test transport", capturedUrl === url);

  const capturedToken = new URL(capturedUrl).searchParams.get("token");
  check("captured token matches the issued one", capturedToken === issued.token);

  // --- 2. only the hash is stored -----------------------------------------
  const [stored] = await query(
    "SELECT token_hash, email, consumed_at, superseded_at, expires_at, created_at FROM email_verifications WHERE user_id = $1",
    [created.userId],
  );
  check("only the SHA-256 hash is stored", stored.token_hash === sha256(issued.token));
  check("raw token is nowhere in the row", !JSON.stringify(stored).includes(issued.token));
  check("row binds the normalized email", stored.email === email1);
  check("unused: consumed_at and superseded_at are NULL",
    stored.consumed_at === null && stored.superseded_at === null);
  const ttlHours = (new Date(stored.expires_at) - new Date(stored.created_at)) / 3600000;
  check("TTL is 24 hours", Math.round(ttlHours) === 24, `${ttlHours}h`);

  // --- 3. GET-style inspect does not mutate -------------------------------
  const inspected = await inspectVerification(issued.token);
  check("inspect reports valid", inspected.status === "valid");
  const [afterInspect] = await query(
    "SELECT consumed_at FROM email_verifications WHERE user_id = $1", [created.userId]);
  check("inspect consumed nothing (scanner-safe)", afterInspect.consumed_at === null);

  // --- 4. consume verifies the account ------------------------------------
  const consumed = await consumeVerification(issued.token);
  check("consume verifies", consumed.status === "verified" && consumed.userId === created.userId);

  const [user] = await query(
    "SELECT email_verified_at, email_verification_required, onboarding_completed, strategy_profile_completed FROM users WHERE id = $1",
    [created.userId],
  );
  check("email_verified_at set", user.email_verified_at !== null);
  check("email_verification_required cleared", user.email_verification_required === false);
  check("onboarding_completed still false", user.onboarding_completed === false);
  check("strategy_profile_completed still false", user.strategy_profile_completed === false);

  // --- 5. replay -----------------------------------------------------------
  check("replay rejected", (await consumeVerification(issued.token)).status === "rejected");
  check("inspect after consume rejects", (await inspectVerification(issued.token)).status === "rejected");

  // --- 6. concurrency: exactly one winner ---------------------------------
  const email2 = normalizeEmail(address(2));
  const acct2 = await createAccount({ ...BASE, email: email2 });
  const t2 = await issueVerification(acct2.userId, email2);
  const racers = await Promise.all(
    Array.from({ length: 8 }, () => consumeVerification(t2.token)),
  );
  const wins = racers.filter((r) => r.status === "verified").length;
  check("8 concurrent consumes -> exactly one wins", wins === 1, `winners=${wins}`);

  // --- 7. supersession -----------------------------------------------------
  const email3 = normalizeEmail(address(3));
  const acct3 = await createAccount({ ...BASE, email: email3 });
  const old = await issueVerification(acct3.userId, email3);
  const fresh = await issueVerification(acct3.userId, email3);
  check("superseded token is rejected", (await consumeVerification(old.token)).status === "rejected");
  check("newest token still works", (await consumeVerification(fresh.token)).status === "verified");
  const live = await query(
    "SELECT count(*) AS n FROM email_verifications WHERE user_id = $1 AND consumed_at IS NULL AND superseded_at IS NULL",
    [acct3.userId]);
  check("no live tokens remain after consume", +live[0].n === 0);

  // --- 8. a token cannot survive an email change --------------------------
  const email4 = normalizeEmail(address(4));
  const acct4 = await createAccount({ ...BASE, email: email4 });
  const beforeChange = await issueVerification(acct4.userId, email4);
  const changed = normalizeEmail(address(44));
  await query(
    "UPDATE users SET email = $2, email_verified_at = NULL, email_verification_required = true WHERE id = $1",
    [acct4.userId, changed]);
  check("token issued for the old address cannot verify the new one",
    (await consumeVerification(beforeChange.token)).status === "rejected");
  check("inspect agrees", (await inspectVerification(beforeChange.token)).status === "rejected");

  // --- 9. cross-user isolation --------------------------------------------
  const email5 = normalizeEmail(address(5));
  const acct5 = await createAccount({ ...BASE, email: email5 });
  const t5 = await issueVerification(acct5.userId, email5);
  const r5 = await consumeVerification(t5.token);
  check("a token verifies only its own account", r5.status === "verified" && r5.userId === acct5.userId);

  // --- cleanup -------------------------------------------------------------
  const tokensBefore = await query(
    "SELECT count(*) AS n FROM email_verifications WHERE email LIKE $1", [`verify+${TAG}%`]);
  const deletedUsers = await query(
    "DELETE FROM users WHERE email LIKE $1 OR email LIKE $2 RETURNING id",
    [`verify+${TAG}%@example.invalid`, `verify+${TAG}44@example.invalid`]);
  // email_verifications rows go with them via ON DELETE CASCADE.
  console.log(`\n  cleanup: expected ${tokensBefore[0].n} token row(s); deleted ${deletedUsers.length} account(s), tag ${TAG}`);

  const after = await counts();
  console.log(`  post-test: users=${after.users} verifications=${after.verifications} attempts=${after.attempts}`);
  check("users back to pre-test count", after.users === before.users, `${before.users} -> ${after.users}`);
  check("email_verifications back to pre-test count (FK CASCADE)",
    after.verifications === before.verifications, `${before.verifications} -> ${after.verifications}`);
  check("auth_attempts unchanged", after.attempts === before.attempts);

  const remaining = await query("SELECT username FROM users ORDER BY id");
  check("ayoub and Ayoub untouched",
    remaining.length === 2 && remaining[0].username === "ayoub" && remaining[1].username === "Ayoub",
    JSON.stringify(remaining.map((r) => r.username)));

  console.log(failures === 0 ? "\nINTEGRATION PASSED" : `\n${failures} CHECK(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("integration error:", e.message);
  process.exit(1);
});
