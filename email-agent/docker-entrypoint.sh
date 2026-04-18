#!/bin/sh
set -eu

cd /app

ensure_connectonion_init() {
  if [ -f /app/.co/config.toml ] && [ -f /app/.co/keys.env ]; then
    return
  fi

  echo "[entrypoint] Initializing ConnectOnion metadata..."
  mkdir -p /app/.co
  co init -y --template minimal
}

load_env_file() {
  if [ -f /app/.env ]; then
    set -a
    # shellcheck disable=SC1091
    . /app/.env
    set +a
  fi
}

load_connectonion_keys() {
  if [ -f /app/.co/keys.env ]; then
    set -a
    # shellcheck disable=SC1091
    . /app/.co/keys.env
    set +a
  fi
}

upsert_env_var() {
  var_name="$1"
  var_value="$2"
  env_file="/app/.env"

  [ -n "${var_value}" ] || return 0
  touch "$env_file"

  awk -v var_name="$var_name" -v var_value="$var_value" '
    BEGIN { replaced = 0 }
    index($0, var_name "=") == 1 {
      if (!replaced) {
        print var_name "=" var_value
        replaced = 1
      }
      next
    }
    { print }
    END {
      if (!replaced) {
        print var_name "=" var_value
      }
    }
  ' "$env_file" > "${env_file}.tmp"

  cat "${env_file}.tmp" > "$env_file"
  rm -f "${env_file}.tmp"
}

sync_connectonion_env() {
  upsert_env_var "OPENONION_API_KEY" "${OPENONION_API_KEY:-}"
  upsert_env_var "AGENT_ADDRESS" "${AGENT_ADDRESS:-}"
  upsert_env_var "AGENT_EMAIL" "${AGENT_EMAIL:-}"
}

run_setup() {
  load_env_file

  has_llm_key="false"
  for key_name in OPENAI_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY OPENROUTER_API_KEY OPENONION_API_KEY; do
    eval "key_value=\${$key_name:-}"
    if [ -n "${key_value}" ]; then
      has_llm_key="true"
      break
    fi
  done

  if [ "${has_llm_key}" != "true" ]; then
    echo "[entrypoint] OpenOnion auth required..."
    co auth
    load_env_file
  fi

  if [ "${LINKED_GMAIL:-}" = "true" ] && [ -z "${GOOGLE_ACCESS_TOKEN:-}" ]; then
    echo "[entrypoint] Google auth required..."
    co auth google
    load_connectonion_keys
    sync_connectonion_env
  fi

  echo "[entrypoint] Setup complete. Start the stack with: docker compose up --build -d"
}

run_default_host() {
  exec python cli.py host --port "${PORT:-8000}" --trust "${EMAIL_AGENT_TRUST:-strict}"
}

ensure_connectonion_init
load_connectonion_keys
sync_connectonion_env

if [ "$#" -eq 0 ]; then
  run_default_host
fi

case "$1" in
  host)
    shift
    if [ "$#" -eq 0 ]; then
      run_default_host
    fi
    exec python cli.py host "$@"
    ;;
  auth-google)
    shift
    exec co auth google "$@"
    ;;
  auth-openonion)
    shift
    exec co auth "$@"
    ;;
  setup)
    shift
    run_setup "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
