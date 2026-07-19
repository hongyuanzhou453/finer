#!/usr/bin/env bash
# launchd wrapper — heartbeat watchdog (C5 / OPS-5).
#
# A SEPARATE periodic job (StartInterval) that reads the driver's heartbeat and
# alerts if it is stale. It must be separate from the driver loop: a crashed loop
# cannot alert on itself. Logs to logs/alert-check-YYYYMMDD.log.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Load .env so FINER_ALERT_WEBHOOK is available to the alert sender.
set -a
# shellcheck disable=SC1091
[ -f .env ] && . ./.env
set +a

mkdir -p logs
LOG="logs/alert-check-$(date +%Y%m%d).log"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] alert-check" >> "$LOG"
exec .venv/bin/python -m finer.cli alert-check >> "$LOG" 2>&1
