# Dark Workspace Priority Remediation Review

**Date:** 2026-08-09

**Branch:** `codex/full-dark-streamlit-redesign`

**Product HEAD reviewed:** `6ac9c6981eab297165fa0515cc39ebd9f36dcdeb`
**Verdict:** the Priority 1–3 remediation is locally verified. No product
blocker was found. Nothing was pushed, merged, deployed, or used to finish the
branch.

## Scope and reviewed commits

This review starts at `63421f7` and covers the complete sequential remediation
through the clean-capture commit. A later evidence-only amendment makes this
document self-contained, corrects the Overview marketing-image description,
and updates the handoff; it changes no product layout or behavior.

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
| Final evidence correction | `docs(audit): make final evidence durable` |

## Before / after priority table

| Priority finding | Before | Verified after | Evidence |
|---|---|---|---|
| P1 sample time/account coherence | Dates crossed the viewing boundary and pages described different sample states. | All 40 browser rows contained zero dates after `2026-08-09` and zero contradictory sample-state phrases; the seeded destination captures use one coherent account. | [Overview capture](assets/2026-08-09/overview-desktop.png), [Journal capture](assets/2026-08-09/journal-desktop.png), [sample tests](../../../tests/test_demo.py), [audit-contradiction tests](../../../tests/test_audit_contradictions.py) |
| P1 ownerless Partner truthfulness | An unavailable ownerless preview exposed a dead launcher and obsolete sign-in copy. | Ownerless tests suppress the launcher and context path. The ready-owner live matrix found exactly one responsive Partner presentation at each applicable viewport and no hidden AI usage; it did not live-drive every availability state. | [Partner drawer](assets/2026-08-09/partner-drawer-desktop.png), [phone Partner page](assets/2026-08-09/partner-page-phone.png), [panel tests](../../../tests/test_partner_panel.py), [turn tests](../../../tests/test_partner_turn.py), [page boot tests](../../../tests/test_pages_boot.py) |
| P1 Journal presentation parity | Sample rows exposed database-shaped identifiers and raw financial values. | The retained ledger uses human session/setup labels, signed money, R units, and semantic result marks; visible Journal labels contained zero raw underscore identifiers at all five configurations. | [Journal capture](assets/2026-08-09/journal-desktop.png), [ledger contracts](../../../tests/test_premium_page_contracts.py) |
| P2 evidence cleanliness/coverage | Captures included non-product overlays and did not cover every destination/Partner presentation. | Four marketing stills and nine audit captures are product-only, fixed-anchor, declared-size assets. They are destination/presentation evidence; the live matrix covers every destination at five configurations and the applicable ready-owner Partner presentation. | [capture contracts](../../../tests/test_capture_app_screenshots.py), [capture cleanup tests](../../../tests/test_capture_cleanup.py), [capture inventory](#clean-screenshot-inventory) |
| P2 recovery and onboarding | Review periods could be empty and Strategy onboarding opened as an undifferentiated field wall. | Review options are populated-only with tested empty recovery routes; the sample Strategy is complete and coherent, while real empty/stored states retain separate tested flows. These alternate states are behavioral-test evidence, not retained visual captures. | [AI Reviews capture](assets/2026-08-09/ai-reviews-desktop.png), [Strategy capture](assets/2026-08-09/strategy-desktop.png), [review tests](../../../tests/test_insights_page.py), [boot tests](../../../tests/test_pages_boot.py) |
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

The measured browser and keyboard results are embedded below so this audit does
not depend on an ignored local report. Durable behavioral contracts include
[sample tests](../../../tests/test_demo.py),
[Partner panel tests](../../../tests/test_partner_panel.py),
[Partner turn tests](../../../tests/test_partner_turn.py),
[page boot tests](../../../tests/test_pages_boot.py),
[capture tests](../../../tests/test_capture_app_screenshots.py), and
[capture cleanup tests](../../../tests/test_capture_cleanup.py).

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

All 40 rows had the requested in-page pointer and motion media state. Across
the matrix, the measured count was zero for rendered exceptions, horizontal
overflow, visible targets below 44px, opaque stale-light surfaces, automated
direct-text contrast flags, contradictory sample states, dates after the
anchor, obsolete ownerless copy, raw underscore Journal labels, and structural
emoji in live controls or toasts.

The matrix used a ready, authenticated seeded owner. At 1440, 1024, coarse 768,
and reduced-motion 1440, the opened drawer was the only visible Partner
presentation and its launcher was absent. At coarse 375, the dedicated Partner
page was the only visible Partner presentation and no launcher was present.
This proves one presentation per responsive viewport/presentation, not one
presentation per availability state. Ownerless, AI-unavailable, no-trades, and
no-profile behavior is covered separately by
[Partner panel tests](../../../tests/test_partner_panel.py),
[Partner turn tests](../../../tests/test_partner_turn.py), and
[page boot tests](../../../tests/test_pages_boot.py).

The drawer was opened with a trusted pointer sequence rather than a synthetic
DOM click. `ai_usage_log` stayed `0 → 0` around the whole matrix, so page loads,
trusted drawer opening, and keyboard traversal caused no hidden model send.
The matrix intentionally did not submit the composer; this is presentation and
no-hidden-send evidence, not an end-to-end model-response test.

## Accessibility evidence

Overview, Journal, AI Reviews, and Strategy were walked at all five
configurations; the Partner drawer was walked at 1440, 1024, coarse 768, and
reduced-motion 1440. Each walk used twelve dispatched `Tab` and four dispatched
`Shift+Tab` key sequences. No DOM focus call was used. Across 24 walks, 380
control stops matched `:focus-visible`; four remaining samples were `BODY`
after drawer traversal wrapped, not controls.

The visible-target probe resolves Streamlit/BaseWeb's tiny internal input node
to its actual styled hit wrapper before applying the 44px floor; hidden,
off-canvas, clipped, and retained `display:none` nodes are not treated as
visible targets. Automated direct-text contrast checks inspect computed visible
text against its nearest opaque background. They found no failure, but remain a
regression check rather than a formal WCAG or assistive-technology audit.
Responsive, focus, reduced-motion, and target rules are also pinned in
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
Their formats and dimensions match the tracked capture manifest. A metadata and
content scan found no auth query, session token, localhost URL, browser text,
or Codex text; the only extended attribute observed was ordinary macOS file
provenance. The capture harness and cleanup boundaries are pinned by
[capture tests](../../../tests/test_capture_app_screenshots.py) and
[cleanup tests](../../../tests/test_capture_cleanup.py).

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

### Coverage boundary

These 13 images are destination/presentation captures, not broad visual
coverage of every key state. The desktop PNG set shows the seven default seeded
destinations and the ready-owner Partner drawer; the phone PNG shows only the
ready-owner Partner page. The 1024, coarse 768, and reduced-motion results are
measured browser rows without retained pixel artifacts.

The retained set does not visually show Journal Calendar or Trade Detail,
non-default Analytics lenses, Weekly/Daily AI Reviews and their populated
selectors, the Evidence Rail/confidence area below the AI Reviews crop, real
empty Strategy onboarding, or ownerless/unavailable/no-trades/no-profile
Partner states. Tracked behavioral tests substantiate those interactions and
states, but do not substitute for visual-state captures. In particular, the
[AI Reviews image](assets/2026-08-09/ai-reviews-desktop.png) shows the review
sheet and first finding; the Evidence Rail is below its retained frame.

## 10K Website Checklist re-score

The app is scored separately from unchanged business proof and public-funnel
work. A cleaner theme alone earns no point. The Phase 2 evidence is the
[previous re-score](2026-08-06-phase2-dark-rescore.md); the original rubric is
the [2026-07-21 audit](../../audits/2026-07-21-10k-checklist-business-audit.md).

| # | Item | Original app | Phase 2 | Final | Evidence and reason |
|---|---|---:|---:|---:|---|
| 01 | Point of view, not a template | 7.5 | 8.5 | **8.5** | The authored dark workspace, review sheet, and responsive Partner remain coherent across [Overview](assets/2026-08-09/overview-desktop.png), [AI Reviews](assets/2026-08-09/ai-reviews-desktop.png), and [Partner](assets/2026-08-09/partner-drawer-desktop.png). The one-Evidence-Rail-per-note behavior is pinned by [reading-shell tests](../../../tests/test_review_reader.py), but the rail itself is below the AI Reviews crop. Held below 9 because the ledger remains visibly framework-backed. |
| 02 | Typography that does work | 8.0 | 8.5 | **8.5** | Editorial headings, restrained mono metadata, and readable note measure remain visible in [AI Reviews](assets/2026-08-09/ai-reviews-desktop.png) and are pinned by [reading-shell tests](../../../tests/test_review_reader.py). The canvas ledger still limits authored numeral control. |
| 03 | A restrained colour system | 8.5 | 9.0 | **9.0** | [Overview](assets/2026-08-09/overview-desktop.png) and [Analytics](assets/2026-08-09/analytics-desktop.png) reserve teal for action/selection and green/red for financial meaning; [design-system tests](../../../tests/test_design_system.py) pin the tokenized dark surfaces. No stale opaque light surface or computed contrast flag appeared in 40 rows. |
| 04 | Hierarchy that breathes | 6.5 | 8.5 | **8.5** | The coherent KPI strips, one-question Analytics shape, indexed review shell, and structured Strategy form are visible in [Analytics](assets/2026-08-09/analytics-desktop.png), [AI Reviews](assets/2026-08-09/ai-reviews-desktop.png), and [Strategy](assets/2026-08-09/strategy-desktop.png). Dense ledger/form states keep this below 9. |
| 05 | Imagery with intent | 6.5 | 6.5 | **7.5** | The four refreshed [marketing captures](#clean-screenshot-inventory) are relevant to their named destinations, legible at declared size, coherently seeded, production-only, and free of capture chrome. The Overview HTML now accurately describes the visible masthead, KPI/risk bands, and opening equity trajectory rather than promising off-frame content. This earns the +1.0 over Phase 2's stale evidence; it is capped at 7.5 because all four remain repeated full-shell product views, the Overview trajectory is only opening in-frame, and none is a compositionally distinct editorial crop. The nine audit PNGs support traceability, not additional marketing-imagery credit. |
| 06 | Motion that whispers | 6.0 | 7.5 | **7.5** | State-linked drawer/lens/press motion and the 300ms ceiling remain pinned by [motion tests](../../../tests/test_phase4_motion.py); reduced motion was read back and clean on seven destinations plus the [Partner drawer](assets/2026-08-09/partner-drawer-desktop.png). No new decorative motion was added. |
| 07 | Mobile that is designed, not shrunk | 5.5 | 8.0 | **8.0** | The [375 Partner page](assets/2026-08-09/partner-page-phone.png) shows the dedicated bottom-navigation shape. All seven destinations passed coarse 768 and coarse 375 with zero overflow or undersized visible targets, corroborated by [responsive contracts](../../../tests/test_premium_page_contracts.py). Only Partner has retained 375px visual evidence; the cross-destination mobile claim is geometry/behavior evidence from Chrome emulation, not a physical-device, assistive-technology, or destination-by-destination mobile screenshot pass. |
| 08 | The invisible expensive stuff | 4.5 | 7.0 | **7.5** | The embedded gate, browser matrix, keyboard counts, ready-owner responsive Partner exclusivity, and `0 → 0` hidden usage support 7.5 alongside the tracked [capture](../../../tests/test_capture_app_screenshots.py), [Partner](../../../tests/test_partner_panel.py), and [motion](../../../tests/test_phase4_motion.py) contracts. Held at 7.5 by the dataframe/framework, probe, state-coverage, and deployment-only limitations below. |

**Final Streamlit product-polish score: 65/80 = 81.25/100, reported as
81/100.** Exact subtotal: `8.5 + 8.5 + 9.0 + 8.5 + 7.5 + 7.5 + 8.0 + 7.5 =
65.0`. The increase from the Phase 2 result is deliberately limited to imagery
(+1.0) and invisible quality (+0.5); the other six categories retain their
previously evidenced scores.

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
5. The retained visual evidence is destination/presentation-level. The 1024,
   coarse 768, and reduced-motion observations are embedded matrix results, not
   retained pixels; the 375 artifact is Partner only. Alternate destination
   and Partner availability states are covered by tracked tests, not by the
   retained screenshot set.
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
- Original Task 8 commit: `docs(audit): re-score the remediated workspace`.
- Final evidence correction: `docs(audit): make final evidence durable`; it
  contains only this audit, the Overview image description in `site/index.html`,
  and the handoff amendment.
- Writer lock after the evidence correction: `NONE`.
- Push/merge/deploy/branch-finish state: none performed.
- Next owner: `OWNER`; review this audit and decide whether to finish, push, or
  deploy the branch.
