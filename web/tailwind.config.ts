import type { Config } from "tailwindcss";

/**
 * Tokens mirror site/styles.css exactly, so the auth pages and the marketing
 * site are one visual system rather than two that happen to look similar.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d1117",
        surface: "#161b22",
        "surface-2": "#1c232b",
        border: "#252a32",
        text: "#e8eaed",
        muted: "#9aa4b2",
        accent: "#00e5cc",
        "accent-dim": "rgba(0, 229, 204, 0.12)",
      },
      fontFamily: {
        display: ["Schibsted Grotesk", "Satoshi", "system-ui", "sans-serif"],
        body: ["Satoshi", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SF Mono", "monospace"],
      },
      transitionTimingFunction: { tl: "cubic-bezier(0.16, 1, 0.3, 1)" },
    },
  },
  plugins: [],
};
export default config;
