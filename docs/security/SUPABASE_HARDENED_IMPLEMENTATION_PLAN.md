# Supabase Hardened Implementation Plan

This document scaffolds a practical, security-first path for taking the pick'em strategy tester from a local demo to a public demo with:

- email/password login
- verified-email access gating
- basic anti-spam and anti-abuse controls
- interaction logging for cost protection
- a rollout path that fits the current FFPy codebase

It is intentionally biased toward shipping a safe v1 quickly, then hardening in layers.

## Executive Summary

Recommended starting stack:

- App hosting: Google Cloud Run
- Primary web database and auth: Supabase
- CAPTCHA / bot friction: Cloudflare Turnstile
- Rate limiting store: Upstash Redis
- Transactional email: Supabase Auth built-in mailer for v1, optional Resend later

Why this shape:

- Supabase gives us hosted auth, verified-email workflows, Postgres, and row-level security.
- Cloud Run keeps compute costs tied to real usage and is easy to lock down.
- Turnstile stops low-effort signup and login spam.
- Upstash lets us add fast IP and user rate limits without overloading Postgres.

## Codebase Constraints

The current public app is in [src/ffpy/pickem_web.py](/home/ricka/Git/FFPy/src/ffpy/pickem_web.py:1) and currently depends on the SQLite-specific `FFPyDatabase` wrapper in [src/ffpy/database.py](/home/ricka/Git/FFPy/src/ffpy/database.py:1).

That matters because:

- `FFPyDatabase` uses `sqlite3` directly
- current migrations are written for SQLite workflows
- `Backtester` currently assumes a database object with SQLite-backed methods and persistence

Do not try to make `FFPyDatabase` directly talk to Supabase.

Instead:

1. keep the local SQLite path for local analysis and tests
2. introduce a small historical-data repository interface for the web app
3. add a Postgres/Supabase implementation for public deployment

This keeps the auth rollout smaller and avoids turning the existing local workflow upside down.

## Security Goals

V1 goals:

- require verified email before any expensive backtest actions
- throttle signup, login, and backtest endpoints
- log enough interaction metadata to investigate abuse
- cap per-user and per-IP usage to prevent cost spikes
- keep secrets and privileged keys server-side only

Non-goals for v1:

- enterprise SSO
- MFA
- social auth
- full billing / subscriptions
- advanced fraud scoring

## Target Architecture

```text
Browser
  -> Vue app served by FastAPI
  -> Supabase auth session
  -> Turnstile on signup / suspicious login

FastAPI on Cloud Run
  -> verifies Supabase JWT/session
  -> checks email_verified gate
  -> checks Upstash rate limits
  -> logs usage event to Supabase Postgres
  -> reads historical games from Postgres repository
  -> runs backtest
  -> stores result metadata / optional cached result

Supabase
  -> auth.users
  -> public.user_profiles
  -> public.usage_events
  -> public.cached_backtests (optional v2)
  -> public.admin_blocks (optional v2)

Upstash Redis
  -> per-IP limits
  -> per-user limits
  -> temporary deny / cooldown keys
```

## Rollout Phases

### Phase 0: Deployment Foundation

Deliverables:

- containerized Cloud Run deployment for the FastAPI app
- Supabase project created
- Turnstile widget created
- Upstash Redis instance created
- production domain configured

Tasks:

- add a production Dockerfile if one does not already exist
- deploy FastAPI app to Cloud Run with `min-instances=0`
- set Cloud Run concurrency conservatively at first
- store secrets in Google Secret Manager or Cloud Run secrets
- configure CORS to only allow the production frontend origin

Acceptance criteria:

- app is reachable over HTTPS
- unauthenticated users can only see login / marketing shell
- no service-role secrets are exposed to the browser

### Phase 1: Auth Foundation

Deliverables:

- email/password signup
- email confirmation required before use
- sign in / sign out
- authenticated session in frontend

Tasks:

- create Supabase project and enable email/password auth
- keep "email confirmation required" enabled
- customize Supabase auth email templates for app branding
- add frontend auth views to the Vue app
- add server-side JWT verification in FastAPI
- add a `user_profiles` table for app-specific metadata

Acceptance criteria:

- unverified users cannot run backtests
- verified users can sign in and access protected routes
- deleted users lose access automatically

### Phase 2: API Gating And Role Separation

Deliverables:

- route-level auth dependency in FastAPI
- admin / normal-user split in app logic
- no anonymous access to costly endpoints

Tasks:

- add `get_current_user()` dependency
- add `require_verified_user()` dependency
- gate:
  - `/api/backtests/run`
  - `/api/backtests/compare`
  - any future optimizer endpoints
- leave lightweight metadata endpoints public only if safe
- separate server-only Supabase service-role usage from user-context access

Acceptance criteria:

- expensive endpoints return `401` for anonymous users
- expensive endpoints return `403` for unverified users
- service-role key is used only server-side

### Phase 3: Anti-Abuse Controls

Deliverables:

- signup/login friction
- endpoint rate limiting
- usage quotas
- deny / cooldown support

Tasks:

- require Turnstile on signup
- require Turnstile after repeated failed logins
- add Upstash-backed limits:
  - signup per IP
  - login failures per IP
  - backtest runs per verified user
  - compare runs per verified user
  - daily cost units per user
- add a short cooldown on repeated denials
- optionally restrict access to allowlisted domains during private beta

Suggested v1 limits:

- signup: 3 attempts per IP per 24 hours
- failed login: 5 per IP per 15 minutes
- backtest runs: 10 per user per hour
- compare runs: 3 per user per hour
- daily backtest cost budget: 100 cost units per user

Cost unit suggestion:

- single-season, single-strategy run: 1 unit
- multi-season run: 2 to 5 units based on window
- compare endpoint: number of strategies times season-window factor

Acceptance criteria:

- obvious bot signup bursts are blocked
- repeated expensive calls from one user are throttled
- operators can temporarily block abusive users without code deploys

### Phase 4: Observability And Incident Response

Deliverables:

- usage event trail
- admin visibility into abuse
- basic alerting on spikes

Tasks:

- write one `usage_events` row per protected action
- track success / denial / error outcomes
- track latency and estimated cost units
- add daily query / dashboard for:
  - top users by runs
  - denied requests by IP hash
  - unusual season-window sizes
- add alerts for sudden spikes in runs or signups

Acceptance criteria:

- you can answer "who ran what, how often, and from where" without storing raw personal data unnecessarily

## Data Model

Use Supabase Auth for identities and add only app-specific tables in `public`.

### `public.user_profiles`

Purpose:

- app-level user state separate from `auth.users`

Fields:

- `id uuid primary key references auth.users(id) on delete cascade`
- `email text not null`
- `display_name text`
- `role text not null default 'user'`
- `status text not null default 'active'`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- `last_seen_at timestamptz`

### `public.usage_events`

Purpose:

- audit trail for protected actions
- abuse analysis
- cost monitoring

Fields:

- `id bigserial primary key`
- `user_id uuid references auth.users(id) on delete set null`
- `event_type text not null`
- `route text not null`
- `success boolean not null`
- `denied_reason text`
- `season_start int`
- `season_end int`
- `week_start int`
- `week_end int`
- `strategy_names jsonb not null default '[]'::jsonb`
- `cost_units int not null default 0`
- `latency_ms int`
- `ip_hash text`
- `user_agent_hash text`
- `request_fingerprint text`
- `created_at timestamptz not null default now()`

### Optional v2 tables

- `public.cached_backtests`
- `public.admin_blocks`
- `public.user_quota_overrides`

## Privacy And Logging Rules

Do not store raw IP addresses in Postgres for a basic demo unless you truly need them.

Preferred approach:

- hash IP using a server-side salt
- hash user-agent using the same or separate salt
- rotate salts only with a migration plan, since rotation breaks historical grouping

Good logging:

- hashed IP
- hashed UA
- user id
- route
- strategy set
- season window
- success / deny / error

Avoid logging:

- passwords
- raw JWTs
- Supabase service-role key
- raw Turnstile tokens after verification

## FastAPI Changes

Primary files to change:

- [src/ffpy/pickem_web.py](/home/ricka/Git/FFPy/src/ffpy/pickem_web.py:1)
- [src/ffpy/config.py](/home/ricka/Git/FFPy/src/ffpy/config.py:1)
- new `src/ffpy/auth.py`
- new `src/ffpy/rate_limit.py`
- new `src/ffpy/repositories/` package

Recommended new modules:

### `src/ffpy/auth.py`

Responsibilities:

- extract bearer token or cookie session
- verify Supabase JWT
- load current user profile
- expose dependencies:
  - `get_current_user`
  - `require_verified_user`
  - `require_admin_user`

### `src/ffpy/rate_limit.py`

Responsibilities:

- Upstash-backed counters
- route-specific rate-limit policies
- helper to calculate cost units for a request

### `src/ffpy/repositories/base.py`

Define a protocol like:

```python
class HistoricalGamesRepository(Protocol):
    def get_historical_games(...) -> pd.DataFrame: ...
    def get_data_coverage(...) -> pd.DataFrame: ...
```

### `src/ffpy/repositories/sqlite_games.py`

- adapter for existing local SQLite workflow

### `src/ffpy/repositories/postgres_games.py`

- Supabase/Postgres implementation for Cloud Run deployment

### `src/ffpy/usage_logging.py`

- writes `usage_events`
- centralizes audit payload creation

## Backtester Refactor Plan

Current `Backtester` takes `FFPyDatabase`.

Recommended change:

- make `Backtester` depend on the new repository protocol for reads
- keep persistence optional and abstracted
- move direct DB persistence behind a separate result-writer abstraction if needed

This should be the minimum refactor that unlocks both:

- local SQLite testing
- hosted Postgres production use

## Frontend Changes

Primary file:

- [src/ffpy/web/pickem_tester/app.js](/home/ricka/Git/FFPy/src/ffpy/web/pickem_tester/app.js:1)

V1 UI changes:

- add auth shell:
  - sign up
  - sign in
  - email verification pending screen
  - signed-in user menu
- hide run buttons until user is authenticated and verified
- show usage quota status:
  - runs left this hour
  - daily budget remaining
- include Turnstile widget on signup

Do not trust the frontend for enforcement.

The backend must enforce:

- auth
- email verification
- quotas
- rate limits

## Environment Variables

Planned env vars:

- `PUBLIC_APP_URL`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `TURNSTILE_SITE_KEY`
- `TURNSTILE_SECRET_KEY`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `ABUSE_HASH_SALT`
- `SESSION_COOKIE_SECURE`
- `MAX_BACKTESTS_PER_HOUR`
- `MAX_COMPARES_PER_HOUR`
- `MAX_DAILY_COST_UNITS`

Rules:

- browser only gets `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `TURNSTILE_SITE_KEY`
- service-role key stays server-side only
- hashing salt stays server-side only

## Deployment Hardening Checklist

Cloud Run:

- use a dedicated service account
- grant least privilege only
- set ingress intentionally
- set low initial max instances
- set request timeout for backtests
- disable unauthenticated admin paths

Supabase:

- enable email confirmation
- enable leaked-password protection if available
- review SMTP sender configuration
- configure RLS on all public tables
- never expose service-role key client-side

App:

- secure cookies in production
- strict CORS allowlist
- response compression only if safe
- request size limits
- input validation on season/week windows
- circuit breaker if cost spikes

## Testing Strategy

Add tests in phases.

### Unit tests

- JWT/session verification helpers
- cost-unit calculator
- rate-limit key generation
- request validation rules

### Integration tests

- anonymous user blocked from protected endpoints
- unverified user blocked from protected endpoints
- verified user allowed
- rate limit exceeded returns `429`
- usage event is written on success and denial

### Manual checks

- signup email arrives
- verification link works
- login works after verification
- unverified login lands on pending screen
- repeated backtest clicks hit quota as expected

## Recommended Delivery Order

Week 1:

- repository abstraction
- Supabase project setup
- auth dependency skeleton
- frontend sign in / sign up shell

Week 2:

- verified-email gate
- protected endpoints
- `user_profiles` and `usage_events`

Week 3:

- Turnstile
- Upstash rate limits
- cost-unit quotas

Week 4:

- dashboards
- admin denylist
- cached repeated backtests

## Open Questions To Resolve Before Implementation

- Will the public demo use Supabase Postgres for historical game data, or keep that data in a separate managed Postgres instance?
- Do you want public signup, or invite-only / allowlist-first beta?
- Is "email verified" enough for launch, or do you want domain restrictions for the first cohort?
- Should we cache backtest results aggressively to minimize repeat compute cost?
- Do you want admin tooling inside the app, or SQL/dashboard-only for the first version?

## Recommended V1 Decision Set

If the goal is a cheap, safe public demo, I recommend:

- public signup enabled
- verified email required
- Turnstile on signup
- no social login yet
- all expensive endpoints authenticated only
- Upstash rate limits enabled from day one
- usage logging from day one
- conservative per-user quotas from day one
- admin-only override path through Supabase table updates, not custom admin UI yet

That gives you a strong demo baseline without overbuilding.
