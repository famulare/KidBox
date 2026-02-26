#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  exec sudo --preserve-env=PATH "$0" "$@"
fi

systemctl set-default graphical.target
restore_gdm_conf() {
  for conf_dir in /etc/gdm3 /etc/gdm; do
    if [[ ! -d "$conf_dir" ]]; then
      continue
    fi
    local conf_path="${conf_dir}/custom.conf"
    if [[ -f "${conf_path}.bak" ]]; then
      cp "${conf_path}.bak" "$conf_path"
      echo "Restored ${conf_path} from backup."
    else
      cat <<EOF >"$conf_path"
[daemon]
AutomaticLoginEnable=false
EOF
      echo "Reset ${conf_path} to disable automatic login."
    fi
  done
}

remove_wayland_session() {
  local session_file="/usr/share/wayland-sessions/toddlerbox.desktop"
  if [[ -f "$session_file" ]]; then
    rm "$session_file"
    echo "Removed toddlerbox Wayland session ($session_file)."
  fi
}

restore_gdm_conf
remove_wayland_session

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
