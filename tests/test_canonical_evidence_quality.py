"""Tests for F5 evidence-text assembly quality (degenerate-mention fix).

The live-data defect: F2 evidence spans are mention-level anchors whose text is
just the alias ("亚马逊"), and _build_evidence_text joined ALL of them verbatim,
producing "亚马逊 | 亚马逊 | 亚马逊 | …" on 49/58 real actions. The fix expands
each span to its surrounding sentence via block text and dedupes.
"""
from __future__ import annotations

from finer.pipeline.canonical_runner import (
    _build_evidence_text,
    _sentence_window,
)
from finer.schemas.evidence import EvidenceSpan

BLOCK_TEXT = (
    "今天先聊美股。然后亚马逊也不是很强，亚马逊也不是很强，但是反正至少是目前来说，"
    "在日线级别还是在高位震荡向上的。所以我觉得亚马逊可以继续拿着。"
)


def make_span(sid: str, start: int, end: int, block_id: str = "blk-1") -> EvidenceSpan:
    return EvidenceSpan.from_dict(
        {
            "schema_version": "1.0",
            "evidence_span_id": sid,
            "block_id": block_id,
            "char_start": start,
            "char_end": end,
            "text": BLOCK_TEXT[start:end],
            "confidence": 0.9,
            "span_type": "claim",
            "metadata": {},
        }
    )


def find_all(text: str, needle: str) -> list[tuple[int, int]]:
    out, i = [], text.find(needle)
    while i != -1:
        out.append((i, i + len(needle)))
        i = text.find(needle, i + 1)
    return out


def test_sentence_window_expands_to_sentence():
    start, end = find_all(BLOCK_TEXT, "亚马逊")[0]
    snippet = _sentence_window(BLOCK_TEXT, start, end)
    assert "亚马逊" in snippet
    assert len(snippet) > len("亚马逊")  # expanded beyond the mention
    assert "。" not in snippet[:-1] or snippet.endswith("。")


def test_degenerate_mention_join_is_gone():
    """Multiple mentions in one block must NOT produce 'X | X | X'."""
    hits = find_all(BLOCK_TEXT, "亚马逊")
    assert len(hits) >= 3
    spans = {f"s{i}": make_span(f"s{i}", s, e) for i, (s, e) in enumerate(hits)}
    ids = list(spans.keys())

    text = _build_evidence_text(ids, spans, block_texts={"blk-1": BLOCK_TEXT})

    parts = [p.strip() for p in text.split(" | ")]
    assert len(parts) == len(set(parts)), f"duplicate snippets: {text}"
    assert all(len(p) > 8 for p in parts), f"mention-only snippets: {text}"
    # the real context sentence should surface
    assert any("不是很强" in p or "继续拿着" in p for p in parts)


def test_fallback_to_span_text_without_block_text():
    hits = find_all(BLOCK_TEXT, "亚马逊")
    spans = {f"s{i}": make_span(f"s{i}", s, e) for i, (s, e) in enumerate(hits)}
    ids = list(spans.keys())

    # no block texts: falls back to span.text but still dedupes
    text = _build_evidence_text(ids, spans, block_texts=None)
    assert text == "亚马逊"  # three identical mentions collapse to one


def test_max_snippets_cap():
    long_text = "。".join(f"第{i}句提到标的X的观点内容" for i in range(10)) + "。"
    spans = {}
    for i, (s, e) in enumerate(find_all(long_text, "标的X")):
        spans[f"s{i}"] = EvidenceSpan.from_dict(
            {
                "schema_version": "1.0",
                "evidence_span_id": f"s{i}",
                "block_id": "blk-2",
                "char_start": s,
                "char_end": e,
                "text": "标的X",
                "confidence": 0.9,
                "span_type": "claim",
                "metadata": {},
            }
        )
    text = _build_evidence_text(
        list(spans.keys()), spans, block_texts={"blk-2": long_text}, max_snippets=3
    )
    assert len(text.split(" | ")) <= 3


def test_pipe_framing_stripped():
    """F1 fake-table pipe framing around the sentence must not survive."""
    table_text = "|  |  |\n| --- | --- |\n| 看好亚马逊的中期逻辑没变。 |"
    s = table_text.find("亚马逊")
    span = EvidenceSpan.from_dict(
        {
            "schema_version": "1.0",
            "evidence_span_id": "s0",
            "block_id": "blk-3",
            "char_start": s,
            "char_end": s + 3,
            "text": "亚马逊",
            "confidence": 0.9,
            "span_type": "claim",
            "metadata": {},
        }
    )
    text = _build_evidence_text(["s0"], {"s0": span}, block_texts={"blk-3": table_text})
    assert not text.startswith("|")
    assert "看好亚马逊" in text
