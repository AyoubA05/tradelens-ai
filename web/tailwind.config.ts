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
        // --- Marketing layer. Mirrors site/styles.css exactly. Do not edit ---
        bg: "#0d1117",
        surface: "#161b22",
        "surface-2": "#1c232b",
        border: "#252a32",
        text: "#e8eaed",
        muted: "#9aa4b2",
        accent: "#00e5cc",
        "accent-dim": "rgba(0, 229, 204, 0.12)",

        // --- App layer -------------------------------------------------
        // The authenticated product needs surfaces and semantics the
        // marketing site never did. These extend that system rather than
        // replacing it: the Streamlit app's separate charcoal (#091216) is
        // retired, because a user must not see the ground shift when they
        // sign in.
        "surface-3": "#222a33", // selected controls, overlays, readouts
        line: "#252a32", // structure without drawing a box around everything
        "line-strong": "#3b444f", // load-bearing boundaries; >=3:1 on every surface
        chart: "#12171f", // plot ground, one step below surface

        // Semantic, and deliberately not teal. Teal means "act"; green and red
        // mean "this is what happened". Overloading the accent with outcome
        // would make every profitable row look like a button.
        positive: "#22c55e",
        negative: "#f56565",
        warning: "#f59e0b",

        // Focus is the accent on purpose: one ring, always the same, always
        // visible. Aliased rather than duplicated so it cannot drift.
        focus: "#00e5cc",
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
