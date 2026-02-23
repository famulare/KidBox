#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
export PYGAME_HIDE_SUPPORT_PROMPT=1

if ! command -v cage >/dev/null 2>&1; then
  echo "cage is not installed. Install with: sudo apt install -y cage seatd" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed or not in PATH." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo ".venv is missing. Run: ./scripts/install-runtime.sh" >&2
  exit 1
fi

exec cage -- ./scripts/run-stable.sh
