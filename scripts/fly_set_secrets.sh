#!/usr/bin/env bash
set -euo pipefail

FLY_APP="${FLY_APP:-ffpy-pickem}"
ENV_FILE="${ENV_FILE:-.env}"
FLY_BIN="${FLY_BIN:-}"

if [[ -z "${FLY_BIN}" ]]; then
  if command -v fly >/dev/null 2>&1; then
    FLY_BIN="fly"
  elif command -v flyctl >/dev/null 2>&1; then
    FLY_BIN="flyctl"
  elif [[ -x "${HOME}/.fly/bin/fly" ]]; then
    FLY_BIN="${HOME}/.fly/bin/fly"
  else
    printf 'flyctl was not found. Install it or add it to PATH, then rerun make fly.secrets.\n' >&2
    printf 'Install: curl -L https://fly.io/install.sh | sh\n' >&2
    printf 'PATH example: export PATH="$HOME/.fly/bin:$PATH"\n' >&2
    exit 127
  fi
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

SUPABASE_URL="${SUPABASE_URL:-}"
SUPABASE_URL="${SUPABASE_URL%/}"
SUPABASE_URL="${SUPABASE_URL%/rest/v1}"
SUPABASE_URL="${SUPABASE_URL%/auth/v1}"

if [[ -z "${SUPABASE_PUBLISHABLE_KEY:-}" && -n "${SUPABASE_ANON_KEY:-}" ]]; then
  SUPABASE_PUBLISHABLE_KEY="${SUPABASE_ANON_KEY}"
fi

required_keys=(
  SUPABASE_URL
  SUPABASE_PUBLISHABLE_KEY
)

missing_keys=()
for key in "${required_keys[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    missing_keys+=("${key}")
  fi
done

if (( ${#missing_keys[@]} > 0 )); then
  printf 'Missing required secret values: %s\n' "${missing_keys[*]}" >&2
  printf 'Add them to %s or export them in your shell, then rerun make fly.secrets.\n' "${ENV_FILE}" >&2
  exit 1
fi

WEB_AUTH_ENABLED="${FLY_WEB_AUTH_ENABLED:-true}"
DATABASE_PATH="${FLY_DATABASE_PATH:-/data/ffpy.db}"
SUPABASE_JWT_AUDIENCE="${FLY_SUPABASE_JWT_AUDIENCE:-authenticated}"
SUPABASE_FETCH_USER_ON_VERIFY="${FLY_SUPABASE_FETCH_USER_ON_VERIFY:-true}"
ABUSE_HASH_SALT="${ABUSE_HASH_SALT:-$(python -c 'import secrets; print(secrets.token_urlsafe(48))')}"

printf 'Setting Fly secrets for app %s.\n' "${FLY_APP}"
printf 'Values are read from %s and the current shell; secret contents will not be printed here.\n' "${ENV_FILE}"
printf 'Using Fly CLI: %s\n' "${FLY_BIN}"

if [[ "${DRY_RUN:-false}" == "true" ]]; then
  printf 'DRY_RUN=true, so no Fly secrets were changed.\n'
  exit 0
fi

secret_args=(
  WEB_AUTH_ENABLED="${WEB_AUTH_ENABLED}" \
  DATABASE_PATH="${DATABASE_PATH}" \
  SUPABASE_URL="${SUPABASE_URL}" \
  SUPABASE_PUBLISHABLE_KEY="${SUPABASE_PUBLISHABLE_KEY}" \
  SUPABASE_JWT_AUDIENCE="${SUPABASE_JWT_AUDIENCE}" \
  SUPABASE_FETCH_USER_ON_VERIFY="${SUPABASE_FETCH_USER_ON_VERIFY}" \
  ABUSE_HASH_SALT="${ABUSE_HASH_SALT}"
)

if [[ -n "${SUPABASE_ANON_KEY:-}" ]]; then
  secret_args+=(SUPABASE_ANON_KEY="${SUPABASE_ANON_KEY}")
fi

if [[ -n "${SUPABASE_JWKS_URL:-}" ]]; then
  secret_args+=(SUPABASE_JWKS_URL="${SUPABASE_JWKS_URL}")
fi

if [[ -n "${SUPABASE_JWT_SECRET:-}" ]]; then
  secret_args+=(SUPABASE_JWT_SECRET="${SUPABASE_JWT_SECRET}")
fi

"${FLY_BIN}" secrets set --app "${FLY_APP}" "${secret_args[@]}"
