# Streamlit redesign browser preflight — 2026-08-03

## Outcome

The backend/model-routing foundation and static route matrix are green. The browser baseline is
**not implementation-ready** because the existing New Trade wizard throws a Streamlit exception
when the user returns from step 2 to step 1. No redesign implementation started.

The checks ran from the canonical worktree on branch
`codex/full-dark-streamlit-redesign`, after commits `97aead9`, `9a7c0c8`, and `6b78125`, against
an isolated seeded SQLite capture database. No development or user database was changed.

## Viewport route matrix

All seven authenticated routes were loaded at 1440, 1024, coarse-pointer 768, and
coarse-pointer 375: Overview, New Trade, Journal, Analytics, AI Reviews, Strategy Profile, and
Settings.

- 28/28 route/viewport combinations rendered their expected page heading.
- 28/28 had zero `stException` elements on initial load.
- 28/28 had no document-level horizontal overflow.
- At 375 the bottom navigation and `More` pattern render.
- At coarse 768 the bottom navigation does **not** render; Streamlit uses its collapsed-sidebar
  control. This live result corrected the Partner breakpoint mapping in spec §1.3, §8.2a,
  and §11: drawer at sidebar-navigation widths (≥768), full-page Partner only at actual
  bottom-navigation widths (≤767).
- Direct nested routes emitted browser-console 404s for relative Streamlit health/host-config
  requests (observed under `/NewTrade/_stcore/...`). The page websocket and UI still loaded.
  Treat this as baseline infrastructure noise to recheck, not as a redesign regression.

Screenshots were captured only as disposable preflight evidence and were not added to Git.

## Workflow checks

### Authentication and recovery surface

At 375 the signed-out login and recovery affordances rendered with zero Streamlit exceptions
and no document overflow. Account creation is not exposed by this deployed configuration.

### New Trade wizard — blocking defect

1. Open step 1, **Screenshot**.
2. Select **Continue**; step 2, **When and what**, renders.
3. Select **Back**.
4. Step 1 reappears with one Streamlit exception:

```text
StreamlitValueAssignmentNotAllowedError:
Values for the widget with key 'nt_shot' cannot be set using st.session_state
```

The traceback points to `src/tradelens/ui/pages/1_NewTrade.py:340`, where the `nt_shot`
`st.file_uploader` is instantiated. This breaks the required five-step draft-preserving flow
and blocks Phase 2. It is a UI-owner fix; Codex did not cross the ownership boundary during
preflight.

### Journal

- Ledger rendered 20 isolated sample trades.
- Selecting the first ledger row opened `GBP/USD · 2026-08-03` trade detail with no exception.
- **Back to trades** returned to the 20-row ledger.
- Calendar → trading day → trade detail also completed with no exception.

The four visible Streamlit dataframe toolbar controls (`Show/hide columns`, `Download as CSV`,
`Search`, `Fullscreen`) measured about 22.4×22.4 CSS px at 1440. They do not meet the spec's
44×44 visible-target requirement and must be corrected or replaced in the redesign.

### Analytics and AI Reviews

- Analytics switched from Performance to Risk without an exception.
- Weekly Recap loaded its cached note.
- Daily Debrief generated and regenerated the seeded note with the existing note retained while
  regeneration ran; no exception appeared.
- A forced browser-level regeneration failure was not injected. Service tests remain the source
  of truth for exception containment until Phase 2 adds the specified stable error presentation.

### Strategy Profile and Settings

- Strategy Name was changed in the isolated database, saved, navigated away from, and verified
  after returning. Persistence worked with no exception.
- Settings exposed CSV export/import, sample-data controls, and both destructive accordions.
  Opening **Delete all trades** revealed a typed `DELETE` confirmation and a separate
  `DELETE MY ACCOUNT` gate. No destructive action was executed.
- Tenant isolation and destructive-operation scope remain covered by the automated test suite;
  the browser check validates presentation and confirmation gating only.

## Reduced motion

With browser context `reducedMotion: "reduce"`, all seven authenticated routes reported
`prefers-reduced-motion: reduce`, rendered their expected heading, had zero `stException`
elements, and had no document-level horizontal overflow.

## Required next action

The UI owner fixes the `nt_shot` Back-navigation exception and adds a browser regression test.
Codex then re-runs the New Trade round trip and reviews the diff. Only after that browser check
is green should the consolidated implementation plan be rebuilt from the Phase 1 spec.
