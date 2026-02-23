#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  exec sudo --preserve-env=PATH "$0" "$@"
fi

systemctl set-default graphical.target
if systemctl list-unit-files | rg -q '^gdm\.service'; then
  systemctl enable gdm || true
fi
if systemctl list-unit-files | rg -q '^gdm3\.service'; then
  systemctl enable gdm3 || true
fi

rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf
systemctl daemon-reload
systemctl restart getty@tty1

echo "Rolled back to graphical boot target."
