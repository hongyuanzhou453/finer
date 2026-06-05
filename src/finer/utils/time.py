"""Canonical time helpers for Finer OS.

All timestamps that cross a contract boundary (ContentRecord, ImportReceipt,
Project Memory rows) MUST be timezone-aware UTC. This module is the single
source of truth for "now" and for coercing legacy naive datetimes.

Rules
-----
- ``now_utc()`` is the canonical replacement for ``datetime.utcnow()`` and
  ``datetime.now()``; it always returns an aware UTC datetime.
- ``ensure_aware_utc()`` is the non-destructive coercion used by Pydantic
  field validators: naive input is *assumed* to already be UTC and tagged as
  such (it does NOT shift wall-clock time), aware input is converted to UTC.
  This keeps historical naive payloads valid without rewriting their values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def ensure_aware_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Coerce *value* to an aware UTC datetime without shifting naive wall-clock.

    - ``None`` passes through unchanged.
    - A naive datetime is interpreted as already being UTC and tagged
      ``tzinfo=UTC`` (non-destructive: the wall-clock fields are preserved).
    - An aware datetime is converted to the UTC zone.

    This is the coercion applied by ContentRecord/ImportReceipt validators so
    that legacy naive inputs remain valid while new data is consistently aware.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
