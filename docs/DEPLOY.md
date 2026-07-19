# Deploying TradeLens AI to Streamlit Community Cloud

This guide takes you from a fork to a live, public URL running in **DEMO_MODE**
(cached AI output, **zero real API calls** — safe for a public portfolio link).

---

## 1. Prerequisites

- A **GitHub account** with this repo (or a fork) pushed to it.
- A free **Streamlit Community Cloud** account — sign in at
  [share.streamlit.io](https://share.streamlit.io) with GitHub.
- (Optional) An **Anthropic API key** — only needed if you want *live* AI
  instead of the cached demo. Get one at
  [console.anthropic.com](https://console.anthropic.com/).

---

## 2. Get the repo onto your GitHub

Fork it (button, top-right of the GitHub repo), **or** push your own clone:

```bash
git clone https://github.com/AyoubA05/tradelens-ai.git
cd tradelens-ai
# (already pushed to your own GitHub if you forked)
```

---

## 3. Create the app on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) → **Create app** →
   **Deploy a public app from GitHub**.
2. **Repository:** `your-username/tradelens-ai`
3. **Branch:** `main`
4. **Main file path:** `src/tradelens/ui/app.py`
   *(This is the entry point. Streamlit auto-discovers the sidebar pages from
   `src/tradelens/ui/pages/` next to it — Home, New Trade, Trades, Trade Detail,
   Analytics, Strategy, Calendar, Weekly Review, AI Partner, Settings.)*
5. **Python version:** under **Advanced settings**, select **3.11** (matches
   `runtime.txt` and CI).

The selected branch must contain the root `requirements.txt`. Community Cloud
looks beside the entry point first, then at the repository root; this repo uses
the root file. Before deploying Postgres support, merge
`sp2-postgres-foundation` into the selected branch so that
`psycopg2-binary==2.9.9` and the dialect-aware database engine are present in
the exact Git revision Community Cloud installs.

---

## 4. Add secrets

In **Advanced settings → Secrets**, paste the contents of
[`.streamlit/secrets.toml.template`](../.streamlit/secrets.toml.template) and
edit the values. For a public demo, the defaults are exactly right:

```toml
DEMO_MODE = "true"
ANTHROPIC_API_KEY = "sk-ant-YOUR-KEY-HERE"
```

**Keys must stay top-level (no `[section]` headers).** Streamlit only exports
top-level scalar secrets as environment variables, and the app reads
`st.secrets["ANTHROPIC_API_KEY"]` plus the `DEMO_MODE` env var. Nesting them
would silently disable the key *and* demo mode.

- `DEMO_MODE = "true"` → the whole app runs on cached fixtures, **no API spend**.
- To enable live AI: set `DEMO_MODE = "false"` and paste a real
  `ANTHROPIC_API_KEY`. (Every visitor would then spend *your* budget — keep it
  `"true"` for a public link.)

---

## 5. Deploy & verify

1. Click **Deploy**. First build installs `requirements.txt` on Python 3.11
   (~1–2 min).
2. When it loads, you should land on the **dashboard** with sample data and a
   teal **"Demo mode"** banner at the top of every page.
3. Click through the sidebar and confirm each page renders without error:
   Home · New Trade · Trades · Trade Detail · Analytics · Strategy · Calendar ·
   Weekly Review · AI Partner · Settings.
4. On an AI page (e.g. Weekly Review), confirm the cached AI output appears and
   no spinner hangs — that proves DEMO_MODE is active.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` on boot | Missing dep / wrong Python | Confirm Python **3.11** in Advanced settings; `requirements.txt` installed cleanly. |
| `ModuleNotFoundError: No module named 'psycopg2'` | The deployed branch predates Postgres support, or its environment was built before the dependency reached that branch. | Confirm the app is configured for `src/tradelens/ui/app.py` and a branch whose root `requirements.txt` contains `psycopg2-binary==2.9.9`. Push/merge that branch, then open the app menu and click **Reboot app** so dependencies are re-resolved. Plain `postgresql://` is correct: SQLAlchemy selects its `psycopg2` dialect automatically. |
| `KeyError: 'ANTHROPIC_API_KEY'` or AI says "API key not configured" | Key nested under a `[section]` | Move `ANTHROPIC_API_KEY` to **top level** in Secrets. |
| App makes real API calls / unexpected spend | `DEMO_MODE` not applied | Ensure `DEMO_MODE = "true"` is **top-level** in Secrets (not under `[general]`). Reboot the app. |
| "main module does not exist" | Wrong entry path | Main file path must be `src/tradelens/ui/app.py`. |
| Data resets between visits | SQLite is ephemeral on Cloud | Expected — the cloud filesystem is not persistent. DEMO_MODE uses synthetic data, so this is invisible to visitors. |
| Pages missing from sidebar | Pages not beside entry | They live in `src/tradelens/ui/pages/`; deploy from repo root so the relative path resolves. |

---

## 7. After deploy

Copy the live URL (e.g. `https://<your-app>.streamlit.app`) into the README's
**Live demo** line and the badge. Re-run CI is not required — deployment is
independent of the test pipeline.
