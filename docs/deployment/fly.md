# Fly.io deployment

This project deploys the pick'em web app as a Docker container on Fly.io with:

- a mounted SQLite volume at `/data`
- auth secrets stored in Fly, not in the image
- CI on every PR/push
- production deploys only from `main`

## One-time setup

Install and sign in to `flyctl`, then create the app and the persistent SQLite volume:

```bash
fly auth login
make fly.app
make fly.volume
```

If `make fly.*` reports `fly: command not found`, install Fly CLI or add the default install location to your shell:

```bash
curl -L https://fly.io/install.sh | sh
export PATH="$HOME/.fly/bin:$PATH"
```

You can also pass an explicit binary path:

```bash
make fly.secrets FLY=$HOME/.fly/bin/fly
make fly.deploy FLY=$HOME/.fly/bin/fly
```

Equivalent raw commands:

```bash
fly apps create ffpy-pickem
fly volumes create ffpy_data --app ffpy-pickem --region iad --size 1
```

Fly will warn that a volume is pinned to a specific physical host:

```text
Warning! Every volume is pinned to a specific physical host. You should create two or more volumes per application to avoid downtime.
? Do you still want to use the volumes feature? (y/N)
```

For this app, answer `y` if you are deploying the current SQLite-backed service. The warning is about high availability, not data correctness. This setup intentionally uses one mounted SQLite database at `/data/ffpy.db`, so the app should run as a single persistent service.

Do not create extra volumes expecting SQLite data to replicate automatically. Multiple Fly volumes are independent disks. For high availability later, use one of these designs instead:

- move shared state to Supabase/Postgres
- add a real SQLite replication layer such as LiteFS
- run separate regional apps with an explicit data sync/restore process

## Environment happy path

`make bootstrap` seeds `.env` from `.env.example` on first run. To do it manually:

```bash
cp .env.example .env
```

### 1. Fill required keys in `.env`

From your Supabase dashboard (Project Settings → API):

| Variable | Where to find it | Required |
|----------|------------------|----------|
| `SUPABASE_URL` | Project URL — `https://<project-ref>.supabase.co` | Yes |
| `SUPABASE_PUBLISHABLE_KEY` | API Keys → Publishable key | Yes (preferred) |
| `SUPABASE_ANON_KEY` | Legacy API Keys → anon key | Only if no publishable key |
| `PUBLIC_APP_URL` | Set to `https://ffpy-pickem.fly.dev` for production secrets | Yes for prod |

Optional in `.env` (usually leave blank):

- `SUPABASE_JWKS_URL` — defaults to `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`
- `SUPABASE_JWT_SECRET` — local HS256 dev tokens only; production uses JWKS

Do **not** put `FLY_API_TOKEN` in `.env` — that token is for GitHub Actions only (see [Deploy via CI](#deploy-via-ci) below).

### 2. Verify locally

```bash
make supabase.check
```

### 3. Push runtime secrets to Fly

After the Fly app exists:

```bash
make fly.secrets
```

The `fly.secrets` target reads values from `.env` or your current shell, sets production-safe defaults for `WEB_AUTH_ENABLED`, `DATABASE_PATH`, `SUPABASE_JWT_AUDIENCE`, and `SUPABASE_FETCH_USER_ON_VERIFY`, includes JWT/JWKS override values only when you provided them, and generates `ABUSE_HASH_SALT` if it is missing.

If you want a local-only dev token flow instead of Supabase browser sign-in, do not use `make fly.secrets`; set only the local-token secrets intentionally:

```bash
fly secrets set --app ffpy-pickem \
  WEB_AUTH_ENABLED=true \
  SUPABASE_JWT_SECRET=<your-local-hs256-secret> \
  SUPABASE_FETCH_USER_ON_VERIFY=false
```

## Deploy

```bash
make fly.deploy
```

Useful deploy commands:

```bash
make fly.status
make fly.logs
```

The GitHub Actions workflow in [.github/workflows/ci-cd.yml](../../.github/workflows/ci-cd.yml) runs lint + tests + Docker build on every PR and push to `main`, then deploys to Fly only on `main`.

### Deploy via CI

Merges to `main` auto-deploy when CI passes. Create a deploy token once:

```bash
make fly.token
```

Add the printed token to GitHub → **Settings** → **Environments** → **production** → **Environment secrets** → `FLY_API_TOKEN`.

(Repo-level **Actions secrets** also works; the workflow uses the `production` environment.)

Manual deploy from your machine does not need this token — use `fly auth login` and `make fly.deploy`.

## Supabase auth redirects (production)

Email confirmation links must return to the deployed app, not `localhost`. Configure both sides:

**Fly** — `PUBLIC_APP_URL` is set in `fly.toml` (`https://ffpy-pickem.fly.dev`) and via `make fly.secrets`. Redeploy after changing it.

**Supabase dashboard** → **Authentication** → **URL Configuration**:

| Setting | Value |
|---------|--------|
| Site URL | `https://ffpy-pickem.fly.dev/league/` |
| Redirect URLs | `https://ffpy-pickem.fly.dev/**` |

Also add `http://localhost:8080/**` if you test locally against the same Supabase project.

The league app passes `emailRedirectTo: …/league/` on sign-up so verification emails land back on the League Manager.

## Security notes

- Keep `FLY_API_TOKEN` only in GitHub Actions secrets or your local shell.
- Keep `SUPABASE_*` and `ABUSE_HASH_SALT` in Fly secrets.
- Leave `WEB_AUTH_ENABLED=true` in production so the app fails closed if auth is not configured.
- The SQLite file lives on the Fly volume at `/data/ffpy.db`; without the volume the app will start but data will not persist.
