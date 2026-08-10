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

The two endpoints have different contracts, and the gate checks them
against the live hosts because neither failure is visible from the repo.

**The marketing site must be public.** An anonymous visitor has to see the
current build, with no login wall in front of it. Both halves have failed
before: an origin serving an older, differently positioned build, and
Vercel deployment protection hiding the site behind SSO.

**The app is gated on purpose.** Requiring sign-in is intended behaviour,
so the verifier treats a redirect to the Streamlit login as a pass — as
long as it *routes back*, i.e. carries a `redirect_uri` pointing at this
app so signing in returns the visitor to TradeLens. A redirect that drops
the destination, points at a different app, or a host that is down, still
fails.

The canonical origin is `https://www.tradelensai.io`. The apex
(`tradelensai.io`) redirects to `www`, so `www` is the canonical host and
`SITE_ORIGIN` must match it — pointing canonical URLs at a host that
redirects is a needless hop for crawlers and social scrapers.

It is set in two independent places that do not follow each other:

| Setting | Where | Controls |
|---|---|---|
| `SITE_ORIGIN` | `vercel.json` → `build.env` | the site's own canonical, OG, and JSON-LD URLs |
| `TRADELENS_SITE_URL` | Streamlit secrets/env | the app auth screen's link back to the site |

Both need changing when a domain is finally pointed at the deployment.
Fixing one does not fix the other.

> **If the domain changes again.** Update `SITE_ORIGIN` here *and*
> `TRADELENS_SITE_URL` on the Streamlit app, and confirm which of apex or
> `www` Vercel treats as canonical — whichever one does not redirect is the
> value both settings need.

### Checklist

1. Vercel Production Deployment Protection: **Off** — otherwise the
   marketing check fails, by design.
2. `SITE_ORIGIN` matches the origin the site is actually served from, so
   the canonical, OG, and JSON-LD URLs point at a reachable page.
3. Run:

   ```bash
   .venv/bin/python scripts/verify_public_funnel.py \
     --site https://www.tradelensai.io \
     --app https://tradelenai.streamlit.app
   ```

4. Expected: two PASS lines and exit code 0.

Items 1 and 2 are settings that code cannot change. The verifier only
reports them.

## Build inputs

`scripts/build_site.py` resolves three tokens and refuses to produce a
publishable site if any is missing or malformed. They are set under
`build.env` in `vercel.json`, or in the Vercel dashboard.

| Variable | Purpose | Where it is set |
|---|---|---|
| `SITE_ORIGIN` | canonical, OG, and JSON-LD URLs | `vercel.json` |
| `APP_ORIGIN` | every CTA link to the app | `vercel.json` |
| `SUPPORT_EMAIL` | contact address on `/privacy`, `/terms`, and the footer | **Vercel dashboard — not committed** |

> **The build fails until `SUPPORT_EMAIL` is set.** This is deliberate. The
> privacy and terms pages carry a contact address, and publishing a policy
> nobody can reply to is worse than publishing none. Add it under
> Project Settings → Environment Variables → Production, then redeploy.

## Outgoing email (password reset)

Password reset needs SMTP. Until it is configured, a reset request tells
the user we could not send the message and to contact support — it never
pretends to have sent one. For a small cohort, handling those by hand is a
reasonable interim position.

Set these in the Streamlit app's secrets (not on Vercel — this is the app,
not the site):

| Variable | Example | Notes |
|---|---|---|
| `TRADELENS_SMTP_HOST` | `smtp.gmail.com` | required |
| `TRADELENS_SMTP_PORT` | `587` | defaults to 587 |
| `TRADELENS_SMTP_USER` | `you@gmail.com` | optional; omit for a relay that needs no auth |
| `TRADELENS_SMTP_PASSWORD` | app password | see below |
| `TRADELENS_SMTP_FROM` | `TradeLens <you@gmail.com>` | required |

`email_configured()` is true only when `HOST` and `FROM` are both present.

### Gmail specifically

Gmail rejects your normal account password over SMTP. You need an app
password:

1. Enable 2-Step Verification on the Google account.
2. Go to Google Account → Security → 2-Step Verification → App passwords.
3. Create one for "Mail", and copy the 16-character value.
4. Use that as `TRADELENS_SMTP_PASSWORD`, with your address as
   `TRADELENS_SMTP_USER`.

Gmail applies a daily send limit. That is irrelevant at cohort scale and
would matter well before any real growth — swap in a transactional relay
before it does.

### Also set

`TRADELENS_SESSION_SECRET` should be set on the app. Reset tokens are
signed with it, so without it they stop working whenever the app restarts.
