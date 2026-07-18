#!/usr/bin/env bash
# launchd wrapper — incremental pipeline driver on a watch interval (C4 / OPS-4).
#
# Runs from the repo's own .venv (system python lacks the `finer` package) and
# logs to logs/pipeline-drive-YYYYMMDD.log. The driver writes a heartbeat
# (data/run_state/heartbeat.json) at the end of every pass.
#
# Env overrides:
#   FINER_DRIVE_INTERVAL  poll interval seconds (default 900)
#   FINER_DRIVE_CHANNEL   import channel filter (default all)
#   FINER_DRIVE_STAGES    stage whitelist, e.g. "f1,f2" (default: all stages)
#
# R2 caveat: channel=all drives every channel. The driver skips already-complete
# items so steady-state cost is low, but do NOT run this while a broker F1
# scale-up process is active — the two would race on data/F1_standardized. Check
# with: ps aux | grep -i scaleup
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

INTERVAL="${FINER_DRIVE_INTERVAL:-900}"
CHANNEL="${FINER_DRIVE_CHANNEL:-all}"

mkdir -p logs
LOG="logs/pipeline-drive-$(date +%Y%m%d).log"

ARGS=(-m finer.cli pipeline-drive --watch "$INTERVAL" --channel "$CHANNEL")
if [ -n "${FINER_DRIVE_STAGES:-}" ]; then
    ARGS+=(--stages "$FINER_DRIVE_STAGES")
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] start pipeline-drive --watch ${INTERVAL} --channel ${CHANNEL} ${FINER_DRIVE_STAGES:+--stages ${FINER_DRIVE_STAGES}}" >> "$LOG"
exec .venv/bin/python "${ARGS[@]}" >> "$LOG" 2>&1
