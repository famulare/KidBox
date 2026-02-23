#!/usr/bin/env bash
set -euo pipefail

PROFILE_NAME="local"
DB_DIR="/etc/dconf/db/${PROFILE_NAME}.d"
SETTINGS_FILE="${DB_DIR}/00-toddlerbox-touchpad"
LOCKS_DIR="${DB_DIR}/locks"
LOCK_FILE="${LOCKS_DIR}/toddlerbox-touchpad"

usage() {
  cat <<'EOF'
Usage:
  scripts/force_touchpad_enabled_dconf.sh [--no-lock] [--remove]

Forces GNOME touchpad "send-events" to 'enabled' via a system dconf profile.

Why:
  Some key-remapping setups (e.g., keyd) create a virtual pointer device.
  If GNOME is set to disable the touchpad when an "external mouse" is present
  (send-events='disabled-on-external-mouse'), the touchpad can appear "stuck"
  off across reboots. This script makes the setting deterministic at boot.

Options:
  --no-lock   Apply the setting but don't lock it.
  --remove    Remove the setting + lock (if present).

Notes:
  - Requires sudo.
  - After applying, log out/in or reboot.
EOF
}

NO_LOCK=0
REMOVE=0
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --no-lock) NO_LOCK=1 ;;
    --remove) REMOVE=1 ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  exec sudo --preserve-env=PATH "$0" "$@"
fi

if [[ "$REMOVE" -eq 1 ]]; then
  rm -f "$SETTINGS_FILE" "$LOCK_FILE"
  # Remove empty dirs (best-effort).
  rmdir --ignore-fail-on-non-empty "$LOCKS_DIR" 2>/dev/null || true
  rmdir --ignore-fail-on-non-empty "$DB_DIR" 2>/dev/null || true
  dconf update
  echo "Removed dconf override/lock for touchpad send-events."
  exit 0
fi

install -d -m 0755 "$DB_DIR"
cat >"$SETTINGS_FILE" <<'EOF'
[org/gnome/desktop/peripherals/touchpad]
send-events='enabled'
EOF

if [[ "$NO_LOCK" -eq 0 ]]; then
  install -d -m 0755 "$LOCKS_DIR"
  cat >"$LOCK_FILE" <<'EOF'
/org/gnome/desktop/peripherals/touchpad/send-events
EOF
fi

dconf update

echo "Forced touchpad send-events='enabled' via ${SETTINGS_FILE}."
if [[ "$NO_LOCK" -eq 0 ]]; then
  echo "Locked via ${LOCK_FILE}."
fi
