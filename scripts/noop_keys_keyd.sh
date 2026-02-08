#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="/etc/keyd/default.conf"

usage() {
  cat <<'EOF'
Usage:
  scripts/noop_keys_keyd.sh [--install]

Writes a keyd config that no-ops a set of "escape hatch" keys (Super/Meta, media
keys, brightness keys, rfkill), then restarts keyd.

Notes:
- Requires keyd (https://github.com/rvaiya/keyd). Use --install to install it on Ubuntu.
- This remaps keys at the Linux input level, so it works on Wayland.
EOF
}

INSTALL=0
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--install" ]]; then
  INSTALL=1
fi
if [[ "${1:-}" != "" && "${1:-}" != "--install" ]]; then
  echo "Unknown argument: ${1:-}" >&2
  usage >&2
  exit 2
fi

if [[ $EUID -ne 0 ]]; then
  exec sudo --preserve-env=PATH "$0" ${INSTALL:+--install}
fi

if ! command -v keyd >/dev/null 2>&1; then
  if [[ "$INSTALL" -eq 1 ]]; then
    apt update
    apt install -y keyd
  else
    echo "keyd is not installed. Re-run with --install or install it manually:" >&2
    echo "  sudo apt install keyd" >&2
    exit 1
  fi
fi

install -d -m 0755 /etc/keyd
cat >"$CONFIG_PATH" <<'EOF'
[ids]
*

[main]
# Super/Windows key(s)
leftmeta = noop
rightmeta = noop

# Brightness keys
brightnessdown = noop
brightnessup = noop

# Volume/media keys
mute = noop
volumedown = noop
volumeup = noop
previoussong = noop
playpause = noop
nextsong = noop

# Airplane mode / RF kill
rfkill = noop
EOF

systemctl enable --now keyd
systemctl restart keyd

echo "Wrote ${CONFIG_PATH} and restarted keyd."
