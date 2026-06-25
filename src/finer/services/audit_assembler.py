"""Read-only Audit Trace assembly for the dashboard.

This service materializes frontend audit bundles from canonical F-stage
artifacts on disk. It does not call pipeline code and does not write data.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from finer.paths import DATA_ROOT
from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappingResult
from finer.schemas.trade_action import TradeAction

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

TRACE_STATUSES = {"canonical", "partial", "non_canonical"}
VALIDATION_STATUSES = {"pending", "verified", "failed", "under_review"}


@dataclass(frozen=True)
class IndexedTradeAction:
    """Cached F5 action plus list-ready projection fields."""

    action: TradeAction
    path: Path
    summary: dict[str, Any]
    ticker_search_values: tuple[str, ...]
    # For actions sourced from a canonical ``*_actions.json`` batch wrapper:
    # the wrapper's ``source_file`` link, and a flag marking that F3/F4 sidecars
    # are not persisted (so the action's self-declared trace status is trusted).
    source_file: str | None = None
    from_wrapper: bool = False


class AuditAssembler:
    """Assemble Audit Trace API responses from F-stage artifact files."""

    def __init__(self, data_root: Path = DATA_ROOT, ttl_seconds: int = 60) -> None:
        self.data_root = Path(data_root)
        self.ttl_seconds = ttl_seconds
        self._actions_cache: list[IndexedTradeAction] | None = None
        self._actions_cache_built_at = 0.0

    def clear_cache(self) -> None:
        """Clear the in-memory F5 index cache."""

        self._actions_cache = None
        self._actions_cache_built_at = 0.0

    def list_action_summaries(
        self,
        *,
        kol_id: str | None = None,
        ticker: str | None = None,
        trace_status: str | None = None,
        validation_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return paginated TradeActionSummary rows for the audit left rail."""

        rows: list[dict[str, Any]] = []
        for indexed in self._get_indexed_actions():
            row = indexed.summary

            if trace_status and row["canonical_trace_status"] != trace_status:
                continue
            if validation_status and row["validation_status"] != validation_status:
                continue
            if kol_id and row.get("kol_id") != kol_id:
                continue
            if ticker and not self._matches_ticker_values(indexed.ticker_search_values, ticker):
                continue

            rows.append(dict(row))

        total = len(rows)
        page = rows[offset: offset + limit]
        return {"actions": page, "total": total}

    def get_trace_bundle(self, trade_action_id: str) -> dict[str, Any] | None:
        """Return an AuditTraceBundle for one TradeAction, or None if missing."""

        indexed = self._find_indexed_action(trade_action_id)
        if indexed is None:
            return None

        action = indexed.action
        intent = self._load_intent_for_action(action)
        policy = self._load_policy_for_action(action)
        envelope = self._load_envelope_for_action(
            action, intent, source_file=indexed.source_file
        )
        materialized_status = self._materialized_trace_status(
            action, intent, policy, trust_self_declared=indexed.from_wrapper
        )

        action_payload = action.model_dump(mode="json")
        action_payload["canonical_trace_status"] = materialized_status

        return {
            "trade_action": action_payload,
            "intent": intent.model_dump(mode="json") if intent else None,
            "policy": policy.model_dump(mode="json") if policy else None,
            "evidence_spans": self._load_evidence_spans_for_action(action),
            "envelope": self._envelope_context(
                action, intent, envelope, source_file=indexed.source_file
            ),
        }

    def _get_indexed_actions(self) -> list[IndexedTradeAction]:
        now = time.time()
        if (
            self._actions_cache is not None
            and now - self._actions_cache_built_at < self.ttl_seconds
        ):
            return self._actions_cache

        f5_dir = self.data_root / "F5_executed"
        indexed: list[IndexedTradeAction] = []
        if f5_dir.exists():
            for path in sorted(f5_dir.glob("*.json")):
                if path.name.endswith("_actions.json"):
                    # Batch wrapper file. The canonical F5 route writes one of
                    # these per source ({model, actions: [...]}); each embedded
                    # dict is a canonical TradeAction. Legacy batch products are
                    # filtered out inside _load_wrapper_entries.
                    indexed.extend(self._load_wrapper_entries(path))
                    continue
                action = self._safe_load_model(path, TradeAction)
                if action is not None:
                    indexed.append(self._build_index_entry(action, path))

        indexed.sort(key=lambda item: item.action.timestamp, reverse=True)
        self._actions_cache = indexed
        self._actions_cache_built_at = now
        logger.debug("Built audit F5 index with %d TradeActions", len(indexed))
        return indexed

    def _build_index_entry(
        self,
        action: TradeAction,
        path: Path,
        *,
        source_file: str | None = None,
        from_wrapper: bool = False,
    ) -> IndexedTradeAction:
        intent = self._load_intent_for_action(action)
        policy = self._load_policy_for_action(action)
        materialized_status = self._materialized_trace_status(
            action, intent, policy, trust_self_declared=from_wrapper
        )
        action_kol_id = self._kol_id(action, intent)

        summary = {
            "trade_action_id": action.trade_action_id,
            "ticker": action.target.ticker,
            "company_name": action.target.company_name,
            "direction": self._enum_value(action.direction),
            "summary": self._summary(action),
            "canonical_trace_status": materialized_status,
            "validation_status": self._validation_status(action),
            "kol_id": action_kol_id,
            "created_at": action.timestamp.isoformat(),
            "backtest_return_pct": self._backtest_return_pct(action),
        }
        ticker_values = (
            action.target.ticker,
            action.target.ticker_normalized or "",
        )
        return IndexedTradeAction(
            action=action,
            path=path,
            summary=summary,
            ticker_search_values=ticker_values,
            source_file=source_file,
            from_wrapper=from_wrapper,
        )

    def _load_wrapper_entries(self, path: Path) -> list[IndexedTradeAction]:
        """Expand a canonical ``*_actions.json`` wrapper into index entries.

        The F5 extraction route writes a batch wrapper shaped as
        ``{"source_file", "extracted_at", "model", "actions": [TradeAction, ...]}``.
        Every embedded dict is a fully-provenanced canonical TradeAction, so each
        one becomes its own audit row and the wrapper's ``source_file`` link is
        carried through. Legacy batch products (pre-canonical extractor output)
        are NOT canonical wrappers and are skipped, preserving the historical
        "drop *_actions.json" behaviour for them.
        """

        payload = self._safe_load_json(path)
        if not isinstance(payload, dict) or not self._is_canonical_wrapper(payload):
            return []

        raw_actions = payload.get("actions")
        if not isinstance(raw_actions, list):
            return []

        source_file = payload.get("source_file")
        if not isinstance(source_file, str) or not source_file:
            source_file = None

        entries: list[IndexedTradeAction] = []
        for raw in raw_actions:
            if not isinstance(raw, dict):
                continue
            action = self._safe_load_model_from_obj(path, raw, TradeAction)
            if action is None:
                continue
            entries.append(
                self._build_index_entry(
                    action, path, source_file=source_file, from_wrapper=True
                )
            )
        return entries

    @staticmethod
    def _is_canonical_wrapper(payload: dict[str, Any]) -> bool:
        """Distinguish canonical route wrappers from legacy batch products.

        The canonical F3→F4→F5 route tags its output with a ``canonical-*``
        model marker (e.g. ``canonical-f2-envelope`` / ``canonical-programmatic``).
        Legacy ``*_actions.json`` files carry a raw model name (or none); those
        must keep being skipped so non-canonical rows never reach the audit
        station.
        """

        return str(payload.get("model") or "").startswith("canonical")

    def _find_indexed_action(self, trade_action_id: str) -> IndexedTradeAction | None:
        for indexed in self._get_indexed_actions():
            if indexed.action.trade_action_id == trade_action_id:
                return indexed
        return None

    def _load_intent_for_action(
        self,
        action: TradeAction,
    ) -> NormalizedInvestmentIntent | None:
        if not action.intent_id:
            return None
        return self._safe_load_model(
            self.data_root / "F3_intents" / f"{action.intent_id}.json",
            NormalizedInvestmentIntent,
        )

    def _load_policy_for_action(self, action: TradeAction) -> PolicyMappingResult | None:
        if not action.policy_id:
            return None
        return self._safe_load_model(
            self.data_root / "F4_policy_mapped" / f"{action.policy_id}.json",
            PolicyMappingResult,
        )

    def _load_evidence_spans_for_action(self, action: TradeAction) -> list[dict[str, Any]]:
        """Resolve the action's evidence_span_ids to EvidenceSpan dicts.

        Reads ``F2_evidence/{evidence_span_id}.json`` sidecars (written by the
        canonical runner). Missing/unreadable spans are skipped so a partial
        evidence set still renders rather than failing the whole bundle.
        """
        spans: list[dict[str, Any]] = []
        evidence_dir = self.data_root / "F2_evidence"
        for span_id in action.evidence_span_ids:
            span = self._safe_load_model(
                evidence_dir / f"{span_id}.json", EvidenceSpan
            )
            if span is not None:
                spans.append(span.model_dump(mode="json"))
        return spans

    def _load_envelope_for_action(
        self,
        action: TradeAction,
        intent: NormalizedInvestmentIntent | None,
        source_file: str | None = None,
    ) -> ContentEnvelope | None:
        # Prefer the wrapper's source_file link: it points at the real F2 file
        # (e.g. ``local_<hash>.json``), whereas ``content_id`` / ``envelope_id``
        # are ``env_<hash>`` ids that do not match the F2 filename, so the
        # content_id lookup silently misses and the envelope panel falls back to
        # a stub. Resolve by basename under data_root so it stays portable
        # regardless of the absolute path baked into source_file.
        if source_file:
            # Try the portable location first (F2 co-located under this
            # data_root — the normal case), then the literal absolute path baked
            # into the wrapper (handles a split F2/F5 layout).
            for candidate in (
                self.data_root / "F2_anchored" / Path(source_file).name,
                Path(source_file),
            ):
                envelope = self._safe_load_model(candidate, ContentEnvelope)
                if envelope is not None:
                    return envelope

        envelope_id = intent.envelope_id if intent else action.source.content_id
        if not envelope_id:
            return None
        return self._safe_load_model(
            self.data_root / "F2_anchored" / f"{envelope_id}.json",
            ContentEnvelope,
        )

    def _materialized_trace_status(
        self,
        action: TradeAction,
        intent: NormalizedInvestmentIntent | None,
        policy: PolicyMappingResult | None,
        *,
        trust_self_declared: bool = False,
    ) -> str:
        has_intent_id = bool(action.intent_id)
        has_policy_id = bool(action.policy_id)
        if not has_intent_id and not has_policy_id:
            return "non_canonical"

        has_full_provenance = (
            has_intent_id
            and has_policy_id
            and bool(action.evidence_span_ids)
            and action.execution_timing is not None
        )

        # Golden-path: confirm canonical against persisted F3/F4 sidecar files.
        if has_full_provenance and intent is not None and policy is not None:
            return "canonical"

        # Wrapper-path: the F5 route persists only F5, so F3/F4 sidecars are
        # absent by design. The canonical runner already validated the full
        # F3→F4→F5 trace before writing, so trust the action's own
        # schema-validated trace status rather than downgrading to "partial".
        if trust_self_declared and has_full_provenance:
            self_declared = self._enum_value(action.canonical_trace_status)
            if self_declared in TRACE_STATUSES:
                return self_declared

        return "partial"

    def _envelope_context(
        self,
        action: TradeAction,
        intent: NormalizedInvestmentIntent | None,
        envelope: ContentEnvelope | None,
        *,
        source_file: str | None = None,
    ) -> dict[str, Any]:
        if envelope is None:
            envelope_id = intent.envelope_id if intent else action.source.content_id
            return self._drop_none(
                {
                    "envelope_id": envelope_id,
                    "source_text": action.source.evidence_text or "",
                    "creator_id": self._kol_id(action, intent),
                    "kol_id": self._kol_id(action, intent),
                    "source_file": source_file,
                }
            )

        kol_id = self._kol_id(action, intent) or envelope.creator_id
        return self._drop_none(
            {
                "envelope_id": envelope.envelope_id,
                "source_text": self._source_text(envelope) or action.source.evidence_text,
                "source_published_at": (
                    envelope.published_at.isoformat()
                    if envelope.published_at is not None
                    else None
                ),
                "creator_id": envelope.creator_id,
                "kol_id": kol_id,
                "source_file": source_file,
            }
        )

    @staticmethod
    def _source_text(envelope: ContentEnvelope) -> str:
        blocks = sorted(envelope.blocks, key=lambda block: block.order_index)
        return "\n\n".join(block.text for block in blocks if block.text)

    @staticmethod
    def _kol_id(
        action: TradeAction,
        intent: NormalizedInvestmentIntent | None = None,
    ) -> str | None:
        return action.source.creator_id or (intent.creator_id if intent else None)

    @staticmethod
    def _summary(action: TradeAction) -> str:
        rationale = (action.rationale or "").strip()
        if rationale:
            return f"{rationale[:40].rstrip()}..." if len(rationale) > 40 else rationale

        if action.action_chain:
            step = action.action_chain[0]
            action_type = AuditAssembler._enum_value(step.action_type)
            trigger = (step.trigger_condition or step.notes or "").strip()
            return f"{action_type}: {trigger}" if trigger else action_type

        evidence = (action.source.evidence_text or "").strip()
        if evidence:
            return f"{evidence[:40].rstrip()}..." if len(evidence) > 40 else evidence
        return action.target.ticker

    @staticmethod
    def _backtest_return_pct(action: TradeAction) -> float | None:
        if action.backtest_result is None:
            return None
        return action.backtest_result.return_pct

    @staticmethod
    def _validation_status(action: TradeAction) -> str:
        return AuditAssembler._enum_value(action.validation_status)

    @staticmethod
    def _matches_ticker_values(values: tuple[str, ...], ticker: str) -> bool:
        needle = ticker.casefold()
        return any(needle in value.casefold() for value in values if value)

    @staticmethod
    def _enum_value(value: Any) -> str:
        return value.value if hasattr(value, "value") else str(value)

    @staticmethod
    def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if value is not None}

    @staticmethod
    def _safe_load_model(path: Path, model_type: type[ModelT]) -> ModelT | None:
        if not path.exists():
            return None
        try:
            return model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            logger.warning("Failed to load %s from %s: %s", model_type.__name__, path, exc)
            return None

    @staticmethod
    def _safe_load_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Failed to read JSON from %s: %s", path, exc)
            return None

    @staticmethod
    def _safe_load_model_from_obj(
        path: Path, raw: Any, model_type: type[ModelT]
    ) -> ModelT | None:
        # Re-serialize to JSON so Pydantic applies its JSON coercion path
        # (enums / datetimes are strict under model_validate on a plain dict,
        # but coerce from strings under model_validate_json).
        try:
            return model_type.model_validate_json(json.dumps(raw))
        except (TypeError, ValidationError, ValueError) as exc:
            logger.warning(
                "Failed to validate %s in %s: %s", model_type.__name__, path, exc
            )
            return None
