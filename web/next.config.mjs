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
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async rewrites() {
    return [{ source: "/", destination: "/index.html" }];
  },
};

export default nextConfig;
