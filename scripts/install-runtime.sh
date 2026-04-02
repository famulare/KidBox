#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/lib/uv-env.sh"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Install uv first." >&2
  exit 1
fi

uv sync --frozen --no-dev
uv run --frozen python -c "import toddlerbox, pygame; print('runtime-ok')"

echo "ToddlerBox runtime install/update complete."
