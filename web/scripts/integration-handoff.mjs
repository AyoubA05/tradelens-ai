/**
 * Real handoff-issuance integration against dev-auth-migration / neondb.
 *
 * Exercises what the unit tests stub: the real row lock under real Postgres
 * concurrency, real invalidation of prior handoffs, and the real session
 * remaining untouched.
 *
 * Disposable tagged accounts only. ayoub/Ayoub never written to. Cleanup in a
 * finally, children before parents. NEVER point this at production.
 *
 * Does NOT redirect anywhere or redeem anything — issuance only. Redemption is
 * step 10.
 */
import { createHash } from "node:crypto";

import { createAccount } from "../lib/auth/signup.ts";
import { query } from "../lib/db/client.ts";
import { normalizeEmail } from "../lib/auth/contract.ts";
import { openWebsiteSession, revokeWebsiteSession } from "../lib/auth/login.ts";
import { authenticateSessionToken } from "../lib/auth/session.ts";
import { completeOnboarding, validateOnboarding } from "../lib/auth/onboarding.ts";
import { consumeVerification, issueVerification } from "../lib/auth/verification.ts";
import { HANDOFF_TTL_SECONDS, handoffEligibility, issueHandoff } from "../lib/auth/handoff.ts";
import { handoffRedirectUrl } from "../lib/security/app-origin.ts";

const TAG = `${Date.now()}`.slice(-8);
const address = (n) => `hand+ih${TAG}${n}@example.invalid`;
const PASSWORD = "Correct-Horse-Battery-9!";
const APP = "https://app.example.test";
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
            (SELECT count(*) FROM auth_handoffs) AS handoffs,
            (SELECT count(*) FROM email_verifications) AS verifications,
            (SELECT count(*) FROM password_resets) AS resets,
            (SELECT count(*) FROM auth_attempts) AS attempts`);
  return { users: +r.users, sessions: +r.sessions, handoffs: +r.handoffs,
           verifications: +r.verifications, resets: +r.resets, attempts: +r.attempts };
}

async function makeReadyUser(n) {
  const email = normalizeEmail(address(n));
  const acct = await createAccount({
    email, password: PASSWORD, fullName: "Handoff Person",
    birthday: "1994-02-17", referralSource: "Reddit", referralOther: null });
  created.push(acct.userId);
  const t = await issueVerification(acct.userId, email);
  await consumeVerification(t.token);
  await query("UPDATE users SET onboarding_completed = false WHERE id = $1", [acct.userId]);
  const input = validateOnboarding({
    fullName: "Handoff Person", birthday: "1994-02-17",
    referralSource: "Reddit", referralOther: null });
  await completeOnboarding(acct.userId, input.value);
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
  console.log(`  post-test: users=${after.users} sessions=${after.sessions} handoffs=${after.handoffs} verifications=${after.verifications} resets=${after.resets} attempts=${after.attempts}`);
  check("users = 2", after.users === 2, `${before.users} -> ${after.users}`);
  check("auth_handoffs back to pre-test", after.handoffs === before.handoffs);
  check("auth_sessions back to pre-test", after.sessions === before.sessions);
  check("auth_attempts back to pre-test", after.attempts === before.attempts);
  check("email_verifications back to pre-test", after.verifications === before.verifications);
  check("password_resets back to pre-test", after.resets === before.resets);

  const rows = await query("SELECT username, password_hash FROM users ORDER BY id");
  check("usernames exactly ayoub / Ayoub",
    rows.length === 2 && rows[0].username === "ayoub" && rows[1].username === "Ayoub",
    JSON.stringify(rows.map((r) => r.username)));
  const fps = rows.map((r) => sha256(r.password_hash).slice(0, 16));
  check("legacy fingerprints unchanged",
    fps[0] === "ad21629058e33b79" && fps[1] === "63585ccd0f71998e", fps.join(" / "));
}

async function run() {
  // 1-3. ready user, session, strategy profile still false
  const { userId } = await makeReadyUser(1);
  const session = await openWebsiteSession(userId);
  const [state] = await query(
    "SELECT onboarding_completed, strategy_profile_completed FROM users WHERE id = $1", [userId]);
  check("onboarding_completed = true", state.onboarding_completed === true);
  check("strategy_profile_completed still false", state.strategy_profile_completed === false);

  const authed = await authenticateSessionToken(session.token);
  check("website session authenticates", authed !== null && authed.userId === userId);
  check("eligible for handoff with strategy profile incomplete",
    handoffEligibility(authed).eligible === true);

  // 4. rendering /continue issues nothing — proven by the row count staying put
  const [{ n: beforeRender }] = await query(
    "SELECT count(*) AS n FROM auth_handoffs WHERE user_id = $1", [userId]);
  check("no handoff exists before issuance", +beforeRender === 0);

  // 5-10. issue
  const issued = await issueHandoff(userId);
  const url = handoffRedirectUrl(issued.token, APP);
  const parsed = new URL(url);
  check("redirect origin is the configured APP_ORIGIN", parsed.origin === APP, parsed.origin);
  check("URL carries only ht", JSON.stringify([...parsed.searchParams.keys()]) === '["ht"]',
    JSON.stringify([...parsed.searchParams.keys()]));
  check("website session credential absent from URL", !url.includes(session.token));

  const [row] = await query(
    "SELECT token_hash, user_id, created_at, expires_at, consumed_at FROM auth_handoffs WHERE user_id = $1 AND consumed_at IS NULL",
    [userId]);
  check("raw token hashes to the stored token_hash", row.token_hash === sha256(issued.token));
  check("raw token not stored anywhere in the row", !JSON.stringify(row).includes(issued.token));
  check("user association is server-side", row.user_id === userId);
  const ttl = (new Date(row.expires_at) - new Date(row.created_at)) / 1000;
  check("TTL is 120 seconds", Math.round(ttl) === HANDOFF_TTL_SECONDS, `${ttl}s`);
  check("issued handoff is unconsumed", row.consumed_at === null);

  // 11. reissue invalidates the prior token
  const second = await issueHandoff(userId);
  check("reissue reports one invalidated", second.invalidated === 1, String(second.invalidated));
  const [oldRow] = await query(
    "SELECT consumed_at FROM auth_handoffs WHERE token_hash = $1", [sha256(issued.token)]);
  check("prior handoff is no longer redeemable", oldRow.consumed_at !== null);
  const [{ n: live }] = await query(
    "SELECT count(*) AS n FROM auth_handoffs WHERE user_id = $1 AND consumed_at IS NULL AND expires_at > now()",
    [userId]);
  check("exactly one redeemable handoff remains", +live === 1, String(live));
  const [newest] = await query(
    "SELECT token_hash FROM auth_handoffs WHERE user_id = $1 AND consumed_at IS NULL", [userId]);
  check("the newest token is the live one", newest.token_hash === sha256(second.token));

  // 12. real concurrency
  const racer = await makeReadyUser(2);
  const results = await Promise.all(Array.from({ length: 8 }, () => issueHandoff(racer.userId)));
  const [{ n: liveAfterRace }] = await query(
    "SELECT count(*) AS n FROM auth_handoffs WHERE user_id = $1 AND consumed_at IS NULL AND expires_at > now()",
    [racer.userId]);
  check("8 concurrent issues leave exactly one redeemable handoff",
    +liveAfterRace === 1, String(liveAfterRace));
  const liveHash = (await query(
    "SELECT token_hash FROM auth_handoffs WHERE user_id = $1 AND consumed_at IS NULL", [racer.userId]))[0].token_hash;
  check("the surviving token is one of the eight issued",
    results.some((r) => sha256(r.token) === liveHash));

  // 13. website session untouched
  const [sess] = await query(
    "SELECT created_at, expires_at, revoked_at FROM auth_sessions WHERE token_hash = $1",
    [sha256(session.token)]);
  check("website session not revoked by issuance", sess.revoked_at === null);
  check("absolute expiry still 12h — issuance did not extend it",
    Math.round((new Date(sess.expires_at) - new Date(sess.created_at)) / 3600000) === 12);
  check("website session still resolves", (await authenticateSessionToken(session.token)) !== null);

  // 14. no Streamlit session created by the issuer
  const [{ n: sessionRows }] = await query(
    "SELECT count(*) AS n FROM auth_sessions WHERE user_id = $1", [userId]);
  check("issuer created no additional auth_sessions row", +sessionRows === 1, String(sessionRows));

  // ineligible cases produce nothing
  const ineligible = await makeReadyUser(3);
  await query("UPDATE users SET onboarding_completed = false WHERE id = $1", [ineligible.userId]);
  const s3 = await openWebsiteSession(ineligible.userId);
  const a3 = await authenticateSessionToken(s3.token);
  check("onboarding-incomplete user is not eligible", handoffEligibility(a3).eligible === false);

  await revokeWebsiteSession(s3.token);
  check("revoked session resolves to nothing", (await authenticateSessionToken(s3.token)) === null);
  check("no session means not eligible", handoffEligibility(null).eligible === false);
}

async function main() {
  console.log("=== dev Neon handoff-issuance integration ===");
  const before = await counts();
  console.log(`  pre-test: users=${before.users} sessions=${before.sessions} handoffs=${before.handoffs} attempts=${before.attempts}`);

  const names = (await query("SELECT username FROM users ORDER BY id")).map((r) => r.username);
  if (names.length !== 2 || names[0] !== "ayoub" || names[1] !== "Ayoub") {
    console.error(`  REFUSING: expected the two dev accounts, found ${JSON.stringify(names)}`);
    process.exit(2);
  }

  try { await run(); }
  catch (e) { failures += 1; console.log(`  [FAIL] run threw: ${e.message}`); }
  finally {
    try { await cleanup(before); }
    catch (e) { failures += 1; console.log(`  [FAIL] cleanup threw: ${e.message}`); }
  }
  console.log(failures === 0 ? "\nINTEGRATION PASSED" : `\n${failures} CHECK(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error("integration error:", e.message); process.exit(1); });
