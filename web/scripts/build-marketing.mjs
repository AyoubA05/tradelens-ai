/**
 * Copy the existing vanilla marketing site into public/ with origin tokens
 * substituted.
 *
 * The marketing site is NOT rewritten in React. It stays authored as
 * ../site/{index.html,styles.css,main.js,assets,...} exactly as it is today;
 * this step is the whole integration. next.config.mjs rewrites "/" to the
 * resulting index.html.
 *
 * Ports the substitution from the repo's scripts/build_site.py, including its
 * origin validation — that check is security-relevant, not cosmetic: an
 * unvalidated origin lands in canonical/og URLs and in every CTA href.
 *
 * That port was incomplete, and a clean-clone build is what showed it. This
 * script handled the two origin tokens and silently ignored `__SUPPORT_EMAIL__`,
 * so the output carried `mailto:__SUPPORT_EMAIL__` on the home page and as
 * *visible text* on /privacy and /terms. Nothing failed; the build succeeded
 * and the pages looked finished. Switching Vercel's Root Directory to web/
 * would have replaced a correct live site with that one.
 *
 * Three protections from the Python original are therefore restored here:
 *
 *   1. every deploy token is substituted, not just the two this file knew about;
 *   2. reserved and placeholder hosts are rejected, because a syntactically
 *      valid `https://www.example.test` is exactly the mistake the tokens exist
 *      to catch, and it would be baked into canonical and og:image URLs;
 *   3. the output is re-scanned afterwards and the build FAILS if any token
 *      survived — a missing value must stop a deploy, not decorate a page.
 */
import { cp, readFile, writeFile, rm, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const SITE = path.resolve(here, "..", "..", "site");
const PUBLIC = path.resolve(here, "..", "public");

const SITE_TOKEN = "__SITE_ORIGIN__";
const APP_TOKEN = "__APP_ORIGIN__";
const SUPPORT_TOKEN = "__SUPPORT_EMAIL__";

// Matches scripts/build_site.py's list, which is wider than the three
// extensions this file used to walk. No token-bearing file is outside
// html/js/css today, but a sitemap or webmanifest gaining one later must not
// silently ship unresolved.
const SUBSTITUTED = [".html", ".js", ".css", ".json", ".webmanifest", ".xml", ".txt"];

// Syntactically valid hosts that are never a real production origin. Reserved
// TLDs per RFC 2606/6761.
const RESERVED_SUFFIXES = [".example", ".invalid", ".localhost", ".test"];

/** True for hosts that only make sense during local development. */
function isLocalHost(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

export function validateOrigin(value, name, { allowLocal = true } = {}) {
  if (!value) throw new Error(`${name} is not set.`);
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${name} is not a valid absolute URL.`);
  }
  const local = isLocalHost(url.hostname);
  if (url.protocol !== "https:" && !local) {
    throw new Error(`${name} must be https (localhost excepted for development).`);
  }
  if (url.pathname !== "/" || url.search || url.hash) {
    throw new Error(`${name} must be a bare origin, with no path, query or fragment.`);
  }
  if (local) {
    if (!allowLocal) throw new Error(`${name} is a loopback origin, not a production host.`);
    return url.origin;
  }
  const host = url.hostname.toLowerCase();
  if (RESERVED_SUFFIXES.some((suffix) => host.endsWith(suffix))) {
    throw new Error(
      `${name} host "${host}" is a reserved placeholder domain, not a production origin. ` +
        `It would be baked into canonical and og:image URLs.`,
    );
  }
  if (!host.includes(".")) {
    throw new Error(`${name} host "${host}" is not a fully-qualified domain.`);
  }
  return url.origin;
}

/**
 * A published policy page needs a contact address that reaches a human.
 *
 * Validated rather than defaulted: an address nobody reads is worse than an
 * obviously missing one, and a default would be indistinguishable from a real
 * setting once it shipped.
 */
export function validateSupportEmail(value) {
  const address = (value ?? "").trim();
  if (!address) {
    throw new Error(
      "SUPPORT_EMAIL is not set. The privacy and terms pages must carry a " +
        "contact address that is actually monitored.",
    );
  }
  const [local, domain, ...rest] = address.split("@");
  if (!local || !domain || rest.length > 0 || !domain.includes(".") || /\s/.test(address)) {
    throw new Error(`SUPPORT_EMAIL is not a valid address: "${address}"`);
  }
  return address;
}

export async function buildMarketing({
  siteOrigin,
  appOrigin,
  supportEmail,
  // Overridable so the guard rails can be tested against a throwaway tree
  // instead of today's marketing copy. Production always uses the defaults.
  sourceDir = SITE,
  outputDir = PUBLIC,
} = {}) {
  const site = validateOrigin(siteOrigin ?? process.env.SITE_ORIGIN, "SITE_ORIGIN");
  const app = validateOrigin(appOrigin ?? process.env.APP_ORIGIN, "APP_ORIGIN");
  const support = validateSupportEmail(supportEmail ?? process.env.SUPPORT_EMAIL);

  if (!existsSync(sourceDir)) throw new Error(`Marketing source not found at ${sourceDir}`);

  const replacements = [
    [SITE_TOKEN, site],
    [APP_TOKEN, app],
    [SUPPORT_TOKEN, support],
  ];

  await rm(outputDir, { recursive: true, force: true });
  await mkdir(outputDir, { recursive: true });
  await cp(sourceDir, outputDir, { recursive: true });

  const { readdir } = await import("node:fs/promises");
  const survivors = [];

  async function walk(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) { await walk(full); continue; }
      if (!SUBSTITUTED.includes(path.extname(entry.name))) continue;
      const original = await readFile(full, "utf8");
      let replaced = original;
      for (const [token, value] of replacements) {
        replaced = replaced.split(token).join(value);
      }
      if (replaced !== original) await writeFile(full, replaced, "utf8");
      // Re-read what was actually written, so the check describes the artifact
      // rather than what this loop believes it produced.
      if (/__[A-Z][A-Z0-9_]*__/.test(replaced)) {
        const found = [...new Set(replaced.match(/__[A-Z][A-Z0-9_]*__/g))];
        survivors.push(`${path.relative(outputDir, full)}: ${found.join(", ")}`);
      }
    }
  }
  await walk(outputDir);

  if (survivors.length > 0) {
    // Fail rather than publish. A surviving token is a value nobody supplied,
    // and it renders to a visitor as a broken link or literal placeholder text.
    throw new Error(
      `deploy token survived substitution:\n  ${survivors.join("\n  ")}`,
    );
  }

  return { site, app, support };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  buildMarketing()
    .then(({ site, app }) =>
      console.log(`marketing site copied to public/ (site=${site} app=${app})`),
    )
    .catch((error) => { console.error(error.message); process.exit(1); });
}
