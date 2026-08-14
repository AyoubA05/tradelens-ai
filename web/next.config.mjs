/**
 * Next configuration.
 *
 * Two things matter here:
 *
 * 1. The existing vanilla marketing site is served from public/ at "/". It is
 *    NOT rewritten in React — scripts/build-marketing.mjs copies ../site into
 *    public/ with origin tokens substituted, and this rewrite points "/" at the
 *    resulting index.html. The marketing work is preserved exactly as authored.
 *
 * 2. Security headers. Auth pages must never be framed (clickjacking on a login
 *    form is a credential-theft primitive), and the Referer must not carry a
 *    session-bearing URL to another origin.
 */
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  // strict-origin-when-cross-origin still sends the origin cross-site.
  // The Streamlit session credential rides in a URL during the beta, so
  // no-referrer is the correct setting until that is no longer true.
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-DNS-Prefetch-Control", value: "off" },
  // Declared here rather than left to the platform. Vercel sends HSTS of its
  // own, but this site's security properties should not depend on which host
  // is serving it, and a plain-HTTP first request to an auth page is exactly
  // the one worth never allowing. Two years, subdomains included. `preload` is
  // deliberately absent: it is effectively irreversible and belongs to a
  // decision about the apex domain, not to this file.
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains",
  },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Next 16 writes web/AGENTS.md and web/CLAUDE.md on dev boot. The repository
  // root already has a CLAUDE.md that every session loads; a generated second
  // one inside web/ would silently take precedence for work in this directory.
  // Instructions here are authored, not generated.
  agentRules: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async rewrites() {
    return [{ source: "/", destination: "/index.html" }];
  },
};

export default nextConfig;
