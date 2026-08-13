/**
 * Runs one disposable dev account through signup -> verification -> login ->
 * onboarding, reporting the four state fields at each boundary.
 *
 * Exists to settle whether the Step 8 report's claim
 * (email_verification_required = true after verification) reflected the code or
 * was a reporting error.
 *
 * Disposable tagged account only. ayoub/Ayoub are never written to. Cleanup in
 * a finally, children before parents. NEVER point this at production.
 */
import { createHash } from "node:crypto";

import { createAccount } from "../lib/auth/signup.ts";
import { query } from "../lib/db/client.ts";
import { normalizeEmail } from "../lib/auth/contract.ts";
import { attemptLogin, openWebsiteSession } from "../lib/auth/login.ts";
import { authenticateSessionToken, emailGatePassed, nextDestinationFor } from "../lib/auth/session.ts";
import { completeOnboarding, validateOnboarding } from "../lib/auth/onboarding.ts";
import { consumeVerification, issueVerification } from "../lib/auth/verification.ts";

const TAG = `${Date.now()}`.slice(-8);
const EMAIL = normalizeEmail(`state+st${TAG}@example.invalid`);
const PASSWORD = "Correct-Horse-Battery-9!";
const sha256 = (v) => createHash("sha256").update(v, "utf8").digest("hex");

let failures = 0;
const created = [];
function check(label, ok, detail = "") {
  if (!ok) failures += 1;
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${label}${detail ? `  -> ${detail}` : ""}`);
}

async function state(userId) {
  const [r] = await query(
    `SELECT email_verified_at, email_verification_required,
            onboarding_completed, strategy_profile_completed
       FROM users WHERE id = $1`, [userId]);
  return r;
}

function report(stage, s) {
  console.log(`\n  --- ${stage} ---`);
  console.log(`    email_verified_at           = ${s.email_verified_at === null ? "NULL" : "non-NULL (" + new Date(s.email_verified_at).toISOString() + ")"}`);
  console.log(`    email_verification_required = ${s.email_verification_required}`);
  console.log(`    onboarding_completed        = ${s.onboarding_completed}`);
  console.log(`    strategy_profile_completed  = ${s.strategy_profile_completed}`);
}

async function run() {
  // --- signup --------------------------------------------------------------
  const acct = await createAccount({
    email: EMAIL, password: PASSWORD, fullName: "State Probe",
    birthday: "1994-02-17", referralSource: "Reddit", referralOther: null });
  created.push(acct.userId);
  await query(
    `UPDATE users SET onboarding_completed = false, full_name = NULL, birthday = NULL,
            referral_source = NULL, referral_source_other = NULL WHERE id = $1`,
    [acct.userId]);

  const afterSignup = await state(acct.userId);
  report("AFTER SIGNUP", afterSignup);
  check("signup: email_verified_at is NULL", afterSignup.email_verified_at === null);
  check("signup: email_verification_required is true", afterSignup.email_verification_required === true);

  // --- verification --------------------------------------------------------
  const token = await issueVerification(acct.userId, EMAIL);
  const consumed = await consumeVerification(token.token);
  check("verification consumed", consumed.status === "verified");

  const afterVerification = await state(acct.userId);
  report("AFTER VERIFICATION", afterVerification);
  check("verification: email_verified_at is non-NULL", afterVerification.email_verified_at !== null);
  check("verification: email_verification_required is FALSE",
    afterVerification.email_verification_required === false,
    String(afterVerification.email_verification_required));
  check("verification: onboarding_completed still false", afterVerification.onboarding_completed === false);
  check("verification: strategy_profile_completed still false", afterVerification.strategy_profile_completed === false);

  // --- login ---------------------------------------------------------------
  const login = await attemptLogin(EMAIL, PASSWORD);
  check("login succeeds after verification", login.ok === true && login.userId === acct.userId);
  check("login reports onboarding incomplete", login.ok && login.onboardingCompleted === false);

  const { token: sessionToken } = await openWebsiteSession(acct.userId);
  const authed = await authenticateSessionToken(sessionToken);
  check("session gate passes", authed !== null);
  check("email gate passes", emailGatePassed(authed));
  check("routing points at onboarding", nextDestinationFor(authed) === "/onboarding");

  // --- onboarding ----------------------------------------------------------
  const input = validateOnboarding({
    fullName: "State Probe", birthday: "1994-02-17",
    referralSource: "Reddit", referralOther: null });
  const outcome = await completeOnboarding(acct.userId, input.value);
  check("onboarding completes", outcome.status === "completed");

  const afterOnboarding = await state(acct.userId);
  report("AFTER ONBOARDING", afterOnboarding);
  check("onboarding: email_verified_at still non-NULL", afterOnboarding.email_verified_at !== null);
  check("onboarding: email_verification_required still FALSE",
    afterOnboarding.email_verification_required === false);
  check("onboarding: onboarding_completed is true", afterOnboarding.onboarding_completed === true);
  check("onboarding: strategy_profile_completed STILL false",
    afterOnboarding.strategy_profile_completed === false);

  // --- the combination the question asks about -----------------------------
  // verified_at non-NULL together with required = true. Not reachable through
  // the real flow, but forced here to confirm the gates read it correctly.
  await query(
    "UPDATE users SET email_verification_required = true WHERE id = $1", [acct.userId]);
  const forced = await authenticateSessionToken(sessionToken);
  check("verified_at non-NULL + required=true is treated as VERIFIED (correct: the timestamp means it was done)",
    emailGatePassed(forced) === true);
  const forcedLogin = await attemptLogin(EMAIL, PASSWORD);
  check("login agrees", forcedLogin.ok === true);
  await query(
    "UPDATE users SET email_verification_required = false WHERE id = $1", [acct.userId]);
}

async function cleanup() {
  if (created.length) {
    await query("DELETE FROM auth_sessions WHERE user_id = ANY($1)", [created]);
    await query("DELETE FROM auth_handoffs WHERE user_id = ANY($1)", [created]);
    await query("DELETE FROM password_resets WHERE user_id = ANY($1)", [created]);
    await query("DELETE FROM email_verifications WHERE user_id = ANY($1)", [created]);
    const gone = await query("DELETE FROM users WHERE id = ANY($1) RETURNING id", [created]);
    console.log(`\n  cleanup: deleted ${gone.length} disposable account(s)`);
  }
  await query("DELETE FROM auth_attempts");

  const rows = await query("SELECT id, username, password_hash FROM users ORDER BY id");
  check("dev users = 2", rows.length === 2, String(rows.length));
  check("usernames exactly ayoub / Ayoub",
    rows[0]?.username === "ayoub" && rows[1]?.username === "Ayoub",
    JSON.stringify(rows.map((r) => r.username)));
  const fps = rows.map((r) => sha256(r.password_hash).slice(0, 16));
  check("legacy password fingerprints unchanged",
    fps[0] === "ad21629058e33b79" && fps[1] === "63585ccd0f71998e", fps.join(" / "));
}

async function main() {
  console.log("=== dev state-transition probe ===");
  const names = (await query("SELECT username FROM users ORDER BY id")).map((r) => r.username);
  if (names.length !== 2 || names[0] !== "ayoub" || names[1] !== "Ayoub") {
    console.error(`  REFUSING: expected the two dev accounts, found ${JSON.stringify(names)}`);
    process.exit(2);
  }
  try { await run(); }
  catch (e) { failures += 1; console.log(`  [FAIL] run threw: ${e.message}`); }
  finally {
    try { await cleanup(); }
    catch (e) { failures += 1; console.log(`  [FAIL] cleanup threw: ${e.message}`); }
  }
  console.log(failures === 0 ? "\nSTATE TRANSITION VERIFIED" : `\n${failures} CHECK(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error("error:", e.message); process.exit(1); });
