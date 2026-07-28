"""Broker declarative F4→F5 executor — the canonical home of the bri_* drive.

Hoisted from ``scripts/drive_broker_recommendations.py`` (C2): the broker
channel's F3+ semantics are declarative (rating → recommendation intent via
``broker_recommendation_adapter``), so its F4/F5 execution must not run through
the generic rule/LLM F3 extractor — that path can never emit
``actionability="recommendation"`` and would mint duplicate ``kol_statement``
actions (external review R2). This module owns:

  * loading pending bri_* F3 intents and their F2-anchored broker envelopes,
  * the anchor grounding bridge (``enrichment.anchor_bridge``),
  * per-envelope F4 mapping + canonical F5 via ``run_canonical_from_artifacts``
    (single construction point preserved — composer does the building),
  * persistence: ``bri_{content_id}_actions.json`` merge-write, F4 sidecars,
    evidence sidecars (persist_dir), SQLite action index, and the
    stage_status F5 upsert with ``source_channel='broker'`` (C3).

Consumers:
  * ``pipeline.driver`` routes broker records here per content_id.
  * ``scripts/drive_broker_recommendations.py`` is a thin CLI shell over
    :func:`run_broker_declarative_f5`.

Idempotent: intents whose intent_id already appears in an existing
bri_*_actions.json are skipped; reruns merge, never duplicate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from finer.enrichment.anchor_bridge import bridge_target_symbol
from finer.pipeline.canonical_runner import (
    _coerce_envelope_anchors,
    run_canonical_from_artifacts,
)
from finer.policy.policy_mapper import PolicyMapper
from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyContext

logger = logging.getLogger(__name__)

__all__ = [
    "BrokerDriveReport",
    "collect_env_spans",
    "load_pending_by_envelope",
    "run_broker_declarative_f5",
    "run_broker_declarative_f5_sync",
]


# ── Report ───────────────────────────────────────────────────────────────────


@dataclass
class BrokerDriveReport:
    """Outcome of one broker declarative F4→F5 run."""

    intents_seen: int = 0
    envelopes_seen: int = 0
    bridged: int = 0
    skips: Dict[str, int] = field(default_factory=dict)
    skip_detail: List[str] = field(default_factory=list)
    executed: bool = False
    actions_written: int = 0
    f4_written: int = 0
    indexed: int = 0
    written_files: List[str] = field(default_factory=list)
    action_hint_dist: Dict[str, int] = field(default_factory=dict)
    trace_status_dist: Dict[str, int] = field(default_factory=dict)
    rejected_reasons: Dict[str, int] = field(default_factory=dict)
    planned: Dict[str, int] = field(default_factory=dict)  # envelope_id -> intent count

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


# ── Loading ──────────────────────────────────────────────────────────────────


def _load_bri_intents(
    f3_dir: Path, intent_glob: str = "bri_*.json"
) -> List[NormalizedInvestmentIntent]:
    intents: List[NormalizedInvestmentIntent] = []
    for path in sorted(f3_dir.glob(intent_glob)):
        # JSON mode: strict models still accept ISO datetime strings here
        intents.append(
            NormalizedInvestmentIntent.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        )
    return intents


def _load_envelopes(
    f2_dir: Path,
    content_ids: Optional[set[str]] = None,
    report: Optional[BrokerDriveReport] = None,
) -> Dict[str, Tuple[Path, ContentEnvelope]]:
    """envelope_id → (file path, coerced ContentEnvelope).

    ``content_ids`` narrows the disk scan to those F2 stems (driver routing
    passes one content_id; the full drive passes None for everything).
    Unparseable envelope files are skipped (counted on the report) rather
    than crashing the drive loop — files are the truth, but one malformed
    F2 doc must not take down the whole pass.
    """
    envs: Dict[str, Tuple[Path, ContentEnvelope]] = {}
    if content_ids is not None:
        paths = [f2_dir / f"{cid}.json" for cid in sorted(content_ids)]
        paths = [p for p in paths if p.exists()]
    else:
        paths = sorted(f2_dir.glob("broker_*.json"))
    for path in paths:
        try:
            env = ContentEnvelope.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — malformed F2 doc, skip + count
            logger.warning("skipping unparseable F2 envelope %s: %s", path, exc)
            if report is not None:
                report.skips["envelope_parse_error"] = (
                    report.skips.get("envelope_parse_error", 0) + 1
                )
                report.skip_detail.append(f"envelope_parse_error: {path.name}")
            continue
        _coerce_envelope_anchors(env)
        envs[env.envelope_id] = (path, env)
    return envs


def _existing_actioned_intent_ids(
    f5_dir: Path, output_prefix: str = "bri_"
) -> set[str]:
    """intent_ids already present in {prefix}*_actions.json files (idempotency)."""
    seen: set[str] = set()
    for path in f5_dir.glob(f"{output_prefix}*_actions.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for action in data.get("actions", []):
                iid = action.get("intent_id")
                if iid:
                    seen.add(iid)
        except (OSError, json.JSONDecodeError):
            continue
    return seen


def collect_env_spans(env: ContentEnvelope) -> List[EvidenceSpan]:
    spans: List[EvidenceSpan] = []
    for block in env.blocks or []:
        raw_spans = (
            block.get("evidence_spans") if isinstance(block, dict)
            else getattr(block, "evidence_spans", None)
        ) or []
        for raw in raw_spans:
            try:
                spans.append(
                    raw if isinstance(raw, EvidenceSpan) else EvidenceSpan.model_validate(raw)
                )
            except Exception:  # noqa: BLE001 — malformed F2 span, skip
                continue
    return spans


def load_pending_by_envelope(
    data_root: Path,
    content_ids: Optional[set[str]] = None,
    report: Optional[BrokerDriveReport] = None,
    intent_glob: str = "bri_*.json",
    output_prefix: str = "bri_",
) -> Tuple[
    Dict[str, List[NormalizedInvestmentIntent]],
    Dict[str, Tuple[Path, ContentEnvelope]],
    BrokerDriveReport,
]:
    """Load, dedupe, and bridge pending bri intents grouped per envelope.

    Returns (per_env groups, envelope lookup, report). Bridging mutates the
    in-memory intents (target_symbol / market rewrite) exactly as the F5 run
    will consume them.
    """
    report = report or BrokerDriveReport()
    f3_dir = data_root / "F3_intents"
    f2_dir = data_root / "F2_anchored"
    f5_dir = data_root / "F5_executed"

    intents = _load_bri_intents(f3_dir, intent_glob)
    report.intents_seen = len(intents)
    if not intents:
        # No declarative intents at all (fresh env / non-broker corpus) —
        # don't pay for envelope parsing.
        return {}, {}, report

    envs = _load_envelopes(f2_dir, content_ids, report)
    already = _existing_actioned_intent_ids(f5_dir, output_prefix)

    report.envelopes_seen = len(envs)

    if content_ids is not None:
        wanted_env_ids = {env.envelope_id for _, env in envs.values()}
    else:
        wanted_env_ids = None

    per_env: Dict[str, List[NormalizedInvestmentIntent]] = defaultdict(list)
    skips: Counter = Counter()

    for intent in intents:
        if wanted_env_ids is not None and intent.envelope_id not in wanted_env_ids:
            continue  # outside this run's content scope — not a skip
        if intent.intent_id in already:
            skips["already_actioned"] += 1
            continue
        pair = envs.get(intent.envelope_id)
        if pair is None:
            skips["no_envelope"] += 1
            report.skip_detail.append(
                f"{intent.intent_id}: envelope {intent.envelope_id} not found"
            )
            continue
        _, env = pair
        # sector intent 不走实体锚点桥：它的 target_symbol 是板块占位符
        # （GOLD / SEMICONDUCTOR），实体锚点里本就不会有，硬套这道桥会把
        # D1 的全部产出判成 no_anchor_match 丢掉。canonical_runner 对
        # target_type=="sector" 有独立解析（configs/sector_proxies.yaml →
        # 代理 ETF，未配置则 reject sector_proxy_not_configured），
        # 那才是 sector 的正确门。
        if intent.target_type == "sector":
            report.bridged += 1
            per_env[intent.envelope_id].append(intent)
            continue
        matched = bridge_target_symbol(intent, env)
        if matched is None:
            skips["no_anchor_match"] += 1
            report.skip_detail.append(
                f"{intent.intent_id}: target_symbol={intent.target_symbol!r} "
                f"has no matching resolved_symbol in {intent.envelope_id}"
            )
            continue
        report.bridged += 1
        per_env[intent.envelope_id].append(intent)

    # Merge (not overwrite): _load_envelopes may already have counted
    # envelope_parse_error entries on the report.
    for reason, count in skips.items():
        report.skips[reason] = report.skips.get(reason, 0) + count
    report.planned = {eid: len(group) for eid, group in per_env.items()}
    return per_env, envs, report


# ── stage_status (C3) ────────────────────────────────────────────────────────


def _upsert_f5_stage_status(
    content_id: str,
    error_message: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Register a broker declarative F5 completion in Project Memory.

    Best-effort (a missing/locked index must not fail the drive — files are
    the truth); writes ``source_channel='broker'`` so channel-scoped progress
    queries see the row (C3).
    """
    try:
        from finer.paths import F0_INDEX_DB_PATH
        from finer.services.project_memory.connection import get_connection

        conn = get_connection(db_path or F0_INDEX_DB_PATH)
        try:
            conn.execute(
                """
                INSERT INTO stage_status
                    (content_id, stage, status, error_code, error_message,
                     updated_at, source_channel)
                VALUES (?, 'F5', 'ready', NULL, ?, ?, 'broker')
                ON CONFLICT(content_id, stage) DO UPDATE SET
                    status = excluded.status,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at,
                    source_channel = COALESCE(excluded.source_channel, stage_status.source_channel)
                """,
                (content_id, error_message, datetime.now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        logger.warning("stage_status F5 upsert failed for %s: %s", content_id, exc)


# ── Execution ────────────────────────────────────────────────────────────────


async def run_broker_declarative_f5(
    data_root: Path,
    *,
    content_ids: Optional[set[str]] = None,
    execute: bool = False,
    repo: Optional[Any] = None,
    update_stage_status: bool = True,
    stage_status_db: Optional[Path] = None,
    intent_glob: str = "bri_*.json",
    output_prefix: str = "bri_",
) -> BrokerDriveReport:
    """Drive pending declarative intents through F4 → canonical F5.

    ``intent_glob`` / ``output_prefix`` default to the broker recommendation
    family (bri_*); the T9 sector adapter reuses the exact same executor with
    ``t9i_*.json`` / ``t9i_`` so both families share one canonical entry and
    stay idempotent within their own namespace (D1).

    Args:
        data_root: Repo data root (F2/F3/F4/F5 live under it).
        content_ids: Restrict to these F2 stems (driver per-content routing);
            None = full corpus.
        execute: False (default) plans only — nothing is written.
        repo: Injected TradeActionRepository (tests); default binds the
            canonical index under ``data_root/cache/trade_actions.db``.
        update_stage_status: Write the F5 stage_status row per completed
            content (disabled in tests without a Project Memory DB).
        stage_status_db: Project Memory DB path override (the driver passes
            its own db_path; default is the canonical F0_INDEX_DB_PATH).
    """
    per_env, envs, report = load_pending_by_envelope(
        data_root, content_ids, intent_glob=intent_glob, output_prefix=output_prefix
    )

    if not execute:
        return report
    report.executed = True

    if repo is None:
        from finer.services.repository import TradeActionRepository

        repo = TradeActionRepository(
            db_path=data_root / "cache" / "trade_actions.db",
            action_dir=data_root / "F5_executed",
        )

    f4_dir = data_root / "F4_policy_mapped"
    f5_dir = data_root / "F5_executed"
    f4_dir.mkdir(parents=True, exist_ok=True)
    f5_dir.mkdir(parents=True, exist_ok=True)

    action_hint_dist: Counter = Counter()
    trace_status_dist: Counter = Counter()
    rejected_reasons: Counter = Counter()

    for eid, group in sorted(per_env.items()):
        env_path, env = envs[eid]

        # F4 — per-envelope batch (composer consumes batch.mapped_intents)
        mapper = PolicyMapper(context=PolicyContext(kol_id=env.creator_id))
        batch = mapper.map_batch(group)
        for m in batch.mappings:
            action_hint_dist[m.action_hint] += 1

        # C7: persist each F4 PolicyMappingResult so /audit can resolve the
        # policy segment (audit_assembler reads F4_policy_mapped/{policy_id}.json).
        for pmr in batch.mappings:
            f4_path = f4_dir / f"{pmr.policy_id}.json"
            with open(f4_path, "w", encoding="utf-8") as f:
                json.dump(pmr.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
            report.f4_written += 1

        # F5 — canonical entry. persist_dir makes the runner write the F2
        # evidence sidecars each emitted action references (the root-cause fix
        # behind the C8 6.6% evidence collapse).
        result = await run_canonical_from_artifacts(
            intents=group,
            policy_batch=batch,
            evidence_spans=collect_env_spans(env),
            envelope=env,
            temporal_anchors=env.temporal_anchors,
            strategy="programmatic",
            persist_dir=data_root,
        )

        for r in result.rejected_intents:
            rejected_reasons[r.reason] += 1
        for a in result.trade_actions:
            trace_status_dist[a.canonical_trace_status] += 1

        content_id = env_path.stem
        if not result.trade_actions:
            if update_stage_status:
                _upsert_f5_stage_status(
                    content_id,
                    error_message="0 actions (all intents rejected)",
                    db_path=stage_status_db,
                )
            continue

        out_path = f5_dir / f"{output_prefix}{content_id}_actions.json"
        # Merge with any prior actions in the same file (idempotent reruns)
        prior_actions: List[Dict[str, Any]] = []
        if out_path.exists():
            try:
                with open(out_path, encoding="utf-8") as f:
                    prior_actions = json.load(f).get("actions", [])
            except (OSError, json.JSONDecodeError):
                prior_actions = []

        output_data = {
            "source_file": str(env_path),
            "extracted_at": datetime.now().isoformat(),
            "model": "canonical-programmatic-bri",
            "actions": prior_actions
            + [a.model_dump(mode="json") for a in result.trade_actions],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        report.written_files.append(str(out_path))
        report.actions_written += len(result.trade_actions)

        for a in result.trade_actions:
            repo.index_trade_action(a, str(out_path))
            report.indexed += 1

        if update_stage_status:
            _upsert_f5_stage_status(content_id, db_path=stage_status_db)

    report.action_hint_dist = dict(action_hint_dist)
    report.trace_status_dist = dict(trace_status_dist)
    report.rejected_reasons = dict(rejected_reasons)
    return report


def run_broker_declarative_f5_sync(
    data_root: Path,
    *,
    content_ids: Optional[set[str]] = None,
    execute: bool = False,
    repo: Optional[Any] = None,
    update_stage_status: bool = True,
    stage_status_db: Optional[Path] = None,
    intent_glob: str = "bri_*.json",
    output_prefix: str = "bri_",
) -> BrokerDriveReport:
    """Synchronous wrapper (driver executors are sync — same pattern as
    ``driver._default_f5_executor``)."""
    return asyncio.run(
        run_broker_declarative_f5(
            data_root,
            content_ids=content_ids,
            execute=execute,
            repo=repo,
            update_stage_status=update_stage_status,
            stage_status_db=stage_status_db,
            intent_glob=intent_glob,
            output_prefix=output_prefix,
        )
    )
