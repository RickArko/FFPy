-- Starter schema for the Supabase-backed public demo.
-- This file is a planning scaffold, not an applied application migration yet.

create table if not exists public.user_profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null,
    display_name text,
    role text not null default 'user',
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_seen_at timestamptz
);

create table if not exists public.usage_events (
    id bigserial primary key,
    user_id uuid references auth.users(id) on delete set null,
    event_type text not null,
    route text not null,
    success boolean not null,
    denied_reason text,
    season_start integer,
    season_end integer,
    week_start integer,
    week_end integer,
    strategy_names jsonb not null default '[]'::jsonb,
    cost_units integer not null default 0,
    latency_ms integer,
    ip_hash text,
    user_agent_hash text,
    request_fingerprint text,
    created_at timestamptz not null default now()
);

create index if not exists idx_usage_events_user_created_at
    on public.usage_events (user_id, created_at desc);

create index if not exists idx_usage_events_route_created_at
    on public.usage_events (route, created_at desc);

create index if not exists idx_usage_events_ip_hash_created_at
    on public.usage_events (ip_hash, created_at desc);

alter table public.user_profiles enable row level security;
alter table public.usage_events enable row level security;

create policy "user_profiles_select_own"
    on public.user_profiles
    for select
    to authenticated
    using (auth.uid() = id);

create policy "user_profiles_update_own"
    on public.user_profiles
    for update
    to authenticated
    using (auth.uid() = id)
    with check (auth.uid() = id);

create policy "usage_events_select_own"
    on public.usage_events
    for select
    to authenticated
    using (auth.uid() = user_id);

-- Server-side writes should use the service role, not client-side inserts.
