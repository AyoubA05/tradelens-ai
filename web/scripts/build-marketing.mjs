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
const SUBSTITUTED = [".html", ".js", ".css"];

export function validateOrigin(value, name) {
  if (!value) throw new Error(`${name} is not set.`);
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${name} is not a valid absolute URL.`);
  }
  if (url.protocol !== "https:" && url.hostname !== "localhost") {
    throw new Error(`${name} must be https (localhost excepted for development).`);
  }
  if (url.pathname !== "/" || url.search || url.hash) {
    throw new Error(`${name} must be a bare origin, with no path, query or fragment.`);
  }
  return url.origin;
}

export async function buildMarketing({ siteOrigin, appOrigin } = {}) {
  const site = validateOrigin(siteOrigin ?? process.env.SITE_ORIGIN, "SITE_ORIGIN");
  const app = validateOrigin(appOrigin ?? process.env.APP_ORIGIN, "APP_ORIGIN");

  if (!existsSync(SITE)) throw new Error(`Marketing source not found at ${SITE}`);

  await rm(PUBLIC, { recursive: true, force: true });
  await mkdir(PUBLIC, { recursive: true });
  await cp(SITE, PUBLIC, { recursive: true });

  const { readdir } = await import("node:fs/promises");
  async function walk(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) { await walk(full); continue; }
      if (!SUBSTITUTED.includes(path.extname(entry.name))) continue;
      const original = await readFile(full, "utf8");
      const replaced = original.split(SITE_TOKEN).join(site).split(APP_TOKEN).join(app);
      if (replaced !== original) await writeFile(full, replaced, "utf8");
    }
  }
  await walk(PUBLIC);
  return { site, app };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  buildMarketing()
    .then(({ site, app }) => console.log(`marketing site copied to public/ (site=${site} app=${app})`))
    .catch((error) => { console.error(error.message); process.exit(1); });
}
