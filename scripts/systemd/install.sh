#!/bin/bash
# Install lh-ingestion systemd timer/service
# Usage: sudo ./install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing lh-ingestion systemd units..."

cp "${SCRIPT_DIR}/lh-ingestion.service" /etc/systemd/system/
cp "${SCRIPT_DIR}/lh-ingestion.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable lh-ingestion.timer
systemctl start lh-ingestion.timer

echo "Done. Timer status:"
systemctl status lh-ingestion.timer --no-pager
