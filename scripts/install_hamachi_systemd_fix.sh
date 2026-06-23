#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

sudo install -m 0755 "${PROJECT_DIR}/scripts/hamachid-systemd-wrapper.sh" /usr/local/sbin/hamachid-systemd-wrapper
sudo install -m 0755 "${PROJECT_DIR}/scripts/hamachi-network-tune.sh" /usr/local/sbin/hamachi-network-tune.sh
sudo install -m 0644 "${PROJECT_DIR}/systemd/logmein-hamachi.service" /etc/systemd/system/logmein-hamachi.service
sudo install -m 0644 "${PROJECT_DIR}/systemd/hamachi-network-tune.service" /etc/systemd/system/hamachi-network-tune.service
sudo systemctl daemon-reload
sudo systemctl stop hamachi-network-tune.service || true
sudo systemctl stop logmein-hamachi.service || true
sudo rm -f /run/logmein-hamachi/hamachid.pid /run/logmein-hamachi/ipc.sock /run/logmein-hamachi/hamachid.lock
sudo systemctl enable --now logmein-hamachi.service
sudo systemctl enable --now hamachi-network-tune.service
sudo systemctl status logmein-hamachi.service --no-pager
sudo systemctl status hamachi-network-tune.service --no-pager
