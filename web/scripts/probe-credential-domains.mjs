/**
 * Reproduces the vulnerability found on 2026-08-13 and proves it is closed.
 *
 * Before domain separation, a session token minted by either surface validated
 * on both, because both hashed with a plain sha256 into one table with no
 * marker. That bridged the weakest credential (the Streamlit URL bearer) to the
 * strongest (the HttpOnly website cookie).
 *
 * Disposable user only. ayoub/Ayoub never written to. Cleanup in a finally.
 * NEVER point this at production.
 */
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";

import { query } from "../lib/db/client.ts";
import { openWebsiteSession, revokeWebsiteSession } from "../lib/auth/login.ts";
import { authenticateSessionToken } from "../lib/auth/session.ts";
import { STREAMLIT_DOMAIN, WEBSITE_DOMAIN } from "../lib/auth/domains.ts";

const TAG = `${Date.now()}`.slice(-8);
let failures = 0;
const created = [];

function check(label, ok, detail = "") {
  if (!ok) failures += 1;
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${label}${detail ? `  -> ${detail}` : ""}`);
}

/** Call the Python Streamlit-side service, so both real implementations are used. */
function python(snippet) {
  return execFileSync(
    "/Users/ayoub/tradelens-ai/.venv/bin/python",
    ["-c", `import sys; sys.path.insert(0, "/Users/ayoub/tradelens-ai")\n${snippet}`],
    { encoding: "utf8", env: process.env, cwd: "/Users/ayoub/tradelens-ai" },
  ).trim();
}

async function run() {
  const [{ id: userId }] = await query(
    `INSERT INTO users (username, password_hash, is_active, onboarding_completed,
                        strategy_profile_completed, email_verification_required)
     VALUES ($1, 'x', 1, true, false, false) RETURNING id`,
    [`u_dom${TAG}`],
  );
  created.push(userId);

  // --- 1. website session, validated on its own surface --------------------
  const website = await openWebsiteSession(userId);
  const asWebsite = await authenticateSessionToken(website.token);
  check("website token validates on the website", asWebsite?.userId === userId);

  // --- 2. website token offered to the Streamlit validator -----------------
  const streamlitRejectsWebsite = python(
    `from src.tradelens.services import auth_sessions\n` +
    `print(auth_sessions.restore_streamlit_session(${JSON.stringify(website.token)}))`,
  );
  check("website token FAILS on the Streamlit validator",
    streamlitRejectsWebsite === "None", streamlitRejectsWebsite);

  // --- 3. Streamlit session, validated on its own surface ------------------
  const streamlitToken = python(
    `from src.tradelens.services import auth_sessions\n` +
    `print(auth_sessions.open_streamlit_session(${userId}))`,
  );
  const streamlitAccepts = python(
    `from src.tradelens.services import auth_sessions\n` +
    `print(auth_sessions.restore_streamlit_session(${JSON.stringify(streamlitToken)}))`,
  );
  check("Streamlit token validates on Streamlit", streamlitAccepts === String(userId), streamlitAccepts);

  // --- 4. THE ORIGINAL EXPLOIT: Streamlit token into the website cookie ----
  const asWebsiteFromStreamlit = await authenticateSessionToken(streamlitToken);
  check("Streamlit token FAILS on the website validator (original exploit closed)",
    asWebsiteFromStreamlit === null,
    asWebsiteFromStreamlit ? `LEAKED as user ${asWebsiteFromStreamlit.userId}` : "rejected");

  // --- 5. the rows visibly carry their surface -----------------------------
  const rows = await query(
    "SELECT surface, token_hash FROM auth_sessions WHERE user_id = $1 ORDER BY surface", [userId]);
  check("two rows, one per surface", rows.length === 2, JSON.stringify(rows.map((r) => r.surface)));
  check("surfaces are exactly streamlit and website",
    rows[0].surface === "streamlit" && rows[1].surface === "website");

  // --- 6. the stored hashes are domain-separated ---------------------------
  const undomainedWebsite = createHash("sha256").update(website.token, "utf8").digest("hex");
  const domainedWebsite = createHash("sha256").update(WEBSITE_DOMAIN + website.token, "utf8").digest("hex");
  const domainedStreamlit = createHash("sha256").update(STREAMLIT_DOMAIN + streamlitToken, "utf8").digest("hex");
  const stored = rows.map((r) => r.token_hash);
  check("no row stores the old undomained sha256", !stored.includes(undomainedWebsite));
  check("website row stores the website-domain hash", stored.includes(domainedWebsite));
  check("streamlit row stores the streamlit-domain hash", stored.includes(domainedStreamlit));
  check("the two hashes differ even though both derive from real tokens",
    domainedWebsite !== domainedStreamlit);

  // --- 7. copying the raw credential exactly still fails -------------------
  const copiedExactly = await authenticateSessionToken(String(streamlitToken));
  check("an exact copy of the Streamlit credential still fails on the website",
    copiedExactly === null);

  // --- 8. revoking one surface leaves the other alone ----------------------
  await revokeWebsiteSession(website.token);
  check("website session revoked", (await authenticateSessionToken(website.token)) === null);
  const streamlitStillLive = python(
    `from src.tradelens.services import auth_sessions\n` +
    `print(auth_sessions.restore_streamlit_session(${JSON.stringify(streamlitToken)}))`,
  );
  check("revoking the website session did NOT revoke the Streamlit one",
    streamlitStillLive === String(userId), streamlitStillLive);

  // --- 9. password-reset style revoke-all crosses both surfaces ------------
  const revokedAll = python(
    `from src.tradelens.services import auth_sessions\n` +
    `print(auth_sessions.revoke_all_for_user(${userId}))`,
  );
  const afterRevokeAll = python(
    `from src.tradelens.services import auth_sessions\n` +
    `print(auth_sessions.restore_streamlit_session(${JSON.stringify(streamlitToken)}))`,
  );
  check("revoke_all_for_user reaches the Streamlit session too",
    afterRevokeAll === "None", `revoked=${revokedAll}`);
}

async function cleanup() {
  if (created.length) {
    await query("DELETE FROM auth_sessions WHERE user_id = ANY($1)", [created]);
    await query("DELETE FROM auth_handoffs WHERE user_id = ANY($1)", [created]);
    await query("DELETE FROM users WHERE id = ANY($1)", [created]);
  }
  const rows = await query("SELECT username, password_hash FROM users ORDER BY id");
  const fps = rows.map((r) => createHash("sha256").update(r.password_hash, "utf8").digest("hex").slice(0, 16));
  check("dev users = 2", rows.length === 2, String(rows.length));
  check("usernames exactly ayoub / Ayoub",
    rows[0]?.username === "ayoub" && rows[1]?.username === "Ayoub");
  check("legacy fingerprints unchanged",
    fps[0] === "ad21629058e33b79" && fps[1] === "63585ccd0f71998e", fps.join(" / "));
  const [{ n }] = await query("SELECT count(*) AS n FROM auth_sessions");
  check("auth_sessions back to 0", Number(n) === 0, String(n));
}

async function main() {
  console.log("=== credential-domain security probe (dev) ===");
  try { await run(); }
  catch (e) { failures += 1; console.log(`  [FAIL] run threw: ${e.message}`); }
  finally {
    try { await cleanup(); }
    catch (e) { failures += 1; console.log(`  [FAIL] cleanup threw: ${e.message}`); }
  }
  console.log(failures === 0 ? "\nEXPLOIT CLOSED — ALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error("error:", e.message); process.exit(1); });
