"""Operational alerting (Phase 0 C5 / OPS-5).

Three triggers → an :class:`~finer.schemas.ops.AlertEvent` carrying a fix_hint:
  * heartbeat_timeout — the driver's last pass is older than 2× its interval;
  * failure_rate      — a drive pass failed more than a threshold fraction;
  * budget_exceeded   — a batch/drive stopped on the token budget.

Delivery is a Feishu custom-bot webhook whose URL comes ONLY from the
``FINER_ALERT_WEBHOOK`` environment variable — never hard-coded, never logged.
If the variable is unset, ``send_alert`` logs and returns False (no crash): a
missing webhook must never break a drive.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from finer.schemas.heartbeat import HeartbeatState
from finer.schemas.ops import AlertEvent

logger = logging.getLogger(__name__)

WEBHOOK_ENV_VAR = "FINER_ALERT_WEBHOOK"
#: Default fraction of a pass that may fail before failure_rate trips.
DEFAULT_FAILURE_RATE_THRESHOLD = 0.2
#: A heartbeat older than this many intervals is considered stale.
HEARTBEAT_STALE_FACTOR = 2


def webhook_url() -> Optional[str]:
    """The configured webhook URL, or None. Never log the return value."""
    url = os.environ.get(WEBHOOK_ENV_VAR)
    return url.strip() if url and url.strip() else None


def webhook_configured() -> bool:
    return webhook_url() is not None


# ---------------------------------------------------------------------------
# Checks (pure — return an AlertEvent or None; no IO)
# ---------------------------------------------------------------------------


def check_heartbeat_stale(
    heartbeat: Optional[HeartbeatState],
    *,
    now: Optional[datetime] = None,
    factor: int = HEARTBEAT_STALE_FACTOR,
) -> Optional[AlertEvent]:
    """Alert if the driver's last pass is older than ``factor`` × its interval."""
    if heartbeat is None:
        return AlertEvent(
            alert_type="heartbeat_timeout",
            severity="critical",
            title="Driver heartbeat missing",
            message="No heartbeat file found — the pipeline driver has never written one or run_state was cleared.",
            fix_hint="Check `launchctl list | grep com.finer`; tail logs/pipeline-drive-*.log; restart the agent.",
            context={},
        )
    interval = heartbeat.interval_seconds or 0
    if interval <= 0:
        return None  # not a watch loop; staleness undefined
    now = now or datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(heartbeat.last_pass_at)
    except (ValueError, TypeError):
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = (now - last).total_seconds()
    if age > factor * interval:
        return AlertEvent(
            alert_type="heartbeat_timeout",
            severity="critical",
            title="Driver heartbeat stale",
            message=(
                f"Last drive pass was {int(age)}s ago (> {factor}× the {interval}s interval). "
                f"pid={heartbeat.pid}, cycles={heartbeat.cycles}."
            ),
            fix_hint="The driver loop is stalled or dead. Check the process/logs and restart the launchd agent.",
            context={"pid": heartbeat.pid, "age_s": int(age), "interval_s": interval},
        )
    return None


def check_failure_rate(
    stats: Dict[str, Any], *, threshold: float = DEFAULT_FAILURE_RATE_THRESHOLD
) -> Optional[AlertEvent]:
    """Alert if a pass failed more than ``threshold`` of what it scanned."""
    scanned = stats.get("scanned") or 0
    failures = stats.get("failure_count")
    if failures is None:
        failures = len(stats.get("failures") or [])
    if scanned <= 0 or failures <= 0:
        return None
    rate = failures / scanned
    if rate > threshold:
        return AlertEvent(
            alert_type="failure_rate",
            severity="warning",
            title="Drive failure rate high",
            message=f"{failures}/{scanned} items failed ({rate:.0%}) — above the {threshold:.0%} threshold.",
            fix_hint="Inspect stage_status.error_code/error_message; a shared cause (auth, missing raw, schema) is likely.",
            context={"scanned": scanned, "failures": failures, "rate": round(rate, 3)},
        )
    return None


def check_budget(status: str, *, context: Optional[Dict[str, Any]] = None) -> Optional[AlertEvent]:
    """Alert when a batch/drive stopped on the token budget."""
    if status != "budget_exceeded":
        return None
    return AlertEvent(
        alert_type="budget_exceeded",
        severity="warning",
        title="Token budget exhausted",
        message="A batch/drive pass hit its hard token budget and stopped.",
        fix_hint="Raise --budget or resume from the checkpoint once quota resets (see the manifest resume_command).",
        context=context or {},
    )


def self_test_event() -> AlertEvent:
    """A canned event for the self-test CLI."""
    return AlertEvent(
        alert_type="test",
        severity="info",
        title="Finer ops alert — test",
        message="This is a test alert from `finer alert-test`. If you see it, the webhook works.",
        fix_hint="No action needed.",
        context={},
    )


# ---------------------------------------------------------------------------
# Formatting + delivery
# ---------------------------------------------------------------------------

_SEVERITY_MARK = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}


def format_alert(event: AlertEvent) -> str:
    """Render an AlertEvent as the plain-text webhook body."""
    mark = _SEVERITY_MARK.get(event.severity, "")
    lines = [
        f"{mark} [Finer/{event.severity.upper()}] {event.title}",
        event.message,
        f"↳ {event.fix_hint}",
    ]
    if event.context:
        ctx = " ".join(f"{k}={v}" for k, v in event.context.items())
        lines.append(f"({ctx})")
    lines.append(f"@ {event.ts}")
    return "\n".join(lines)


def send_alert(event: AlertEvent, *, url: Optional[str] = None, timeout: float = 10.0) -> bool:
    """POST the alert to the Feishu webhook. Returns True on a 200.

    URL resolves from the ``url`` arg or ``FINER_ALERT_WEBHOOK``; if neither is
    set the alert is logged and False is returned (never raises). The URL is
    never logged.
    """
    target = url or webhook_url()
    if not target:
        logger.warning("alert not sent (%s unset): %s", WEBHOOK_ENV_VAR, event.title)
        return False
    payload = {"msg_type": "text", "content": {"text": format_alert(event)}}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(target, json=payload)
        if resp.status_code == 200:
            return True
        logger.warning("alert webhook returned HTTP %s for %s", resp.status_code, event.title)
        return False
    except Exception as exc:  # noqa: BLE001 — alerting must never break the caller
        logger.warning("alert webhook post failed (%s): %s", type(exc).__name__, event.title)
        return False
