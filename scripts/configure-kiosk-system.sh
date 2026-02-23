#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $EUID -ne 0 ]]; then
  exec sudo --preserve-env=PATH "$0" "$@"
fi

KIOSK_USER="${1:-mike-famulare}"

make_group() {
  local grp="$1"
  if ! getent group "${grp}" >/dev/null 2>&1; then
    groupadd --system "${grp}" >/dev/null 2>&1 || groupadd "${grp}"
  fi
}

run_apt_with_retry() {
  local max_attempts=20
  local attempt=1
  local output

  while true; do
    if output="$("$@" 2>&1)"; then
      printf '%s\n' "$output"
      return 0
    fi

    printf '%s\n' "$output" >&2
    if [[ "$output" == *"Could not get lock"* ]] || [[ "$output" == *"Unable to lock directory"* ]]; then
      if (( attempt >= max_attempts )); then
        echo "apt lock was not released after multiple retries; aborting." >&2
        return 1
      fi
      echo "apt is locked by another process; retrying in 5s (${attempt}/${max_attempts})..." >&2
      attempt=$((attempt + 1))
      sleep 5
      continue
    fi

    return 1
  done
}

run_apt_with_retry apt update
run_apt_with_retry apt install -y cage seatd dconf-cli
systemctl enable --now seatd

for grp in seat input video render; do
  make_group "${grp}"
  if getent group "${grp}" >/dev/null 2>&1; then
    usermod -aG "${grp}" "${KIOSK_USER}"
  fi
done

install -d -m 0755 /etc/systemd/system/getty@tty1.service.d
cat >/etc/systemd/system/getty@tty1.service.d/autologin.conf <<CONF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${KIOSK_USER} --noclear %I \$TERM
CONF

systemctl daemon-reload
systemctl restart getty@tty1

systemctl set-default multi-user.target
if systemctl list-unit-files | rg -q '^gdm\.service'; then
  systemctl disable gdm || true
fi
if systemctl list-unit-files | rg -q '^gdm3\.service'; then
  systemctl disable gdm3 || true
fi

# Force GNOME touchpad send-events='enabled' so the trackpad stays active in the kiosk session.
if [[ -x "$ROOT_DIR/scripts/force_touchpad_enabled_dconf.sh" ]]; then
  "$ROOT_DIR/scripts/force_touchpad_enabled_dconf.sh"
else
  echo "Warning: touchpad override helper missing; please ensure scripts/force_touchpad_enabled_dconf.sh is present." >&2
fi

echo "Kiosk system configuration applied for user: ${KIOSK_USER}"
echo "If group membership changed, log out/in or reboot before testing Cage."
