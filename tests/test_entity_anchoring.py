"""Tests for F2 EntityAnchor L1 producer (deterministic registry alias scan).

See src/finer/enrichment/entity_anchoring.py and
docs/specs/2026-06-14-f2-anchoring-design.md.
"""

from finer.enrichment.entity_anchoring import (
    anchor_entities_l1,
    anchor_envelope_l1,
    build_f2_l1_envelope,
    scan_text,
)
from finer.schemas.content import ContentRecord
from finer.schemas.content_envelope import ContentEnvelope
from finer.schemas.entity_anchor import EntityAnchor


def _quality() -> dict:
    return {
        "readability_score": 0.9,
        "semantic_completeness_score": 0.9,
        "financial_relevance_score": 0.8,
        "entity_resolution_score": 0.0,
        "temporal_resolution_score": 0.0,
        "evidence_traceability_score": 0.8,
    }


def _block(block_id: str, text: str, *, page_index=None, bbox=None) -> dict:
    data = {
        "block_id": block_id,
        "block_type": "paragraph",
        "text": text,
        "order_index": int(block_id.removeprefix("b")) - 1,
        "quality": {
            "readability": 0.9,
            "extraction_confidence": 0.9,
            "structural_confidence": 0.8,
            "completeness": 1.0,
            "noise_score": 0.1,
            "quality_flags": [],
        },
        "provenance": {
            "raw_path": "data/L0_ingest/sample.pdf",
            "extractor": "test",
            "extractor_version": "1.0",
        },
    }
    if page_index is not None:
        data["page_index"] = page_index
    if bbox is not None:
        data["bbox"] = bbox
    return data


def _envelope(blocks: list[dict]) -> dict:
    return {
        "envelope_id": "env_test",
        "source_record_id": "local_test",
        "schema_version": "v1.0",
        "source_type": "pdf",
        "standardization_profile": "pdf_layout_v1",
        "source_uri": "data/L0_ingest/sample.pdf",
        "source_title": "sample.pdf",
        "raw_path": "data/L0_ingest/sample.pdf",
        "creator_name": "trader_ji",
        "ingested_at": "2026-06-14T00:00:00",
        "blocks": blocks,
        "quality_card": _quality(),
        "metadata": {"file_size_bytes": 123},
    }


def _f0_record() -> ContentRecord:
    return ContentRecord(
        content_id="local_test",
        source_type="livestream_audio",
        source_platform="local",
        creator_id="trader_ji",
        creator_name="trader_ji",
        raw_path="data/L0_ingest/sample.pdf",
        file_type="pdf",
    )


def test_cjk_alias_hit():
    tickers = {h.ticker for h in scan_text("今天看好腾讯和阿里")}
    assert "0700.HK" in tickers
    assert "9988.HK" in tickers


def test_english_ticker_hit():
    assert any(h.ticker == "NVDA" for h in scan_text("NVDA 大涨"))


def test_english_ticker_word_boundary_no_substring():
    # "LI"(理想) 不应误命中 "QUALITY" 中的子串 LI
    assert not any(h.alias == "LI" for h in scan_text("QUALITY CONTROL"))


def test_numeric_alias_word_boundary():
    assert any(h.ticker == "0700.HK" for h in scan_text("0700 今日收盘"))
    # 更长数字串不误命中
    assert not any(h.alias == "0700" for h in scan_text("订单号 070012345"))


def test_type_mapping_ticker_to_stock():
    anchors = anchor_entities_l1([("b1", "腾讯不错")])
    a = next(a for a in anchors if a.resolved_symbol == "0700.HK")
    assert a.entity_type == "stock"  # registry "ticker" → schema "stock"


def test_index_and_crypto_type():
    anchors = anchor_entities_l1([("b1", "大A走强，比特币反弹")])
    by_sym = {a.resolved_symbol: a for a in anchors}
    assert by_sym["000001.SH"].entity_type == "index"
    assert by_sym["BTC"].entity_type == "crypto"


def test_alias_merge_same_ticker():
    anchors = anchor_entities_l1([("b1", "腾讯控股就是腾讯")])
    tx = [a for a in anchors if a.resolved_symbol == "0700.HK"]
    assert len(tx) == 1  # 多别名合并为一个 anchor
    assert {"腾讯", "腾讯控股"}.issubset(set(tx[0].aliases))


def test_occurrences_recorded_across_blocks():
    anchors = anchor_entities_l1([("b1", "腾讯"), ("b2", "腾讯港股")])
    a = next(a for a in anchors if a.resolved_symbol == "0700.HK")
    assert a.metadata["mention_count"] == 2
    assert {o["block_id"] for o in a.metadata["occurrences"]} == {"b1", "b2"}


def test_char_offsets_valid():
    # offset 必须能切回原别名——这是 EvidenceSpan(步骤5) 的前提
    text = "看好英伟达"
    anchors = anchor_entities_l1([("b1", text)])
    a = next(a for a in anchors if a.resolved_symbol == "NVDA")
    occ = a.metadata["occurrences"][0]
    assert text[occ["char_start"]:occ["char_end"]] == occ["alias"]


def test_no_hit_returns_empty():
    assert anchor_entities_l1([("b1", "今天天气很好")]) == []


def test_schema_compliant_roundtrip():
    anchors = anchor_entities_l1([("b1", "英伟达和比特币")])
    assert anchors
    for a in anchors:
        assert isinstance(a, EntityAnchor)
        assert 0.0 <= a.confidence <= 1.0
        EntityAnchor.from_dict(a.to_dict())  # 序列化往返合规
    syms = {a.resolved_symbol for a in anchors}
    assert {"NVDA", "BTC"}.issubset(syms)


def test_anchor_envelope_l1():
    env = {
        "blocks": [
            {"block_id": "blk1", "text": "腾讯涨了"},
            {"block_id": "blk2", "text": "AAPL 财报"},
        ]
    }
    syms = {a.resolved_symbol for a in anchor_envelope_l1(env)}
    assert "0700.HK" in syms
    assert "AAPL" in syms


def test_build_f2_l1_envelope_stable_ids_and_offsets():
    env = _envelope([_block("b1", "看好腾讯控股和NVDA", page_index=0)])
    f2_first = build_f2_l1_envelope(env, f0_record=_f0_record())
    f2_second = build_f2_l1_envelope(env, f0_record=_f0_record())

    assert f2_first.model_dump(mode="json") == f2_second.model_dump(mode="json")
    assert isinstance(f2_first, ContentEnvelope)
    assert f2_first.source_type == "pdf"
    assert f2_first.metadata["f0_source_type"] == "livestream_audio"

    spans = f2_first.blocks[0].evidence_spans
    assert spans
    text = f2_first.blocks[0].text
    for span in spans:
        assert text[span["char_start"]:span["char_end"]] == span["text"]
        assert span["evidence_span_id"].startswith("span_")

    anchors = f2_first.entity_anchors
    assert {a["resolved_symbol"] for a in anchors} >= {"0700.HK", "NVDA"}
    assert all(a["entity_anchor_id"].startswith("entity_") for a in anchors)


def test_build_f2_l1_envelope_keeps_overlapping_aliases_auditable():
    env = _envelope([_block("b1", "腾讯控股继续强于腾讯", page_index=0)])
    f2 = build_f2_l1_envelope(env, f0_record=_f0_record())
    tx = next(a for a in f2.entity_anchors if a["resolved_symbol"] == "0700.HK")
    span_texts = [s["text"] for s in f2.blocks[0].evidence_spans]

    assert {"腾讯", "腾讯控股"}.issubset(set(tx["aliases"]))
    assert {"腾讯", "腾讯控股"}.issubset(set(span_texts))
    assert len(tx["metadata"]["evidence_span_ids"]) == tx["metadata"]["mention_count"]


def test_build_f2_l1_envelope_sets_provenance_granularity():
    env = _envelope(
        [
            _block(
                "b1",
                "腾讯",
                page_index=0,
                bbox={"x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0},
            ),
            _block("b2", "英伟达", page_index=1),
            _block("b3", "比特币"),
        ]
    )
    f2 = build_f2_l1_envelope(env, f0_record=_f0_record())
    by_block = {
        block.block_id: block.evidence_spans[0]["metadata"]
        for block in f2.blocks
        if block.evidence_spans
    }

    assert by_block["b1"]["provenance_granularity"] == "bbox"
    assert by_block["b1"]["bbox"] == {"x0": 1.0, "y0": 2.0, "x1": 3.0, "y1": 4.0}
    assert by_block["b2"]["provenance_granularity"] == "page"
    assert by_block["b2"]["page_index"] == 1
    assert by_block["b3"]["provenance_granularity"] == "file"


def test_build_f2_l1_envelope_updates_only_f2_quality_dimensions():
    env = _envelope([_block("b1", "腾讯"), _block("b2", "无实体文本")])
    f2 = build_f2_l1_envelope(env, f0_record=_f0_record())
    q = f2.quality_card

    assert q.readability_score == 0.9
    assert q.semantic_completeness_score == 0.9
    assert q.financial_relevance_score == 0.8
    assert q.entity_resolution_score == 0.5
    assert q.evidence_traceability_score == 0.8
