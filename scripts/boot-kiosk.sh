#!/usr/bin/env bash
set -euo pipefail

# Enforce text boot and prevent GDM from grabbing tty1 so the kiosk shell starts.
sudo systemctl set-default multi-user.target
sudo systemctl mask --now gdm.service gdm3.service
sudo systemctl daemon-reload
sudo systemctl restart getty@tty1
