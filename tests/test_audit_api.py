"""Tests for the Audit Trace backend API."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finer.schemas.content_envelope import (
    BlockProvenance,
    BlockQuality,
    ContentBlock,
    ContentEnvelope,
)
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappingResult, PolicyRiskConstraints
from finer.schemas.quality import QualityCard
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    BacktestResult,
    ExecutionTiming,
    MarketSession,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeDirection,
    TriggerType,
    ValidationStatus,
)
from finer.services.audit_assembler import AuditAssembler


def _dt(hour: int = 9) -> datetime:
    return datetime(2026, 5, 20, hour, 30, tzinfo=timezone.utc)


def _block_quality() -> BlockQuality:
    return BlockQuality(
        readability=0.9,
        extraction_confidence=0.9,
        structural_confidence=0.9,
        completeness=0.9,
        noise_score=0.1,
        quality_flags=[],
    )


def _block_provenance() -> BlockProvenance:
    return BlockProvenance(extractor="test", extractor_version="1")


def _quality_card() -> QualityCard:
    return QualityCard(
        readability_score=0.9,
        semantic_completeness_score=0.9,
        financial_relevance_score=0.9,
        entity_resolution_score=0.9,
        temporal_resolution_score=0.9,
        evidence_traceability_score=0.9,
    )


def _timing() -> ExecutionTiming:
    return ExecutionTiming(
        intent_published_at=_dt(9),
        intent_effective_at=_dt(10),
        action_decision_at=_dt(9),
        action_executable_at=_dt(10),
        market="CN",
        timezone="Asia/Shanghai",
        market_session_at_publish=MarketSession.AFTER_CLOSE,
        timing_policy_id="market-calendar-v1",
    )


def _action(
    *,
    trade_action_id: str,
    ticker: str,
    content_id: str,
    creator_id: str | None,
    intent_id: str | None,
    policy_id: str | None,
    evidence_span_ids: list[str],
    validation_status: ValidationStatus = ValidationStatus.PENDING,
    timestamp: datetime | None = None,
    rationale: str = "看好基本面修复，分批建仓并设置止损。",
    return_pct: float | None = None,
) -> TradeAction:
    backtest_result = (
        BacktestResult(return_pct=return_pct)
        if return_pct is not None
        else None
    )
    return TradeAction(
        trade_action_id=trade_action_id,
        timestamp=timestamp or _dt(12),
        source=SourceInfo(
            creator_id=creator_id,
            content_id=content_id,
            evidence_text="今天看好测试标的，准备分批建仓。",
        ),
        target=TargetInfo(
            ticker=ticker,
            market="CN",
            instrument_type="stock",
            company_name=f"{ticker} 公司",
        ),
        direction=TradeDirection.BULLISH,
        action_chain=[
            ActionStep(
                sequence=1,
                action_type=ActionType.LONG,
                trigger_type=TriggerType.MANUAL,
                trigger_condition="分批建仓",
            )
        ],
        intent_id=intent_id,
        policy_id=policy_id,
        evidence_span_ids=evidence_span_ids,
        execution_timing=_timing() if intent_id or policy_id else None,
        confidence=0.9,
        model_version="test",
        extraction_method="test",
        validation_status=validation_status,
        rationale=rationale,
        backtest_result=backtest_result,
    )


def _intent(
    *,
    intent_id: str,
    envelope_id: str,
    creator_id: str,
    target_symbol: str,
    evidence_span_ids: list[str],
) -> NormalizedInvestmentIntent:
    return NormalizedInvestmentIntent(
        intent_id=intent_id,
        envelope_id=envelope_id,
        block_ids=[f"block-{envelope_id}"],
        creator_id=creator_id,
        target_type="stock",
        target_name=f"{target_symbol} 公司",
        target_symbol=target_symbol,
        market="CN",
        direction="bullish",
        actionability="explicit_action",
        position_delta_hint="open",
        conviction=0.85,
        confidence=0.9,
        evidence_span_ids=evidence_span_ids,
        created_at=_dt(11),
    )


def _policy(policy_id: str, intent_id: str, creator_id: str) -> PolicyMappingResult:
    return PolicyMappingResult(
        policy_id=policy_id,
        intent_id=intent_id,
        creator_id=creator_id,
        kol_id=creator_id,
        policy_version="global-base-v1",
        policy_layers_applied=["GlobalBase"],
        action_hint="open_position",
        position_sizing_hint="medium",
        holding_period_hint="medium_term",
        risk_constraints=PolicyRiskConstraints(
            max_position_hint="medium",
            requires_human_review=False,
        ),
        mapping_rationale="explicit action maps to open_position",
        layer_traces=[],
        decisions=[],
        confidence=0.9,
        original_intent_confidence=0.9,
        created_at=_dt(11),
    )


def _envelope(envelope_id: str, creator_id: str, text: str) -> ContentEnvelope:
    return ContentEnvelope(
        envelope_id=envelope_id,
        source_type="feishu_chat",
        creator_id=creator_id,
        published_at=_dt(9),
        quality_card=_quality_card(),
        blocks=[
            ContentBlock(
                block_id=f"block-{envelope_id}",
                envelope_id=envelope_id,
                block_type="paragraph",
                text=text,
                order_index=0,
                quality=_block_quality(),
                provenance=_block_provenance(),
            )
        ],
    )


def _write_model(path: Path, model) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _seed_action_set(data_root: Path) -> None:
    canonical = _action(
        trade_action_id="ta-canonical",
        ticker="600519",
        content_id="env-canonical",
        creator_id="kol-a",
        intent_id="intent-canonical",
        policy_id="policy-canonical",
        evidence_span_ids=["span-1"],
        validation_status=ValidationStatus.VERIFIED,
        timestamp=_dt(12),
        return_pct=0.123,
    )
    partial = _action(
        trade_action_id="ta-partial",
        ticker="000858",
        content_id="env-partial",
        creator_id=None,
        intent_id="intent-partial",
        policy_id="policy-missing",
        evidence_span_ids=["span-2"],
        validation_status=ValidationStatus.UNDER_REVIEW,
        timestamp=_dt(11),
    )
    non_canonical = _action(
        trade_action_id="ta-non-canonical",
        ticker="300750",
        content_id="env-non-canonical",
        creator_id="kol-c",
        intent_id=None,
        policy_id=None,
        evidence_span_ids=[],
        timestamp=_dt(10),
        rationale="",
    )

    _write_model(data_root / "F5_executed" / "ta-canonical.json", canonical)
    _write_model(data_root / "F5_executed" / "ta-partial.json", partial)
    _write_model(data_root / "F5_executed" / "ta-non-canonical.json", non_canonical)
    wrapper_path = data_root / "F5_executed" / "legacy_source_actions.json"
    wrapper_path.write_text(
        json.dumps(
            {
                "source_file": "legacy_source.json",
                "actions": [canonical.model_dump(mode="json")],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    _write_model(
        data_root / "F3_intents" / "intent-canonical.json",
        _intent(
            intent_id="intent-canonical",
            envelope_id="env-canonical",
            creator_id="kol-a",
            target_symbol="600519",
            evidence_span_ids=["span-1"],
        ),
    )
    _write_model(
        data_root / "F3_intents" / "intent-partial.json",
        _intent(
            intent_id="intent-partial",
            envelope_id="env-partial",
            creator_id="kol-b",
            target_symbol="000858",
            evidence_span_ids=["span-2"],
        ),
    )
    _write_model(
        data_root / "F4_policy_mapped" / "policy-canonical.json",
        _policy("policy-canonical", "intent-canonical", "kol-a"),
    )
    _write_model(
        data_root / "F2_anchored" / "env-canonical.json",
        _envelope("env-canonical", "kol-a", "今天看好 600519，准备分批建仓。"),
    )
    _write_model(
        data_root / "F2_anchored" / "env-partial.json",
        _envelope("env-partial", "kol-b", "今天看好 000858，准备分批建仓。"),
    )


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from finer.api.routes import audit as audit_route
    from finer.api.server import create_app

    _seed_action_set(tmp_path)
    monkeypatch.setattr(
        audit_route,
        "_ASSEMBLER",
        AuditAssembler(data_root=tmp_path, ttl_seconds=0),
    )
    return TestClient(create_app(), raise_server_exceptions=False)


def test_trace_bundle_canonical(client: TestClient) -> None:
    resp = client.get("/api/audit/actions/ta-canonical/trace")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {
        "trade_action",
        "intent",
        "policy",
        "evidence_spans",
        "envelope",
    }
    assert data["trade_action"]["canonical_trace_status"] == "canonical"
    assert data["intent"]["intent_id"] == "intent-canonical"
    assert data["policy"]["policy_id"] == "policy-canonical"
    assert data["evidence_spans"] == []
    assert data["envelope"]["envelope_id"] == "env-canonical"
    assert data["envelope"]["source_text"] == "今天看好 600519，准备分批建仓。"


def test_trace_bundle_partial_when_f4_missing(client: TestClient) -> None:
    resp = client.get("/api/audit/actions/ta-partial/trace")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["trade_action"]["canonical_trace_status"] == "partial"
    assert data["intent"]["intent_id"] == "intent-partial"
    assert data["policy"] is None
    assert data["envelope"]["kol_id"] == "kol-b"


def test_trace_bundle_non_canonical_fallback_envelope(client: TestClient) -> None:
    resp = client.get("/api/audit/actions/ta-non-canonical/trace")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["trade_action"]["canonical_trace_status"] == "non_canonical"
    assert data["intent"] is None
    assert data["policy"] is None
    assert data["envelope"]["envelope_id"] == "env-non-canonical"
    assert data["envelope"]["source_text"] == "今天看好测试标的，准备分批建仓。"


def test_action_list_filters_and_pagination(client: TestClient) -> None:
    canonical = client.get(
        "/api/audit/actions",
        params={"trace_status": "canonical", "kol_id": "kol-a", "ticker": "600"},
    ).json()["data"]
    assert canonical["total"] == 1
    assert canonical["actions"][0]["trade_action_id"] == "ta-canonical"
    assert canonical["actions"][0]["backtest_return_pct"] == 0.123

    partial = client.get(
        "/api/audit/actions",
        params={"trace_status": "partial", "kol_id": "kol-b"},
    ).json()["data"]
    assert partial["total"] == 1
    assert partial["actions"][0]["trade_action_id"] == "ta-partial"

    reviewed = client.get(
        "/api/audit/actions",
        params={"validation_status": "under_review"},
    ).json()["data"]
    assert reviewed["total"] == 1
    assert reviewed["actions"][0]["validation_status"] == "under_review"

    paged = client.get("/api/audit/actions", params={"limit": 1, "offset": 1}).json()["data"]
    assert paged["total"] == 3
    assert len(paged["actions"]) == 1


def test_wrapper_actions_files_are_skipped_without_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    wrapper_dir = tmp_path / "F5_executed"
    wrapper_dir.mkdir(parents=True)
    (wrapper_dir / "source_actions.json").write_text(
        json.dumps({"source_file": "source.json", "actions": []}),
        encoding="utf-8",
    )

    assembler = AuditAssembler(data_root=tmp_path, ttl_seconds=0)
    with caplog.at_level(logging.WARNING):
        data = assembler.list_action_summaries()

    assert data == {"actions": [], "total": 0}
    assert "Failed to load" not in caplog.text


def test_action_list_uses_cached_projection_without_reloading_trace_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_action_set(tmp_path)
    assembler = AuditAssembler(data_root=tmp_path, ttl_seconds=60)
    first = assembler.list_action_summaries()

    def fail_reload(*args, **kwargs):
        raise AssertionError("list endpoint should use cached projection")

    monkeypatch.setattr(assembler, "_load_intent_for_action", fail_reload)
    monkeypatch.setattr(assembler, "_load_policy_for_action", fail_reload)

    second = assembler.list_action_summaries(trace_status="canonical")
    assert first["total"] == 3
    assert second["total"] == 1
    assert second["actions"][0]["trade_action_id"] == "ta-canonical"


def test_action_summary_contract_keys(client: TestClient) -> None:
    data = client.get("/api/audit/actions", params={"limit": 1}).json()["data"]
    assert set(data["actions"][0].keys()) == {
        "trade_action_id",
        "ticker",
        "company_name",
        "direction",
        "summary",
        "canonical_trace_status",
        "validation_status",
        "kol_id",
        "created_at",
        "backtest_return_pct",
    }


def test_unknown_trade_action_returns_canonical_error(client: TestClient) -> None:
    resp = client.get(
        "/api/audit/actions/does-not-exist/trace",
        headers={"X-Request-ID": "req-audit-404"},
    )

    assert resp.status_code == 404
    data = resp.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "API_NTF_001"
    details = data["error"]["details"]
    assert details["request_id"] == "req-audit-404"
    assert details["stage"] == "F5_audit"
    assert details["operation"] == "get_trace"
    assert details["retryable"] is False
    assert "fix_hint" in details
    for sensitive in ("token", "secret", "password", "cookie", "authorization", "api_key"):
        assert sensitive not in details


# ---------------------------------------------------------------------------
# Canonical ``*_actions.json`` batch-wrapper bridging
#
# The F5 extraction route writes one wrapper file per source, shaped as
# ``{"source_file", "extracted_at", "model": "canonical-*", "actions": [...]}``.
# The assembler must expand these into per-action audit rows (and keep skipping
# legacy batch products that lack the canonical model marker).
# ---------------------------------------------------------------------------


def _write_canonical_wrapper(
    data_root: Path,
    stem: str,
    actions: list[TradeAction],
    *,
    model: str = "canonical-f2-envelope",
    source_file: str | None = None,
) -> Path:
    """Write a canonical F5 route wrapper file (``{stem}_actions.json``)."""

    path = data_root / "F5_executed" / f"{stem}_actions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source_file": source_file or f"/abs/data/F2_anchored/{stem}.json",
                "extracted_at": _dt(12).isoformat(),
                "model": model,
                "actions": [a.model_dump(mode="json") for a in actions],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _wrapper_action(trade_action_id: str, ticker: str, *, hour: int = 12) -> TradeAction:
    return _action(
        trade_action_id=trade_action_id,
        ticker=ticker,
        content_id=f"env-{trade_action_id}",
        creator_id="kol-wrap",
        intent_id=f"intent-{trade_action_id}",
        policy_id=f"policy-{trade_action_id}",
        evidence_span_ids=[f"span-{trade_action_id}"],
        timestamp=_dt(hour),
    )


def test_canonical_wrapper_expands_into_rows(tmp_path: Path) -> None:
    """Every embedded action in a canonical wrapper becomes its own audit row."""

    a1 = _wrapper_action("wrap-a1", "600519", hour=13)
    a2 = _wrapper_action("wrap-a2", "000858", hour=12)
    _write_canonical_wrapper(tmp_path, "local_w1", [a1, a2])

    assembler = AuditAssembler(data_root=tmp_path, ttl_seconds=0)
    listing = assembler.list_action_summaries(limit=100)

    assert listing["total"] == 2
    assert {row["trade_action_id"] for row in listing["actions"]} == {"wrap-a1", "wrap-a2"}
    # F3/F4 sidecars are not persisted by the route, yet the action self-declares
    # canonical with full provenance, so the materialized status stays canonical.
    assert all(row["canonical_trace_status"] == "canonical" for row in listing["actions"])


def test_canonical_wrapper_trace_bundle_keeps_source_file(tmp_path: Path) -> None:
    """The trace bundle resolves a wrapped action and preserves the source link."""

    action = _wrapper_action("wrap-trace", "600519")
    _write_canonical_wrapper(
        tmp_path, "local_wt", [action], source_file="/abs/F2_anchored/local_wt.json"
    )

    assembler = AuditAssembler(data_root=tmp_path, ttl_seconds=0)
    bundle = assembler.get_trace_bundle("wrap-trace")

    assert bundle is not None
    assert bundle["trade_action"]["trade_action_id"] == "wrap-trace"
    assert bundle["trade_action"]["canonical_trace_status"] == "canonical"
    assert bundle["envelope"]["source_file"] == "/abs/F2_anchored/local_wt.json"
    # F3/F4 sidecars are not persisted alongside the wrapper.
    assert bundle["intent"] is None
    assert bundle["policy"] is None


def test_legacy_wrapper_without_canonical_marker_is_skipped(tmp_path: Path) -> None:
    """A ``*_actions.json`` file lacking the canonical model marker stays skipped.

    This guards the distinction between canonical route output and legacy batch
    products: even when a legacy wrapper happens to embed a provenanced action,
    the missing ``canonical-*`` model tag keeps it out of the audit station.
    """

    legacy_action = _wrapper_action("legacy-a1", "600519")
    wrapper = tmp_path / "F5_executed" / "legacy_batch_actions.json"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        json.dumps(
            {
                "source_file": "legacy.json",
                "model": "qwen-max",  # raw model name → legacy, not canonical
                "actions": [legacy_action.model_dump(mode="json")],
            }
        ),
        encoding="utf-8",
    )

    assembler = AuditAssembler(data_root=tmp_path, ttl_seconds=0)
    assert assembler.list_action_summaries() == {"actions": [], "total": 0}


def test_canonical_wrapper_via_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list + trace endpoints serve actions sourced from a canonical wrapper."""

    from finer.api.routes import audit as audit_route
    from finer.api.server import create_app

    action = _wrapper_action("http-wrap", "600519")
    _write_canonical_wrapper(tmp_path, "local_http", [action])
    monkeypatch.setattr(
        audit_route,
        "_ASSEMBLER",
        AuditAssembler(data_root=tmp_path, ttl_seconds=0),
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    listing = client.get("/api/audit/actions").json()["data"]
    assert listing["total"] == 1
    assert listing["actions"][0]["trade_action_id"] == "http-wrap"

    trace = client.get("/api/audit/actions/http-wrap/trace")
    assert trace.status_code == 200
    assert trace.json()["data"]["trade_action"]["trade_action_id"] == "http-wrap"


def test_canonical_wrapper_and_single_file_coexist(tmp_path: Path) -> None:
    """Golden-path single files and route wrappers index together without clashing."""

    _seed_action_set(tmp_path)  # 3 single-file actions + 1 skipped legacy wrapper
    _write_canonical_wrapper(tmp_path, "local_mix", [_wrapper_action("wrap-mix", "AAPL")])

    assembler = AuditAssembler(data_root=tmp_path, ttl_seconds=0)
    listing = assembler.list_action_summaries(limit=100)

    # 3 single-file + 1 wrapped action; the no-marker legacy wrapper stays skipped.
    assert listing["total"] == 4
    ids = {row["trade_action_id"] for row in listing["actions"]}
    assert "wrap-mix" in ids
    assert {"ta-canonical", "ta-partial", "ta-non-canonical"} <= ids


# ---------------------------------------------------------------------------
# Optional smoke test against the real ``data/F5_executed`` produced by the F5
# route. Skips automatically when the canonical wrappers are absent (e.g. CI),
# so the suite stays portable. Override the data root with
# FINER_AUDIT_REAL_DATA_ROOT when running from an isolated worktree.
# ---------------------------------------------------------------------------

_REAL_DATA_ROOT = Path(
    os.environ.get(
        "FINER_AUDIT_REAL_DATA_ROOT",
        str(Path(__file__).resolve().parents[1] / "data"),
    )
)


def _has_real_canonical_wrappers() -> bool:
    f5_dir = _REAL_DATA_ROOT / "F5_executed"
    return f5_dir.is_dir() and any(f5_dir.glob("*_actions.json"))


@pytest.mark.skipif(
    not _has_real_canonical_wrappers(),
    reason="real canonical F5 *_actions.json wrappers not present",
)
def test_real_f5_executed_wrappers_are_served() -> None:
    assembler = AuditAssembler(data_root=_REAL_DATA_ROOT, ttl_seconds=0)
    listing = assembler.list_action_summaries(limit=10_000)

    assert listing["total"] >= 1
    assert all(
        row["canonical_trace_status"] in {"canonical", "partial", "non_canonical"}
        for row in listing["actions"]
    )

    first_id = listing["actions"][0]["trade_action_id"]
    bundle = assembler.get_trace_bundle(first_id)
    assert bundle is not None
    assert bundle["trade_action"]["trade_action_id"] == first_id
    assert set(bundle.keys()) == {
        "trade_action",
        "intent",
        "policy",
        "evidence_spans",
        "envelope",
    }
