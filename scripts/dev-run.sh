#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

if [ -d ".venv" ]; then
  if [ "${UV_VENV_CLEAR:-0}" = "1" ]; then
    uv venv --clear .venv
  else
    echo "Using existing virtual environment at .venv"
  fi
else
  uv venv .venv
fi
uv pip install -e ".[dev]"

APP="${1:-launcher}"
case "$APP" in
  launcher|paint|photos|typing)
    uv run python -m "toddlerbox.${APP}"
    ;;
  tests|test)
    uv run pytest
    ;;
  *)
    echo "Usage: $0 [launcher|paint|photos|typing|tests]" >&2
    exit 2
    ;;
esac
