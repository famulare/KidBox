#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "${ROOT_DIR}/scripts/lib/uv-env.sh"
export PYGAME_HIDE_SUPPORT_PROMPT=1
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-wayland}"
export XDG_SESSION_TYPE="${XDG_SESSION_TYPE:-wayland}"

start_recovery_shell() {
  echo "kiosk startup failed; dropping to shell on tty1 for recovery." >&2
  exec "${SHELL:-/bin/bash}" -l
}

if ! command -v cage >/dev/null 2>&1; then
  echo "cage is not installed. Install with: sudo apt install -y cage seatd" >&2
  start_recovery_shell
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed or not in PATH." >&2
  start_recovery_shell
fi

if [[ ! -d .venv ]]; then
  echo ".venv is missing. Run: ./scripts/install-runtime.sh" >&2
  start_recovery_shell
fi

if [[ -z "${LIBSEAT_BACKEND:-}" ]] && command -v loginctl >/dev/null 2>&1; then
  # Prefer logind on systemd hosts to avoid seatd socket permission failures.
  export LIBSEAT_BACKEND=logind
fi

# Ensure Cage and SDL don't inherit a stale nested-session display.
unset DISPLAY
unset WAYLAND_DISPLAY
unset SWAYSOCK

if ! cage -- ./scripts/run-stable.sh; then
  echo "cage exited with an error; check logs, then retry from tty1." >&2
  start_recovery_shell
fi
