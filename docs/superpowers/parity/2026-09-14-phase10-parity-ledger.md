# Phase 10 — §8 parity ledger

Source: spec §8. Status is one of `implemented`, `blocker`, `removed — <reason>`.
A `removed` row requires the owner's recorded decision (T8). Built against `16376d0`.

Evidence standard (owner-mandated, 2026-09-17): a row is `implemented` only when the
implementation was READ and confirmed to perform the behaviour the item names, AND a test
was found that pins that behaviour. A page-renders test is not evidence for a behaviour.
Where an implementation exists but no test pins the behaviour, the status is `blocker` and
the Location column still records where it lives. Where neither exists, the status is
`blocker`. Nothing here was marked `implemented` on the strength of a keyword grep.

Vitest rows cite `path` plus the test title; pytest rows cite `path::test_name`.

| Section | Item | Location | Test | Status |
|---|---|---|---|---|
| Overview | KPI row (net P&L, win rate, expectancy, profit factor, trades) | web/components/app/overview/kpi-row.tsx | web/__tests__/overview-kpi.test.tsx — "shows the five headline figures" | implemented |
| Overview | today P&L | web/components/app/overview/current-standing.tsx | web/__tests__/overview-kpi.test.tsx — "shows today and the running week, spec §8's pair" | implemented |
| Overview | this-week P&L | web/components/app/overview/current-standing.tsx | web/__tests__/overview-kpi.test.tsx — "says these two are not scoped to the selected period" | implemented |
| Overview | max drawdown | web/components/app/overview/risk-discipline.tsx | web/__tests__/overview-risk.test.tsx — "writes a drawdown as the loss it is, in text and not only in colour" | implemented |
| Overview | rule adherence | web/components/app/overview/risk-discipline.tsx | web/__tests__/overview-risk.test.tsx — "shows adherence as a rate with its sample size" | implemented |
| Overview | edge leak | web/components/app/overview/risk-discipline.tsx | web/__tests__/overview-risk.test.tsx — "warns that profitable rule-breaking is not repeatable edge" | implemented |
| Overview | consistency score | web/components/app/overview/risk-discipline.tsx | web/__tests__/overview-risk.test.tsx — "says a consistency score is not yet earned rather than showing zero" | implemented |
| Overview | equity curve | web/components/app/overview/equity-curve.tsx | web/__tests__/equity-curve.test.tsx — "draws the curve when the sample has earned it" | implemented |
| Overview | current/best streak | web/components/app/overview/trajectory.tsx | web/__tests__/overview-trajectory.test.tsx — "says which way a streak runs, in a word" | implemented |
| Overview | average win | web/components/app/overview/trajectory.tsx | web/__tests__/overview-trajectory.test.tsx — "explains an empty average instead of leaving a bare dash" | implemented |
| Overview | average loss | web/components/app/overview/trajectory.tsx | web/__tests__/overview-trajectory.test.tsx — "explains an empty average instead of leaving a bare dash" | implemented |
| Overview | killzone performance | web/components/app/overview/recurring-edge.tsx | web/__tests__/overview-trajectory.test.tsx — "shows where the account repeats itself, with sample sizes" | implemented |
| Overview | setup performance | web/components/app/overview/recurring-edge.tsx | web/__tests__/overview-trajectory.test.tsx — "shows where the account repeats itself, with sample sizes" | implemented |
| Overview | trading-days calendar | web/components/app/overview/trading-calendar.tsx | web/__tests__/trading-calendar.test.tsx — "marks traded days and leaves untraded ones blank" | implemented |
| Overview | activation next-step | web/components/app/overview/next-review-action.tsx | web/__tests__/overview-next-and-recent.test.tsx — "has copy for every step the contract can send" | implemented |
| Overview | recent trades | web/components/app/overview/recent-trades.tsx | web/__tests__/overview-next-and-recent.test.tsx — "lists the most recent trades with their outcome in text" | implemented |
| Overview | filter panel | web/components/app/overview/asset-filter.tsx: asset scope, beside the existing web/components/app/period-lens.tsx period scope | web/__tests__/overview-asset-filter.test.tsx — "navigates to the scoped URL when an instrument is chosen" and "says the scope is empty instead of showing a strip of zeros" | implemented |
| Overview | low-data states | web/components/app/states/empty-state.tsx | web/__tests__/overview-risk.test.tsx — "renders nothing measurable when the sample has not earned it" | implemented |
| Journal / Trades | date range | web/components/app/period-lens.tsx | web/__tests__/period-lens.test.ts — "governs the surfaces that aggregate performance" | implemented |
| Journal / Trades | asset | web/components/app/trades/filter-bar.tsx | web/__tests__/trades-filter-bar.test.tsx — "writes the asset filter to the URL on blur, resetting offset" | implemented |
| Journal / Trades | session | web/components/app/trades/filter-bar.tsx | web/__tests__/trade-filters.test.ts — "is exactly the four filter fields the API accepts" | implemented |
| Journal / Trades | setup filters | web/components/app/trades/filter-bar.tsx | web/__tests__/trade-filters.test.ts — "reads each known filter" | implemented |
| Journal / Trades | trades table (date, asset, session, setup, result, P&L, R, grade, screenshot) | web/components/app/trades/trades-table.tsx | web/__tests__/trades-table.test.tsx — "renders the date, asset, session, setup, result, P&L and R columns" | implemented |
| Journal / Trades | calendar month view | web/components/app/trades/journal-calendar.tsx | web/__tests__/journal-calendar.test.tsx — "marks a day outside the selected period as dimmed, not linked" | implemented |
| Journal / Trades | open-from-day | web/components/app/trades/journal-calendar.tsx | web/__tests__/journal-calendar.test.tsx — "links a day with trades into that day's filtered list" | implemented |
| Journal / Trades | trade detail | web/app/app/trades/[id]/page.tsx | web/__tests__/trade-detail-view.test.tsx — "shows the read view and screenshots by default, not the edit form" | implemented |
| Journal / Trades | AI summary of the filtered set | web/components/app/trades/summary-panel.tsx | web/__tests__/trade-summary-panel.test.tsx — "enqueues the current filters, polls, and renders provider text as inert React text" | implemented |
| Journal / Trades | edit | web/components/app/trade-detail/edit-trade-form.tsx | web/__tests__/edit-trade-form.test.tsx — "sends an edited field's new value" | implemented |
| Journal / Trades | delete with confirmation | web/components/app/trade-detail/delete-trade-dialog.tsx | web/__tests__/delete-trade-dialog.test.tsx — "is a modal that states plainly what happens, and requires an explicit confirm" | implemented |
| Journal / Trades | per-trade screenshot upload | web/components/app/trade-detail/attach-screenshot.tsx: file-upload path only — the paste-a-link path stays on New Trade — over the existing web/app/api/trades/[id]/screenshot/route.ts relay | web/__tests__/trade-detail-attach-screenshot.test.tsx — "runs presign → PUT → finalize through the existing relay, then refreshes" | implemented |
| New Trade | upload or image URL | web/components/app/new-trade/screenshot-upload.tsx | web/__tests__/screenshot-url-ingest.test.ts — "attaches on 201 and returns the screenshot descriptor" | implemented |
| New Trade | quality check | src/tradelens/services/trade_autofill.py:213 | tests/test_trade_autofill.py::test_an_unusable_image_never_reaches_the_provider | implemented |
| New Trade | AI analysis | web/components/app/trade-detail/ai-review-panel.tsx | web/__tests__/ai-review-panel.test.tsx — "renders the stored analysis instead of the not-analysed line" | implemented |
| New Trade | autofill review per field | web/components/app/new-trade/autofill-review.tsx | web/__tests__/autofill-review.test.tsx — "PATCHes only the accepted, patchable fields when applying" | implemented |
| New Trade | trade date | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-fields.test.ts — "names every field the Streamlit form collects, and nothing else" | implemented |
| New Trade | entry time | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade.test.ts — "requires a readable entry time" | implemented |
| New Trade | session auto-detect | src/tradelens/api/routers/trades.py:226 | tests/test_api_trades.py::test_list_killzone_renders_the_label_not_the_raw_key | implemented |
| New Trade | asset | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-form.test.tsx — "reveals the custom asset field only when 'Other / Custom' is picked" | implemented |
| New Trade | timeframe | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-fields.test.ts — "names every field the Streamlit form collects, and nothing else" | implemented |
| New Trade | HTF bias | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-fields.test.ts — "names every field the Streamlit form collects, and nothing else" | implemented |
| New Trade | LTF bias | web/lib/app/new-trade.ts | web/__tests__/new-trade.test.ts — "sends ltf_bias as TradeCreate.bias, lowercased" | implemented |
| New Trade | setup model | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-fields.test.ts — "names every field the Streamlit form collects, and nothing else" | implemented |
| New Trade | evidence | web/lib/app/new-trade.ts | web/__tests__/new-trade.test.ts — "folds confluences into the five TradeCreate boolean flags" | implemented |
| New Trade | confirmation text | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-fields.test.ts — "names every field the Streamlit form collects, and nothing else" | implemented |
| New Trade | followed-rules (yes/no/partial) | web/lib/app/new-trade.ts | web/__tests__/new-trade.test.ts — "folds rule_broken/did_well/do_better into notes as labelled lines" | implemented |
| New Trade | result | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade.test.ts — "allows a result that matches P&L's sign" | implemented |
| New Trade | P&L | web/lib/app/new-trade.ts | web/__tests__/new-trade.test.ts — "flags a result that contradicts a non-zero P&L — mirrors canonical_outcome" | implemented |
| New Trade | risk | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-fields.test.ts — "names every field the Streamlit form collects, and nothing else" | implemented |
| New Trade | position size | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-fields.test.ts — "names every field the Streamlit form collects, and nothing else" | implemented |
| New Trade | R multiple | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-fields.test.ts — "names every field the Streamlit form collects, and nothing else" | implemented |
| New Trade | exact price levels | web/lib/app/new-trade.ts | web/__tests__/new-trade.test.ts — "keeps exact price precision through the fold" | implemented |
| New Trade | reflection notes | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade.test.ts — "folds rule_broken/did_well/do_better into notes as labelled lines" | implemented |
| New Trade | emotion log (before/during/after) | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade.test.ts — "falls back mindset into emotions_during only when During was left unset" | implemented |
| New Trade | mistake tags | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-fields.test.ts — "names every field the Streamlit form collects, and nothing else" | implemented |
| New Trade | completeness warnings | web/lib/app/new-trade.ts | web/__tests__/new-trade-form.test.tsx — "shows completeness warnings without blocking submit (global rule 5)" | implemented |
| New Trade | draft persistence | web/lib/app/draft-autosave.ts | web/__tests__/draft-autosave.test.tsx — "debounces: rapid edits within the window produce exactly one PUT" | implemented |
| New Trade | duplicate detection | web/components/app/new-trade/new-trade-form.tsx | web/__tests__/new-trade-form.test.tsx — "shows a duplicate as 'already logged', not as an error, and creates nothing new" | implemented |
| New Trade | outcome/P&L contradiction block | web/lib/app/new-trade.ts | web/__tests__/new-trade-form.test.tsx — "shows a P&L/result contradiction inline, mirroring canonical_outcome, without disabling submit" | implemented |
| AI Reviews | Patterns (candidates, cards, confidence, evidence, sample size, next review action) | web/components/app/reviews/patterns-lens.tsx | web/__tests__/reviews-page.test.tsx — "opens on Patterns with the lead thesis, findings and the period strip" | implemented |
| AI Reviews | Weekly Recap (week selector, generate, retry, validated sections) | web/components/app/reviews/weekly-lens.tsx | web/__tests__/reviews-weekly-lens.test.tsx — "replaces the saved recap on success" | implemented |
| AI Reviews | Daily Debrief (day selector, five sections) | web/components/app/reviews/daily-lens.tsx | web/__tests__/reviews-daily-lens.test.tsx — "generates, polls and shows the Day in review note" | implemented |
| AI Reviews | read-full-note disclosure | web/components/app/reviews/review-note.tsx | web/__tests__/reviews-note.test.tsx — "shows the first section and discloses the rest" | implemented |
| Analytics | date range | web/components/app/period-lens.tsx | web/__tests__/analytics-page.test.tsx — "renders no date input anywhere on the page" | implemented |
| Analytics | asset/session/strategy filters | web/components/app/analytics/filter-bar.tsx | web/__tests__/analytics-page.test.tsx — "forwards the period and the three filters to fetchAnalytics" | implemented |
| Analytics | four lenses (Performance, Risk, Timing, Setups) | web/components/app/analytics/lens-tabs.tsx | web/__tests__/analytics-lens-tabs.test.tsx — "names all four lenses in words, not colour alone" | implemented |
| Analytics | equity curve | web/components/app/analytics/performance-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "gives the performance and risk lenses their real chart regions" | implemented |
| Analytics | daily P&L | web/components/app/analytics/performance-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "gives the performance and risk lenses their real chart regions" | implemented |
| Analytics | drawdown series | web/components/app/analytics/risk-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "gives the performance and risk lenses their real chart regions" | implemented |
| Analytics | R-multiple distribution | web/components/app/analytics/distribution-chart.tsx | web/__tests__/analytics-charts.test.tsx — "scales every bar from the real maximum count" | implemented |
| Analytics | by day of week | web/components/app/analytics/timing-lens.tsx | web/__tests__/analytics-page.test.tsx — "renders the timing breakdowns when the timing lens is selected" | implemented |
| Analytics | by session | web/components/app/analytics/timing-lens.tsx | web/__tests__/analytics-page.test.tsx — "renders the timing breakdowns when the timing lens is selected" | implemented |
| Analytics | by strategy | web/components/app/analytics/setups-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "renders each setups breakdown and the recorded mistakes" | implemented |
| Analytics | by timeframe | web/components/app/analytics/setups-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "renders each setups breakdown and the recorded mistakes" | implemented |
| Analytics | by asset | web/components/app/analytics/setups-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "renders each setups breakdown and the recorded mistakes" | implemented |
| Analytics | by setup type | web/components/app/analytics/setups-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "renders each setups breakdown and the recorded mistakes" | implemented |
| Analytics | emotion vs RR | src/tradelens/services/analytics.py: _emotion_rr feeds build_setups by_emotion_rr from the read-only metrics.emotion_vs_rr, rendered by web/components/app/analytics/setups-lens.tsx | tests/test_analytics_service.py::test_setups_lens_reports_average_r_by_pre_trade_emotion and ::test_an_emotion_with_no_recorded_r_is_undefined_not_a_flat_zero | implemented |
| Analytics | by hour of day | src/tradelens/services/analytics.py:449 build_timing (deliberately omits it) | tests/test_analytics_service.py::test_the_timing_lens_does_not_offer_an_hour_breakdown_it_cannot_fill | removed — owner decision (2026-09-18): historical entry times cannot support the visualisation (`entry_time` is stored hash-only, so the Streamlit panel could never be filled either) and no new clock column is to be introduced. NOT implemented; the timing lens ships without an hour breakdown, pinned by the named test. |
| Analytics | killzone performance | web/components/app/analytics/timing-lens.tsx | web/__tests__/analytics-page.test.tsx — "renders the timing breakdowns when the timing lens is selected" | implemented |
| Analytics | confirmation-model performance | web/components/app/analytics/setups-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "renders each setups breakdown and the recorded mistakes" | implemented |
| Analytics | mistake frequency | web/components/app/analytics/setups-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "renders each setups breakdown and the recorded mistakes" | implemented |
| Analytics | total edge leak | web/components/app/analytics/performance-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "shows the discipline figures on the performance lens" | implemented |
| Analytics | rule adherence | web/components/app/analytics/performance-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "shows the discipline figures on the performance lens" | implemented |
| Analytics | consistency score | web/components/app/analytics/performance-lens.tsx | web/__tests__/analytics-lenses.test.tsx — "shows the discipline figures on the performance lens" | implemented |
| Analytics | trade of the week | src/tradelens/services/metrics.py:1413 trade_of_the_week (no caller in either surface) | tests/test_dashboard.py::test_trade_of_the_week_* | removed — owner decision (2026-09-18): the live Streamlit dashboard stopped rendering it at commit `a0ef59b` (2026-06-25, "Session A"), which deleted the card and its `trade_of_week` payload — two months before migration Phase 0. NOT a migration regression and NOT implemented in the new app; no other feature replaces it. The metric function and its tests remain uncalled. |
| Analytics | period deltas | web/app/app/analytics/page.tsx | web/__tests__/analytics-page.test.tsx — "shows the deltas it says it compared, not just the dates" | implemented |
| Analytics | evidence narrative per lens | web/components/app/analytics/breakdown-section.tsx | web/__tests__/analytics-lenses.test.tsx — "ranks a comparable breakdown and names the largest recorded category" | implemented |
| Strategy Profile | identity (name, style) | web/components/app/strategy/playbook-editor.tsx | web/__tests__/strategy-editor.test.tsx — "sends exactly the twelve fields plus the version it was loaded from" | implemented |
| Strategy Profile | markets | web/components/app/strategy/playbook-editor.tsx | web/__tests__/strategy-editor.test.tsx — "sends exactly the twelve fields plus the version it was loaded from" | implemented |
| Strategy Profile | timeframes | web/components/app/strategy/playbook-editor.tsx | web/__tests__/strategy-editor.test.tsx — "sends exactly the twelve fields plus the version it was loaded from" | implemented |
| Strategy Profile | entry rules | web/components/app/strategy/playbook-editor.tsx | web/__tests__/strategy-editor.test.tsx — "sends exactly the twelve fields plus the version it was loaded from" | implemented |
| Strategy Profile | exit rules (stop, target) | web/components/app/strategy/playbook-editor.tsx | web/__tests__/strategy-editor.test.tsx — "sends exactly the twelve fields plus the version it was loaded from" | implemented |
| Strategy Profile | risk rules | web/components/app/strategy/playbook-editor.tsx | web/__tests__/strategy-editor.test.tsx — "sends exactly the twelve fields plus the version it was loaded from" | implemented |
| Strategy Profile | setups | web/components/app/strategy/playbook-editor.tsx | web/__tests__/strategy-editor.test.tsx — "sends exactly the twelve fields plus the version it was loaded from" | implemented |
| Strategy Profile | mistakes to avoid | web/components/app/strategy/playbook-editor.tsx | web/__tests__/strategy-editor.test.tsx — "sends exactly the twelve fields plus the version it was loaded from" | implemented |
| Strategy Profile | active strategy | web/components/app/strategy/playbook-summary.tsx | web/__tests__/strategy-page.test.tsx — "shows the saved facets and the active badge" | implemented |
| Strategy Profile | ICT/SMC starter playbook | web/components/app/strategy/playbook-editor.tsx | web/__tests__/strategy-editor.test.tsx — "fills the editor and sends nothing" | implemented |
| Strategy Profile | sections-written progress | web/components/app/strategy/playbook-summary.tsx | web/__tests__/strategy-page.test.tsx — "shows the server's section count" | implemented |
| Strategy Profile | skip path | web/components/app/strategy/first-run-banner.tsx | web/__tests__/strategy-editor.test.tsx — "skips first run with no body and returns to the Overview" | implemented |
| Strategy Profile | AI insight append | web/components/app/strategy/insight-suggestions.tsx | tests/test_api_strategy.py::test_an_insight_is_added_to_risk_rules_and_then_no_longer_suggested | implemented |
| AI Partner | global chat | web/components/app/partner-drawer.tsx | web/__tests__/partner-drawer.test.tsx — "holds the global conversation, sent to the global relay" | implemented |
| AI Partner | per-trade chat | web/components/app/trade-detail/trade-partner-panel.tsx | web/__tests__/trade-partner-panel.test.tsx — "sends to this trade's relay and names no screenshot by default" | implemented |
| AI Partner | journal-grounded context | src/tradelens/services/partner_context.py | tests/test_partner_context.py::test_context_orders_journal_notes_before_trades_before_strategy | implemented |
| AI Partner | evidence sources | web/components/app/partner/conversation.tsx | web/__tests__/partner-conversation-ui.test.tsx — "links only evidence the server linked, and only to a trade page" | implemented |
| AI Partner | history trimming | src/tradelens/services/partner.py:492 | tests/test_partner.py::test_trim_history_keeps_last_10_and_summarizes | implemented |
| AI Partner | scope guard | src/tradelens/services/partner.py:528 | tests/test_partner.py::test_apply_scope_guard_fires_on_signal_seeking | implemented |
| AI Partner | image attachment | web/components/app/trade-detail/trade-partner-panel.tsx | tests/test_api_partner.py::test_asking_for_the_screenshot_attaches_the_trades_own_image | implemented |
| Settings | recovery email | web/components/app/settings/profile-section.tsx (display-only; decision S1) | web/__tests__/settings-page.test.tsx — "shows the email and its verification but offers no way to change it" | removed — owner decision (2026-09-18): Streamlit's save-a-new-address path is NOT migrated. The approved S1 behaviour is retained: the sign-in email and its verification state are displayed only. A verified email-change flow is out of migration scope; password recovery continues through the reset flow. |
| Settings | timezone | web/components/app/settings/preferences-section.tsx | web/__tests__/settings-page.test.tsx — "saves a timezone change through the relay and confirms beside the control" | implemented |
| Settings | API-key guidance | web/components/app/settings/preferences-section.tsx (availability only; decision S2) | web/__tests__/settings-page.test.tsx — "describes the %s AI state without secret instructions (S2)" | removed — owner decision (2026-09-18): user-managed API-key configuration is NOT restored. The approved S2 behaviour is retained: on the SaaS the key is an operator secret and the page shows managed-AI availability (`enabled` / `demo` / `unavailable`) with no key-configuration instructions. |
| Settings | CSV export | web/components/app/settings/data-section.tsx | web/__tests__/settings-data-section.test.tsx — "fetches the same-origin relay and saves the file" | implemented |
| Settings | CSV import | web/components/app/settings/data-section.tsx | web/__tests__/settings-data-section.test.tsx — "sends the file text and reports counts in the Streamlit wording" | implemented |
| Settings | load sample trades | web/components/app/settings/data-section.tsx | web/__tests__/settings-data-section.test.tsx — "loads samples and updates the counts" | implemented |
| Settings | clear sample trades | web/components/app/settings/data-section.tsx | web/__tests__/settings-data-section.test.tsx — "clears samples with DELETE" | implemented |
| Settings | delete all trades | web/components/app/settings/danger-zone.tsx | web/__tests__/settings-danger-zone.test.tsx — "sends exactly the constant confirmation and reports the count" | implemented |
| Settings | delete account | web/components/app/settings/danger-zone.tsx | web/__tests__/settings-danger-zone.test.tsx — "sends the constant phrase, never the typed text, and hands off to the landing page" | implemented |
| Settings | monthly cost by feature | web/components/app/settings/data-section.tsx | web/__tests__/settings-data-section.test.tsx — "shows this month's cost with four decimals and the total" | implemented |
| Settings | demo banner | web/components/app/settings/preferences-section.tsx | web/__tests__/settings-page.test.tsx — "shows demo status only as a line (S3)" | implemented |
| Cross-cutting | onboarding gate | web/lib/auth/session.ts | web/__tests__/app-surface-routing.test.ts — "still gates on email and onboarding before surface is considered" | implemented |
| Cross-cutting | strategy gate | web/app/app/page.tsx | web/__tests__/overview-page-auth.test.tsx — "sends an account with no playbook step to /app/strategy before any fetch" | implemented |
| Cross-cutting | activation status | src/tradelens/services/activation.py | tests/test_activation.py::test_the_api_contract_pins_the_same_step_keys_the_service_emits | implemented |
| Cross-cutting | corrections capture feeding few-shot | src/tradelens/services/corrections.py:217 | tests/test_ai_client.py::test_chat_injects_past_corrections_block | implemented |
| Cross-cutting | AI usage and cost logging | src/tradelens/services/cost.py | tests/test_cost.py::test_log_ai_usage_writes_row | implemented |
| Cross-cutting | DEMO_MODE | src/tradelens/services/demo.py | tests/test_ai_client.py::test_chat_demo_mode_returns_demo_response | implemented |
| Cross-cutting | low-sample confidence policy | src/tradelens/services/sample_policy.py | tests/test_sample_policy.py::test_patterns_need_five_trades | implemented |
| Cross-cutting | reflection-only safety language (never signals, predictions, or advice) | src/tradelens/services/reflection_guard.py | tests/test_reflection_guard.py::test_trade_guidance_is_rejected_with_the_callers_error | implemented |
| Carried decisions | Strategy demo-playbook preview | — | — | removed — owner decision T2 (2026-09-14): the ICT/SMC starter playbook on /app/strategy covers the workflow; no signed-in flow needs a demo read path |

---

## Notes

### Analytics — trade of the week

The Streamlit dashboard rendered a "Trade of the Week" card until commit `a0ef59b`
(2026-06-25, "Session A"), which deleted the card and its `trade_of_week` payload. The
metric function (`src/tradelens/services/metrics.py:1413 trade_of_the_week`) and its tests
in `tests/test_dashboard.py` survive with **no caller in either surface**. Phase 6 recorded
it as deliberately deferred.

It is therefore **not a migration regression** — it is an **unresolved product decision**
for the owner: implement it in Analytics, or record a deliberate removal. It stays a Gate 1
blocker until the owner decides. No other feature in this ledger replaces it.

### Why each blocker is a blocker

Five §8 items carry `blocker`, in two distinct shapes.

**Implementation is absent or unreachable from the new surface (four items).**

1. **Overview — filter panel.** The Streamlit dashboard's filter panel scoped every figure
   by **asset** (`src/tradelens/ui/app.py:472-506`, a `selectbox` plus a "Show all assets"
   reset) as well as by period. The Next.js Overview accepts only `from`/`to`
   (`src/tradelens/api/routers/overview.py:70`, `web/lib/app/overview.ts`), so the period
   lens is the whole of it and no asset filter exists. Needs an owner decision: restore an
   Overview asset filter (API parameter + control), or record the reduction.
2. **Journal / Trades — per-trade screenshot upload.** Streamlit's Trades detail offered an
   "Add screenshot" uploader for an already-logged trade
   (`src/tradelens/ui/pages/2_Trades.py:718-722`). The per-trade relay and API exist and are
   tested, but `ScreenshotUpload` is imported **only** by `new-trade-form.tsx`; the trade
   detail page renders a read-only `screenshot-gallery.tsx`. Attaching a screenshot to a
   trade already saved is unreachable in the new app. Small, well-shaped fix — the server
   side is done.
3. **Analytics — emotion vs RR.** `metrics.emotion_vs_rr` and `charts.emotion_vs_rr_chart`
   exist, and the Streamlit Analytics page rendered a "P&L by emotional state going in"
   panel (`4_Analytics.py:835-851`). The analytics API's `SetupsLens`/`TimingLens` carry no
   emotion breakdown, and no Next.js component renders one. Implemented in the old surface,
   not the new one.
4. **Analytics — by hour of day.** Deliberately absent from the new contract, with a written
   rationale (`src/tradelens/services/analytics.py:449`) and a test pinning the absence:
   `entry_time` is hash-only and `Trade` stores no clock column, so
   `metrics.by_hour_of_day` returns zero rows for any real sample — the Streamlit panel
   could not have been filled either. This is **not** a migration regression, but it has no
   recorded owner decision, so under T8 it blocks Gate 1 until the owner marks it
   "implement" (which needs a persisted time column — a schema change) or "removed".

**Behaviour deliberately narrowed by a phase decision with no owner §8 decision (two
items).** Both were read in code and both are pinned by tests that assert the *absence*:

5. **Settings — recovery email.** Streamlit let a trader save a recovery email
   (`9_Settings.py:170`). Phase 9 decision S1 made the Next.js profile section
   display-only, because on the website the email is the sign-in identity. Password
   recovery itself works (the forgot/reset flow ships and is tested), but there is no
   recovery-email write path. Owner decision needed.
6. **Settings — API-key guidance.** Streamlit shipped a "How to configure an API key"
   expander (`9_Settings.py:274`). Phase 9 decision S2 replaced it with an availability
   line, and the test asserts no key-configuration text appears. Owner decision needed.

S1 and S2 are phase-level design decisions, not the explicit §8 removal decisions T8 asks
for, so they are recorded as blockers rather than silently as removals.

### Items where the reading differed from the 2026-09-14 keyword sweep

- "trade of the week" and the demo-playbook preview: the sweep's finding (no match under
  `web/`) is **confirmed** by reading.
- Three further items the sweep did not flag are recorded as blockers here: the Overview
  filter panel, the trade-detail screenshot upload, and Analytics' emotion-vs-RR panel. All
  three match a keyword somewhere under `web/` or `src/` but do not perform the §8
  behaviour where a trader can reach it.
- Two items are `implemented` on a **different surface** from the Streamlit original, and a
  keyword sweep of the matching page would have missed them: "AI analysis" (§8 New Trade)
  ships on the trade-detail page as `ai-review-panel.tsx`, and "session auto-detect" is
  derived server-side in `routers/trades.py` rather than in the form.
- "demo banner" ships as a status **line** (decision S3), not a banner. Recorded as
  implemented: the behaviour — telling the trader the deployment is in demo mode — is
  present and tested.

### Work that would need its own implementation plan

| Item | Shape | Rough size |
|---|---|---|
| Analytics — emotion vs RR | API schema field + service breakdown + lens panel + tests | Small-to-medium: ~1 task (the metric exists; the frame already carries `emotions_before`) |
| Journal — per-trade screenshot upload | Reuse `ScreenshotUpload` on the trade-detail page; wire to the existing relay | Small: ~1 task, server side already done |
| Overview — asset filter panel | API query parameter, service filter, control, tests | Medium: ~1-2 tasks, touches the overview contract |
| Settings — recovery email | New column or reuse, write path, verification flow, relay, UI, tests | Medium: a verify-the-new-address flow is its own design question |
| Settings — API-key guidance | Copy only, if the owner reverses S2 | Trivial |
| Analytics — by hour of day | Persist a clock column on `Trade` + migration + backfill question + breakdown + panel | **Medium-to-large: its own phase.** A schema change, and no historical data to backfill from |
| Analytics — trade of the week | A card in Analytics fed by the existing metric | Small, once the owner decides |

## Carried findings (pre-existing, outside Phase 10B's range)

- **An oversized screenshot can orphan its quarantine object.** `web/lib/app/screenshot-upload.ts` rejects a file for
  size only after the server's `max_bytes` is known, i.e. after a presign has already created a quarantine object —
  and that rejection path returns without a `pendingKey`, so nothing calls `abandonScreenshotUpload`. The object is
  never adopted and never abandoned. This predates Phase 10B and affects New Trade today; the trade-detail attach
  island inherits it unchanged. Found by the Phase 10B independent review (2026-09-18). Not fixed here: it belongs to
  the upload helper, outside this phase's scope. Live R2 verification (a hard pre-release gate) should confirm whether
  such objects exist in the bucket, and the fix is a separate scoped change.
- **Playwright pinned at 1.63.0, not the plan's 1.49.1** (Task R3): Next.js 16 declares `@playwright/test@^1.51.1`,
  so the older pin could not install without `--force`. Dev-only; excluded from `npm audit --omit=dev`.
