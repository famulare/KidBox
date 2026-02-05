#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/famulare/git/KidBox"
SERVICE_SRC="$ROOT/scripts/kidbox.service"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_DEST="$SERVICE_DIR/kidbox.service"

mkdir -p "$SERVICE_DIR"
cp "$SERVICE_SRC" "$SERVICE_DEST"

systemctl --user daemon-reload
systemctl --user enable --now kidbox.service

echo "KidBox service installed and started."
