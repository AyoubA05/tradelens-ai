# TradeLens AI — Session Memory

## Project
AI-powered POST-TRADE day trading journal for SMC/ICT traders. NOT a signal app.
Stack: Python, Streamlit, SQLite (Alembic), Anthropic API, Plotly, Pandas.
Repo: /Users/ayoub/tradelens-ai

## Architecture
- All business logic: src/tradelens/services/*.py
- Streamlit pages only render — never contain business logic
- AI calls only through services/ai_client.py
- DB changes via Alembic migrations only (reversible)
- Prompts: prompts/*_v2.txt — extend contracts only, never rewrite them

## Current State (Week 5)
Building: SMC/ICT schema, killzone engine, pattern detection, weekly AI review,
correction memory, AI partner chat, consistency score, cost dashboard.
85+ tests target. Commit format: week5-d<N>: <summary>

## Key Rules
- DEMO_MODE=true in CI (zero API spend), false locally
- No live signals, predictions, or broker sync ever
- pytest -q must pass before every commit
- ruff + black must pass before final commit

## UI Polish Session (2026-07-06) — Decision Log
Substitute for claude-mem (not connected). Log every decision here.
- Unavailable tools: claude-mem, Superpowers, Impeccable, ui-ux-pro-max.
  Owner approved local fallbacks: this file = memory; manual
  brainstorm→design→implement→test→validate per phase; PRODUCT.md
  maintained by hand; emil-design-eng skill = design seed.
- Context7 findings: repo pins streamlit==1.50.0, plotly==6.7.0.
  st.plotly_chart use_container_width removed in Streamlit 1.57 —
  works at 1.50 but deprecated; prefer pinned-safe API and note it.
  st.html() available as alternative to st.markdown(unsafe_allow_html=True).
  No official stability guarantee for data-testid attrs; keep the set
  theme.py already uses on 1.50.0.
- PRODUCT.md already existed (old palette #20808D/#0E1117, theme.py
  tokens). Merged: kept register/users/accessibility, updated palette to
  #00c2b2 on #0d0f11, source of truth → design_system.py (migration).
- Open conflict flagged for Phase 1: spec's tl-insight-card colored left
  borders vs anti-pattern "no colored side borders on cards".
- New design tokens/CSS/helpers → src/tradelens/ui/design_system.py.
  Assets → src/tradelens/ui/assets/ (Higgsfield-generated).
- Baseline before Phase 1: 58 test files / 727 test functions (verified).
- Impeccable plugin became available mid-session — use /impeccable at
  phase gates as originally specified (manual substitute retired).
- Owner decisions: NO colored left borders on insight cards (use badges/
  tinted bg/header accent); Phase 1B tokens authoritative; only reuse
  data-testid selectors already proven in this repo on 1.50.0
  (stAppViewContainer, stHeader, stSidebar, stMetricValue/Delta/Label);
  spec's stToolbar/stDecoration/metric-container NOT proven here — must
  verify visually before adopting; note migration risks, don't change pin.
- Repo .venv is macOS Python 3.9.6 (CLAUDE.md says 3.11) — unusable in
  Linux sandbox. Test runs use /tmp/tlvenv (Python 3.10.12, sandbox-only,
  repo untouched). Flagged as env drift, not changed.
- Page filename mapping (spec name → actual file): dashboard → app.py,
  new_trade → pages/1_NewTrade.py, journal → pages/2_Trades.py,
  analytics → pages/4_Analytics.py, strategy_profile → pages/5_Strategy.py,
  insights → pages/6_Insights.py. Plus 9_Settings.py (not in spec) and
  pages/_archive/ (5 retired pages — do not touch).
- Phase 1 implemented (pending user gate): design_system.py written
  (tokens/build_css/helpers, pure module, lazy streamlit import);
  config.toml → new [theme] palette + client.toolbarMode="minimal"
  (showSidebarNavigation=false + comment preserved);
  tests/test_design_system.py added (~35 tests incl. R1 mirror, proven-
  testid allowlist, no-border-left assertion); app.py calls
  inject_design_system() right after inject_css() (test_page_polish
  exactly-one-inject_css() still satisfied — import line has no parens).
- inject_design_system deviation: re-injects CSS every run (Streamlit
  clears elements on rerun; spec's session_state skip-flag would drop
  styling after first interaction). Flag kept as marker only.
- Impeccable NOT invocable this session after all: only the
  impeccable-manual-edit-applier agent is exposed, no /impeccable skill.
  Substituted manual audit vs PRODUCT.md (recorded in phase report).
- Contrast flags (spec tokens kept as authoritative, flagged not fixed):
  TL_TEXT_MUTED #6b7280 on #13161a ≈ 3.7:1 (below AA 4.5:1 for body;
  used only for 11-13px labels/deltas); TL_TEXT_FAINT #3d4451 ≈ 1.9:1
  (decorative empty-state body only). Revisit at Phase 9 accessibility QA.
- Logo A (job ef881152) confirmed; user must curl to
  src/tradelens/ui/assets/logo_mark.png (sandbox cannot download CDN).
- Phase 1 gate PASSED by owner (local pytest/ruff/black/visual OK).
- Phase 2 complete (2026-07-07). All 8 assets confirmed; user downloads
  via curl. Asset → job id:
  hero_bg.png → e28a7480 (v3b "lifted midtones"; 2 iterations: v1 too
  bright, v2 too empty; owner direction: +20-30% chart detail, lifted
  midtones, no hotspot);
  empty_trades.png → dc5f568b (gpt_image_2, baked-in caption "No trades
  logged yet" — owner verified text visually);
  welcome.png → 6c96c086; strategy_banner.png → e574608f (21:9);
  recap_bg.png → 84c9cd66; cta_log_trade.png → 43c38831 (4:3);
  ai_scanning.mp4 → 9562abec (4s 720p);
  landing_loop.mp4 → 05778858 (4s 720p).
- Budget decision: spec's 8s Video 2 would cost 36cr (total 74 > ~58
  budget). Owner chose 4s for both videos → total spend 56cr, balance
  ~42. Seedance output is 720p (model default), not the spec's "4K" —
  fine for in-app ambient loops; upscale_video available later if needed.
  Higgsfield "IN THE DARK" preset declined for landing_loop (literal
  generation per spec).
- Phase 3 implemented (pending user gate). design_system.py: added
  .tl-hero-wrap/.tl-kpi-row, .tl-table (+.mono/.pnl-pos/.pnl-neg),
  .tl-welcome*, .tl-action-link/-title/-sub/-go — no border-left/right
  (count still 1, R1 clean, testids unchanged). app.py: header =
  tl-section-header + get_active_strategy() name badge (primary);
  sample-trades st.info → render_banner info; KPI row = single HTML flex
  row in .tl-hero-wrap (hero_bg base64 + rgba(13,15,17,0.65) gradient
  overlay) with render_kpi_card ×6 (currency/currency/percent/number/
  ratio/currency, win_rate×100, compute_profit_factor_raw → ∞);
  calendar retitled "Trading Calendar" (kept render_trade_calendar(df),
  NOT the spec's Plotly heatmap — test-pinned); equity curve keeps
  equity_curve_chart(eq) + TL_SURFACE/TL_TEXT/TL_BORDER overrides,
  height=320, displayModeBar=False, hover adds trades/day via customdata;
  recent trades = HTML .tl-table 10 rows (Date|Asset|Session|Setup|
  Result badge|P&L|R Multiple) + st.page_link View All; quick actions =
  3 tl-action-card anchors (📝📖📊 per spec, overrides no-emoji-icon
  note in ui.py — spec wins); welcome empty state = tl-empty-state
  tl-welcome (welcome.png full width, cta_log_trade.png 300px, Log Your
  First Trade → + kept secondary "Load sample trades" link).
  Spec deviations: "Week's P&L"→"This Week's P&L" (test-pinned label);
  st.columns(6)→HTML flex row (hero bg must wrap all 6 cards); calendar
  heatmap skipped; KPI zero renders $0.00 neutral (N/A only for missing).
  tl-empty-state boot marker also satisfied by theme.py CSS — keep class
  on welcome wrapper so marker survives Phase 9 dedupe.
  SQLite MCP validation (20 real trades; entry_time col doesn't exist →
  ordered by trade_date DESC): wins green, losses red, BE $0.00 neutral,
  PF 3.2x, no-loss slice ∞, None → N/A. Unused imports removed (TEAL/
  TERRA/kpi_card/section_header/empty_state/format_profit_factor).
  Impeccable again not invocable (only manual-edit-applier agent) →
  manual PRODUCT.md audit substituted, same as Phase 1.
- Phase 4 implemented (pending user gate). New Trade UX cleanup:
  1_NewTrade.py + components/ai_autofill_review.py only (no schema, no
  design_system.py changes needed — existing classes covered everything).
  ai_autofill_review.py: removed "AI Autofill (optional)" header; killed
  st.dialog modal (_open_detection_dialog deleted; dialog-dismiss key
  kept only in clear lists); new inline two-panel detection UI
  (_render_detection_panel: chart image left, bordered AI card right w/
  render_badge + identity chips + checkboxes + prices; Apply detected
  fields → / Skip AI → buttons); _render_scanning_video plays
  assets/ai_scanning.mp4 (loop/muted, try/except) before both spinners;
  has_staged_detection() exported so page hides its duplicate preview;
  confluence chips via render_chip_row. All pinned pure functions
  (build_form_writes/build_overlay_writes/should_autocheck/
  entry_time_write_allowed/_source_signature/auto-trigger) untouched.
  1_NewTrade.py: 5-step stepper (Chart/Context/Trade Details/Psychology/
  Review) via render_step_indicator on every tab; SMC/ICT option lists
  (DEFAULT_SETUPS, CONFLUENCES incl. MSS/CHOCH, DEFAULT_MISTAKES);
  session shown as badge not disabled input; avoid-list warning banner
  (_avoid_list_match); Evidence chips; pnl→result auto-sync callback +
  mismatch banner; Planned R (_planned_r) + Realized R readouts w/ faint
  "(calculated)"; Step 4 reordered (process notes, mindset, did well,
  do better, mistake multiselect nt_mistake_tags w/ danger chips,
  emotions expander); Review = structured ticket (_ticket_html, sections
  Market/Setup/Risk & Outcome/Psychology/AI Suggested/Missing Fields,
  all user values escape()d); saved state via just_saved_trade_id →
  banner + View in Journal / Log Another / Dashboard links.
  Keys: +nt_did_well +nt_do_better +nt_mistake_tags +just_saved_trade_id;
  −nt_mistake −nt_mistake_other −_nt_saved_id −_nt_ai_keep −_nt_ai_reopen.
  Spec deviations: (a) "MSS/CHOCH" kept over spec's "CHoCH" — label
  test-pinned in test_ai_autofill.py and AI writes it into
  nt_confluences; (b) AI panel = st.container(border=True), not literal
  .tl-ai-card div (widgets can't live in static HTML); (c) price
  confidence = "· NN% confidence" text in checkbox labels (no HTML in
  checkbox labels); (d) mindset textarea kept (test-pinned) alongside
  new questions; (e) did_well/do_better persist into notes column
  (schema read-only); (f) mistake multiselect replaces conditional
  selectbox; (g) confirmation input → text_area, same nt_confirm key.
  Sandbox smoke: py_compile OK; all test pins present; forbidden strings
  absent; line lengths ≤88; evidence options cover all 6 AI labels.
  Impeccable skill invoked but its script/reference files unreachable
  from sandbox → manual audit substituted (ban greps): no border-left/
  right, no gradient text, no backdrop-filter, no hardcoded hex, no
  !important, all ticket HTML escaped. Deferred to Phase 9 (known token
  flags): --tl-text-faint 1.9:1 on "Not entered yet"/"(calculated)" and
  --tl-text-muted 3.7:1 on 12px uppercase ticket labels — fix at token
  level in theme.py, not inline. /tmp/tlvenv streamlit wiped + PyPI
  unreachable → no AppTest in sandbox; pytest runs locally at gate.
- Phase 5 implemented (pending user gate). Journal redesign, file stays
  2_Trades.py (spec says journal.py — tests pin the filename). SQLite
  validation first per spec: 20 trades, sessions NY/London/Asian, 4
  setups, 4 assets, 5 screenshots; page filter expression matched raw
  SQL on 4 combined-filter cases (incl. NQ+ES × NY × Win × Liquidity
  Sweep → 3). Filters card = st.container(border=True): From/To dates +
  Asset multiselect (row 1), Session/Result/Setup + Clear Filters (row
  2); keys jf_from/jf_to/jf_assets/jf_session/jf_result/jf_setup; Clear
  via on_click callback (safe pre-instantiation pop); stale multiselect/
  selectbox values sanitized before widgets render (date-range change
  can shrink option sets → would raise). One fetch per run: get_trades
  (date+user server-side), asset/session/result/setup page-side (same
  precedent as old direction filter). Table: Date|Killzone|Asset|Session
  |Setup|Direction|Result|P&L|R|Grade|📷 via st.dataframe on_select
  single-row → session_state["selected_trade_id"] (renamed from
  journal_selected_id — nothing pinned it); Styler row tint by result
  (TL_SUCCESS_DIM/TL_DANGER_DIM) + sign color on P&L/R cells (tokens
  imported from design_system, no hardcoded hex in page). Fallback
  picker expander kept (AppTest can't click dataframes). Empty states:
  filtered-empty → render_empty_state card; true-empty →
  render_empty_state w/ empty_trades.png + page_link CTAs wrapped in
  try/except → slug <a> fallback (sidebar _nav_link pattern; page_link
  raises in registry-less AppTest boots — empty-DB boot hits this
  branch). Detail panel: header card (asset·date, session+result badges,
  large mono P&L sign-colored) → screenshot left (width=460, uploader
  when none, analyzer kept) → right: Setup (setup chip primary +
  evidence chips from SMC flag cols liquidity_sweep/bos/choch/fvg_used/
  order_block_used + followed-rules badge) → Risk & Outcome flex grid
  (Entry/Stop/TP/Exit/Planned R/Realized R mono) → Psychology
  (trade_process_notes, Did well/Improve/Rule broken parsed back out of
  the composed notes column via _split_notes, mistake_tags JSON → danger
  chips, emotions caption, leftover notes). Edit/Delete expanders,
  render_ai_review, render_ask_ai (has pinned AI Coach Notes + QA input)
  all kept. Pins kept: "AI summary of these"/generate_debrief/
  log_ai_usage "Trade Summary"/"never signals"; summary sig now includes
  all new filters. Spec deviations: (a) Time column → Killzone (no
  entry_time column; schema read-only); (b) Result rendered as plain
  text + row tint in dataframe (HTML badges impossible in st.dataframe;
  badges used in detail header instead); (c) Quality column → Grade
  (user_grade or ai_grade) — trade_quality lives on aianalysis; per-row
  fetch would be N+1 queries; AI quality shown in detail via the
  pinned AI Coach Notes expander; (d) direction filter dropped per
  spec's filter list (column kept); (e) coach notes + Ask AI = existing
  ai_trade_chat component (test-pinned), not a new tl-ai-card block;
  (f) screenshot cap via width=460 (no height cap API). st.toast icons
  ✅→✓. Sandbox smoke ALL PASS (pins, bans, line lengths, no dup keys,
  filter parity vs SQL). ruff/black not installed in sandbox → local.

- 2026-07-07 — Phase 6 (Insights & Review, 6_Insights.py) COMPLETE.
  Header → render_section_header + inject_design_system() (after
  inject_css, so ds wins ties). Empty state → render_empty_state +
  page_link wrapped try/except → /NewTrade slug anchor (AppTest-safe).
  Pattern Insights: render_section_header + info banner "Reflective
  insights only, not trade signals." + 2-col tl-insight-card grid
  (variant strength/leak/neutral from insight type, icon ▲/▼/◆ —
  geometric glyphs outside banned emoji ranges) with
  render_badge("<Tier> confidence", "confidence-<tier>") in card head
  and "Evidence: based on N journaled trades" footer; all user values
  escape()d. Weekly Recap: _render_week_stats → render_kpi_card hero
  row (Trades|Win Rate|Net P&L|Profit Factor|Edge Leak) inside
  .tl-hero-wrap with recap_bg.png + rgba(13,15,17,0.72) overlay
  (module-level _recap_b64/_RECAP_STYLE, app.py hero pattern); PF:
  0 trades → None→"N/A", pf None w/ trades → inf→"∞"; edge leak sign
  preserved (negative = leak cost money). Char-by-char render bug:
  already fixed in current code (single st.markdown of complete
  content_md, no st.write-on-generator) — contract documented via
  comment on _render_review_body. Section markers "Weekly Recap"/
  "Daily Debrief" → render_section_header. Spec deviations: (a) recap
  headings stay "###" h3 — weekly._REQUIRED_SECTIONS test-pinned +
  prompts/ LOCKED (spec said "##"); (b) categorical confidence badges
  (Low/Medium/High) composed in-page on tl-insight-card CSS instead of
  render_insight_card — the pinned helper renders a float percentage,
  which would fake precision from categorical data; (c) Daily Debrief
  section otherwise untouched (test-pinned: generate_debrief,
  log_ai_usage "Daily Debrief", ins_dbf_* keys); (d) file stays
  6_Insights.py (test-pinned path). All pins kept: _auto_run_weekly,
  get_weekly_review(monday, uid), generate_weekly_review(\n ×2,
  _wk_err_, "couldn't run:", strategy_profile=_strategy. Sandbox smoke
  ALL PASS (py_compile, 40+ checks); 'signal' grep hits are all
  disclaimers/pinned "Pattern Signals" name — false positives. Manual
  ban-grep audit clean (no border accents/gradient text/backdrop-
  filter/!important/hex in page). Impeccable scripts unreachable →
  manual substitution (established precedent). ruff/black → local gate.

- 2026-07-07 — Phase 7 (Analytics, 4_Analytics.py) COMPLETE. Context7
  confirmed update_layout params current (merge semantics keep per-chart
  axis settings). _styled(): PLOTLY_TEMPLATE + plot/paper bg TL_SURFACE,
  font TL_TEXT, grid TL_BORDER showgrid, margin l16 r16 t32 b16 — spec
  hex == tokens exactly, no hardcoded hex. _chart(fig, key, title):
  single st.plotly_chart call site, config displayModeBar False, wrapped
  in st.container(border=True) — tl-form-card HTML wrap impossible
  around Streamlit elements AND stPlotlyChart is NOT in design_system's
  proven-selector set (doc lines 16-18) → bordered container is the
  version-safe card (deviation). All 8 chart keys an_* preserved. All
  blank areas → render_empty_state (spec icons 📏/🧠 kept — emoji ban is
  headings/page_icon only; others 📈📉🕐📅🗓📐🧩◆): equity, drawdown,
  session, dow, heatmap-else, rules, emotion, setup, range-empty (+
  page_link try/except → /NewTrade slug), filtered-empty (was
  st.warning). Worst Session: pnl >= 0 → label "Lowest Session" +
  delta_color="off" (danger only for truly negative). Setup leaderboard:
  st.dataframe → HTML .tl-table in .tl-form-card, Rank|Setup|Trades|
  Win Rate|Avg P&L|PF, ranked by compute_breakdown's total_pnl desc
  (spec omitted rank basis; Total P&L col dropped per spec's exact
  list); Win Rate ≥50% → pnl-pos else plain (red never for win rate);
  Avg P&L sign-colored mono; setup names escape()d; section subtitle
  no longer claims click-sortable. Sections 1-6 via render_section_
  header incl. new "Calendar View" section (was "📅 Calendar view"
  expander; render_calendar(df_raw) unchanged). inject_design_system()
  added after inject_css(). Leaderboard logic validated against real
  data/tradelens.db (20 trades, 4 setups, ranking asserted). Sandbox
  smoke ALL PASS (63 checks). plotly not importable in sandbox →
  Context7 used for API confirmation per spec. ruff/black/pytest →
  local gate.

- 2026-07-07 — Phase 8 (Strategy Profile, 5_Strategy.py) COMPLETE.
  Header → render_section_header + inject_design_system(). Active
  banner: tl-ai-card with strategy_banner.png + rgba(13,15,17,0.75)
  overlay (module _banner_b64/_BANNER_STYLE, cover/center), inline
  flex: name 1.35rem/600 (escape()d) + render_badge Active/success +
  "Last updated" date right-aligned muted (escape()d). No profile →
  render_banner("No strategy profile yet. Fill this in to unlock
  strategy-aware AI analysis.", "info") — replaced two inline-hex
  markdown banners (#2e7d32/#20808D etc. removed). Saved flash →
  st.toast icon ✓ (was inline green div w/ ✅); required-name +
  save-failure toasts ❌→✕. Starter button: type primary if no
  profile else secondary (ghost); key strategy_starter kept. Chips
  preview the SAVED profile via services.strategy parse helpers
  (parse_markets primary under Markets input, parse_timeframes →
  "Entry X"/"HTF Y" neutral under Timeframes, parse_setups primary,
  parse_list(setups_avoided) danger, parse_mistakes warning) — _chips()
  helper, render_chip_row(items, {c: variant}); validated against real
  DB active profile "Ayoub" (NQ/MNQ, Entry 1m/HTF 15m, 2+3+4 chips)
  and empty-profile paths (boot-safe). Rules/Setups/News/Mistakes → 8
  st.expanders inside the form (Entry Rules expanded=True, rest
  collapsed; textarea labels label_visibility="collapsed", labels kept
  unique for auto-keys). Form keys strategy_form + all
  upsert_strategy_profile kwargs unchanged. Spec deviations: (a) sticky
  save button skipped — needs unproven CSS selectors (proven-set rule);
  kept full-width type="primary" submit; (b) Identity tl-form-card =
  the st.form's own bordered container (HTML wrap impossible around
  widgets); (c) dark input styling already config-first
  (.streamlit/config.toml theme base=dark, secondaryBackgroundColor =
  TL_SURFACE) — no CSS added; (d) tl-ai-card carries the small "AI"
  corner tag (::before) — accepted, profile feeds AI analysis; (e)
  redundant page caption removed (subtitle covers it). Sandbox smoke
  ALL PASS (60 checks). sqlalchemy absent in sandbox → parse helpers
  exec'd standalone for validation. ruff/black/pytest → local gate.

### Phase 9 — Final QA (2026-07-07)
- theme.py dedupe: removed the 7 .tl-* classes duplicated by
  design_system.py (tl-kpi-card/-delta/-label/-value,
  tl-section-header/-subtitle/-title) + their hover/reduced-motion
  refs; kept the 8 theme-only classes (tl-chat-ai/-user,
  tl-empty-cta/-icon/-message/-state, tl-grade-chip,
  tl-killzone-badge). design_system.py is now single source of truth
  for KPI/section markup (its docstring anticipated this removal).
- 9_Settings.py: added inject_design_system() after inject_css()
  (was the only page rendering tl-section-header without it — dedupe
  blocker); swapped 4 old-palette hardcoded-hex status boxes
  (#2e7d32/#20808D/#A84B2F/#7bd88f/...) to CSS vars
  (--tl-success[-dim], --tl-primary[-dim], --tl-danger[-dim]).
- Contrast fixes (deferred from Phase 4; not test-pinned):
  TL_TEXT_MUTED #6b7280→#848d9c (3.75:1→5.42:1 on SURFACE, 5.0:1 on
  SURFACE_2); TL_TEXT_FAINT #3d4451→#79828f (1.85:1→4.67:1 on
  SURFACE). Hierarchy preserved: text > muted > faint. Pinned tokens
  (TL_BG/TL_SURFACE/TL_PRIMARY) untouched.
- _archive/0_Home.py: border-left:3px side-stripe → full 1px border
  (impeccable hard ban; file is archived/unregistered but in scan
  tree).
- Detect (manual ban-grep substitution, Impeccable scripts still
  unreachable): CLEAN after fixes — no side-stripes, gradient text,
  backdrop-filter, !important, z-index 999+, lorem, signal language,
  or hardcoded hex in pages/.
- 10-item app checklist verified statically (all code paths present;
  visual run = owner's local gate). "Never red checkboxes" note:
  st.checkbox opt-in Apply flow is deliberate (Phase 4, test-pinned
  should_autocheck); renders TEAL via config.toml primaryColor.
- Sandbox smoke: py_compile OK ×4 edited files, line lengths OK
  (theme.py:144 >88 is pre-existing/untouched), polish contracts OK.
  pytest/ruff/black/streamlit run → owner's local gate.
- 2026-07-07: Owner confirmed local gate passed (pytest, ruff, black,
  streamlit run). Phase 9 closed — PREMIUM UI/UX POLISH BUILD complete.
