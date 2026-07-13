"""Tests for the F2 sector→ETF proxy registry and its F5 gates.

Covers three layers:
  1. SectorProxyRegistry — YAML file truth, TTL cache, instrument validation,
     market preference / fallback, audit provenance.
  2. Repo consistency pins — every sector placeholder in ENTITY_REGISTRY must
     have a proxy entry in configs/sector_proxies.yaml, and every configured
     instrument must be a plausible tradable symbol (drift guard between the
     two file truths).
  3. Canonical runner gates — a sector intent now trades through its proxy
     (with metadata.sector_proxy provenance), an unmapped sector is rejected
     as sector_proxy_not_configured, and pseudo-tickers are rejected instead
     of masquerading as TargetInfo.ticker.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from finer.entity_registry import ENTITY_REGISTRY, is_plausible_tradable_symbol
from finer.enrichment.sector_proxy import (
    SectorProxyRegistry,
    get_sector_proxy_registry,
    resolve_sector_proxy,
)
from finer.pipeline.canonical_runner import run_canonical_from_artifacts
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.entity_anchor import EntityAnchor
from finer.schemas.evidence import EvidenceSpan
from finer.schemas.investment_intent import NormalizedInvestmentIntent
from finer.schemas.policy import PolicyMappedIntent, PolicyMappingBatch
from finer.schemas.quality import QualityCard

_PUBLISHED_AT = datetime(2026, 3, 12, 15, 36, tzinfo=timezone(timedelta(hours=8)))
_REPO_ROOT = Path(__file__).resolve().parents[1]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_config(root: Path, body: str) -> None:
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / "configs" / "sector_proxies.yaml").write_text(body, encoding="utf-8")


_MINIMAL_CONFIG = """
version: 3
proxies:
  ENERGY_STORAGE:
    sector_name: 储能
    instruments:
      - symbol: "159566.SZ"
        market: CN
        name: 储能电池ETF易方达
        priority: 1
      - symbol: "LIT"
        market: US
        name: Global X Lithium & Battery Tech
        priority: 2
  BROKEN_SECTOR:
    sector_name: 坏板块
    instruments:
      - symbol: "NOT_A_TICKER"
        market: CN
        name: 占位符混入
"""


def _pass_card() -> QualityCard:
    return QualityCard(
        readability_score=0.95,
        semantic_completeness_score=0.9,
        financial_relevance_score=0.95,
        entity_resolution_score=0.9,
        temporal_resolution_score=0.85,
        evidence_traceability_score=0.9,
    )


def _intent(
    *,
    target_type: str = "sector",
    target_name: str = "储能",
    target_symbol: str = "ENERGY_STORAGE",
    market: str = "CN",
    direction: str = "bullish",
) -> NormalizedInvestmentIntent:
    return NormalizedInvestmentIntent(
        intent_id=str(uuid4()),
        envelope_id="env-test-001",
        block_ids=["b0"],
        creator_id="kol-test-001",
        target_type=target_type,
        target_name=target_name,
        target_symbol=target_symbol,
        market=market,
        direction=direction,
        actionability="explicit_action",
        position_delta_hint="add",
        conviction=0.8,
        confidence=0.8,
        evidence_span_ids=["span-f3"],
        ambiguity_flags=[],
    )


def _mapped(intent: NormalizedInvestmentIntent) -> PolicyMappedIntent:
    return PolicyMappedIntent(
        mapped_id=str(uuid4()),
        intent_id=intent.intent_id,
        policy_id="policy-test-001",
        original_intent_summary=f"{intent.direction} {intent.target_name}",
        action_hint="open_position",
        position_sizing_hint="small",
        holding_period_hint="short_term",
        risk_notes=[],
        mapping_confidence=0.9,
        requires_human_review=False,
    )


def _envelope_with_anchor(symbol: str, raw_text: str) -> ContentEnvelope:
    """F2-shaped envelope: one block, one anchor grounded by one block span."""
    span = EvidenceSpan(
        evidence_span_id="f2-span-0",
        block_id="b0",
        char_start=0,
        char_end=len(raw_text),
        text=raw_text,
        span_type="entity",
        confidence=1.0,
    )
    anchor = EntityAnchor(
        entity_type="sector",
        raw_text=raw_text,
        resolved_symbol=symbol,
        market="CN",
        confidence=1.0,
        evidence_span_id=span.evidence_span_id,
        metadata={"evidence_span_ids": [span.evidence_span_id]},
    )
    block = ContentBlock(
        block_id="b0",
        block_type="paragraph",
        text=f"{raw_text}板块今天继续走强，建议关注。",
        order=0,
        quality_card=_pass_card(),
        evidence_spans=[span],
    )
    return ContentEnvelope(
        envelope_id="env-test-001",
        source_type="feishu_doc",
        creator_id="kol-test-001",
        published_at=_PUBLISHED_AT,
        quality_card=_pass_card(),
        blocks=[block],
        entity_anchors=[anchor],
        temporal_anchors=[],
    )


async def _run(
    intent: NormalizedInvestmentIntent,
    envelope: ContentEnvelope,
    strategy: str = "programmatic",
):
    mapped = _mapped(intent)
    batch = PolicyMappingBatch(mapped_intents=[mapped])
    return await run_canonical_from_artifacts(
        intents=[intent],
        policy_batch=batch,
        evidence_spans=[],
        envelope=envelope,
        strategy=strategy,
    )


def _mock_llm(raw_actions: list) -> MagicMock:
    """LLMClient stub whose chat() returns the given F5 action array."""
    client = MagicMock()
    client.chat.return_value = json.dumps(raw_actions)
    return client


# ── 1. SectorProxyRegistry unit tests ────────────────────────────────────────


class TestSectorProxyRegistry:
    def test_resolves_priority_and_provenance(self, tmp_path: Path):
        _write_config(tmp_path, _MINIMAL_CONFIG)
        registry = SectorProxyRegistry(root=tmp_path)
        res = registry.resolve("ENERGY_STORAGE")
        assert res is not None
        assert res.proxy_symbol == "159566.SZ"
        assert res.proxy_market == "CN"
        assert res.sector_name == "储能"
        assert res.config_version == 3
        assert res.rule == "configs/sector_proxies.yaml#ENERGY_STORAGE/159566.SZ"
        meta = res.audit_metadata()
        assert meta["sector_symbol"] == "ENERGY_STORAGE"
        assert meta["proxy_symbol"] == "159566.SZ"
        assert meta["rule"].startswith("configs/sector_proxies.yaml#")

    def test_market_preference_and_fallback(self, tmp_path: Path):
        _write_config(tmp_path, _MINIMAL_CONFIG)
        registry = SectorProxyRegistry(root=tmp_path)
        assert registry.resolve("ENERGY_STORAGE", market="US").proxy_symbol == "LIT"
        # Unknown market falls back to priority order, never to None.
        assert registry.resolve("ENERGY_STORAGE", market="HK").proxy_symbol == "159566.SZ"

    def test_placeholder_instrument_rejected_at_load(self, tmp_path: Path):
        _write_config(tmp_path, _MINIMAL_CONFIG)
        registry = SectorProxyRegistry(root=tmp_path)
        # BROKEN_SECTOR's only instrument is a placeholder → entry dropped.
        assert registry.resolve("BROKEN_SECTOR") is None
        assert "BROKEN_SECTOR" not in registry.known_sectors()

    def test_unknown_sector_and_missing_config(self, tmp_path: Path):
        _write_config(tmp_path, _MINIMAL_CONFIG)
        registry = SectorProxyRegistry(root=tmp_path)
        assert registry.resolve("NO_SUCH_SECTOR") is None
        assert registry.resolve(None) is None
        empty = SectorProxyRegistry(root=tmp_path / "nowhere")
        assert empty.resolve("ENERGY_STORAGE") is None

    def test_file_edit_visible_after_cache_clear(self, tmp_path: Path):
        _write_config(tmp_path, _MINIMAL_CONFIG)
        registry = SectorProxyRegistry(root=tmp_path)
        assert registry.resolve("ENERGY_STORAGE") is not None
        _write_config(tmp_path, "version: 4\nproxies: {}\n")
        registry.clear_cache()
        assert registry.resolve("ENERGY_STORAGE") is None

    def test_malformed_values_degrade_never_crash(self, tmp_path: Path):
        """Operator hand-edits (`version: v2`, `priority: high`) must degrade
        with a warning, never raise out of resolve() into F5 (2026-07-11
        review finding)."""
        _write_config(
            tmp_path,
            """
version: v2
proxies:
  ENERGY_STORAGE:
    sector_name: 储能
    instruments:
      - symbol: "159566.SZ"
        market: CN
        name: 储能电池ETF易方达
        priority: high
  BROKERAGE:
    sector_name: 券商
    instruments:
      - symbol: "512880.SH"
        market: CN
        name: 证券ETF
""",
        )
        registry = SectorProxyRegistry(root=tmp_path)
        res = registry.resolve("ENERGY_STORAGE")
        assert res is not None and res.proxy_symbol == "159566.SZ"
        assert res.config_version == 0  # bad version coerces to 0, not a crash
        assert registry.resolve("BROKERAGE") is not None

    def test_proxies_as_list_degrades_to_empty(self, tmp_path: Path):
        _write_config(tmp_path, "version: 1\nproxies:\n  - ENERGY_STORAGE\n")
        registry = SectorProxyRegistry(root=tmp_path)
        assert registry.resolve("ENERGY_STORAGE") is None

    def test_per_root_singleton(self, tmp_path: Path):
        _write_config(tmp_path, _MINIMAL_CONFIG)
        assert get_sector_proxy_registry(tmp_path) is get_sector_proxy_registry(tmp_path)
        res = resolve_sector_proxy("ENERGY_STORAGE", root=tmp_path)
        assert res is not None and res.proxy_symbol == "159566.SZ"


# ── 2. Repo consistency pins ─────────────────────────────────────────────────


class TestRepoConfigConsistency:
    def test_every_registry_sector_has_a_proxy(self):
        """Drift guard: a sector alias without a proxy entry silently turns
        that sector's viewpoints into sector_proxy_not_configured rejections."""
        registry = SectorProxyRegistry(root=_REPO_ROOT, ttl_seconds=0)
        sector_symbols = {
            ticker
            for (ticker, _market, etype) in ENTITY_REGISTRY.values()
            if etype == "sector"
        }
        missing = {s for s in sector_symbols if registry.resolve(s) is None}
        assert not missing, f"sectors without proxy config: {sorted(missing)}"

    def test_every_configured_instrument_is_tradable_shaped(self):
        registry = SectorProxyRegistry(root=_REPO_ROOT, ttl_seconds=0)
        for sector in registry.known_sectors():
            res = registry.resolve(sector)
            assert res is not None
            assert is_plausible_tradable_symbol(res.proxy_symbol), (
                sector,
                res.proxy_symbol,
            )


# ── 3. Tradable-symbol validation ────────────────────────────────────────────


class TestPlausibleTradableSymbol:
    def test_known_and_well_formed_symbols_pass(self):
        for sym in ["NVDA", "0700.HK", "600989.SH", "159566.SZ", "SOX", "BTC", "ORCL"]:
            assert is_plausible_tradable_symbol(sym), sym

    def test_pseudo_tickers_fail(self):
        for sym in [None, "", "宁德时代", "ENERGY_STORAGE", "OPTICAL_MODULE",
                    "nvda", "TOOLONGSYM", "N/A", "US stock"]:
            assert not is_plausible_tradable_symbol(sym), sym


# ── 4. Canonical runner gates ────────────────────────────────────────────────


class TestRunnerSectorProxyGate:
    @pytest.mark.asyncio
    async def test_sector_intent_trades_through_proxy(self):
        """储能 sector intent → action on the configured ETF proxy, grounded in
        the sector placeholder's F2 evidence, with full provenance metadata."""
        intent = _intent()
        envelope = _envelope_with_anchor("ENERGY_STORAGE", "储能")
        result = await _run(intent, envelope)
        assert not result.rejected_intents
        assert len(result.trade_actions) == 1
        action = result.trade_actions[0]
        assert action.target.ticker == "159566.SZ"
        assert action.target.instrument_type == "etf"
        assert action.target.company_name == "储能电池ETF易方达"
        # grounding ran against the ORIGINAL sector symbol's F2 evidence
        assert action.evidence_span_ids == ["f2-span-0"]
        proxy_meta = action.metadata.get("sector_proxy")
        assert proxy_meta is not None
        assert proxy_meta["sector_symbol"] == "ENERGY_STORAGE"
        assert proxy_meta["sector_name"] == "储能"
        assert proxy_meta["proxy_symbol"] == "159566.SZ"
        assert proxy_meta["rule"].startswith("configs/sector_proxies.yaml#")

    @pytest.mark.asyncio
    async def test_unmapped_sector_rejected_with_new_reason(self):
        intent = _intent(
            target_name="神秘板块", target_symbol="UNMAPPED_SECTOR_X"
        )
        envelope = _envelope_with_anchor("UNMAPPED_SECTOR_X", "神秘板块")
        result = await _run(intent, envelope)
        assert not result.trade_actions
        assert [r.reason for r in result.rejected_intents] == [
            "sector_proxy_not_configured"
        ]

    @pytest.mark.asyncio
    async def test_pseudo_ticker_rejected(self):
        """A stock-typed intent whose symbol is a Chinese name must not reach
        TargetInfo.ticker."""
        intent = _intent(
            target_type="stock",
            target_name="宁德时代",
            target_symbol="宁德时代",
        )
        envelope = _envelope_with_anchor("宁德时代", "宁德时代")
        result = await _run(intent, envelope)
        assert not result.trade_actions
        assert [r.reason for r in result.rejected_intents] == ["pseudo_ticker_symbol"]

    @pytest.mark.asyncio
    async def test_well_formed_unknown_symbol_still_passes(self):
        """The pseudo-ticker gate must not reject legit tickers that simply
        aren't in the registry yet."""
        intent = _intent(
            target_type="stock",
            target_name="Oracle",
            target_symbol="ORCL",
        )
        envelope = _envelope_with_anchor("ORCL", "Oracle")
        result = await _run(intent, envelope)
        assert not result.rejected_intents
        assert len(result.trade_actions) == 1
        assert result.trade_actions[0].target.ticker == "ORCL"


class TestRunnerLLMPathGates:
    """The llm_guided path mirrors every programmatic gate and never trusts
    the LLM's ticker/market echo for the composed TargetInfo."""

    @pytest.mark.asyncio
    async def test_llm_sector_intent_trades_through_proxy(self):
        intent = _intent()  # 储能 sector → ENERGY_STORAGE
        envelope = _envelope_with_anchor("ENERGY_STORAGE", "储能")
        llm = _mock_llm([{
            "ticker": "ENERGY_STORAGE", "market": "CN", "direction": "bullish",
            "action_type": "long", "position_size_pct": 0.05,
            "confidence": 0.8, "notes": "sector view",
        }])
        with patch("finer.llm.LLMClient.auto", return_value=llm):
            result = await _run(intent, envelope, strategy="llm_guided")
        assert len(result.trade_actions) == 1
        action = result.trade_actions[0]
        assert action.target.ticker == "159566.SZ"
        assert action.target.instrument_type == "etf"
        assert action.metadata["sector_proxy"]["sector_symbol"] == "ENERGY_STORAGE"

    @pytest.mark.asyncio
    async def test_llm_market_echo_and_instrument_come_from_intent(self):
        """LLM claims market=US for a CN stock: the composed action keeps the
        intent's market and maps instrument_type from the intent target_type."""
        intent = _intent(
            target_type="stock",
            target_name="宁德时代",
            target_symbol="300750.SZ",
            market="CN",
        )
        envelope = _envelope_with_anchor("300750.SZ", "宁德时代")
        llm = _mock_llm([{
            "ticker": "300750.SZ", "market": "US", "direction": "bullish",
            "action_type": "long", "confidence": 0.7, "notes": "",
        }])
        with patch("finer.llm.LLMClient.auto", return_value=llm):
            result = await _run(intent, envelope, strategy="llm_guided")
        assert len(result.trade_actions) == 1
        action = result.trade_actions[0]
        assert action.target.ticker == "300750.SZ"
        assert action.target.market == "CN"
        assert action.target.instrument_type == "stock"

    @pytest.mark.asyncio
    async def test_llm_pseudo_ticker_rejected(self):
        """LLM echoes the company name as ticker; the intent's own symbol is
        also a Chinese name → pseudo_ticker_symbol, no action."""
        intent = _intent(
            target_type="stock",
            target_name="宁德时代",
            target_symbol="宁德时代",
        )
        envelope = _envelope_with_anchor("宁德时代", "宁德时代")
        llm = _mock_llm([{
            "ticker": "宁德时代", "market": "CN", "direction": "bullish",
            "action_type": "long", "confidence": 0.7, "notes": "",
        }])
        with patch("finer.llm.LLMClient.auto", return_value=llm):
            result = await _run(intent, envelope, strategy="llm_guided")
        assert not result.trade_actions
        assert "pseudo_ticker_symbol" in [r.reason for r in result.rejected_intents]

    @pytest.mark.asyncio
    async def test_llm_unmapped_sector_rejected(self):
        intent = _intent(target_name="神秘板块", target_symbol="UNMAPPED_SECTOR_X")
        envelope = _envelope_with_anchor("UNMAPPED_SECTOR_X", "神秘板块")
        llm = _mock_llm([{
            "ticker": "UNMAPPED_SECTOR_X", "market": "CN", "direction": "bullish",
            "action_type": "long", "confidence": 0.7, "notes": "",
        }])
        with patch("finer.llm.LLMClient.auto", return_value=llm):
            result = await _run(intent, envelope, strategy="llm_guided")
        assert not result.trade_actions
        assert "sector_proxy_not_configured" in [
            r.reason for r in result.rejected_intents
        ]
