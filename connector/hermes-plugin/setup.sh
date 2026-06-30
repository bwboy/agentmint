#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  connector/hermes-plugin/setup.sh \
    --connector-id conn_xxxxxxxx \
    --connector-token conn_sk_xxx \
    --platform-url ws://SERVER:8000/ws \
    [--mode link|copy] [--hermes-home PATH]

Options:
  --mode MODE                  Install mode. Default: link.
  --hermes-home PATH           Hermes home directory. Default: $HERMES_HOME or ~/.hermes.
  --connector-id ID            AgentMint connector id.
  --connector-token TOKEN      AgentMint connector token.
  --platform-url URL           AgentMint backend WebSocket URL.
  --queue-db PATH              Optional queue database path.
  --max-concurrent N           Default: 3.
  --usage-wait-seconds N       Default: 1.0.
  --debug-usage                Enable usage debug logs.
  --skip-enable                Do not call `hermes plugins enable platforms/agentmint`.
  -h, --help                   Show this help.
EOF
}

MODE="link"
HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
CONNECTOR_ID=""
CONNECTOR_TOKEN=""
PLATFORM_URL=""
QUEUE_DB=""
MAX_CONCURRENT="3"
USAGE_WAIT_SECONDS="1.0"
DEBUG_USAGE=0
SKIP_ENABLE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --mode=*) MODE="${1#*=}"; shift ;;
    --hermes-home) HERMES_HOME_DIR="${2:-}"; shift 2 ;;
    --hermes-home=*) HERMES_HOME_DIR="${1#*=}"; shift ;;
    --connector-id) CONNECTOR_ID="${2:-}"; shift 2 ;;
    --connector-id=*) CONNECTOR_ID="${1#*=}"; shift ;;
    --connector-token) CONNECTOR_TOKEN="${2:-}"; shift 2 ;;
    --connector-token=*) CONNECTOR_TOKEN="${1#*=}"; shift ;;
    --platform-url) PLATFORM_URL="${2:-}"; shift 2 ;;
    --platform-url=*) PLATFORM_URL="${1#*=}"; shift ;;
    --queue-db) QUEUE_DB="${2:-}"; shift 2 ;;
    --queue-db=*) QUEUE_DB="${1#*=}"; shift ;;
    --max-concurrent) MAX_CONCURRENT="${2:-}"; shift 2 ;;
    --max-concurrent=*) MAX_CONCURRENT="${1#*=}"; shift ;;
    --usage-wait-seconds) USAGE_WAIT_SECONDS="${2:-}"; shift 2 ;;
    --usage-wait-seconds=*) USAGE_WAIT_SECONDS="${1#*=}"; shift ;;
    --debug-usage) DEBUG_USAGE=1; shift ;;
    --skip-enable) SKIP_ENABLE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$CONNECTOR_ID" || -z "$CONNECTOR_TOKEN" || -z "$PLATFORM_URL" ]]; then
  echo "--connector-id, --connector-token, and --platform-url are required" >&2
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  candidates=(
    "$SCRIPT_DIR/../../backend/.venv/bin/python"
    "python3"
    "python"
  )
  for candidate in "${candidates[@]}"; do
    if [[ "$candidate" == */* ]]; then
      [[ -x "$candidate" ]] || continue
    else
      command -v "$candidate" >/dev/null 2>&1 || continue
    fi
    if "$candidate" -c "import yaml" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
  if [[ -z "$PYTHON_BIN" ]]; then
    cat >&2 <<'EOF'
setup.sh needs a Python interpreter with PyYAML to edit Hermes config.yaml safely.

Options:
  1. Run with the Hermes Python that has yaml:
     PYTHON=/path/to/python connector/hermes-plugin/setup.sh ...
  2. Install PyYAML for your python3:
     python3 -m pip install PyYAML
  3. Install only the plugin, then edit config.yaml manually:
     connector/hermes-plugin/install.sh --mode link
EOF
    exit 1
  fi
fi

"$SCRIPT_DIR/install.sh" --mode "$MODE" --hermes-home "$HERMES_HOME_DIR"

configure_args=(
  "$SCRIPT_DIR/configure.py"
  --connector-id "$CONNECTOR_ID"
  --connector-token "$CONNECTOR_TOKEN"
  --platform-url "$PLATFORM_URL"
  --hermes-home "$HERMES_HOME_DIR"
  --max-concurrent "$MAX_CONCURRENT"
  --usage-wait-seconds "$USAGE_WAIT_SECONDS"
)

if [[ -n "$QUEUE_DB" ]]; then
  configure_args+=(--queue-db "$QUEUE_DB")
fi
if [[ "$DEBUG_USAGE" == "1" ]]; then
  configure_args+=(--debug-usage)
fi
if [[ "$SKIP_ENABLE" == "1" ]]; then
  configure_args+=(--skip-enable)
fi

"$PYTHON_BIN" "${configure_args[@]}"

cat <<EOF

AgentMint Hermes plugin setup complete.

Start or restart:
  hermes gateway

Expected startup log:
  agentmint ws client 2026-06-30.1 loaded from ...
EOF
