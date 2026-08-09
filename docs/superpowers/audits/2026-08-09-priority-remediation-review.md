# Dark Workspace Priority Remediation Review

**Date:** 2026-08-09

**Branch:** `codex/full-dark-streamlit-redesign`

**Product HEAD reviewed:** `6ac9c6981eab297165fa0515cc39ebd9f36dcdeb`
**Verdict:** the Priority 1–3 remediation is locally verified. No product
blocker was found. Nothing was pushed, merged, deployed, or used to finish the
branch.

## Scope and reviewed commits

This review starts at `63421f7` and covers the complete sequential remediation
through the clean-capture commit. The final audit/handoff commit contains only
this document and `docs/coordination/CLAUDE_CODEX_HANDOFF.md`.

| Task | Commit(s) |
|---|---|
| Execution checkpoint | `efe73eed7bdaa04fe4b9eafcc21896009f5217e5` |
| 1 — coherent bounded sample account | `a59839ac85a92b039e7a2fad3c0040dc3211f1de`, `05dc3b0c90d682161568bc9115b25c2a68cd87ca`, `3a2665d7ba48bc56a9556f563dc65351da194c92` |
| 2 — Journal presentation | `891c49652b1c664e8d1e6e6460d869403e3db3a6`, `11c1c32407ba77792dbdd0aa41be65ef6727416a` |
| 3 — truthful Partner availability | `30c593295ba9a68f8610d19ca003dc261f88e327`, `5f51ea7cd33f23da31ce4382f24f7712676ff260` |
| 4 — coherent Strategy state | `fd9e2f6e1c40b03ea74d3be87ec7269e6dbd5e15` |
| 5 — populated review periods | `fa7cd73a3a7d577635e17c0ed3d32d11696edf0e` |
| 6 — icon and killzone vocabulary | `324b5d829a40a76aa08cb134310a95c10ab8d767` |
| 7 — clean evidence | `6ac9c6981eab297165fa0515cc39ebd9f36dcdeb` |
| 8 — final audit and handoff | `docs(audit): re-score the remediated workspace` (the commit containing this file) |

## Before / after priority table

| Priority finding | Before | Verified after | Evidence |
|---|---|---|---|
| P1 sample time/account coherence | Dates crossed the viewing boundary and pages described different sample states. | All 40 browser rows contained zero dates after `2026-08-09` and zero contradictory sample-state phrases; Overview, Journal, Analytics, AI Reviews, Strategy, and the rail use the same account. | [Overview capture](assets/2026-08-09/overview-desktop.png), [Journal capture](assets/2026-08-09/journal-desktop.png), [sample tests](../../../tests/test_demo.py), [browser report](../../../.superpowers/sdd/2026-08-09-dark-workspace-priority-remediation/task-8-verifier-report.md) |
| P1 ownerless Partner truthfulness | An unavailable ownerless preview exposed a dead launcher and obsolete sign-in copy. | Ownerless tests suppress the launcher/context path; the live matrix found zero obsolete copy, one presentation per Partner state, and no hidden AI usage. | [Partner drawer](assets/2026-08-09/partner-drawer-desktop.png), [phone Partner page](assets/2026-08-09/partner-page-phone.png), [panel tests](../../../tests/test_partner_panel.py), [turn tests](../../../tests/test_partner_turn.py) |
| P1 Journal presentation parity | Sample rows exposed database-shaped identifiers and raw financial values. | The retained ledger uses human session/setup labels, signed money, R units, and semantic result marks; visible Journal labels contained zero raw underscore identifiers at all five configurations. | [Journal capture](assets/2026-08-09/journal-desktop.png), [ledger contracts](../../../tests/test_premium_page_contracts.py), [browser report](../../../.superpowers/sdd/2026-08-09-dark-workspace-priority-remediation/task-8-verifier-report.md) |
| P2 evidence cleanliness/coverage | Captures included non-product overlays and did not cover every destination/Partner shape. | Four production stills and nine audit captures are product-only, fixed-anchor, declared-size assets; the live matrix covers every destination at five configurations and the applicable Partner shape. | [capture contracts](../../../tests/test_capture_app_screenshots.py), [capture inventory](#clean-screenshot-inventory), [browser report](../../../.superpowers/sdd/2026-08-09-dark-workspace-priority-remediation/task-8-verifier-report.md) |
| P2 recovery and onboarding | Review periods could be empty and Strategy onboarding opened as an undifferentiated field wall. | Review options are populated-only with tested empty recovery routes; the sample Strategy is complete and coherent, while real empty/stored states retain separate tested flows. | [AI Reviews capture](assets/2026-08-09/ai-reviews-desktop.png), [Strategy capture](assets/2026-08-09/strategy-desktop.png), [review tests](../../../tests/test_insights_page.py), [boot tests](../../../tests/test_pages_boot.py) |
| P3 structural icons/terminology | Decorative emoji and session/killzone wording remained on routed surfaces. | All 40 rows found zero structural emoji in controls/toasts; source contracts pin supported icons and `Killzone performance`. | [toast tests](../../../tests/test_toast_icons.py), [Overview contracts](../../../tests/test_overview_bands.py), [Overview capture](assets/2026-08-09/overview-desktop.png) |

## Automated verification

The gate ran after the Task 7 capture-only Streamlit process was identified by
its worktree cwd and stopped. Results are fresh for this audit:

```text
pytest -q             2176 passed, 7 skipped in 124.19s
ruff check .          All checks passed!
black --check .       221 files would be left unchanged
git diff --check      exit 0, no output
```

The exact protected-boundary command from the brief also exited 0 with no
output:

```text
git diff 63421f7 -- \
  src/tradelens/services/ai_client.py \
  src/tradelens/services/partner.py \
  src/tradelens/db \
  src/tradelens/ui/components/auth.py \
  alembic .streamlit/config.toml
```

The full count and focused behavioral coverage are retained in the
[Task 8 verifier report](../../../.superpowers/sdd/2026-08-09-dark-workspace-priority-remediation/task-8-verifier-report.md),
[sample tests](../../../tests/test_demo.py),
[Partner tests](../../../tests/test_partner_panel.py),
[page boot tests](../../../tests/test_pages_boot.py), and
[capture tests](../../../tests/test_capture_app_screenshots.py).

## Browser matrix

The matrix used a fresh owned SQLite database and disposable Chrome profile.
Each row read pointer and reduced-motion media state inside the rendered page.
The 768 and 375 runs used `mobile=true` device metrics and touch emulation, so
they are coarse-pointer browser emulation rather than width-only desktop
resizes.

| Configuration | Surfaces | Exceptions | Overflow | Targets <44px | Contrast flags | Stale light | Demo/date/copy/label/icon defects |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1440 fine | 7 destinations + drawer | 0 | 0 | 0 | 0 | 0 | 0 |
| 1024 fine | 7 destinations + drawer | 0 | 0 | 0 | 0 | 0 | 0 |
| 768 coarse | 7 destinations + drawer | 0 | 0 | 0 | 0 | 0 | 0 |
| 375 coarse | 7 destinations + Partner page | 0 | 0 | 0 | 0 | 0 | 0 |
| 1440 reduced motion | 7 destinations + drawer | 0 | 0 | 0 | 0 | 0 | 0 |

All 40 rows also had the requested in-page media state. Each open drawer and
the phone Partner page had exactly one visible drawer/page presentation and no
simultaneous launcher. `ai_usage_log` stayed `0 → 0` around the whole matrix,
so page loads, trusted drawer opening, and keyboard traversal performed no
hidden model send. Exact row counts and probe qualifications are in the
[browser report](../../../.superpowers/sdd/2026-08-09-dark-workspace-priority-remediation/task-8-verifier-report.md).

## Accessibility evidence

Overview, Journal, AI Reviews, and Strategy were walked at all five
configurations; the Partner drawer was walked at 1440, 1024, coarse 768, and
reduced-motion 1440. Each walk used twelve dispatched `Tab` and four dispatched
`Shift+Tab` key sequences. No DOM focus call was used. Across 24 walks, 380
control stops matched `:focus-visible`; four remaining samples were `BODY`
after drawer traversal wrapped, not controls.

The visible-target probe resolves Streamlit/BaseWeb's tiny internal input node
to its actual styled hit wrapper before applying the 44px floor. Automated
direct-text contrast checks found no failure, but remain a computed-style
regression check rather than a formal assistive-technology audit. Responsive,
focus, reduced-motion, and target rules are also pinned in
[design-system tests](../../../tests/test_design_system.py),
[page-polish tests](../../../tests/test_page_polish.py), and
[motion tests](../../../tests/test_phase4_motion.py).

## Demo coherence evidence

- The fixed evidence anchor is `2026-08-09`; no matrix row rendered a later
  date. The sample generator's 60-row time boundary and deterministic schema
  are pinned in [test_demo.py](../../../tests/test_demo.py).
- [Overview](assets/2026-08-09/overview-desktop.png),
  [Journal](assets/2026-08-09/journal-desktop.png),
  [Analytics](assets/2026-08-09/analytics-desktop.png), and
  [AI Reviews](assets/2026-08-09/ai-reviews-desktop.png) present the same
  20-trade seeded evidence and coherent totals.
- [Strategy](assets/2026-08-09/strategy-desktop.png) and the rail both name
  `ICT/SMC Day Trading`; the shared fixture and six-section rule are covered by
  [page-polish tests](../../../tests/test_page_polish.py).
- Daily and Weekly review choices are restricted to populated periods by
  [review-date tests](../../../tests/test_insights_page.py) and browser boot
  coverage in [test_pages_boot.py](../../../tests/test_pages_boot.py).

## Clean screenshot inventory

Every file below was re-opened at original detail for this audit. The images
show only the product viewport: no browser chrome, Codex overlay/composer,
Streamlit management surface, cursor, tooltip, transient focus, or auth query.

Marketing WebP:

- [Overview — 1600×1000](../../../site/assets/shot-dashboard-wide.webp)
- [New Trade — 1400×933](../../../site/assets/shot-newtrade.webp)
- [Analytics — 1400×933](../../../site/assets/shot-analytics.webp)
- [Strategy — 1400×933](../../../site/assets/shot-strategy.webp)

Audit PNG:

- [Overview](assets/2026-08-09/overview-desktop.png)
- [New Trade](assets/2026-08-09/new-trade-desktop.png)
- [Journal](assets/2026-08-09/journal-desktop.png)
- [Analytics](assets/2026-08-09/analytics-desktop.png)
- [AI Reviews](assets/2026-08-09/ai-reviews-desktop.png)
- [Strategy](assets/2026-08-09/strategy-desktop.png)
- [Settings](assets/2026-08-09/settings-desktop.png)
- [Partner drawer](assets/2026-08-09/partner-drawer-desktop.png)
- [Partner phone page](assets/2026-08-09/partner-page-phone.png)

## 10K Website Checklist re-score

The app is scored separately from unchanged business proof and public-funnel
work. A cleaner theme alone earns no point. The Phase 2 evidence is the
[previous re-score](2026-08-06-phase2-dark-rescore.md); the original rubric is
the [2026-07-21 audit](../../audits/2026-07-21-10k-checklist-business-audit.md).

| # | Item | Original app | Phase 2 | Final | Evidence and reason |
|---|---|---:|---:|---:|---|
| 01 | Point of view, not a template | 7.5 | 8.5 | **8.5** | The authored dark workspace, evidence rail, review sheet, and responsive Partner remain coherent across [Overview](assets/2026-08-09/overview-desktop.png), [AI Reviews](assets/2026-08-09/ai-reviews-desktop.png), and [Partner](assets/2026-08-09/partner-drawer-desktop.png). Held below 9 because the ledger remains visibly framework-backed. |
| 02 | Typography that does work | 8.0 | 8.5 | **8.5** | Editorial headings, restrained mono metadata, and readable note measure remain visible in [AI Reviews](assets/2026-08-09/ai-reviews-desktop.png) and are pinned by [reading-shell tests](../../../tests/test_review_reader.py). The canvas ledger still limits authored numeral control. |
| 03 | A restrained colour system | 8.5 | 9.0 | **9.0** | [Overview](assets/2026-08-09/overview-desktop.png) and [Analytics](assets/2026-08-09/analytics-desktop.png) reserve teal for action/selection and green/red for financial meaning; [design-system tests](../../../tests/test_design_system.py) pin the tokenized dark surfaces. No stale opaque light surface or computed contrast flag appeared in 40 rows. |
| 04 | Hierarchy that breathes | 6.5 | 8.5 | **8.5** | The coherent KPI strips, one-question Analytics shape, indexed review shell, and structured Strategy form are visible in [Analytics](assets/2026-08-09/analytics-desktop.png), [AI Reviews](assets/2026-08-09/ai-reviews-desktop.png), and [Strategy](assets/2026-08-09/strategy-desktop.png). Dense ledger/form states keep this below 9. |
| 05 | Imagery with intent | 6.5 | 6.5 | **7.5** | The four [marketing captures](#clean-screenshot-inventory) are relevant, legible at declared size, coherently seeded, cleanly cropped, and production-only; nine audit views prove complete destination/Partner coverage. Held at 7.5 because the four marketing assets remain repeated full-page product stills rather than four compositionally distinct editorial crops. |
| 06 | Motion that whispers | 6.0 | 7.5 | **7.5** | State-linked drawer/lens/press motion and the 300ms ceiling remain pinned by [motion tests](../../../tests/test_phase4_motion.py); reduced motion was read back and clean on seven destinations plus the [Partner drawer](assets/2026-08-09/partner-drawer-desktop.png). No new decorative motion was added. |
| 07 | Mobile that is designed, not shrunk | 5.5 | 8.0 | **8.0** | The [375 Partner page](assets/2026-08-09/partner-page-phone.png) has the dedicated bottom-navigation shape; all seven destinations passed coarse 768 and coarse 375 with zero overflow/undersized targets, corroborated by [responsive contracts](../../../tests/test_premium_page_contracts.py). Coarse rows are emulated, not physical-device evidence. |
| 08 | The invisible expensive stuff | 4.5 | 7.0 | **7.5** | `2176 passed, 7 skipped`, clean format/lint/diff gates, an empty protected-boundary diff, 40 clean browser rows, real keyboard traversal, exclusive Partner presentation, and `0 → 0` hidden usage are retained in the [verifier report](../../../.superpowers/sdd/2026-08-09-dark-workspace-priority-remediation/task-8-verifier-report.md). Held at 7.5 by the dataframe/framework and deployment-only limitations below. |

**Final Streamlit product-polish score: 65/80 = 81.25/100, reported as
81/100.** The increase from the Phase 2 result is deliberately limited to
imagery (+1.0) and invisible quality (+0.5); the other six categories retain
their previously evidenced scores.

## Remaining limitations

1. Streamlit dataframe column headers still omit `aria-sort`: all 9/8/7/4
   visible headers at 1440/1024/768/375 and all 9 under reduced motion lacked
   the attribute. This task did not add JavaScript or replace the ledger with
   an authored table.
2. The older dataframe-toolbar accessible-name limitation did **not** remain:
   current browser evidence exposes `Show/hide columns`, `Download as CSV`,
   `Search`, and `Fullscreen` on the four controls. It is recorded here so the
   earlier limitation is not copied forward after being disproved.
3. The dataframe/canvas path still prevents complete authored tabular-numeral
   control. Journal label evidence combines the retained screenshot, visible
   label probe, and pure ledger transformation tests.
4. Coarse-pointer rows are Chrome emulation, not physical-device tests. No
   screen-reader, voice-control, forced-colours, or physical-device pass was
   run. The contrast scan is automated computed-style evidence, not a formal
   WCAG audit.
5. The 1024, coarse 768, and reduced-motion observations are report-only; the
   retained pixel artifacts are the clean 1440 destination set and 375 Partner
   page. The in-page state/count evidence is retained in the ignored local
   [verifier report](../../../.superpowers/sdd/2026-08-09-dark-workspace-priority-remediation/task-8-verifier-report.md).
6. The owner-only Streamlit Cloud secret check remains required before any
   deployment: inspect the deployed app's Settings → Secrets and confirm the
   legacy username/password values are present and non-blank or treat the old
   published pair as disclosed and rotate it wherever reused.

## Exact Git state

- Canonical worktree:
  `/Users/ayoub/tradelens-ai/.claude/worktrees/codex+full-dark-streamlit-redesign`
- Branch: `codex/full-dark-streamlit-redesign`
- Remediated product/evidence HEAD reviewed:
  `6ac9c6981eab297165fa0515cc39ebd9f36dcdeb`
- Task 8 commit: `docs(audit): re-score the remediated workspace`; it contains
  only this audit and the handoff update.
- Writer lock after the Task 8 commit: `NONE`.
- Push/merge/deploy/branch-finish state: none performed.
- Next owner: `OWNER`; review this audit and decide whether to finish, push, or
  deploy the branch.
