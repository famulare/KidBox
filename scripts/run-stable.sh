#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

if [ ! -d ".venv" ]; then
  uv venv .venv
fi

RESTARTS=0
BACKOFF=1
MAX_BACKOFF=5

while true; do
  TS="$(date -Iseconds)"
  echo "${TS} starting toddlerbox launcher"
  if uv run --frozen python -m toddlerbox.launcher; then
    TS="$(date -Iseconds)"
    echo "${TS} launcher exited cleanly"
    exit 0
  fi

  RESTARTS=$((RESTARTS + 1))
  TS="$(date -Iseconds)"
  echo "${TS} launcher crashed (restart #${RESTARTS}); retry in ${BACKOFF}s"
  sleep "${BACKOFF}"
  BACKOFF=$((BACKOFF + 1))
  if [ "${BACKOFF}" -gt "${MAX_BACKOFF}" ]; then
    BACKOFF="${MAX_BACKOFF}"
  fi
done
