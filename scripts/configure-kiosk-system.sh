#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  exec sudo --preserve-env=PATH "$0" "$@"
fi

KIOSK_USER="${1:-mike-famulare}"

apt update
apt install -y cage seatd
systemctl enable --now seatd

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

echo "Kiosk system configuration applied for user: ${KIOSK_USER}"
