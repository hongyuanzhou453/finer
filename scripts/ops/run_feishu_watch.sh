#!/usr/bin/env bash
# launchd wrapper — Feishu chat watcher (C4 / OPS-4).
#
# Runs from the repo's own .venv and logs to logs/feishu-watch-YYYYMMDD.log.
#
# Env overrides:
#   FINER_FEISHU_INTERVAL  poll interval seconds (default 300)
#   FINER_FEISHU_NO_NLM    if set to 1, skip the NotebookLM sync step
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

INTERVAL="${FINER_FEISHU_INTERVAL:-300}"

mkdir -p logs
LOG="logs/feishu-watch-$(date +%Y%m%d).log"

ARGS=(-m finer.cli feishu-watch --interval "$INTERVAL")
if [ "${FINER_FEISHU_NO_NLM:-0}" = "1" ]; then
    ARGS+=(--no-nlm)
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] start feishu-watch --interval ${INTERVAL}" >> "$LOG"
exec .venv/bin/python "${ARGS[@]}" >> "$LOG" 2>&1
