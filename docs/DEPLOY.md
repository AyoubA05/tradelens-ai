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

## Legacy ownership assignment

1. Create a database backup/snapshot.
2. Dry run:
   `.venv/bin/python scripts/assign_legacy_data.py --username ayoub`
3. Review every count.
4. Apply only after approval:
   `.venv/bin/python scripts/assign_legacy_data.py --username ayoub --apply`
5. Run the dry run again; expected count for every table is 0.

## Public funnel release gate

An anonymous visitor must be able to go from the marketing site to the
TradeLens sign-in screen without meeting anyone else's login wall. Both
failure modes below shipped once and neither was visible from the repo,
so this gate is checked against the live hosts.

There is no custom domain yet, so the canonical origin is the Vercel URL.
It is set in two independent places that do not follow each other:

| Setting | Where | Controls |
|---|---|---|
| `SITE_ORIGIN` | `vercel.json` → `build.env` | the site's own canonical, OG, and JSON-LD URLs |
| `TRADELENS_SITE_URL` | Streamlit secrets/env | the app auth screen's link back to the site |

Both need changing when a domain is finally pointed at the deployment.
Fixing one does not fix the other.

> **Note on the current value.** `…-6b0eiih51-…` is a *deployment-specific*
> URL: it is pinned to one build and will not follow future pushes to
> main. That is fine while the origin is only being used to make metadata
> resolvable, but the canonical URL will keep pointing at this snapshot as
> newer deployments go out. The `…-git-main-…` alias tracks the latest
> deploy if that becomes the more useful behaviour.

1. Vercel Production Deployment Protection: Off.
2. `SITE_ORIGIN` matches the origin the site is actually served from, so
   the canonical, OG, and JSON-LD URLs point at a reachable page.
3. Streamlit app visibility is Public, so anonymous visitors reach the
   TradeLens auth screen rather than `share.streamlit.io/-/auth`.
4. Run:

   ```bash
   .venv/bin/python scripts/verify_public_funnel.py \
     --site https://tradelens-ai-site-6b0eiih51-ayouba05s-projects.vercel.app \
     --app https://tradelens-app.streamlit.app
   ```

5. Expected: two PASS lines and exit code 0.

Items 1-3 are dashboard settings that code cannot change. The verifier
only reports them.

### Known-failing today

The marketing check passes. The app check reports, correctly, that
anonymous visitors are redirected to Streamlit provider auth.

That is not fixable in code: set the Streamlit app's visibility to Public
so visitors reach the TradeLens sign-in screen instead.
