"""Tests for F2 EntityAnchor deterministic producer.

See src/finer/enrichment/entity_anchoring.py and
docs/specs/2026-06-14-f2-anchoring-design.md.
"""

from finer.enrichment.entity_anchoring import (
    anchor_entities_deterministic,
    anchor_envelope_deterministic,
    build_f2_deterministic_envelope,
    scan_deterministic_temporal_expressions,
    scan_explicit_temporal_expressions,
    scan_relative_temporal_expressions,
    scan_text,
)
from finer.entity_registry import resolve
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
            "raw_path": "data/raw/sample.pdf",
            "extractor": "test",
            "extractor_version": "1.0",
        },
    }
    if page_index is not None:
        data["page_index"] = page_index
    if bbox is not None:
        data["bbox"] = bbox
    return data


def _envelope(blocks: list[dict], *, published_at="2026-06-13T09:30:00+08:00") -> dict:
    return {
        "envelope_id": "env_test",
        "source_record_id": "local_test",
        "schema_version": "v1.0",
        "source_type": "pdf",
        "standardization_profile": "pdf_layout_v1",
        "source_uri": "data/raw/sample.pdf",
        "source_title": "sample.pdf",
        "raw_path": "data/raw/sample.pdf",
        "creator_name": "trader_ji",
        "published_at": published_at,
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
        raw_path="data/raw/sample.pdf",
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


def test_explicit_temporal_scan_accepts_high_precision_dates_only():
    text = "会议将在2026年4月1日复盘，执行窗口是4月2日，不要误抓19.49、5.6或10/15。"

    hits = scan_explicit_temporal_expressions(
        text,
        published_at="2026-03-31T09:30:00+08:00",
    )

    by_raw = {hit.raw_text: hit for hit in hits}
    assert set(by_raw) == {"2026年4月1日", "4月2日"}
    assert by_raw["2026年4月1日"].resolved_time.isoformat() == "2026-04-01T00:00:00+08:00"
    assert by_raw["2026年4月1日"].resolution_strategy == "explicit_date"
    assert by_raw["4月2日"].resolved_time.isoformat() == "2026-04-02T00:00:00+08:00"
    assert by_raw["4月2日"].resolution_strategy == "rule_based"


def test_month_day_temporal_scan_requires_published_at_year():
    assert scan_explicit_temporal_expressions("4月2日复盘", published_at=None) == []


def test_relative_temporal_scan_uses_published_at_reference_only():
    text = "今天复盘，明天执行，下周一看非农，本月控制仓位，下月再评估。"

    hits = scan_relative_temporal_expressions(
        text,
        published_at="2026-04-15T10:00:00+08:00",
    )

    by_raw = {hit.raw_text: hit for hit in hits}
    assert by_raw["今天"].resolved_time.isoformat() == "2026-04-15T00:00:00+08:00"
    assert by_raw["明天"].resolved_time.isoformat() == "2026-04-16T00:00:00+08:00"
    assert by_raw["下周一"].resolved_time.isoformat() == "2026-04-20T00:00:00+08:00"
    assert by_raw["本月"].resolved_time.isoformat() == "2026-04-01T00:00:00+08:00"
    assert by_raw["本月"].resolved_end_time.isoformat() == "2026-05-01T00:00:00+08:00"
    assert by_raw["下月"].resolved_time.isoformat() == "2026-05-01T00:00:00+08:00"
    assert all(hit.resolution_strategy == "relative_date" for hit in hits)
    assert scan_relative_temporal_expressions(text, published_at=None) == []


def test_relative_week_period_scan_resolves_to_week_start_and_end():
    hits = scan_relative_temporal_expressions(
        "上周兑现，本周观察，下周加仓。",
        published_at="2026-04-15T10:00:00+08:00",
    )

    by_raw = {hit.raw_text: hit for hit in hits}
    assert by_raw["上周"].resolved_time.isoformat() == "2026-04-06T00:00:00+08:00"
    assert by_raw["上周"].resolved_end_time.isoformat() == "2026-04-13T00:00:00+08:00"
    assert by_raw["本周"].resolved_time.isoformat() == "2026-04-13T00:00:00+08:00"
    assert by_raw["下周"].resolved_time.isoformat() == "2026-04-20T00:00:00+08:00"
    assert by_raw["下周"].temporal_granularity == "week"


def test_numeric_month_day_requires_event_cue():
    hits = scan_deterministic_temporal_expressions(
        "04.08 非农公布，4.1元目标价和10/15胜率不要误抓。",
        published_at="2026-04-01T09:30:00+08:00",
    )

    by_raw = {hit.raw_text: hit for hit in hits}
    assert set(by_raw) == {"04.08"}
    assert by_raw["04.08"].resolved_time.isoformat() == "2026-04-08T00:00:00+08:00"
    assert by_raw["04.08"].rule == "numeric_month_day_with_event_cue"


def test_human_confirmed_hk_registry_gaps_resolve_and_scan():
    expected = {
        "新华保险": "1336.HK",
        "民生银行": "1988.HK",
        "吉利汽车": "0175.HK",
        "蓝思科技": "6613.HK",
        "中国光大银行": "6818.HK",
        "华能国际电力股份": "0902.HK",
    }

    for alias, ticker in expected.items():
        assert resolve(alias) == (ticker, "HK", "ticker")

    text = "新华保险 1336.HK、民生银行、吉利汽车、蓝思科技、中国光大银行、华能国际电力股份"
    hit_tickers = {hit.ticker for hit in scan_text(text)}

    assert set(expected.values()).issubset(hit_tickers)


def test_phlx_semiconductor_index_registry_gap_resolves_and_scans():
    assert resolve("费城半导体") == ("SOX", "US", "index")
    assert resolve("费城半导体指数") == ("SOX", "US", "index")

    anchors = anchor_entities_deterministic([("b1", "费城半导体/foundry/存储/光纤/电力")])
    sox = next(anchor for anchor in anchors if anchor.resolved_symbol == "SOX")

    assert sox.entity_type == "index"
    assert "费城半导体" in sox.aliases


def test_cn_stock_registry_gap_resolves_and_scans():
    assert resolve("中宠股份") == ("002891.SZ", "CN", "ticker")

    anchors = anchor_entities_deterministic([("b1", "中宠转2 -16.55% | 中宠股份 -5.20%")])
    zhongchong = next(anchor for anchor in anchors if anchor.resolved_symbol == "002891.SZ")

    assert zhongchong.entity_type == "stock"
    assert "中宠股份" in zhongchong.aliases


def test_public_market_registry_gaps_resolve_and_scan():
    expected = {
        "MU": ("MU", "US", "ticker"),
        "美光科技": ("MU", "US", "ticker"),
        "希捷科技控股有限公司": ("STX", "US", "ticker"),
        "南亚科技股份有限公司": ("2408.TW", "TW", "ticker"),
        "VIX": ("VIX", "US", "index"),
        "KOSPI": ("KS11", "KR", "index"),
        "WTI": ("WTI", "COMMODITY", "commodity"),
    }
    for alias, entry in expected.items():
        assert resolve(alias) == entry

    anchors = anchor_entities_deterministic(
        [
            (
                "b1",
                "存储MU和美光科技走强，希捷科技控股有限公司、南亚科技股份有限公司、"
                "VIX、KOSPI、WTI原油都被提及。",
            )
        ]
    )
    by_symbol = {anchor.resolved_symbol: anchor for anchor in anchors}

    assert by_symbol["MU"].entity_type == "stock"
    assert by_symbol["STX"].entity_type == "stock"
    assert by_symbol["2408.TW"].entity_type == "stock"
    assert by_symbol["VIX"].entity_type == "index"
    assert by_symbol["KS11"].entity_type == "index"
    assert by_symbol["WTI"].entity_type == "commodity"


def test_f2_gap_review_additions_resolve_and_scan():
    """Human-triaged tradable entities from the 2026-06-26 all-local gap scan."""
    expected = {
        "中金公司": ("3908.HK", "HK", "ticker"),
        "CICC": ("3908.HK", "HK", "ticker"),
        "曹操出行": ("2643.HK", "HK", "ticker"),
        "高盛": ("GS", "US", "ticker"),
        "GS": ("GS", "US", "ticker"),
        "MUFG": ("MUFG", "US", "ticker"),
        "SAP": ("SAP", "US", "ticker"),
        "CRWV": ("CRWV", "US", "ticker"),
        "CoreWeave": ("CRWV", "US", "ticker"),
    }
    for alias, entry in expected.items():
        assert resolve(alias) == entry

    anchors = anchor_entities_deterministic(
        [
            (
                "b1",
                "CICC 中金公司研报，曹操出行上市，高盛GS看多软件，"
                "MUFG联合主承销，SAP和CRWV被反复提及。",
            )
        ]
    )
    by_symbol = {anchor.resolved_symbol: anchor for anchor in anchors}

    assert {"3908.HK", "2643.HK", "GS", "MUFG", "SAP", "CRWV"}.issubset(by_symbol)
    assert by_symbol["3908.HK"].entity_type == "stock"
    assert by_symbol["2643.HK"].entity_type == "stock"


def test_f2_llm_proposal_additions_resolve_and_scan():
    """Tradable entities surfaced by the F2 constrained-LLM proposal eval (2026-06-26)."""
    expected = {
        "地平线": ("9660.HK", "HK", "ticker"),
        "地平线机器人": ("9660.HK", "HK", "ticker"),
        "吉利": ("0175.HK", "HK", "ticker"),
    }
    for alias, entry in expected.items():
        assert resolve(alias) == entry

    anchors = anchor_entities_deterministic(
        [("b1", "说一下地平线的财报，进取组合卖出20%吉利。")]
    )
    by_symbol = {anchor.resolved_symbol: anchor for anchor in anchors}
    assert {"9660.HK", "0175.HK"}.issubset(by_symbol)
    assert by_symbol["9660.HK"].entity_type == "stock"


def test_public_etf_and_index_registry_gaps_resolve_and_scan():
    expected = {
        "QQQ": ("QQQ", "US", "etf"),
        "SOXX": ("SOXX", "US", "etf"),
        "SOXL": ("SOXL", "US", "etf"),
        "SMH": ("SMH", "US", "etf"),
        "IGV": ("IGV", "US", "etf"),
        "EWY": ("EWY", "US", "etf"),
        "SPY": ("SPY", "US", "etf"),
        "SP500": ("SPX", "US", "index"),
        "DXY": ("DXY", "US", "index"),
        "TCL科技": ("000100.SZ", "CN", "ticker"),
        "ANTA": ("2020.HK", "HK", "ticker"),
    }
    for alias, entry in expected.items():
        assert resolve(alias) == entry

    anchors = anchor_entities_deterministic(
        [
            (
                "b1",
                "SOXX、SOXL、SMH、QQQ、IGV、EWY、SPY、SP500、DXY、TCL科技和ANTA被提及。",
            )
        ]
    )
    by_symbol = {anchor.resolved_symbol: anchor for anchor in anchors}

    assert by_symbol["QQQ"].entity_type == "etf"
    assert by_symbol["SOXX"].entity_type == "etf"
    assert by_symbol["SPX"].entity_type == "index"
    assert by_symbol["DXY"].entity_type == "index"
    assert by_symbol["000100.SZ"].entity_type == "stock"
    assert by_symbol["2020.HK"].entity_type == "stock"
    assert not any(anchor.resolved_symbol == "2020.HK" for anchor in anchor_entities_deterministic([("b1", "2020年业绩")]))


def test_public_hk_robosense_registry_gap_resolves_and_scans():
    expected = {
        "速腾聚创": ("2498.HK", "HK", "ticker"),
        "速腾聚创科技": ("2498.HK", "HK", "ticker"),
        "RoboSense": ("2498.HK", "HK", "ticker"),
        "2498.HK": ("2498.HK", "HK", "ticker"),
    }
    for alias, entry in expected.items():
        assert resolve(alias) == entry

    anchors = anchor_entities_deterministic(
        [("b1", "速腾聚创科技 RoboSense 2498.HK 公告提到激光雷达销量。")]
    )
    robosense = next(anchor for anchor in anchors if anchor.resolved_symbol == "2498.HK")

    assert robosense.entity_type == "stock"
    assert {"速腾聚创", "速腾聚创科技", "RoboSense", "2498.HK"}.issubset(
        set(robosense.aliases)
    )
    assert not any(
        anchor.resolved_symbol == "2498.HK"
        for anchor in anchor_entities_deterministic([("b1", "订单号24981234")])
    )


def test_type_mapping_ticker_to_stock():
    anchors = anchor_entities_deterministic([("b1", "腾讯不错")])
    a = next(a for a in anchors if a.resolved_symbol == "0700.HK")
    assert a.entity_type == "stock"  # registry "ticker" → schema "stock"


def test_index_and_crypto_type():
    anchors = anchor_entities_deterministic([("b1", "大A走强，比特币反弹")])
    by_sym = {a.resolved_symbol: a for a in anchors}
    assert by_sym["000001.SH"].entity_type == "index"
    assert by_sym["BTC"].entity_type == "crypto"


def test_alias_merge_same_ticker():
    anchors = anchor_entities_deterministic([("b1", "腾讯控股就是腾讯")])
    tx = [a for a in anchors if a.resolved_symbol == "0700.HK"]
    assert len(tx) == 1  # 多别名合并为一个 anchor
    assert {"腾讯", "腾讯控股"}.issubset(set(tx[0].aliases))


def test_occurrences_recorded_across_blocks():
    anchors = anchor_entities_deterministic([("b1", "腾讯"), ("b2", "腾讯港股")])
    a = next(a for a in anchors if a.resolved_symbol == "0700.HK")
    assert a.metadata["mention_count"] == 2
    assert {o["block_id"] for o in a.metadata["occurrences"]} == {"b1", "b2"}


def test_char_offsets_valid():
    # offset 必须能切回原别名——这是 EvidenceSpan(步骤5) 的前提
    text = "看好英伟达"
    anchors = anchor_entities_deterministic([("b1", text)])
    a = next(a for a in anchors if a.resolved_symbol == "NVDA")
    occ = a.metadata["occurrences"][0]
    assert text[occ["char_start"]:occ["char_end"]] == occ["alias"]


def test_no_hit_returns_empty():
    assert anchor_entities_deterministic([("b1", "今天天气很好")]) == []


def test_schema_compliant_roundtrip():
    anchors = anchor_entities_deterministic([("b1", "英伟达和比特币")])
    assert anchors
    for a in anchors:
        assert isinstance(a, EntityAnchor)
        assert 0.0 <= a.confidence <= 1.0
        EntityAnchor.from_dict(a.to_dict())  # 序列化往返合规
    syms = {a.resolved_symbol for a in anchors}
    assert {"NVDA", "BTC"}.issubset(syms)


def test_anchor_envelope_deterministic():
    env = {
        "blocks": [
            {"block_id": "blk1", "text": "腾讯涨了"},
            {"block_id": "blk2", "text": "AAPL 财报"},
        ]
    }
    syms = {a.resolved_symbol for a in anchor_envelope_deterministic(env)}
    assert "0700.HK" in syms
    assert "AAPL" in syms


def test_build_f2_deterministic_envelope_stable_ids_and_offsets():
    env = _envelope([_block("b1", "看好腾讯控股和NVDA，2026年4月1日复盘，下周一执行", page_index=0)])
    f2_first = build_f2_deterministic_envelope(env, f0_record=_f0_record())
    f2_second = build_f2_deterministic_envelope(env, f0_record=_f0_record())

    assert f2_first.model_dump(mode="json") == f2_second.model_dump(mode="json")
    assert isinstance(f2_first, ContentEnvelope)
    assert f2_first.source_type == "pdf"
    assert f2_first.metadata["f0_source_type"] == "livestream_audio"
    assert f2_first.metadata["f2_anchor"]["layer"] == "deterministic_registry"
    assert f2_first.metadata["f2_anchor"]["temporal_anchor_count"] == 3
    assert f2_first.metadata["f2_anchor"]["temporal_evidence_span_count"] == 2

    temporal = f2_first.temporal_anchors
    assert len(temporal) == 3
    assert temporal[0]["anchor_id"].startswith("time_")
    assert temporal[0]["anchor_type"] == "published_at"
    assert temporal[0]["raw_text"] == "published_at"
    assert temporal[0]["resolved_time"] == "2026-06-13T09:30:00+08:00"
    assert temporal[0]["resolution_strategy"] == "explicit_date"
    assert temporal[0]["confidence"] == 1.0
    assert temporal[0]["timezone"] == "UTC+08:00"
    assert temporal[0]["metadata"]["layer"] == "deterministic_temporal"
    assert temporal[1]["anchor_type"] == "mentioned_at"
    assert temporal[1]["raw_text"] == "2026年4月1日"
    assert temporal[1]["resolved_time"] == "2026-04-01T00:00:00+08:00"
    assert temporal[1]["evidence_span_id"].startswith("span_")
    assert temporal[1]["metadata"]["rule"] == "full_date"
    assert temporal[2]["anchor_type"] == "mentioned_at"
    assert temporal[2]["raw_text"] == "下周一"
    assert temporal[2]["resolved_time"] == "2026-06-15T00:00:00+08:00"
    assert temporal[2]["resolution_strategy"] == "relative_date"
    assert temporal[2]["metadata"]["rule"] == "relative_weekday_from_published_at"

    spans = f2_first.blocks[0].evidence_spans
    assert spans
    temporal_spans = [span for span in spans if span["span_type"] == "temporal"]
    assert [span["text"] for span in temporal_spans] == ["2026年4月1日", "下周一"]
    assert temporal_spans[0]["metadata"]["layer"] == "deterministic_temporal"
    text = f2_first.blocks[0].text
    for span in spans:
        assert text[span["char_start"]:span["char_end"]] == span["text"]
        assert span["evidence_span_id"].startswith("span_")
    for span in spans:
        if span["span_type"] != "entity":
            continue
        assert span["metadata"]["layer"] == "deterministic_registry"

    anchors = f2_first.entity_anchors
    assert {a["resolved_symbol"] for a in anchors} >= {"0700.HK", "NVDA"}
    assert all(a["entity_anchor_id"].startswith("entity_") for a in anchors)
    assert all(a["metadata"]["layer"] == "deterministic_registry" for a in anchors)


def test_build_f2_deterministic_envelope_keeps_overlapping_aliases_auditable():
    env = _envelope([_block("b1", "腾讯控股继续强于腾讯", page_index=0)])
    f2 = build_f2_deterministic_envelope(env, f0_record=_f0_record())
    tx = next(a for a in f2.entity_anchors if a["resolved_symbol"] == "0700.HK")
    span_texts = [s["text"] for s in f2.blocks[0].evidence_spans]

    assert {"腾讯", "腾讯控股"}.issubset(set(tx["aliases"]))
    assert {"腾讯", "腾讯控股"}.issubset(set(span_texts))
    assert len(tx["metadata"]["evidence_span_ids"]) == tx["metadata"]["mention_count"]


def test_build_f2_deterministic_envelope_sets_provenance_granularity():
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
    f2 = build_f2_deterministic_envelope(env, f0_record=_f0_record())
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


def test_build_f2_deterministic_envelope_updates_only_f2_quality_dimensions():
    env = _envelope([_block("b1", "腾讯"), _block("b2", "无实体文本")])
    f2 = build_f2_deterministic_envelope(env, f0_record=_f0_record())
    q = f2.quality_card

    assert q.readability_score == 0.9
    assert q.semantic_completeness_score == 0.9
    assert q.financial_relevance_score == 0.8
    assert q.entity_resolution_score == 0.5
    assert q.temporal_resolution_score == 1.0
    assert q.evidence_traceability_score == 0.8


def test_build_f2_deterministic_envelope_does_not_infer_missing_published_at():
    env = _envelope([_block("b1", "腾讯今天下周一")], published_at=None)
    f2 = build_f2_deterministic_envelope(env, f0_record=None)

    assert f2.temporal_anchors == []
    assert f2.metadata["f2_anchor"]["temporal_anchor_count"] == 0
    assert f2.quality_card.temporal_resolution_score == 0.0


def test_build_f2_deterministic_envelope_uses_f0_published_at_fallback():
    env = _envelope([_block("b1", "腾讯")], published_at=None)
    f0 = _f0_record().model_dump(mode="json")
    f0["published_at"] = "2026-06-12T15:45:00+08:00"

    f2 = build_f2_deterministic_envelope(env, f0_record=f0)

    assert len(f2.temporal_anchors) == 1
    assert f2.temporal_anchors[0]["resolved_time"] == "2026-06-12T15:45:00+08:00"
