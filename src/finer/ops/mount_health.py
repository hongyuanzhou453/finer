"""External-volume mount health (Phase 0 C6 / OPS-6).

Broker research raw PDFs live on an external volume (default ``/Volumes/NAMEZY``);
the F0 records, F1 envelopes, F2 anchors and T3 JSONL all live on the internal
disk. So an unmounted external volume only blocks *re-standardizing broker raw*
(F1 from the PDF) — everything already produced is unaffected.

This module is the single mount check reused by the driver and the broker intake
so an unmounted volume degrades gracefully (skip the broker channel + warn)
instead of erroring and blocking the other channels. The volume path comes from
``FINER_BROKER_SOURCE_VOLUME`` (default ``/Volumes/NAMEZY``) so it is overridable
in tests / on other machines.
"""

from __future__ import annotations

import os
from pathlib import Path

from finer.schemas.ops import AlertEvent

ENV_VAR = "FINER_BROKER_SOURCE_VOLUME"
DEFAULT_BROKER_VOLUME = "/Volumes/NAMEZY"


def broker_source_volume() -> Path:
    """Configured external volume root for broker raw (env-overridable)."""
    return Path(os.environ.get(ENV_VAR, DEFAULT_BROKER_VOLUME))


def is_volume_mounted(path: Path) -> bool:
    """True if ``path`` is a live mount point (a mounted external volume)."""
    return os.path.ismount(str(path))


def broker_volume_available() -> bool:
    """True if the configured broker source volume is mounted and reachable."""
    return is_volume_mounted(broker_source_volume())


def broker_mount_alert(*, skipped: int, job: str) -> AlertEvent:
    """Warning-level alert for an unmounted broker volume (broker skipped)."""
    volume = broker_source_volume()
    return AlertEvent(
        alert_type="volume_unmounted",
        severity="warning",
        title="Broker source volume unmounted",
        message=(
            f"{job}: the broker source volume {volume} is not mounted — "
            f"skipped {skipped} broker item(s). Other channels are unaffected."
        ),
        fix_hint=f"Mount {volume} (external disk), then re-run; already-standardized broker content is unaffected.",
        context={"volume": str(volume), "skipped": skipped, "job": job},
    )
