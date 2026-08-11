/**
 * Real signup integration against dev-auth-migration / neondb.
 *
 * Exercises the database path the unit tests stub: the actual INSERT, the
 * actual unique index, and the actual concurrency behaviour. Everything the
 * stubs cannot prove.
 *
 * Safety: refuses to run unless the target already contains the two known dev
 * accounts and nothing else, records the exact pre-test state, and deletes only
 * rows it created — matched by the `+it` tag it puts in the address, never by
 * anything broader.
 *
 * NEVER point this at production.
 */
import bcrypt from "bcryptjs";
import { createAccount } from "../lib/auth/signup.ts";
import { query } from "../lib/db/client.ts";
import { generateInternalUsername, normalizeEmail } from "../lib/auth/contract.ts";

const TAG = `it${Date.now()}`;
const address = (n) => `contract+${TAG}${n}@example.invalid`;

let failures = 0;
function check(label, condition, detail = "") {
  if (!condition) failures += 1;
  console.log(`  [${condition ? "PASS" : "FAIL"}] ${label}${detail ? `  -> ${detail}` : ""}`);
}

async function counts() {
  const rows = await query(
    "SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM auth_attempts) AS attempts",
  );
  return { users: Number(rows[0].users), attempts: Number(rows[0].attempts) };
}

async function main() {
  console.log("=== dev Neon signup integration ===");

  const before = await counts();
  console.log(`  pre-test: users=${before.users} auth_attempts=${before.attempts}`);

  const existing = await query("SELECT username FROM users ORDER BY id");
  const names = existing.map((r) => r.username);
  if (names.length !== 2 || names[0] !== "ayoub" || names[1] !== "Ayoub") {
    console.error(`  REFUSING: expected exactly the two dev accounts, found ${JSON.stringify(names)}`);
    process.exit(2);
  }

  const base = {
    password: "Correct-Horse-Battery-9!",
    fullName: "Integration Person",
    birthday: "1994-02-17",
    referralSource: "Reddit",
    referralOther: null,
  };

  // --- 1. a real account is created with the contract defaults ------------
  const email1 = normalizeEmail(address(1).toUpperCase());
  const created = await createAccount({ ...base, email: email1 });
  check("account created", created.status === "created", created.status);

  const [row] = await query(
    `SELECT id, username, email, password_hash, is_active, full_name, birthday,
            referral_source, referral_source_other, onboarding_completed,
            strategy_profile_completed, email_verified_at, email_verification_required
       FROM users WHERE email = $1`,
    [email1],
  );
  check("stored email is normalized (lowercased)", row.email === email1, row.email);
  check("username is opaque", /^u_[0-9a-f]{16}$/.test(row.username), row.username);
  check(
    "username contains no part of the email",
    !row.username.toLowerCase().includes("contract") && !row.username.includes(TAG),
  );
  check("onboarding_completed = false", row.onboarding_completed === false);
  check("strategy_profile_completed = false", row.strategy_profile_completed === false);
  check("email_verified_at IS NULL", row.email_verified_at === null);
  check("email_verification_required = true", row.email_verification_required === true);
  check("is_active = 1", Number(row.is_active) === 1);
  check("profile fields stored", row.full_name === base.fullName && row.referral_source === "Reddit");
  check(
    "password verifies and is bcrypt cost 12",
    bcrypt.compareSync(base.password, row.password_hash) &&
      row.password_hash.startsWith("$2b$12$"),
  );
  check("password not stored in plaintext", !row.password_hash.includes(base.password));

  // --- 2. duplicate normalized email is refused ---------------------------
  const dupe = await createAccount({ ...base, email: normalizeEmail(`  ${address(1).toUpperCase()}  `) });
  check("duplicate normalized email refused", dupe.status === "duplicate_email", dupe.status);

  // --- 3. concurrency: the database, not the pre-check, is the authority ---
  const email2 = normalizeEmail(address(2));
  const racers = await Promise.all(
    Array.from({ length: 8 }, () => createAccount({ ...base, email: email2 })),
  );
  const won = racers.filter((r) => r.status === "created").length;
  const [{ n }] = await query("SELECT count(*) AS n FROM users WHERE email = $1", [email2]);
  check("exactly one concurrent signup wins", won === 1, `winners=${won}`);
  check("exactly one row exists for that email", Number(n) === 1, `rows=${n}`);
  check("losers get the safe duplicate response", racers.filter((r) => r.status === "duplicate_email").length === 7);

  // --- 4. usernames stay unique across many creations ---------------------
  const generated = new Set(Array.from({ length: 1000 }, generateInternalUsername));
  check("1000 generated usernames are unique", generated.size === 1000);

  // --- cleanup ------------------------------------------------------------
  const deleted = await query(
    "DELETE FROM users WHERE email LIKE $1 RETURNING id",
    [`contract+${TAG}%@example.invalid`],
  );
  console.log(`\n  cleanup: deleted ${deleted.length} test account(s) (tag ${TAG})`);

  const after = await counts();
  console.log(`  post-test: users=${after.users} auth_attempts=${after.attempts}`);
  check("users returned to pre-test count", after.users === before.users,
    `${before.users} -> ${after.users}`);
  check("auth_attempts unchanged", after.attempts === before.attempts);

  const remaining = await query("SELECT username FROM users ORDER BY id");
  check(
    "the two real dev accounts are untouched",
    remaining.length === 2 && remaining[0].username === "ayoub" && remaining[1].username === "Ayoub",
    JSON.stringify(remaining.map((r) => r.username)),
  );

  console.log(failures === 0 ? "\nINTEGRATION PASSED" : `\n${failures} CHECK(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error("integration error:", error.message);
  process.exit(1);
});
