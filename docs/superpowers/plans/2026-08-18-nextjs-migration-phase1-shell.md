# Phase 1 — Shell & Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the authenticated TradeLens app shell — routing, navigation, chrome, state primitives, the AI Partner drawer, and one unified design token system — so that later phases have somewhere to render, and so a user never sees a seam between the marketing site and the product.

**Architecture:** A `/app` route tree in the existing Next.js application, server-rendered by default with client islands only where interaction demands one. Identity comes from the session the website already validates; **Phase 1 makes no FastAPI calls**, because a shell with no data has nothing to fetch. The Phase 0 security boundary is therefore untouched, not re-opened.

**Tech Stack:** Next.js 16 (App Router, RSC) · React 19 · TypeScript · Tailwind CSS · framer-motion · lucide-react · Vitest + Testing Library. **No new dependencies.**

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` (§7 phase 1, §12 design direction, §12b execution corrections)

## Global Constraints

- **Do not re-open the Phase 0 security architecture.** Specifically preserved, and out of scope to change: the domain-separated session handle + HMAC boundary; mandatory service-layer ownership; the R2 quarantine/finalization model; the HMAC canonicalization contract (pair order preserved, leading `?` literal); the generated OpenAPI/TypeScript contract gates.
- TradeLens is a **post-trade reflection journal**. Never a signal app, a bot, or financial advice. This binds every label, empty state, error string, and comment. Nothing in the shell may imply a live market opinion or a good moment to trade.
- Presentation only. **Do not implement Overview, Trades, New Trade, Analytics, AI Reviews, Strategy or Settings functionality.** Those routes get non-functional placeholders that prove the shell, and nothing more.
- No new npm dependencies. Everything needed is already installed.
- `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build` must all pass. `next build` runs Turbopack.
- Python gates must stay green and untouched: `pytest tests/`, `ruff check src/ scripts/`, `black --check src/ scripts/ tests/`.
- Accessibility floor, non-negotiable: visible keyboard focus, reduced motion respected, WCAG AA contrast, every interactive element reachable and operable by keyboard.
- Work happens in `web/`. Server-only modules keep `import "server-only"`.

---

## Design decisions

Stated here because they shape every task, and because they are the decisions worth disagreeing with before code exists.

**1. The marketing token set is canonical; the app extends it.**
`web/tailwind.config.ts` already mirrors `site/styles.css` (`bg #0d1117`, `surface #161b22`, `accent #00e5cc`). The Streamlit app used a different charcoal (`#091216`). One of them has to lose, and it is Streamlit's: the marketing site is live, recently redesigned, and is the identity a user meets first. The app joins that system. Phase 1 **adds** the tokens the app needs and marketing lacks — elevated surfaces, semantic green/red, hairlines, a chart ground — and changes no existing value. A test pins the marketing values so this config cannot drift the live site.

**2. Signature element: the period lens — the global analysis range.**
Every figure in a post-trade journal is meaningless without its window and its sample size — that is the single most characteristic fact about this product, and the 10K audit's sharpest criticism was that the old app showed confident numbers over tiny samples. So on the surfaces that aggregate performance, the period under examination is **chrome rather than a control each page re-invents**. It renders in JetBrains Mono, reads `2026-08-12 → 2026-08-18`, and owns the `?from=&to=` URL contract.

**It is the global analysis range, not a universal filter.** It governs the performance-oriented surfaces — Overview, Journal/Trades, Analytics, and the AI review views whose temporal semantics match it. Routes whose temporal meaning differs ignore it entirely and keep their own control:

| Route | Its own temporal scope |
|---|---|
| Trade Detail | one trade — a range means nothing |
| New Trade | the trade being logged |
| Weekly Recap | keeps its week selector |
| Daily Debrief | keeps its day selector |
| Strategy Profile | not time-scoped |
| Settings | not time-scoped |

**The invariant is that no view ever shows two controls claiming the same temporal scope.** The lens is therefore hidden on routes it does not govern rather than displayed inertly beside a week or day selector — a control that appears to govern a page but does not is worse than no control at all. And `?from=&to=` is never forced onto a route with no use for it, so URLs do not carry parameters that mean nothing.

This is the one place Phase 1 spends its boldness. Everything else in the shell stays quiet.

**3. Navigation reproduces the Streamlit information architecture exactly.**
Six destinations — Overview, Journal, Analytics, AI Reviews, Strategy Profile, Settings — plus "Log completed trade" as the primary action and AI Partner as a drawer. Migrating the visual system and the IA simultaneously would make any regression unattributable: a user complaint could mean either "you moved my thing" or "you broke my thing". The IA moves in a later phase, deliberately, or not at all.

**4. Phase 1 calls no API.**
The shell has no data to fetch. Identity comes from `authenticateWebsiteRequest`, exactly as `/continue` already does. This keeps the shell buildable and testable with no backend running, no `TL_API_ORIGIN`, and no `TL_SERVICE_SECRET` — and it means Phase 1 cannot possibly weaken the Phase 0 boundary, because it never touches it.

**5. `users.app_surface` becomes the live cutover switch — opt-in only.**
Phase 0 added the column; nothing reads it. Phase 1 teaches the session query to select it and routes `/continue` on it: `'nextjs'` goes to `/app`, everything else keeps the existing Streamlit handoff untouched.

**Reading the column must not move anybody.** The Phase 0 migration adds it with `server_default='streamlit'` and performs no backfill, so every existing account is already on Streamlit and stays there until somebody is deliberately opted in, one row at a time. Phase 1 therefore ships **no bulk switch, no default flip, and no "migrate all users" path** — and a test pins that, because this is the kind of invariant that survives review and then dies quietly in a later convenience commit. The switch is per-account and reversible in both directions.

## Risks

**Two controls claiming the same temporal scope.** The audit's specific finding against New Trade was two progress systems competing, and a period lens sitting above a page that has its own week or day selector would repeat that mistake exactly. Mitigation: `routeUsesPeriod()` is an explicit allowlist and the lens renders nowhere else, so a route that does not opt in cannot display it. Adding a period-scoped surface is a deliberate one-line act, not something a new route inherits by accident.

**The inverse risk — a page silently ignoring the range.** A visible lens over a surface that does not honour it would be a lie about what the numbers mean. Same mitigation from the other side: if the lens is shown, that route is on the allowlist, and its phase owes the reader a range-scoped view.

**Token changes regressing the live marketing site.** `tailwind.config.ts` is shared. Mitigation: additive only, plus a test that asserts each existing marketing value is unchanged.

**Focus management is where shells actually break.** A drawer, a mobile sheet, and a nav rail all trap or lose focus in ways typing tests never catch. Mitigation: focus and keyboard behaviour get their own task with real assertions, after the components exist, rather than being sprinkled through each.

**Route-group layout nesting.** Next's App Router silently applies the root layout too; a second `<html>` or a duplicated font import is easy and invisible until the production build. Mitigation: the layout task asserts document structure, and `npm run build` is run in that task, not deferred.

---

## File Structure

**New — shared model (no React, unit-testable on its own)**

| File | Responsibility |
|---|---|
| `web/lib/app/navigation.ts` | The six destinations, the primary action, and active-route matching. One source of truth for sidebar, bottom nav and the More sheet. |
| `web/lib/app/period.ts` | The period lens contract: presets, parsing from and serialising to search params, formatting. |

**New — chrome**

| File | Responsibility |
|---|---|
| `web/app/app/layout.tsx` | Server component. Auth gate, then the shell frame. |
| `web/components/app/app-shell.tsx` | Grid frame: sidebar, top bar, main, drawer, bottom nav. |
| `web/components/app/sidebar.tsx` | Desktop rail: brand, primary action, destinations, active marker. |
| `web/components/app/top-bar.tsx` | Page title slot, the period lens, the Partner launcher. |
| `web/components/app/period-lens.tsx` | Client island. The signature control. |
| `web/components/app/bottom-nav.tsx` | Phone navigation: four destinations plus More. |
| `web/components/app/more-sheet.tsx` | Phone overflow for the remaining destinations. |
| `web/components/app/partner-drawer.tsx` | Drawer shell — frame, open/close, focus trap. No conversation. |
| `web/components/app/skip-link.tsx` | Skip to main content. |

**New — state primitives**

| File | Responsibility |
|---|---|
| `web/components/app/states/loading-state.tsx` | Skeleton and spinner primitives. |
| `web/components/app/states/empty-state.tsx` | Empty state: what this is, and the one action that fills it. |
| `web/components/app/states/error-state.tsx` | Error state: what happened and how to recover. |

**New — route placeholders** (`web/app/app/*/page.tsx`): `page.tsx` (Overview), `journal/`, `analytics/`, `reviews/`, `strategy/`, `settings/`, `trades/new/`.

**Modified**

| File | Change |
|---|---|
| `web/tailwind.config.ts` | Add app-layer tokens. Existing values untouched. |
| `web/app/globals.css` | Focus-visible ring, app scrollbar treatment. |
| `web/lib/auth/session.ts` | Select `app_surface`; add it to `WebsiteUser`; route on it. |
| `web/app/continue/page.tsx` | Send `app_surface = 'nextjs'` accounts to `/app`. |

---

### Task 1: Unified design tokens

**Files:**
- Modify: `web/tailwind.config.ts`
- Modify: `web/app/globals.css`
- Test: `web/__tests__/design-tokens.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces: Tailwind colour names `surface-3`, `line`, `line-strong`, `positive`, `negative`, `warning`, `chart`, and `focus`; the `--tl-focus-ring` CSS custom property

- [ ] **Step 1: Write the failing test**

```typescript
// web/__tests__/design-tokens.test.ts
import { describe, expect, it } from "vitest";

import config from "../tailwind.config";

const colors = (config.theme?.extend?.colors ?? {}) as Record<string, string>;

describe("marketing tokens are load-bearing and must not drift", () => {
  // These exact values are what site/styles.css ships. The app joins the
  // marketing system; it does not get to redefine it. If one of these changes,
  // the live site changes with it.
  it.each([
    ["bg", "#0d1117"],
    ["surface", "#161b22"],
    ["surface-2", "#1c232b"],
    ["border", "#252a32"],
    ["text", "#e8eaed"],
    ["muted", "#9aa4b2"],
    ["accent", "#00e5cc"],
  ])("%s is still %s", (name, value) => {
    expect(colors[name]).toBe(value);
  });
});

describe("app layer tokens", () => {
  it.each(["surface-3", "line", "line-strong", "positive", "negative", "warning", "chart", "focus"])(
    "defines %s",
    (name) => {
      expect(colors[name]).toBeTruthy();
    },
  );

  it("keeps one accent, so teal stays the action colour rather than decoration", () => {
    const teals = Object.entries(colors).filter(
      ([, v]) => typeof v === "string" && v.toLowerCase() === "#00e5cc",
    );
    expect(teals.map(([k]) => k).sort()).toEqual(["accent", "focus"]);
  });

  it("separates profit and loss from the accent", () => {
    expect(colors.positive).not.toBe(colors.accent);
    expect(colors.negative).not.toBe(colors.accent);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/design-tokens.test.ts`
Expected: FAIL — `surface-3` and the other app tokens are undefined.

- [ ] **Step 3: Add the app layer to the Tailwind config**

In `web/tailwind.config.ts`, replace the `colors` block with:

```typescript
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
```

- [ ] **Step 4: Add the focus ring to globals**

Append to `web/app/globals.css`:

```css
/* One focus treatment for the whole product.
   :focus-visible, not :focus — a mouse user clicking a button should not get a
   ring, and a keyboard user must never lose one. */
:root { --tl-focus-ring: 0 0 0 2px theme('colors.bg'), 0 0 0 4px theme('colors.focus'); }

:where(a, button, input, select, textarea, summary, [tabindex]):focus-visible {
  outline: none;
  box-shadow: var(--tl-focus-ring);
  border-radius: 6px;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/design-tokens.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd web && npx tsc --noEmit && npx eslint . && cd ..
git add web/tailwind.config.ts web/app/globals.css web/__tests__/design-tokens.test.ts
git commit -m "feat(app): one token system for marketing and product

The app layer extends the marketing tokens rather than replacing them.
Streamlit's separate charcoal is retired: a user must not see the ground
shift when they sign in. Green and red stay out of the accent, because
teal means act and overloading it would make every profitable row look
like a button. A test pins the marketing values, since this config is
shared with the live site."
```

---

### Task 2: Route on `app_surface`

**Files:**
- Modify: `web/lib/auth/session.ts`
- Modify: `web/app/continue/page.tsx`
- Test: `web/__tests__/app-surface-routing.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces: `WebsiteUser.appSurface: string`; `nextDestinationFor(user)` returning `/app` for `'nextjs'` accounts only. **No bulk-switch path is created.**

- [ ] **Step 1: Write the failing test**

```typescript
// web/__tests__/app-surface-routing.test.ts
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { nextDestinationFor, type WebsiteUser } from "@/lib/auth/session";

function user(overrides: Partial<WebsiteUser> = {}): WebsiteUser {
  return {
    userId: 1,
    email: "trader@example.com",
    emailVerifiedAt: new Date(),
    emailVerificationRequired: true,
    onboardingCompleted: true,
    strategyProfileCompleted: true,
    appSurface: "streamlit",
    ...overrides,
  };
}

describe("app_surface routing", () => {
  it("sends a migrated account to the new app", () => {
    expect(nextDestinationFor(user({ appSurface: "nextjs" }))).toBe("/app");
  });

  it("leaves every other account on the existing handoff", () => {
    expect(nextDestinationFor(user({ appSurface: "streamlit" }))).toBe("/continue");
  });

  it("treats an unrecognised value as not migrated", () => {
    // Fail closed: an unknown surface must not strand a trader on a shell that
    // cannot yet show their journal.
    expect(nextDestinationFor(user({ appSurface: "something-else" }))).toBe("/continue");
  });

  it("still gates on email and onboarding before surface is considered", () => {
    expect(
      nextDestinationFor(user({ appSurface: "nextjs", emailVerifiedAt: null })),
    ).toBe("/verify-email");
    expect(
      nextDestinationFor(user({ appSurface: "nextjs", onboardingCompleted: false })),
    ).toBe("/onboarding");
  });
});

describe("the cutover is opt-in", () => {
  it("moves nobody by default", () => {
    // Reading the column must not migrate anyone. Every account arrives here
    // as "streamlit" because the Phase 0 migration set that server-side
    // default and backfilled nothing.
    expect(nextDestinationFor(user())).toBe("/continue");
  });

  it("has no bulk switch anywhere in the web layer", () => {
    // The invariant that survives review and then dies in a later convenience
    // commit. If a "migrate all users" path is ever added, this fails.
    const dir = path.join(__dirname, "..", "lib");
    const files: string[] = [];
    (function walk(d: string) {
      for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
        const full = path.join(d, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.name.endsWith(".ts")) files.push(full);
      }
    })(dir);

    for (const file of files) {
      const source = fs.readFileSync(file, "utf8");
      // A write to app_surface that is not scoped to a single id.
      expect(
        /UPDATE\s+users\s+SET\s+app_surface(?![\s\S]{0,200}WHERE[\s\S]{0,40}id)/i.test(source),
        `${file} appears to switch app_surface without scoping to one account`,
      ).toBe(false);
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/app-surface-routing.test.ts`
Expected: FAIL — `appSurface` is not a property of `WebsiteUser`.

- [ ] **Step 3: Select the column and add it to the type**

In `web/lib/auth/session.ts`, add to the `WebsiteUser` type:

```typescript
  /** Which product this account lands on: "streamlit" or "nextjs". */
  appSurface: string;
```

Add `app_surface: string;` to the row type of the `query<...>` generic, add `u.app_surface` to the `RETURNING` list, and add to the returned object:

```typescript
    appSurface: row.app_surface,
```

- [ ] **Step 4: Route on it**

Replace `nextDestinationFor`:

```typescript
/**
 * Where an authenticated user belongs right now.
 *
 * One function so login, onboarding, and the continuation page cannot disagree
 * about it.
 *
 * The surface check is last, and deliberately so: a migrated account still has
 * to clear the email and onboarding gates. It also compares against the one
 * known value rather than checking "not streamlit", so an unrecognised entry
 * keeps the existing journal instead of stranding a trader on a shell that
 * cannot yet show their trades.
 */
export function nextDestinationFor(user: WebsiteUser): string {
  if (!emailGatePassed(user)) return "/verify-email";
  if (!user.onboardingCompleted) return "/onboarding";
  if (user.appSurface === "nextjs") return "/app";
  return "/continue";
}
```

- [ ] **Step 5: Send migrated accounts past the handoff**

In `web/app/continue/page.tsx`, immediately after the `user` is resolved and the existing null/eligibility checks, add:

```tsx
  // A migrated account never mints a Streamlit handoff. The redirect is here
  // rather than in middleware so the decision stays in the same place as the
  // rest of the continuation logic.
  if (user && user.appSurface === "nextjs") redirect("/app");
```

- [ ] **Step 6: Run tests**

Run: `cd web && npx vitest run __tests__/app-surface-routing.test.ts __tests__/routes.test.tsx`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd web && npx tsc --noEmit && npx eslint . && cd ..
git add web/lib/auth/session.ts web/app/continue/page.tsx web/__tests__/app-surface-routing.test.ts
git commit -m "feat(app): route migrated accounts to the new shell

Phase 0 added users.app_surface and nothing read it. The session query
now selects it and the continuation page routes on it, which is what
makes the shell reachable at all — per account, and reversible by
changing one column.

The check is last, so a migrated account still clears the email and
onboarding gates, and it compares against the one known value rather
than 'not streamlit', so an unrecognised entry keeps the journal that
works today."
```

---

### Task 3: Navigation model

**Files:**
- Create: `web/lib/app/navigation.ts`
- Test: `web/__tests__/navigation-model.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `type AppDestination = { href: string; label: string; icon: LucideIcon; phonePriority: boolean }`
  - `APP_DESTINATIONS: AppDestination[]` (six entries)
  - `PRIMARY_ACTION: { href: string; label: string }`
  - `isActiveDestination(pathname: string, href: string): boolean`

- [ ] **Step 1: Write the failing test**

```typescript
// web/__tests__/navigation-model.test.ts
import { describe, expect, it } from "vitest";

import {
  APP_DESTINATIONS,
  PRIMARY_ACTION,
  isActiveDestination,
} from "@/lib/app/navigation";

describe("destinations", () => {
  it("reproduces the journal's information architecture", () => {
    expect(APP_DESTINATIONS.map((d) => d.label)).toEqual([
      "Overview",
      "Journal",
      "Analytics",
      "AI Reviews",
      "Strategy Profile",
      "Settings",
    ]);
  });

  it("gives every destination a route under /app", () => {
    for (const d of APP_DESTINATIONS) expect(d.href.startsWith("/app")).toBe(true);
  });

  it("has no duplicate routes", () => {
    const hrefs = APP_DESTINATIONS.map((d) => d.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("marks exactly four destinations for the phone bar", () => {
    // Four plus More. A fifth makes the targets too narrow to hit at 375px.
    expect(APP_DESTINATIONS.filter((d) => d.phonePriority)).toHaveLength(4);
  });

  it("keeps logging a trade as the primary action, not a destination", () => {
    expect(PRIMARY_ACTION.label).toBe("Log completed trade");
    expect(APP_DESTINATIONS.map((d) => d.href)).not.toContain(PRIMARY_ACTION.href);
  });
});

describe("active matching", () => {
  it("matches a destination exactly", () => {
    expect(isActiveDestination("/app/journal", "/app/journal")).toBe(true);
  });

  it("matches a child route", () => {
    expect(isActiveDestination("/app/journal/42", "/app/journal")).toBe(true);
  });

  it("does not let Overview swallow every other route", () => {
    // "/app" is a prefix of everything under it, so a naive startsWith would
    // light up Overview on every screen in the product.
    expect(isActiveDestination("/app/journal", "/app")).toBe(false);
    expect(isActiveDestination("/app", "/app")).toBe(true);
  });

  it("does not match a route that merely shares a prefix", () => {
    expect(isActiveDestination("/app/journalling", "/app/journal")).toBe(false);
  });

  it("ignores a trailing slash", () => {
    expect(isActiveDestination("/app/journal/", "/app/journal")).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/navigation-model.test.ts`
Expected: FAIL — cannot resolve `@/lib/app/navigation`.

- [ ] **Step 3: Write the model**

```typescript
// web/lib/app/navigation.ts
import {
  BookOpen,
  BarChart3,
  Brain,
  Flag,
  LayoutDashboard,
  Settings,
  type LucideIcon,
} from "lucide-react";

/**
 * The product's information architecture, in one place.
 *
 * The sidebar, the phone bar and the overflow sheet all read this array, so
 * they cannot drift into three different ideas of what the app contains.
 *
 * The six destinations are deliberately the same six the Streamlit journal
 * had. Moving the visual system and the navigation in one step would make any
 * regression unattributable — a complaint could mean "you moved my thing" or
 * "you broke my thing", and there would be no way to tell which.
 */
export type AppDestination = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Shown in the phone bar rather than behind More. */
  phonePriority: boolean;
};

export const APP_DESTINATIONS: AppDestination[] = [
  { href: "/app", label: "Overview", icon: LayoutDashboard, phonePriority: true },
  { href: "/app/journal", label: "Journal", icon: BookOpen, phonePriority: true },
  { href: "/app/analytics", label: "Analytics", icon: BarChart3, phonePriority: false },
  { href: "/app/reviews", label: "AI Reviews", icon: Brain, phonePriority: true },
  { href: "/app/strategy", label: "Strategy Profile", icon: Flag, phonePriority: false },
  { href: "/app/settings", label: "Settings", icon: Settings, phonePriority: true },
];

/**
 * Logging a trade is an action, not a place. It keeps its own affordance at the
 * top of the sidebar instead of sitting in the list, because it is the one
 * thing a trader comes here to do that is not reading.
 */
export const PRIMARY_ACTION = {
  href: "/app/trades/new",
  label: "Log completed trade",
};

/**
 * Whether `href` is the destination currently being viewed.
 *
 * Overview is matched exactly. Every other destination also matches its own
 * children, so a trade detail page keeps Journal lit. Without the exact case
 * for "/app", a prefix match would light Overview up on every screen in the
 * product, and the boundary check stops "/app/journalling" matching
 * "/app/journal".
 */
export function isActiveDestination(pathname: string, href: string): boolean {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (href === "/app") return path === "/app";
  return path === href || path.startsWith(`${href}/`);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/navigation-model.test.ts`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
cd web && npx tsc --noEmit && npx eslint . && cd ..
git add web/lib/app/navigation.ts web/__tests__/navigation-model.test.ts
git commit -m "feat(app): one navigation model for every surface

The sidebar, phone bar and overflow sheet read one array so they cannot
drift into three ideas of what the app contains. The six destinations
are deliberately the Streamlit journal's: moving the visual system and
the IA together would make any regression unattributable.

isActiveDestination matches Overview exactly, because /app is a prefix
of every route under it and a naive startsWith lights Overview up on
every screen in the product."
```

---

### Task 4: The period lens contract

**Files:**
- Create: `web/lib/app/period.ts`
- Test: `web/__tests__/period-lens.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `type Period = { from: string; to: string; presetId: string }`
  - `PERIOD_PRESETS: { id: string; label: string; days: number }[]`
  - `periodFromParams(params: URLSearchParams, today?: Date): Period`
  - `periodToParams(period: Period): URLSearchParams`
  - `formatPeriod(period: Period): string`
  - `PERIOD_SCOPED_ROUTES: string[]`
  - `routeUsesPeriod(pathname: string): boolean`

- [ ] **Step 1: Write the failing test**

```typescript
// web/__tests__/period-lens.test.ts
import { describe, expect, it } from "vitest";

import {
  PERIOD_PRESETS,
  formatPeriod,
  periodFromParams,
  periodToParams,
  routeUsesPeriod,
} from "@/lib/app/period";

const TODAY = new Date("2026-08-18T12:00:00Z");

describe("reading a period from the URL", () => {
  it("defaults to the last 30 days when nothing is set", () => {
    const p = periodFromParams(new URLSearchParams(), TODAY);
    expect(p.to).toBe("2026-08-18");
    expect(p.from).toBe("2026-07-20");
    expect(p.presetId).toBe("30d");
  });

  it("reads an explicit range", () => {
    const p = periodFromParams(
      new URLSearchParams("from=2026-08-01&to=2026-08-15"),
      TODAY,
    );
    expect(p).toEqual({ from: "2026-08-01", to: "2026-08-15", presetId: "custom" });
  });

  it("recognises a range that matches a preset", () => {
    const p = periodFromParams(
      new URLSearchParams("from=2026-08-12&to=2026-08-18"),
      TODAY,
    );
    expect(p.presetId).toBe("7d");
  });

  it("falls back to the default when a date is unparseable", () => {
    // A hand-edited URL must not produce a window no page can render.
    const p = periodFromParams(new URLSearchParams("from=yesterday&to=soon"), TODAY);
    expect(p.presetId).toBe("30d");
  });

  it("swaps a reversed range rather than returning an empty window", () => {
    const p = periodFromParams(
      new URLSearchParams("from=2026-08-18&to=2026-08-01"),
      TODAY,
    );
    expect(p.from).toBe("2026-08-01");
    expect(p.to).toBe("2026-08-18");
  });

  it("ignores a partial range", () => {
    expect(periodFromParams(new URLSearchParams("from=2026-08-01"), TODAY).presetId).toBe("30d");
  });
});

describe("writing a period back", () => {
  it("round-trips", () => {
    const p = periodFromParams(new URLSearchParams("from=2026-08-01&to=2026-08-15"), TODAY);
    expect(periodFromParams(periodToParams(p), TODAY)).toEqual(p);
  });

  it("emits both bounds so a link is self-contained", () => {
    const params = periodToParams({ from: "2026-08-01", to: "2026-08-15", presetId: "custom" });
    expect(params.get("from")).toBe("2026-08-01");
    expect(params.get("to")).toBe("2026-08-15");
  });
});

describe("presets", () => {
  it("offers windows a trader actually reviews in", () => {
    expect(PERIOD_PRESETS.map((p) => p.id)).toEqual(["7d", "30d", "90d", "ytd"]);
  });
});

describe("formatting", () => {
  it("reads as a range, in ISO order, for the mono top bar", () => {
    expect(formatPeriod({ from: "2026-08-12", to: "2026-08-18", presetId: "7d" })).toBe(
      "2026-08-12 → 2026-08-18",
    );
  });
});

describe("which routes the range governs", () => {
  it("governs the surfaces that aggregate performance", () => {
    expect(routeUsesPeriod("/app")).toBe(true);
    expect(routeUsesPeriod("/app/journal")).toBe(true);
    expect(routeUsesPeriod("/app/analytics")).toBe(true);
    expect(routeUsesPeriod("/app/reviews")).toBe(true);
  });

  it("leaves a single trade alone — a range means nothing there", () => {
    expect(routeUsesPeriod("/app/journal/42")).toBe(false);
  });

  it("leaves routes that are not time-scoped alone", () => {
    expect(routeUsesPeriod("/app/trades/new")).toBe(false);
    expect(routeUsesPeriod("/app/strategy")).toBe(false);
    expect(routeUsesPeriod("/app/settings")).toBe(false);
  });

  it("yields to a view that carries its own temporal control", () => {
    // Weekly Recap keeps its week selector and Daily Debrief its day selector.
    // Two controls claiming the same scope on one view is the thing this
    // allowlist exists to prevent.
    expect(routeUsesPeriod("/app/reviews/weekly")).toBe(false);
    expect(routeUsesPeriod("/app/reviews/daily")).toBe(false);
  });

  it("does not let a child route inherit the range by accident", () => {
    // Exact matching, deliberately: a new sub-route must opt in on purpose
    // rather than acquire a lens nobody decided it should have.
    expect(routeUsesPeriod("/app/analytics/setups")).toBe(false);
  });

  it("ignores a trailing slash", () => {
    expect(routeUsesPeriod("/app/journal/")).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/period-lens.test.ts`
Expected: FAIL — cannot resolve `@/lib/app/period`.

- [ ] **Step 3: Write the contract**

```typescript
// web/lib/app/period.ts

/**
 * The period lens: the window every figure in the product is measured over.
 *
 * This exists as chrome rather than as a per-page filter because no number in a
 * post-trade journal means anything without its window and its sample size. A
 * win rate over four days and a win rate over four months are different claims,
 * and the old app let a page show one while the reader assumed the other.
 *
 * It lives in the URL so a period is linkable, back-button-able, and shared
 * between pages without a client store. Later phases READ this; no page may
 * introduce a second date control.
 */
export type Period = {
  /** Inclusive ISO date, YYYY-MM-DD. */
  from: string;
  /** Inclusive ISO date, YYYY-MM-DD. */
  to: string;
  /** The preset this range corresponds to, or "custom". */
  presetId: string;
};

export const PERIOD_PRESETS = [
  { id: "7d", label: "Last 7 days", days: 7 },
  { id: "30d", label: "Last 30 days", days: 30 },
  { id: "90d", label: "Last 90 days", days: 90 },
  { id: "ytd", label: "Year to date", days: 0 },
] as const;

const DEFAULT_PRESET = "30d";
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function toIso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function parseIso(value: string | null): Date | null {
  if (!value || !ISO_DATE.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function shiftDays(from: Date, days: number): Date {
  const out = new Date(from);
  out.setUTCDate(out.getUTCDate() - days);
  return out;
}

function rangeForPreset(presetId: string, today: Date): { from: string; to: string } {
  if (presetId === "ytd") {
    return { from: `${today.getUTCFullYear()}-01-01`, to: toIso(today) };
  }
  const preset = PERIOD_PRESETS.find((p) => p.id === presetId) ?? PERIOD_PRESETS[1];
  // Inclusive of both ends: "last 7 days" is today plus the six before it.
  return { from: toIso(shiftDays(today, preset.days - 1)), to: toIso(today) };
}

function presetMatching(from: string, to: string, today: Date): string {
  for (const preset of PERIOD_PRESETS) {
    const candidate = rangeForPreset(preset.id, today);
    if (candidate.from === from && candidate.to === to) return preset.id;
  }
  return "custom";
}

/**
 * Read a period from search params, falling back to the default window.
 *
 * Bad input fails to the default rather than raising: this comes from a URL, so
 * it is attacker- and typo-reachable, and a window nothing can render is worse
 * than a window the reader did not ask for. A reversed range is swapped rather
 * than rejected, because the intent is unambiguous.
 */
export function periodFromParams(params: URLSearchParams, today: Date = new Date()): Period {
  const fromDate = parseIso(params.get("from"));
  const toDate = parseIso(params.get("to"));

  if (!fromDate || !toDate) {
    const fallback = rangeForPreset(DEFAULT_PRESET, today);
    return { ...fallback, presetId: DEFAULT_PRESET };
  }

  const [start, end] = fromDate <= toDate ? [fromDate, toDate] : [toDate, fromDate];
  const from = toIso(start);
  const to = toIso(end);
  return { from, to, presetId: presetMatching(from, to, today) };
}

/** Serialise a period back to search params. Both bounds, always. */
export function periodToParams(period: Period): URLSearchParams {
  const params = new URLSearchParams();
  params.set("from", period.from);
  params.set("to", period.to);
  return params;
}

/** The top-bar reading. ISO order, because the mono column has to align. */
export function formatPeriod(period: Period): string {
  return `${period.from} → ${period.to}`;
}

/**
 * The routes the global analysis range governs.
 *
 * Exact matches, and an allowlist rather than a denylist. A new sub-route has to
 * opt in on purpose instead of inheriting a control nobody decided it should
 * have, and forgetting to add a route costs a missing lens — visible and easily
 * fixed — where forgetting to exclude one costs a lens that appears to govern a
 * page it does not, which a reader has no way to detect.
 */
export const PERIOD_SCOPED_ROUTES = [
  "/app", // Overview
  "/app/journal", // Trades
  "/app/analytics",
  "/app/reviews", // Patterns; the weekly and daily views keep their own controls
];

/**
 * Whether this route is governed by the global analysis range.
 *
 * Routes whose temporal semantics differ are absent by design: a trade detail
 * page describes one trade, New Trade describes the trade being logged, Weekly
 * Recap keeps its week selector, Daily Debrief its day selector, and Strategy
 * Profile and Settings are not time-scoped at all.
 *
 * The lens is hidden where this returns false rather than shown inertly. A
 * control that appears to govern a page but does not is worse than no control:
 * the reader cannot tell that the numbers in front of them ignore it.
 */
export function routeUsesPeriod(pathname: string): boolean {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return PERIOD_SCOPED_ROUTES.includes(path);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/period-lens.test.ts`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
cd web && npx tsc --noEmit && npx eslint . && cd ..
git add web/lib/app/period.ts web/__tests__/period-lens.test.ts
git commit -m "feat(app): the period lens contract

No number in a post-trade journal means anything without its window and
sample size, so the period is chrome rather than a control each page
re-invents. It lives in the URL, which makes it linkable and shared
between pages without a client store.

Bad input falls back to the default and a reversed range is swapped:
this value comes from a URL, so it is typo- and attacker-reachable, and
a window nothing can render is worse than one the reader did not ask
for. Later phases read this; no page adds a second date control."
```

---

### Task 5: Authenticated layout and the shell frame

**Files:**
- Create: `web/app/app/layout.tsx`, `web/components/app/app-shell.tsx`, `web/components/app/skip-link.tsx`
- Create: `web/app/app/page.tsx` (Overview placeholder, so the route resolves)
- Test: `web/__tests__/app-shell.test.tsx`

**Interfaces:**
- Consumes: `APP_DESTINATIONS` (Task 3)
- Produces: `<AppShell sidebar top drawer bottomNav>{children}</AppShell>`; `<SkipLink />`; the `#main-content` landmark id

- [ ] **Step 1: Write the failing test**

```tsx
// web/__tests__/app-shell.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/app/app-shell";

function renderShell() {
  return render(
    <AppShell
      sidebar={<nav aria-label="Sections">sidebar</nav>}
      top={<div>top</div>}
      drawer={<div>drawer</div>}
      bottomNav={<nav aria-label="Primary">bottom</nav>}
    >
      <h1>Overview</h1>
    </AppShell>,
  );
}

describe("app shell", () => {
  it("renders one main landmark for the page content", () => {
    renderShell();
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });

  it("gives main the id the skip link targets", () => {
    renderShell();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("makes main focusable so the skip link can land on it", () => {
    // Without tabindex the browser moves the URL fragment but leaves focus
    // where it was, so the next Tab returns to the navigation the user was
    // trying to skip.
    renderShell();
    expect(screen.getByRole("main")).toHaveAttribute("tabindex", "-1");
  });

  it("renders each region it is given", () => {
    renderShell();
    expect(screen.getByText("sidebar")).toBeInTheDocument();
    expect(screen.getByText("top")).toBeInTheDocument();
    expect(screen.getByText("drawer")).toBeInTheDocument();
    expect(screen.getByText("bottom")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
  });

  it("puts the skip link first in the tab order", () => {
    const { container } = renderShell();
    const focusable = container.querySelectorAll("a, button, [tabindex]:not([tabindex='-1'])");
    expect(focusable[0]).toHaveTextContent("Skip to main content");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/app-shell.test.tsx`
Expected: FAIL — cannot resolve `@/components/app/app-shell`.

- [ ] **Step 3: Write the skip link**

```tsx
// web/components/app/skip-link.tsx
/**
 * First thing in the tab order, invisible until focused.
 *
 * Without it a keyboard user tabs through every destination before reaching
 * the page on every navigation.
 */
export function SkipLink() {
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface-2 focus:px-4 focus:py-2 focus:text-sm focus:text-text"
    >
      Skip to main content
    </a>
  );
}
```

- [ ] **Step 4: Write the shell**

```tsx
// web/components/app/app-shell.tsx
import type { ReactNode } from "react";

import { SkipLink } from "@/components/app/skip-link";

/**
 * The frame every authenticated screen renders inside.
 *
 * It takes its regions as props rather than importing them, so it stays a
 * layout with no opinion about navigation, and so a test can render it without
 * a router.
 *
 * The sidebar is hidden below `lg` and the bottom bar above it — one of the two
 * is always present, never both, so there is a single navigation in the
 * accessibility tree at any width.
 */
export function AppShell({
  sidebar,
  top,
  drawer,
  bottomNav,
  children,
}: {
  sidebar: ReactNode;
  top: ReactNode;
  drawer: ReactNode;
  bottomNav: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-bg text-text">
      <SkipLink />
      <div className="lg:grid lg:grid-cols-[16rem_1fr]">
        <div className="hidden lg:block">{sidebar}</div>
        <div className="flex min-h-dvh flex-col">
          {top}
          {/*
            tabIndex -1 so the skip link actually moves focus here. Without it
            the fragment scrolls but focus stays put, and the next Tab walks
            back into the navigation the user just skipped.
            pb-20 on phones clears the fixed bottom bar.
          */}
          <main
            id="main-content"
            tabIndex={-1}
            className="flex-1 px-4 pb-20 pt-6 focus:outline-none sm:px-6 lg:px-8 lg:pb-10"
          >
            {children}
          </main>
        </div>
      </div>
      {drawer}
      <div className="lg:hidden">{bottomNav}</div>
    </div>
  );
}
```

- [ ] **Step 5: Write the layout and the Overview placeholder**

```tsx
// web/app/app/layout.tsx
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app/app-shell";
import { Sidebar } from "@/components/app/sidebar";
import { TopBar } from "@/components/app/top-bar";
import { BottomNav } from "@/components/app/bottom-nav";
import { PartnerDrawer } from "@/components/app/partner-drawer";
import {
  authenticateSessionToken,
  emailGatePassed,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";

// The shell reflects one account's session, so it must never be cached.
export const dynamic = "force-dynamic";

/**
 * The authenticated frame.
 *
 * Authorisation happens here, server-side, before any child renders — the same
 * gate the continuation page applies, so a deep link into /app cannot bypass
 * what /continue enforces.
 *
 * No API call is made. Phase 1 has no data to fetch, so the FastAPI boundary is
 * not touched: identity comes from the session the website already validated.
 */
export default async function AppLayout({ children }: { children: ReactNode }) {
  const cookieHeader = (await headers()).get("cookie") ?? "";
  const user = await authenticateSessionToken(sessionTokenFromCookieHeader(cookieHeader));

  if (!user) redirect("/login");
  if (!emailGatePassed(user)) redirect("/verify-email");
  if (!user.onboardingCompleted) redirect("/onboarding");

  return (
    <AppShell
      sidebar={<Sidebar />}
      top={<TopBar />}
      drawer={<PartnerDrawer />}
      bottomNav={<BottomNav />}
    >
      {children}
    </AppShell>
  );
}
```

```tsx
// web/app/app/page.tsx
export default function OverviewPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Overview</h1>
      <p className="mt-2 text-muted">Where the week stands, and what deserves review next.</p>
    </div>
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/app-shell.test.tsx`
Expected: PASS (5 tests). The layout's imports of Sidebar, TopBar, BottomNav and PartnerDrawer do not exist yet — that is expected, and Tasks 6-9 create them. Do NOT run `npm run build` in this task; it will fail until Task 9 lands.

- [ ] **Step 7: Commit**

```bash
git add web/app/app web/components/app/app-shell.tsx web/components/app/skip-link.tsx web/__tests__/app-shell.test.tsx
git commit -m "feat(app): authenticated layout and shell frame

The gate runs server-side in the layout, applying the same email and
onboarding checks as the continuation page, so a deep link into /app
cannot bypass what /continue enforces. No API call: Phase 1 has no data
to fetch, so the FastAPI boundary stays untouched.

main carries tabindex -1 because a skip link without it moves the URL
fragment and leaves focus behind, sending the next Tab back into the
navigation the user was trying to skip."
```

---

### Task 6: Sidebar

**Files:**
- Create: `web/components/app/sidebar.tsx`
- Test: `web/__tests__/sidebar.test.tsx`

**Interfaces:**
- Consumes: `APP_DESTINATIONS`, `PRIMARY_ACTION`, `isActiveDestination` (Task 3)
- Produces: `<Sidebar />`

- [ ] **Step 1: Write the failing test**

```tsx
// web/__tests__/sidebar.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockPathname = vi.fn(() => "/app");
vi.mock("next/navigation", () => ({ usePathname: () => mockPathname() }));

import { Sidebar } from "@/components/app/sidebar";
import { APP_DESTINATIONS } from "@/lib/app/navigation";

describe("sidebar", () => {
  it("links to every destination", () => {
    mockPathname.mockReturnValue("/app");
    render(<Sidebar />);
    for (const d of APP_DESTINATIONS) {
      expect(screen.getByRole("link", { name: d.label })).toHaveAttribute("href", d.href);
    }
  });

  it("offers logging a trade as the primary action", () => {
    mockPathname.mockReturnValue("/app");
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Log completed trade" })).toHaveAttribute(
      "href",
      "/app/trades/new",
    );
  });

  it("marks the current destination for assistive technology, not just visually", () => {
    mockPathname.mockReturnValue("/app/journal");
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Journal" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("marks exactly one destination current", () => {
    mockPathname.mockReturnValue("/app/journal/42");
    render(<Sidebar />);
    const current = screen
      .getAllByRole("link")
      .filter((el) => el.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName("Journal");
  });

  it("names the navigation so a screen reader can distinguish it", () => {
    mockPathname.mockReturnValue("/app");
    render(<Sidebar />);
    expect(screen.getByRole("navigation", { name: "Sections" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/sidebar.test.tsx`
Expected: FAIL — cannot resolve `@/components/app/sidebar`.

- [ ] **Step 3: Write the sidebar**

```tsx
// web/components/app/sidebar.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LineChart } from "lucide-react";

import {
  APP_DESTINATIONS,
  PRIMARY_ACTION,
  isActiveDestination,
} from "@/lib/app/navigation";

/**
 * The desktop rail.
 *
 * A client component only because it reads the current path to mark the active
 * destination. Everything it renders is static.
 *
 * The active state is an edge bar plus a surface change, and `aria-current`
 * carries the same fact to assistive technology — a colour difference alone
 * tells a screen reader nothing.
 */
export function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="sticky top-0 flex h-dvh flex-col border-r border-line bg-surface">
      <div className="px-5 py-6">
        <Link href="/app" className="flex items-center gap-2.5">
          <LineChart className="h-5 w-5 text-accent" aria-hidden="true" />
          <span className="font-display text-base font-bold tracking-tight">TradeLens AI</span>
        </Link>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          Post-trade journal
        </p>
      </div>

      <div className="px-3 pb-4">
        <Link
          href={PRIMARY_ACTION.href}
          className="flex w-full items-center justify-center rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90"
        >
          {PRIMARY_ACTION.label}
        </Link>
      </div>

      <nav aria-label="Sections" className="flex-1 px-3">
        <ul className="space-y-0.5">
          {APP_DESTINATIONS.map((destination) => {
            const active = isActiveDestination(pathname, destination.href);
            const Icon = destination.icon;
            return (
              <li key={destination.href}>
                <Link
                  href={destination.href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150 ease-tl",
                    active
                      ? "bg-surface-2 font-medium text-text"
                      : "text-muted hover:bg-surface-2/60 hover:text-text",
                  ].join(" ")}
                >
                  {active && (
                    <span
                      aria-hidden="true"
                      className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-accent"
                    />
                  )}
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {destination.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/sidebar.test.tsx`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
cd web && npx tsc --noEmit && npx eslint . && cd ..
git add web/components/app/sidebar.tsx web/__tests__/sidebar.test.tsx
git commit -m "feat(app): desktop sidebar

Active state is an edge bar plus a surface change, and aria-current
carries the same fact to assistive technology — a colour difference
alone tells a screen reader nothing. Logging a trade sits above the
list, because it is the one thing a trader comes here to do that is not
reading."
```

---

### Task 7: Top bar and the period lens

**Files:**
- Create: `web/components/app/top-bar.tsx`, `web/components/app/period-lens.tsx`
- Test: `web/__tests__/period-lens-control.test.tsx`

**Interfaces:**
- Consumes: `periodFromParams`, `periodToParams`, `formatPeriod`, `PERIOD_PRESETS` (Task 4)
- Produces: `<TopBar />`, `<PeriodLens />`

- [ ] **Step 1: Write the failing test**

```tsx
// web/__tests__/period-lens-control.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const searchParams = new URLSearchParams("from=2026-08-12&to=2026-08-18");
const mockPathname = vi.fn(() => "/app/journal");
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => mockPathname(),
  useSearchParams: () => searchParams,
}));

import { PeriodLens } from "@/components/app/period-lens";

describe("period lens", () => {
  it("shows the window every figure on the page is measured over", () => {
    render(<PeriodLens />);
    expect(screen.getByText("2026-08-12 → 2026-08-18")).toBeInTheDocument();
  });

  it("says what it is, so the range is not a bare pair of dates", () => {
    render(<PeriodLens />);
    expect(screen.getByRole("button", { name: /period/i })).toBeInTheDocument();
  });

  it("keeps the menu closed until asked", () => {
    render(<PeriodLens />);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("opens a menu of the windows a trader reviews in", () => {
    render(<PeriodLens />);
    fireEvent.click(screen.getByRole("button", { name: /period/i }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Last 7 days" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Year to date" })).toBeInTheDocument();
  });

  it("writes the choice to the URL, so the period is linkable and shared", () => {
    render(<PeriodLens />);
    fireEvent.click(screen.getByRole("button", { name: /period/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Last 7 days" }));
    expect(replace).toHaveBeenCalled();
    const target = replace.mock.calls.at(-1)![0] as string;
    expect(target.startsWith("/app/journal?")).toBe(true);
    expect(target).toContain("from=");
    expect(target).toContain("to=");
  });

  it("reports expanded state to assistive technology", () => {
    render(<PeriodLens />);
    const trigger = screen.getByRole("button", { name: /period/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("closes on Escape", () => {
    render(<PeriodLens />);
    fireEvent.click(screen.getByRole("button", { name: /period/i }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

describe("routes the range does not govern", () => {
  it.each([
    ["a single trade", "/app/journal/42"],
    ["New Trade", "/app/trades/new"],
    ["Weekly Recap, which keeps its week selector", "/app/reviews/weekly"],
    ["Daily Debrief, which keeps its day selector", "/app/reviews/daily"],
    ["Strategy Profile", "/app/strategy"],
    ["Settings", "/app/settings"],
  ])("renders nothing on %s", (_name, pathname) => {
    // Hidden, not inert. A lens shown beside a week selector claims to govern a
    // page it does not, and the reader has no way to tell which one won.
    mockPathname.mockReturnValue(pathname);
    const { container } = render(<PeriodLens />);
    expect(container).toBeEmptyDOMElement();
  });

  it("comes back on a surface it does govern", () => {
    mockPathname.mockReturnValue("/app/analytics");
    render(<PeriodLens />);
    expect(screen.getByRole("button", { name: /period/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/period-lens-control.test.tsx`
Expected: FAIL — cannot resolve `@/components/app/period-lens`.

- [ ] **Step 3: Write the lens**

```tsx
// web/components/app/period-lens.tsx
"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CalendarRange, ChevronDown } from "lucide-react";

import {
  PERIOD_PRESETS,
  formatPeriod,
  periodFromParams,
  periodToParams,
  routeUsesPeriod,
} from "@/lib/app/period";

/**
 * The signature control: the window under examination, always visible.
 *
 * It is chrome rather than a page filter on purpose. A win rate over four days
 * and a win rate over four months are different claims, and a control that
 * lives inside one page lets a reader carry the wrong assumption to the next
 * one. Later phases read this from the URL instead of adding their own.
 *
 * `router.replace` rather than `push`: changing the window is refining one
 * question, not navigating, and it should not fill the back button with
 * near-identical entries.
 */
export function PeriodLens() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [open, setOpen] = useState(false);

  const period = periodFromParams(new URLSearchParams(searchParams.toString()));

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  function choose(presetId: string) {
    const today = new Date();
    const params = new URLSearchParams(searchParams.toString());
    const next = periodFromParams(
      // Round-trip through the contract so the control cannot invent a range
      // shape the readers do not expect.
      presetRange(presetId, today),
      today,
    );
    for (const [key, value] of periodToParams(next)) params.set(key, value);
    setOpen(false);
    router.replace(`${pathname}?${params.toString()}`);
  }

  // After the hooks, never before: a conditional return above them would change
  // the hook order between routes. The lens is absent on routes the range does
  // not govern rather than disabled, because a control that looks like it
  // governs a page but does not is worse than no control at all.
  if (!routeUsesPeriod(pathname)) return null;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-left transition-colors duration-150 ease-tl hover:border-line-strong"
      >
        <CalendarRange className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
        <span className="sr-only">Period under review</span>
        <span className="font-mono text-xs text-text">{formatPeriod(period)}</span>
        <ChevronDown className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Period presets"
          className="absolute right-0 z-30 mt-1.5 w-48 rounded-lg border border-line bg-surface-2 py-1 shadow-xl"
        >
          {PERIOD_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              role="menuitem"
              onClick={() => choose(preset.id)}
              className={[
                "flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors duration-150 ease-tl hover:bg-surface-3",
                period.presetId === preset.id ? "text-accent" : "text-text",
              ].join(" ")}
            >
              {preset.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Build the search params a preset corresponds to, for the contract to parse. */
function presetRange(presetId: string, today: Date): URLSearchParams {
  const params = new URLSearchParams();
  if (presetId === "ytd") {
    params.set("from", `${today.getUTCFullYear()}-01-01`);
    params.set("to", today.toISOString().slice(0, 10));
    return params;
  }
  const preset = PERIOD_PRESETS.find((p) => p.id === presetId) ?? PERIOD_PRESETS[1];
  const start = new Date(today);
  start.setUTCDate(start.getUTCDate() - (preset.days - 1));
  params.set("from", start.toISOString().slice(0, 10));
  params.set("to", today.toISOString().slice(0, 10));
  return params;
}
```

- [ ] **Step 4: Write the top bar**

```tsx
// web/components/app/top-bar.tsx
import { Suspense } from "react";

import { PeriodLens } from "@/components/app/period-lens";
import { PartnerLauncher } from "@/components/app/partner-drawer";

/**
 * The top bar carries two things and refuses the rest: the window under review,
 * and the way into the AI partner. Page titles live in the page, where the
 * content that explains them lives.
 *
 * The lens is wrapped in Suspense because it reads search params, which opts
 * its subtree into client-side rendering; without the boundary that would opt
 * the whole route out of static rendering.
 */
export function TopBar() {
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-end gap-3 border-b border-line bg-bg/80 px-4 backdrop-blur sm:px-6 lg:px-8">
      <Suspense fallback={<div className="h-7 w-52 rounded-md bg-surface" />}>
        <PeriodLens />
      </Suspense>
      <PartnerLauncher />
    </header>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/period-lens-control.test.tsx`
Expected: PASS (14 tests). The `PartnerLauncher` import does not exist until Task 9.

- [ ] **Step 6: Commit**

```bash
git add web/components/app/top-bar.tsx web/components/app/period-lens.tsx web/__tests__/period-lens-control.test.tsx
git commit -m "feat(app): top bar and the period lens

The window under review is permanent chrome. A win rate over four days
and one over four months are different claims, and a date control that
lives inside a page lets a reader carry the wrong assumption to the next
one. It writes to the URL, so a period is linkable and shared without a
client store, using replace rather than push because refining a window
is not navigation and should not fill the back button."
```

---

### Task 8: Phone navigation

**Files:**
- Create: `web/components/app/bottom-nav.tsx`, `web/components/app/more-sheet.tsx`
- Test: `web/__tests__/bottom-nav.test.tsx`

**Interfaces:**
- Consumes: `APP_DESTINATIONS`, `isActiveDestination` (Task 3)
- Produces: `<BottomNav />`, `<MoreSheet open onClose />`

- [ ] **Step 1: Write the failing test**

```tsx
// web/__tests__/bottom-nav.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockPathname = vi.fn(() => "/app");
vi.mock("next/navigation", () => ({ usePathname: () => mockPathname() }));

import { BottomNav } from "@/components/app/bottom-nav";

describe("phone navigation", () => {
  it("shows the four priority destinations plus More", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Journal" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI Reviews" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More" })).toBeInTheDocument();
  });

  it("keeps the lower-frequency destinations out of the bar", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    expect(screen.queryByRole("link", { name: "Analytics" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Strategy Profile" })).not.toBeInTheDocument();
  });

  it("reveals them behind More", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getByRole("link", { name: "Analytics" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Strategy Profile" })).toBeInTheDocument();
  });

  it("closes the sheet on Escape", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("link", { name: "Analytics" })).not.toBeInTheDocument();
  });

  it("marks the current destination", () => {
    mockPathname.mockReturnValue("/app/journal");
    render(<BottomNav />);
    expect(screen.getByRole("link", { name: "Journal" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("names itself so it does not collide with the sidebar in the a11y tree", () => {
    mockPathname.mockReturnValue("/app");
    render(<BottomNav />);
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/bottom-nav.test.tsx`
Expected: FAIL — cannot resolve `@/components/app/bottom-nav`.

- [ ] **Step 3: Write the More sheet**

```tsx
// web/components/app/more-sheet.tsx
"use client";

import { useEffect } from "react";
import Link from "next/link";

import { APP_DESTINATIONS, PRIMARY_ACTION } from "@/lib/app/navigation";

/**
 * Phone overflow.
 *
 * Holds the destinations a trader reaches occasionally — reading analytics or
 * editing a strategy is desk work — plus logging a trade, which has no room in
 * a five-slot bar but is the reason the app exists.
 */
export function MoreSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const overflow = APP_DESTINATIONS.filter((d) => !d.phonePriority);

  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <button
        type="button"
        aria-label="Close menu"
        onClick={onClose}
        className="absolute inset-0 bg-bg/70 backdrop-blur-sm"
      />
      <div className="absolute inset-x-0 bottom-0 rounded-t-2xl border-t border-line bg-surface p-4 pb-8">
        <ul className="space-y-1">
          {overflow.map((destination) => {
            const Icon = destination.icon;
            return (
              <li key={destination.href}>
                <Link
                  href={destination.href}
                  onClick={onClose}
                  className="flex items-center gap-3 rounded-lg px-3 py-3 text-sm text-text hover:bg-surface-2"
                >
                  <Icon className="h-4 w-4 text-muted" aria-hidden="true" />
                  {destination.label}
                </Link>
              </li>
            );
          })}
          <li className="pt-2">
            <Link
              href={PRIMARY_ACTION.href}
              onClick={onClose}
              className="flex items-center justify-center rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-bg"
            >
              {PRIMARY_ACTION.label}
            </Link>
          </li>
        </ul>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write the bottom bar**

```tsx
// web/components/app/bottom-nav.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MoreHorizontal } from "lucide-react";

import { APP_DESTINATIONS, isActiveDestination } from "@/lib/app/navigation";
import { MoreSheet } from "@/components/app/more-sheet";

/**
 * Phone navigation.
 *
 * Four destinations and More. Five slots is the most that leaves a 44px target
 * at 375px, and a sixth would make every one of them harder to hit rather than
 * making the app feel more complete.
 */
export function BottomNav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const primary = APP_DESTINATIONS.filter((d) => d.phonePriority);

  return (
    <>
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur"
      >
        <ul className="grid grid-cols-5">
          {primary.map((destination) => {
            const active = isActiveDestination(pathname, destination.href);
            const Icon = destination.icon;
            return (
              <li key={destination.href}>
                <Link
                  href={destination.href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "flex min-h-[3.25rem] flex-col items-center justify-center gap-1 px-1 py-2 text-[10px]",
                    active ? "text-accent" : "text-muted",
                  ].join(" ")}
                >
                  <Icon className="h-5 w-5" aria-hidden="true" />
                  {destination.label}
                </Link>
              </li>
            );
          })}
          <li>
            <button
              type="button"
              onClick={() => setMoreOpen(true)}
              className="flex min-h-[3.25rem] w-full flex-col items-center justify-center gap-1 px-1 py-2 text-[10px] text-muted"
            >
              <MoreHorizontal className="h-5 w-5" aria-hidden="true" />
              More
            </button>
          </li>
        </ul>
      </nav>
      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} />
    </>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/bottom-nav.test.tsx`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
cd web && npx tsc --noEmit && npx eslint . && cd ..
git add web/components/app/bottom-nav.tsx web/components/app/more-sheet.tsx web/__tests__/bottom-nav.test.tsx
git commit -m "feat(app): phone navigation

Four destinations and More. Five slots is the most that leaves a 44px
target at 375px; a sixth would make every one harder to hit rather than
making the app feel more complete. Analytics and Strategy go behind More
because reading analytics and editing a strategy are desk work, while
logging a trade joins them there since it has no room in the bar and is
the reason the app exists."
```

---

### Task 9: AI Partner drawer shell

**Files:**
- Create: `web/components/app/partner-drawer.tsx`
- Test: `web/__tests__/partner-drawer.test.tsx`

**Interfaces:**
- Consumes: nothing
- Produces: `<PartnerDrawer />`, `<PartnerLauncher />`

- [ ] **Step 1: Write the failing test**

```tsx
// web/__tests__/partner-drawer.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PartnerDrawer, PartnerLauncher } from "@/components/app/partner-drawer";

function renderBoth() {
  return render(
    <>
      <PartnerLauncher />
      <PartnerDrawer />
    </>,
  );
}

describe("partner drawer", () => {
  it("stays closed until asked", () => {
    renderBoth();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens from the launcher", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("is a named dialog, so a screen reader announces what opened", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByRole("dialog")).toHaveAccessibleName(/ai partner/i);
  });

  it("is modal, so the page behind it is not reachable", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });

  it("closes on Escape", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes from its own control", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("says it reviews trades that already happened", () => {
    // The identity rule is not decoration: this surface must never read as a
    // place to ask what to trade next.
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.getByText(/already logged/i)).toBeInTheDocument();
  });

  it("carries no conversation yet", () => {
    renderBoth();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/partner-drawer.test.tsx`
Expected: FAIL — cannot resolve `@/components/app/partner-drawer`.

- [ ] **Step 3: Write the drawer**

```tsx
// web/components/app/partner-drawer.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { MessageSquareText, X } from "lucide-react";

/**
 * The AI partner drawer — frame only.
 *
 * Phase 1 ships the shell: how it opens, how it traps focus, how it closes, and
 * what it says it is for. The conversation itself arrives with the phase that
 * has something to talk about.
 *
 * Open state lives in a module-level store rather than a context because the
 * launcher sits in the top bar and the drawer is mounted by the layout, and
 * threading a provider between them buys nothing at this size.
 */
let listeners: Array<(open: boolean) => void> = [];
let isOpen = false;

function setOpen(next: boolean) {
  isOpen = next;
  for (const listener of listeners) listener(next);
}

function useDrawerOpen() {
  const [open, setLocal] = useState(isOpen);
  useEffect(() => {
    listeners.push(setLocal);
    return () => {
      listeners = listeners.filter((l) => l !== setLocal);
    };
  }, []);
  return open;
}

export function PartnerLauncher() {
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-xs text-muted transition-colors duration-150 ease-tl hover:border-line-strong hover:text-text"
    >
      <MessageSquareText className="h-3.5 w-3.5" aria-hidden="true" />
      Ask about a trade
    </button>
  );
}

export function PartnerDrawer() {
  const open = useDrawerOpen();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;

      // Focus stays inside a modal surface. Without this, Tab walks into the
      // page behind the overlay, which a sighted user cannot see and a screen
      // reader user cannot escape from.
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40">
      <button
        type="button"
        aria-label="Close AI Partner"
        onClick={() => setOpen(false)}
        className="absolute inset-0 bg-bg/70 backdrop-blur-sm"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="AI Partner"
        className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-line bg-surface"
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h2 className="font-display text-sm font-semibold">AI Partner</h2>
            <p className="mt-0.5 text-xs text-muted">
              Ask about trades you have already logged.
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close AI Partner"
            className="rounded-md p-1.5 text-muted transition-colors duration-150 ease-tl hover:bg-surface-2 hover:text-text"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="flex flex-1 items-center justify-center px-6 text-center">
          <p className="max-w-xs text-sm text-muted">
            The partner reads your journal and answers questions about what already
            happened. It arrives with the review features.
          </p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/partner-drawer.test.tsx`
Expected: PASS (8 tests)

- [ ] **Step 5: Verify the whole app now builds**

Every import the layout needs now exists.

Run: `cd web && npm run build`
Expected: build succeeds (Turbopack). If a route fails to prerender because it reads search params, confirm the Suspense boundary from Task 7 is in place.

- [ ] **Step 6: Commit**

```bash
cd web && npx tsc --noEmit && npx eslint . && cd ..
git add web/components/app/partner-drawer.tsx web/__tests__/partner-drawer.test.tsx
git commit -m "feat(app): AI Partner drawer shell

Frame only: how it opens, traps focus, closes, and what it says it is
for. Tab is confined to the panel, because without that it walks into
the page behind the overlay — which a sighted user cannot see and a
screen reader user cannot get out of.

The copy says the partner answers questions about trades already
logged. This surface must never read as a place to ask what to trade
next."
```

---

### Task 10: Loading, empty and error primitives

**Files:**
- Create: `web/components/app/states/loading-state.tsx`, `empty-state.tsx`, `error-state.tsx`
- Test: `web/__tests__/state-primitives.test.tsx`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `<Skeleton className? />`, `<LoadingState label />`
  - `<EmptyState title description action? />` where `action?: { href: string; label: string }`
  - `<ErrorState title? description retry? />` where `retry?: { onRetry: () => void; label?: string }`

- [ ] **Step 1: Write the failing test**

```tsx
// web/__tests__/state-primitives.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LoadingState, Skeleton } from "@/components/app/states/loading-state";
import { EmptyState } from "@/components/app/states/empty-state";
import { ErrorState } from "@/components/app/states/error-state";

describe("loading", () => {
  it("announces itself rather than showing a silent grey box", () => {
    render(<LoadingState label="Loading your trades" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your trades");
  });

  it("hides decorative skeletons from assistive technology", () => {
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });
});

describe("empty", () => {
  it("says what the screen is for and offers the action that fills it", () => {
    render(
      <EmptyState
        title="No trades in this period"
        description="Widen the period, or log a completed trade."
        action={{ href: "/app/trades/new", label: "Log completed trade" }}
      />,
    );
    expect(screen.getByRole("heading", { name: "No trades in this period" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log completed trade" })).toHaveAttribute(
      "href",
      "/app/trades/new",
    );
  });

  it("works without an action", () => {
    render(<EmptyState title="Nothing here yet" description="It will fill as you log trades." />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("error", () => {
  it("is announced assertively, because it interrupts what the reader wanted", () => {
    render(<ErrorState description="That period could not be loaded." />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("offers a way out", () => {
    const onRetry = vi.fn();
    render(<ErrorState description="That period could not be loaded." retry={{ onRetry }} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("does not apologise or blame the reader", () => {
    render(<ErrorState description="That period could not be loaded." />);
    const text = screen.getByRole("alert").textContent ?? "";
    expect(text.toLowerCase()).not.toMatch(/sorry|oops|whoops/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/state-primitives.test.tsx`
Expected: FAIL — cannot resolve the state modules.

- [ ] **Step 3: Write the primitives**

```tsx
// web/components/app/states/loading-state.tsx
/**
 * A skeleton is decoration: it stands in for content that is not there yet, and
 * a screen reader gains nothing from being told about the shape of an absence.
 * The status message is what carries the information.
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-md bg-surface-2 ${className}`}
    />
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-3 py-8 text-sm text-muted">
      <span
        aria-hidden="true"
        className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line-strong border-t-accent"
      />
      {label}
    </div>
  );
}
```

```tsx
// web/components/app/states/empty-state.tsx
import Link from "next/link";

/**
 * An empty screen is an invitation to act, not a shrug.
 *
 * It names what is missing and offers the one action that fills it. Anything
 * more turns a dead end into a menu.
 */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: { href: string; label: string };
}) {
  return (
    <div className="rounded-xl border border-line bg-surface px-6 py-12 text-center">
      <h2 className="font-display text-base font-semibold text-text">{title}</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted">{description}</p>
      {action && (
        <Link
          href={action.href}
          className="mt-5 inline-flex items-center rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90"
        >
          {action.label}
        </Link>
      )}
    </div>
  );
}
```

```tsx
// web/components/app/states/error-state.tsx
"use client";

import { AlertTriangle } from "lucide-react";

/**
 * Errors say what happened and how to get out of it.
 *
 * They do not apologise, and they are never vague: "Sorry, something went
 * wrong" tells a trader nothing they can act on, and spends the interface's
 * credibility on politeness.
 */
export function ErrorState({
  title = "That did not load",
  description,
  retry,
}: {
  title?: string;
  description: string;
  retry?: { onRetry: () => void; label?: string };
}) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-negative/30 bg-negative/5 px-6 py-8 text-center"
    >
      <AlertTriangle className="mx-auto h-5 w-5 text-negative" aria-hidden="true" />
      <h2 className="mt-3 font-display text-base font-semibold text-text">{title}</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted">{description}</p>
      {retry && (
        <button
          type="button"
          onClick={retry.onRetry}
          className="mt-5 inline-flex items-center rounded-lg border border-line-strong px-4 py-2 text-sm font-medium text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
        >
          {retry.label ?? "Try again"}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/state-primitives.test.tsx`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd web && npx tsc --noEmit && npx eslint . && cd ..
git add web/components/app/states web/__tests__/state-primitives.test.tsx
git commit -m "feat(app): loading, empty and error primitives

Skeletons are aria-hidden because a screen reader gains nothing from the
shape of an absence; the status message carries the information. Empty
states name what is missing and offer the one action that fills it.
Errors say what happened and how to get out, and do not apologise —
'something went wrong' spends the interface's credibility on politeness
and tells a trader nothing they can act on."
```

---

### Task 11: Route placeholders

**Files:**
- Create: `web/app/app/journal/page.tsx`, `analytics/page.tsx`, `reviews/page.tsx`, `strategy/page.tsx`, `settings/page.tsx`, `trades/new/page.tsx`
- Test: `web/__tests__/app-routes.test.tsx`

**Interfaces:**
- Consumes: `APP_DESTINATIONS`, `PRIMARY_ACTION` (Task 3); `EmptyState` (Task 10)
- Produces: a rendering route for every navigation target

- [ ] **Step 1: Write the failing test**

```tsx
// web/__tests__/app-routes.test.tsx
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { APP_DESTINATIONS, PRIMARY_ACTION } from "@/lib/app/navigation";

const APP_DIR = path.join(__dirname, "..", "app");

function pageFileFor(href: string): string {
  const segments = href.replace(/^\/app\/?/, "");
  return path.join(APP_DIR, "app", segments, "page.tsx");
}

describe("every navigation target resolves to a route", () => {
  it.each(APP_DESTINATIONS.map((d) => [d.label, d.href]))(
    "%s has a page at %s",
    (_label, href) => {
      expect(fs.existsSync(pageFileFor(href))).toBe(true);
    },
  );

  it("the primary action has a page", () => {
    expect(fs.existsSync(pageFileFor(PRIMARY_ACTION.href))).toBe(true);
  });

  it("no destination links somewhere that does not exist", () => {
    // A nav entry pointing at a 404 is worse than a missing entry: it looks
    // like the product is broken rather than incomplete.
    const missing = APP_DESTINATIONS.filter((d) => !fs.existsSync(pageFileFor(d.href)));
    expect(missing.map((d) => d.href)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run __tests__/app-routes.test.tsx`
Expected: FAIL — only `/app` has a page.

- [ ] **Step 3: Write the placeholders**

Each file states what the section will hold, so the shell can be navigated and reviewed without pretending to have data. Create each with this shape, substituting the values from the table below:

```tsx
// web/app/app/journal/page.tsx
import { EmptyState } from "@/components/app/states/empty-state";

export default function JournalPage() {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Journal</h1>
      <p className="mt-2 text-muted">Find a trade, work a month, or read one closely.</p>
      <div className="mt-8">
        <EmptyState
          title="The journal arrives next"
          description="Trades, the calendar and trade detail move here in the phase after this one."
        />
      </div>
    </div>
  );
}
```

| File | Component | `h1` | Subtitle | Empty title | Empty description |
|---|---|---|---|---|---|
| `journal/page.tsx` | `JournalPage` | Journal | Find a trade, work a month, or read one closely. | The journal arrives next | Trades, the calendar and trade detail move here in the phase after this one. |
| `analytics/page.tsx` | `AnalyticsPage` | Analytics | One question at a time, with the evidence behind the answer. | Analytics is not migrated yet | The four lenses and their charts move here once the journal is in place. |
| `reviews/page.tsx` | `ReviewsPage` | AI Reviews | Evidence-backed reading of your own journal. | Reviews are not migrated yet | Patterns, the weekly recap and the daily debrief move here after the journal. |
| `strategy/page.tsx` | `StrategyPage` | Strategy Profile | Your own rules, written down. | The profile is not migrated yet | Your markets, setups and risk rules move here in a later phase. |
| `settings/page.tsx` | `SettingsPage` | Settings | Your account, your data, and how the app reads it. | Settings are not migrated yet | Recovery email, timezone, import and export move here in a later phase. |
| `trades/new/page.tsx` | `NewTradePage` | Log completed trade | Five steps. Your draft is kept as you move between them. | The form is not migrated yet | Screenshot upload, AI autofill and the review step move here in a later phase. |

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run __tests__/app-routes.test.tsx`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
cd web && npm run build && npx eslint . && cd ..
git add web/app/app web/__tests__/app-routes.test.tsx
git commit -m "feat(app): route placeholders for every destination

Each section says what it will hold rather than pretending to have data,
so the shell can be navigated and reviewed on its own. A test asserts
every navigation entry resolves to a real page: an entry pointing at a
404 makes the product look broken rather than incomplete."
```

---

### Task 12: Keyboard and focus model

**Files:**
- Test: `web/__tests__/shell-accessibility.test.tsx`
- Modify: whichever component a failing assertion exposes

**Interfaces:**
- Consumes: every component built so far
- Produces: no new exports; a proof that the shell is operable by keyboard

- [ ] **Step 1: Write the test**

```tsx
// web/__tests__/shell-accessibility.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockPathname = vi.fn(() => "/app");
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname(),
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { AppShell } from "@/components/app/app-shell";
import { Sidebar } from "@/components/app/sidebar";
import { BottomNav } from "@/components/app/bottom-nav";
import { PartnerDrawer, PartnerLauncher } from "@/components/app/partner-drawer";

function renderShell() {
  return render(
    <AppShell
      sidebar={<Sidebar />}
      top={<PartnerLauncher />}
      drawer={<PartnerDrawer />}
      bottomNav={<BottomNav />}
    >
      <h1>Overview</h1>
    </AppShell>,
  );
}

describe("landmarks", () => {
  it("names both navigations distinctly", () => {
    // Two unnamed <nav>s are indistinguishable in a screen reader's landmark
    // list, which is how a user ends up in the phone bar looking for the rail.
    renderShell();
    expect(screen.getByRole("navigation", { name: "Sections" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("has exactly one main landmark", () => {
    renderShell();
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });
});

describe("keyboard operation", () => {
  it("reaches the skip link first", () => {
    const { container } = renderShell();
    const focusable = container.querySelectorAll<HTMLElement>(
      "a[href], button:not([disabled]), [tabindex]:not([tabindex='-1'])",
    );
    expect(focusable[0]).toHaveTextContent("Skip to main content");
  });

  it("points the skip link at the main landmark", () => {
    renderShell();
    const link = screen.getByRole("link", { name: "Skip to main content" });
    expect(link).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("moves focus into the drawer when it opens", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("closes every overlay on Escape", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: /ask about a trade/i }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("link", { name: "Analytics" })).not.toBeInTheDocument();
  });

  it("gives every interactive element an accessible name", () => {
    // An icon-only control with no name is a button a screen reader announces
    // as "button".
    const { container } = renderShell();
    const controls = container.querySelectorAll<HTMLElement>("a[href], button");
    for (const control of controls) {
      const name =
        control.textContent?.trim() ||
        control.getAttribute("aria-label") ||
        control.getAttribute("title");
      expect(name, control.outerHTML.slice(0, 120)).toBeTruthy();
    }
  });

  it("hides decorative icons from the accessibility tree", () => {
    const { container } = renderShell();
    for (const svg of container.querySelectorAll("svg")) {
      expect(svg.getAttribute("aria-hidden")).toBe("true");
    }
  });
});
```

- [ ] **Step 2: Run the test**

Run: `cd web && npx vitest run __tests__/shell-accessibility.test.tsx`
Expected: most assertions pass because earlier tasks built for this. Any that fail name a real gap.

- [ ] **Step 3: Fix whatever failed**

Fix the component, not the assertion. The likely candidates and their fixes:
- An icon-only control with no name → add `aria-label` describing the action, not the icon.
- An `svg` missing `aria-hidden` → add `aria-hidden="true"`; the label belongs on the control.
- Focus not entering the drawer → confirm the close button's `ref` is focused in the open effect.

- [ ] **Step 4: Run the whole web suite**

Run: `cd web && npm test`
Expected: PASS, all files.

- [ ] **Step 5: Commit**

```bash
cd web && npx tsc --noEmit && npx eslint . && npm run build && cd ..
git add web/__tests__/shell-accessibility.test.tsx web/components web/app
git commit -m "test(app): pin the shell's keyboard and focus model

Two unnamed navigations are indistinguishable in a screen reader's
landmark list, which is how someone ends up in the phone bar looking for
the rail — so both are named and the test holds them that way. Also
asserts every control has an accessible name, every decorative icon is
hidden, focus enters the drawer when it opens, and Escape closes every
overlay."
```

---

### Task 13: Verify and hand off

**Files:**
- Modify: `docs/coordination/CLAUDE_CODEX_HANDOFF.md`

- [ ] **Step 1: Run every gate and record the real output**

```bash
cd web && npm test && npm run lint && npm run typecheck && npm run build && cd ..
/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/ -q
/Users/ayoub/tradelens-ai/.venv/bin/ruff check src/ scripts/
/Users/ayoub/tradelens-ai/.venv/bin/black --check src/ scripts/ tests/
```

Record the actual numbers. If anything fails, Phase 1 is not complete — fix it and rerun. Do not write a handoff claiming a green suite you have not seen.

- [ ] **Step 2: Check the shell against the design intent**

Start the dev server and look at it at 1440px and at 375px:

```bash
cd web && npm run dev
```

Confirm, and note anything that is not true:
- The app and the marketing site read as one product — same ground, same accent, same type.
- Teal appears as the primary action and one active state per viewport, and nowhere else.
- The period lens is legible and obviously the window under review.
- At 375px the sidebar is gone, the bottom bar is present, and targets are comfortable.
- Tab from a cold load reaches the skip link first, and every stop is visible.

- [ ] **Step 3: Append the Phase 1 record to the handoff**

Include: the real gate numbers; the design decisions from the top of this plan and anything that changed while building; every deviation from the plan and why; and what Phase 2 inherits — specifically the period-lens URL contract (`?from=&to=`), which Phase 2 must read rather than re-implement.

State plainly that the three pre-deployment gates at the top of the handoff remain open and untouched by Phase 1.

- [ ] **Step 4: Commit**

```bash
git add docs/coordination/CLAUDE_CODEX_HANDOFF.md
git commit -m "docs(handoff): Phase 1 shell complete"
```

- [ ] **Step 5: Stop**

Phase 1 is complete. **Do not begin Phase 2.** Overview's data, metrics and charts wait for their own plan, written after this phase is reviewed.

---

## Self-Review

**Spec coverage.** §7's Phase 1 row lists: unified design tokens (Task 1), six routes (Tasks 5, 11), sidebar (6), top bar (7), Partner drawer shell (9), loading/empty/error primitives (10), mobile bottom nav (8), focus and keyboard model (12). All present. §12's design direction is carried by Tasks 1, 6, 7 and 10. Two additions the spec implies but does not list: routing on `app_surface` (Task 2), without which the shell is unreachable, and the navigation model (Task 3), which prevents three surfaces disagreeing about the app's contents.

**Owner revisions folded in (2026-08-18).** The lens is the *global analysis range*
for performance-oriented surfaces, not a universal filter of record: Trade Detail,
New Trade, Weekly Recap, Daily Debrief, Strategy Profile and Settings ignore it and
keep their own controls, enforced by the `routeUsesPeriod` allowlist in Task 4 and
the hidden-not-inert rendering in Task 7. `?from=&to=` is never forced onto a route
that has no use for it. And the cutover is explicitly opt-in: Task 2 pins that no
existing account moves by default and that no bulk switch exists.

**Deliberate deviations, both recorded above:**
1. **No FastAPI calls in Phase 1.** §2.2's lifecycle describes Next.js forwarding to the API; a shell with no data has nothing to forward. This keeps the shell testable with no backend and guarantees Phase 1 cannot weaken the Phase 0 boundary.
2. **The period lens is new** — not named in the spec. It is the phase's signature element and the answer to the audit's finding that the old product showed confident numbers over tiny samples. It carries a real risk of colliding with a page's own temporal control, which is why its scope is an explicit allowlist and it renders nowhere else.

**Placeholder scan.** No TBD/TODO. Every step carries real code. Task 11's table is a substitution table for six near-identical files, with the full shape given once — repeating it six times would be noise, not clarity. Task 12's Step 3 lists concrete fixes for the specific failures that assertion set can produce, rather than "fix any issues".

**Type consistency.** `AppDestination` fields (`href`, `label`, `icon`, `phonePriority`) are used identically in Tasks 3, 6, 8 and 11. `Period` (`from`, `to`, `presetId`) is consistent across Tasks 4 and 7, and `routeUsesPeriod(pathname)` has one signature in both. `isActiveDestination(pathname, href)` has one signature everywhere. `EmptyState`'s `action` prop is `{ href, label }` in both its definition (Task 10) and its uses (Task 11). `PartnerLauncher` and `PartnerDrawer` are exported from one module, imported by Task 7's top bar and Task 5's layout.

**Ordering.** Tasks 5, 7 and 9 are mutually dependent through the layout's imports, so `npm run build` is deferred to Task 9 and stated as such in Task 5's Step 6. Tests still pass at every task boundary; only the production build has to wait.
