"""Tests for OCR output quality gates (finer.parsing.ocr_quality).

Covers the two silent-failure modes MiMo vision exhibits: content-safety
refusals captured as OCR text, and fabricated placeholder image URLs — plus the
critical false-positive guard (real research text mentioning 风险/无法 must pass).
"""

from finer.parsing.ocr_quality import (
    envelope_failure_tag,
    gate_vision_output,
    has_placeholder,
    is_refusal,
    strip_placeholder_urls,
)


def test_refusal_detected_and_gated():
    msg = "The request was rejected because it was considered high risk"
    assert is_refusal(msg)
    assert gate_vision_output(msg) is None
    assert is_refusal("抱歉，我无法处理该图片")


def test_refusal_no_false_positive_on_research_text():
    # Real research text mentioning 风险 / 无法 must NOT be flagged as a refusal.
    txt = "市场风险较高，短期无法预测走势，但中长期看好科技板块的配置价值。" * 20
    assert not is_refusal(txt)
    assert gate_vision_output(txt) is not None


def test_placeholder_stripped_keeps_real_text():
    txt = (
        "这是一段真实的投研OCR文字内容足够长\n"
        "![chart](https://via.placeholder.com/600x300?text=x)\n"
        "*真实图表说明应当保留*"
    )
    assert has_placeholder(txt)
    cleaned = strip_placeholder_urls(txt)
    assert "placeholder" not in cleaned
    assert "真实的投研OCR文字内容" in cleaned
    assert "真实图表说明应当保留" in cleaned


def test_placeholder_only_gated_to_none():
    assert gate_vision_output("![](https://via.placeholder.com/600x300)") is None


def test_normal_text_passes_unchanged():
    txt = "收入114,583百万港元同比+15.4%，归母净利润2,495百万港元同比+41.8%"
    assert gate_vision_output(txt) == txt
    assert not is_refusal(txt)
    assert not has_placeholder(txt)


def test_empty_and_thin_gated():
    assert gate_vision_output("") is None
    assert gate_vision_output("   ") is None
    assert gate_vision_output("短文") is None


def test_envelope_failure_tag():
    fb = {"blocks": [{"text": "x", "quality": {"quality_flags": ["no_vision_transcript"]}}]}
    assert envelope_failure_tag(fb) == "fallback"

    ref = {"blocks": [{"text": "The request was rejected because it was considered high risk", "quality": {}}]}
    assert envelope_failure_tag(ref) == "refusal"

    hal = {"blocks": [{"text": "真实文字" * 10 + " https://via.placeholder.com/600", "quality": {}}]}
    assert envelope_failure_tag(hal) == "hallucination"

    clean = {"blocks": [{"text": "收入114,583百万港元同比增长15.4%，业绩稳健向好趋势延续。", "quality": {}}]}
    assert envelope_failure_tag(clean) is None
