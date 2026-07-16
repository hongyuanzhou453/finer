"""F7 stance snapshots + day-over-day diff (真快照-diff 服务).

Persists a daily snapshot of every KOL's current stance per ticker (latest
action by the canonical execution clock) plus their credibility score, and
diffs consecutive snapshots into change events:

  - flip          same KOL+ticker, direction changed vs the previous snapshot
  - new_call      KOL+ticker appears that wasn't in the previous snapshot
  - score_change  credibility moved vs the previous snapshot

Snapshots live under ``data/F7_timeline/stance_snapshots/{YYYY-MM-DD}.json``
(one per day, atomic overwrite within the day). The dashboard previously
derived flips client-side from opinion history because no snapshot history
existed; the /api/opinions/changes endpoint now serves both: history-derived
events for cold start plus true snapshot diffs once history accumulates.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from finer.paths import DATA_ROOT
from finer.schemas.trade_action import TradeAction

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = DATA_ROOT / "F7_timeline" / "stance_snapshots"


def signal_clock_of(action: TradeAction) -> str:
    """Canonical signal clock (executable_at first, extraction time fallback)."""
    timing = action.execution_timing
    dt = None
    if timing is not None:
        dt = timing.action_executable_at or timing.intent_effective_at
    if dt is None:
        dt = action.timestamp
    return dt.isoformat()


def stance_key_of(action: TradeAction, ticker: str) -> str:
    """Stance-slot key for a (KOL, stance) pair.

    Two distinct sectors can proxy to the SAME ETF ticker (e.g. COMPUTE_POWER
    and AI_COMPUTING both → 159819). Keying stances purely by the proxy ticker
    would collapse those independent viewpoints into one slot and fabricate
    flips. When the action carries F2 sector-proxy provenance, key by
    ``metadata.sector_proxy.sector_symbol`` so each underlying sector keeps its
    own stance; the display ticker stays the proxy ETF the reader recognizes.
    Direct-ticker actions (no sector proxy) key by ticker as before.
    """
    meta = getattr(action, "metadata", None) or {}
    proxy = meta.get("sector_proxy") if isinstance(meta, dict) else None
    if isinstance(proxy, dict):
        sector_symbol = proxy.get("sector_symbol")
        if sector_symbol:
            return f"sector:{sector_symbol}"
    return ticker


def build_snapshot(
    actions: List[TradeAction],
    credibility_by_kol: Optional[Dict[str, int]] = None,
    snapshot_date: Optional[date] = None,
) -> dict:
    """Current stance per (KOL, ticker) — latest action by signal clock."""
    kols: Dict[str, dict] = {}
    for action in actions:
        # Strip: a whitespace-padded creator_id must land on the same key the
        # credibility map uses (opinions._kol_settled_record strips), or the
        # credibility join below silently misses forever.
        kol = (action.source.creator_id or "").strip()
        if not kol or kol.lower() in ("unknown", "none"):
            continue
        ticker = action.target.ticker_normalized or action.target.ticker
        if not ticker:
            continue
        stance_key = stance_key_of(action, ticker)
        clock = signal_clock_of(action)
        entry = kols.setdefault(kol, {"credibility": None, "stances": {}})
        prev = entry["stances"].get(stance_key)
        # deterministic: latest clock wins; ties broken by trade_action_id
        if prev is None or (clock, action.trade_action_id) > (
            prev["clock"],
            prev["trade_action_id"],
        ):
            entry["stances"][stance_key] = {
                "direction": action.direction.value,
                "clock": clock,
                "trade_action_id": action.trade_action_id,
                "ticker": ticker,
                "company_name": action.target.company_name or ticker,
            }

    for kol, cred in (credibility_by_kol or {}).items():
        if kol in kols:
            kols[kol]["credibility"] = cred

    return {
        "snapshot_date": (snapshot_date or date.today()).isoformat(),
        "generated_at": datetime.now().isoformat(),
        "kols": kols,
    }


def persist_snapshot(snapshot: dict, snapshot_dir: Path = SNAPSHOT_DIR) -> Path:
    """Write the snapshot for its date (atomic; overwrites within the day)."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{snapshot['snapshot_date']}.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    os.replace(tmp, path)
    return path


def load_latest_snapshot_before(
    before: date, snapshot_dir: Path = SNAPSHOT_DIR
) -> Optional[Tuple[date, dict]]:
    """Most recent persisted snapshot strictly older than ``before``."""
    if not snapshot_dir.exists():
        return None
    best: Optional[Tuple[date, Path]] = None
    for fp in snapshot_dir.glob("*.json"):
        try:
            d = date.fromisoformat(fp.stem)
        except ValueError:
            continue
        if d < before and (best is None or d > best[0]):
            best = (d, fp)
    if best is None:
        return None
    try:
        return best[0], json.loads(best[1].read_text())
    except Exception as e:  # corrupt snapshot must not break the feed
        logger.warning("Unreadable stance snapshot %s: %s", best[1], e)
        return None


def diff_snapshots(prev: dict, curr: dict) -> List[dict]:
    """Change events between two snapshots (flip / new_call / score_change)."""
    events: List[dict] = []
    prev_kols: Dict[str, dict] = prev.get("kols") or {}
    curr_kols: Dict[str, dict] = curr.get("kols") or {}
    curr_date = curr.get("snapshot_date") or date.today().isoformat()

    for kol, curr_entry in curr_kols.items():
        prev_entry = prev_kols.get(kol) or {}
        prev_stances: Dict[str, dict] = prev_entry.get("stances") or {}

        for stance_key, stance in (curr_entry.get("stances") or {}).items():
            before = prev_stances.get(stance_key)
            # display ticker rides in the stance value (proxy ETF); older
            # snapshots keyed directly by ticker fall back to the key.
            display_ticker = stance.get("ticker") or stance_key
            if before is None and display_ticker != stance_key:
                # Migration: snapshots persisted before sector-aware keys hold
                # this stance under its raw proxy ticker. Without the fallback,
                # the first post-deploy diff fabricates a new_call for every
                # sector-proxy stance and drops fromDirection on real flips.
                before = prev_stances.get(display_ticker)
            if before is None:
                if prev_entry:  # KOL existed before → this name is new coverage
                    events.append(
                        {
                            "id": f"new-{stance['trade_action_id']}",
                            "type": "new_call",
                            "kolId": kol,
                            "kolName": kol,
                            "ticker": display_ticker,
                            "companyName": stance.get("company_name") or display_ticker,
                            "toDirection": stance["direction"],
                            "detail": "较上一快照新增覆盖标的",
                            "timestamp": stance.get("clock") or curr_date,
                        }
                    )
            elif before.get("direction") != stance.get("direction"):
                events.append(
                    {
                        "id": f"flip-{stance['trade_action_id']}",
                        "type": "flip",
                        "kolId": kol,
                        "kolName": kol,
                        "ticker": display_ticker,
                        "companyName": stance.get("company_name") or display_ticker,
                        "fromDirection": before.get("direction"),
                        "toDirection": stance.get("direction"),
                        "detail": "较上一快照立场翻向",
                        "timestamp": stance.get("clock") or curr_date,
                    }
                )

        prev_cred = prev_entry.get("credibility")
        curr_cred = curr_entry.get("credibility")
        if (
            isinstance(prev_cred, int)
            and isinstance(curr_cred, int)
            and prev_cred != curr_cred
        ):
            delta = curr_cred - prev_cred
            events.append(
                {
                    "id": f"score-{kol}-{curr_date}",
                    "type": "score_change",
                    "kolId": kol,
                    "kolName": kol,
                    "detail": f"信誉分 {prev_cred} → {curr_cred}",
                    "timestamp": curr_date,
                    "value": delta,
                }
            )

    return events
