#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  connector/hermes-plugin/install.sh [--mode link|copy] [--hermes-home PATH]

Options:
  --mode MODE          Install mode: link for development, copy for stable installs.
                       Default: link.
  --hermes-home PATH   Hermes home directory. Default: $HERMES_HOME or ~/.hermes.
  -h, --help           Show this help.
EOF
}

MODE="link"
HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --mode=*)
      MODE="${1#*=}"
      shift
      ;;
    --hermes-home)
      HERMES_HOME_DIR="${2:-}"
      shift 2
      ;;
    --hermes-home=*)
      HERMES_HOME_DIR="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$MODE" != "link" && "$MODE" != "copy" ]]; then
  echo "--mode must be link or copy" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$HERMES_HOME_DIR/plugins/platforms/agentmint"
PLUGIN_PARENT="$(dirname "$PLUGIN_DIR")"
PYTHON_BIN="${PYTHON:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$SCRIPT_DIR/../../backend/.venv/bin/python" ]]; then
    PYTHON_BIN="$SCRIPT_DIR/../../backend/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "python3 or python is required" >&2
    exit 1
  fi
fi

mkdir -p "$PLUGIN_PARENT"

if [[ "$MODE" == "link" ]]; then
  if [[ -e "$PLUGIN_DIR" || -L "$PLUGIN_DIR" ]]; then
    if [[ -L "$PLUGIN_DIR" && "$(readlink "$PLUGIN_DIR")" == "$SCRIPT_DIR" ]]; then
      echo "AgentMint plugin link already installed: $PLUGIN_DIR -> $SCRIPT_DIR"
    else
      backup="${PLUGIN_DIR}.backup.$(date +%Y%m%d%H%M%S)"
      mv "$PLUGIN_DIR" "$backup"
      echo "Existing plugin moved to $backup"
      ln -s "$SCRIPT_DIR" "$PLUGIN_DIR"
      echo "AgentMint plugin linked: $PLUGIN_DIR -> $SCRIPT_DIR"
    fi
  else
    ln -s "$SCRIPT_DIR" "$PLUGIN_DIR"
    echo "AgentMint plugin linked: $PLUGIN_DIR -> $SCRIPT_DIR"
  fi
else
  if command -v rsync >/dev/null 2>&1; then
    mkdir -p "$PLUGIN_DIR"
    rsync -a --delete "$SCRIPT_DIR/" "$PLUGIN_DIR/"
  else
    if [[ -e "$PLUGIN_DIR" || -L "$PLUGIN_DIR" ]]; then
      backup="${PLUGIN_DIR}.backup.$(date +%Y%m%d%H%M%S)"
      mv "$PLUGIN_DIR" "$backup"
      echo "Existing plugin moved to $backup"
    fi
    mkdir -p "$PLUGIN_DIR"
    cp -R "$SCRIPT_DIR/." "$PLUGIN_DIR/"
  fi
  echo "AgentMint plugin copied to $PLUGIN_DIR"
fi

HERMES_HOME="$HERMES_HOME_DIR" "$PYTHON_BIN" "$SCRIPT_DIR/check-install.py"

cat <<EOF

Next:
  hermes plugins enable platforms/agentmint
  hermes gateway
EOF
