# Deploying the API (Render)

This covers first deploy of the FastAPI backend (`Dockerfile.api`, `render.yaml`)
to Render, alongside the Next.js website on Vercel and the database on Neon.

The API is deployed as a Render **web** service, not a private one. Vercel
functions egress from dynamic addresses outside Render's private network, so a
private service would simply be unreachable from the website. Render is
treated as an internet-exposed backend and defended at the application layer —
`TL_SERVICE_SECRET` plus database-backed session validation — rather than by
network topology. See the comment block at the top of `render.yaml` before
"fixing" this.

## 1. Generate `TL_SERVICE_SECRET`

```bash
openssl rand -hex 32
```

Set the result as `TL_SERVICE_SECRET` in **both**:
- Render → tradelens-api → Environment
- Vercel → website project → Environment Variables

The values must be byte-for-byte identical. If they diverge, every
website→API request 401s (the API checks the presented secret against
`TL_SERVICE_SECRET` and, during rotation, `TL_SERVICE_SECRET_PREVIOUS`).

## 2. Rotating `TL_SERVICE_SECRET`

Rotation is two-step so it never requires both sides to change at the same
instant (which would mean an outage):

1. Generate a new secret. On Render, move the *current* value of
   `TL_SERVICE_SECRET` into `TL_SERVICE_SECRET_PREVIOUS`, then set
   `TL_SERVICE_SECRET` to the new value. Redeploy the API.
2. Update `TL_SERVICE_SECRET` on Vercel to the new value and redeploy the
   website.
3. Once you've confirmed the website is using the new secret (no 401s), clear
   `TL_SERVICE_SECRET_PREVIOUS` on Render and redeploy the API again.

Skipping step 3 leaves the old secret valid indefinitely.

## 3. Create the private R2 bucket

In the Cloudflare dashboard: R2 → Create bucket. The bucket must be:
- **Private** — no public access enabled.
- No public bucket listing.
- No R2.dev / custom-domain public website endpoint attached.

All access goes through the API using signed requests, never direct browser
access to R2.

Create an R2 API token scoped to that bucket only (Object Read & Write), and
set on Render:

- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET`

## 4. Run migrations against Neon before first deploy

The API container does not run migrations on boot. Before the first deploy
(and before any deploy that ships a new migration), run from a machine with
network access to the Neon database:

```bash
DATABASE_URL="postgresql://USER:PASSWORD@ep-xxxx.REGION.aws.neon.tech/DBNAME?sslmode=require" \
  alembic upgrade head
```

Use the same `DATABASE_URL` you set on Render — the API and the migration
must target the same database. Every migration in this repo implements
`downgrade()`, so `alembic downgrade -1` is available if a migration needs to
be rolled back.

## 5. Deploy

Push `render.yaml` to the branch Render is configured to deploy, or trigger a
manual deploy of both services (`tradelens-api`, `tradelens-worker`) from the
Render dashboard. Both services build from the same `Dockerfile.api`; the
worker overrides the container command with `dockerCommand`.

Confirm the API is healthy:

```bash
curl -fsS https://<your-render-service>.onrender.com/health
```

Expected: `{"status":"ok"}`.

## 6. Set `TL_API_ORIGIN` on the website

On Vercel, set `TL_API_ORIGIN` to the API's Render URL
(`https://<your-render-service>.onrender.com`). This is server-side only and
must never be exposed to the browser — the website's server-side code calls
the API, the browser never talks to Render directly.
