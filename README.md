<!-- Badges (HTML img so they are not markdown screenshot links) -->
<p>
  <img src="https://github.com/AyoubA05/tradelens-ai/actions/workflows/ci.yml/badge.svg" alt="CI status">
  <img src="https://img.shields.io/badge/coverage-92%25-brightgreen" alt="Service coverage 92%">
  <img src="https://img.shields.io/badge/python-3.11-blue" alt="Python 3.11">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT">
  <img src="https://img.shields.io/badge/Streamlit-1.50-FF4B4B" alt="Streamlit 1.50">
</p>

# TradeLens AI

**A post-trade reflection journal and analytics dashboard for SMC/ICT day traders — it reviews every chart, grades your process against your own rules, and learns your corrections.** Not a signal app, not a bot, not financial advice.

**Live demo:** _pending deploy_ <!-- LIVE_URL: replace this line with the live https://<app>.streamlit.app URL after Streamlit Cloud deploy --> · runs in `DEMO_MODE` (cached AI, zero API spend).

<!-- screenshot: dashboard — full home dashboard with KPI glass cards, equity curve, and Trade of the Week. Replace after Streamlit Cloud deploy. -->

---

## What makes TradeLens different

Most journals store outcomes. TradeLens models the *process* behind them, with structure a generic journal can't express:

- **SMC/ICT-native schema** — first-class fields for HTF bias, killzones, liquidity sweeps, FVGs, order blocks, BOS/CHoCH, confirmation model, and entry type. Not free-text notes — queryable columns that power analytics.
- **Strategy-aware grading** — trades are graded A–F on *process*, scored against the rules in *your* Strategy Profile, not a generic checklist.
- **Correction memory** — every time you edit an AI label, the change is stored and injected as few-shot context into future calls, so the model stops repeating mistakes you've already corrected.
- **Weekly AI review** — a structured 5-section retrospective over the last 7 days, with the model's reasoning surfaced in a "How the AI reasoned" expander.
- **AI Partner Mode** — a multi-turn chat that reviews completed trades in precise SMC/ICT language, hard-scoped against signals or predictions.
- **Edge-leak & consistency analytics** — quantifies what rule-breaks cost you and scores process consistency 0–100.

---

## Architecture

```mermaid
flowchart LR
    User([Trader]) --> UI["Streamlit UI<br/>pages + components"]
    UI --> SVC["services/<br/>business logic"]
    SVC --> AIC["ai_client.py<br/>single Anthropic wrapper"]
    AIC -->|claude-fable-5| API[(Anthropic API)]
    SVC --> DB[("SQLite<br/>SQLAlchemy + Alembic")]
    SVC --> CHARTS["Plotly charts"]
    CHARTS --> UI
```

Pages only render and call services; **all** business logic lives in `services/`, and **all** AI calls route through one audited `ai_client.py` (no page ever calls the API directly). Database access is SQLAlchemy 2.x over SQLite (Postgres-ready), with every schema change shipped as a reversible Alembic migration.

---

## Features

| Feature | What it does | Screenshot |
|---|---|---|
| New Trade | Log a trade with full SMC/ICT fields; killzone auto-fills from entry time | <!-- screenshot: new-trade — the New Trade form with SMC/ICT expander and killzone auto-fill --> |
| Trade Detail | Two-column review: chart left, AI analysis + journal + grade right | <!-- screenshot: trade-detail — two-column layout with grade chip and rubric --> |
| Analytics | Equity curve, drawdown, killzone performance, edge leak, consistency, AI pattern cards | <!-- screenshot: analytics — KPI row + killzone performance + pattern insights --> |
| Calendar | Monthly P&L heatmap with day drill-down and grade chips | <!-- screenshot: calendar — month heatmap with day detail --> |
| Weekly Review | 5-section AI retrospective with reasoning expander | <!-- screenshot: weekly-review — 5-section report --> |
| AI Partner | Multi-turn SMC/ICT review of a completed trade | <!-- screenshot: ai-partner — chat bubbles reviewing a trade --> |
| Settings | CSV import/export, monthly AI cost dashboard | <!-- screenshot: settings — AI cost table --> |

---

## Quickstart

```bash
git clone https://github.com/AyoubA05/tradelens-ai.git && cd tradelens-ai
pip install -r requirements.txt
python -m src.tradelens.db.init_db
alembic upgrade head          # apply schema migrations to an existing DB
streamlit run src/tradelens/ui/app.py
```

### Login

The app is gated by a sign-in page. Credentials come from Streamlit secrets / environment:

```toml
# .streamlit/secrets.toml  (or .env)
TRADELENS_USERNAME = "demo"
TRADELENS_PASSWORD = "tradelens2025"
```

If you don't set them, the app falls back to **`demo` / `tradelens2025`** so the public demo stays usable. Set your own values in production. The **Sign out** button lives at the bottom of the sidebar.

### Enable AI

This app uses **Anthropic**. Add the key named `ANTHROPIC_API_KEY`:

- **Streamlit Cloud** → App Settings → Secrets → `ANTHROPIC_API_KEY = "your-key-here"`
- **Locally** → add it to `.streamlit/secrets.toml` or `.env`, then restart.

Settings → **AI Status** shows whether the key is detected, with step-by-step instructions. Prefer to explore first? Set `DEMO_MODE=true` and the whole app runs on cached AI output at zero API cost (see [Demo Mode](#demo-mode)).

---

## AI Prompt Architecture

Six prompts power six features. Each is a locked contract in `prompts/` — versioned, never rewritten in place, only extended. Every prompt below is also wrapped by a central **correction few-shot** block (`<past_corrections>`): the trader's most-repeated and most-recent label edits, de-duplicated and capped at ~800 tokens, injected into *every* call so the model converges on the user's labeling over time. The design goal across all six is the same: deterministic pre-processing in Python wherever possible, then a single well-shaped model call with a strict output contract the service can validate.

### A — Screenshot Vision (`prompts/screenshot_v2.txt` → `services/vision.py`)
**Problem:** turn a raw chart image into structured, reviewable SMC/ICT labels after a trade has closed. **Input:** the resized chart (≤1024px, base64 JPEG), the trade context, and the active strategy profile. **Output contract:** a single JSON object — bias and confidence, market structure, BOS/CHoCH booleans, a list of key zones, and four SMC *proposals* (HTF bias, liquidity sweep, FVG, order block) that pre-fill editable widgets but are never auto-applied. **Token strategy:** one `claude-fable-5` vision call; the image is downscaled before encoding to cap input tokens, and `response_format=json_object` removes parse retries. Malformed JSON is caught and surfaced as a typed error, never a crash.

### B — Journal Generation (`prompts/journal_v1.txt` → `services/journal.py`)
**Problem:** produce a consistent, reflective write-up from confirmed labels so journaling isn't a blank page. **Input:** the trade dict plus the user-confirmed AI labels and strategy profile. **Output contract:** an 8-section markdown document — Trade Summary, Market Bias, Strategy Used, What Went Well, What Went Wrong, Missed Opportunities, Emotional Review, Improvement Plan — validated for presence *and* order before persistence. **Token strategy:** a single `claude-fable-5` call; because the labels are already structured upstream, the prompt carries no image and stays text-light. The strict section contract means the UI can render the result verbatim with no post-processing.

### C — Process Grading (`prompts/grade_v1.txt` → `services/grading.py`)
**Problem:** grade *process quality*, not outcome — a winning trade can be a bad process and vice-versa. **Input:** the trade, the confirmed vision labels, and the strategy rules (or a generic ICT fallback). **Output contract:** JSON with a letter `grade`, numeric `score`, a `one_line_verdict`, and a `rubric` of exactly five dimensions (entry quality, risk management, exit quality, rule adherence, emotional control), each with its own score and note — all validated. **Token strategy:** this is the one feature routed to **`claude-haiku-4-5`**, a deliberate cost optimization — grading is a bounded, rubric-shaped task that a smaller model handles well at a fraction of the price of the primary model.

### D — Weekly Review (`prompts/weekly_v2.txt` → `services/weekly.py`)
**Problem:** summarize a week of trading into an actionable retrospective. **Input:** the last 7 days of trades with metrics, detected patterns, and the correction few-shot — all pre-aggregated in pandas so the model reasons over numbers, not raw rows. **Output contract:** a 5-section markdown report (What Worked, What Didn't, Killzone Review, Rule Adherence, Focus for Next Week), validated for completeness. **Token strategy:** a single `claude-fable-5` call run at **`effort="high"`** with the thinking summary captured and shown in a "How the AI reasoned" expander. A zero-trade week short-circuits before any API call — no spend on empty input.

### E — Pattern Detection (`prompts/patterns_v2.txt` → `services/patterns.py`)
**Problem:** surface behavioral edges and leaks without hallucinating from sparse data. **Input:** a deterministic pandas pre-pass computes candidate statistics (killzone win rates, streaks, mistake clusters, rule-violation cost); only those numbers go to the model. **Output contract:** at most six JSON cards, each with an insight, an evidence stat, sample size, confidence, impact, and a suggested rule; cards under five samples are labeled "early signal — low sample." **Token strategy:** the deterministic pre-pass keeps the prompt small and grounds every claim in a real statistic, so a single `claude-fable-5` call produces reflection, never prediction.

### F — AI Partner (`prompts/partner_v2.txt` → `services/partner.py`)
**Problem:** let a trader interrogate a completed trade conversationally, with a senior partner's SMC/ICT vocabulary — and never drift into giving signals. **Input:** the trade context, vision analysis, the prompt-cached strategy profile, the correction few-shot, and the trimmed chat history. **Output contract:** a conversational reply; a hard scope guard lives in the system prompt and a post-check replaces any signal-seeking answer with a redirect. **Token strategy:** the strategy profile is sent with `cache_control` so multi-turn conversations bill it at cache rates; history is trimmed to the last 10 turns with a running summary; the call runs at `effort="medium"`. Per-conversation token and cost are displayed in the UI.

---

## Demo Mode

Set `DEMO_MODE=true` (env var or `.streamlit/secrets.toml`) and the entire app runs on cached, synthetic output:

- A deterministic 60-trade dataset (`services/demo.py`) renders the dashboard, analytics, and calendar with **zero database writes**.
- Every AI feature returns a cached fixture (`tests/fixtures/demo_ai/`), keyed by trade with a default fallback — **zero API calls, zero spend**, guaranteed by a short-circuit in `ai_client._complete()` before any network access.
- A banner on every page makes the demo state explicit.

This is what the public deployment runs on, so visitors never spend the owner's API budget.

---

## Roadmap

Post-MVP, intentionally out of scope today:

- **Broker import** — auto-sync fills from broker APIs / statements.
- **Mobile** — a responsive or native companion for on-the-go review.
- **Multi-user** — accounts, auth, and per-user Postgres isolation.

---

## License

MIT. See [LICENSE](LICENSE).
