#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

uv venv .venv
uv pip install -e ".[dev]"

APP="${1:-launcher}"
case "$APP" in
  launcher|paint|photos|typing)
    uv run python -m "kidbox.${APP}"
    ;;
  tests|test)
    uv run pytest
    ;;
  *)
    echo "Usage: $0 [launcher|paint|photos|typing|tests]" >&2
    exit 2
    ;;
esac
