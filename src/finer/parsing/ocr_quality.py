"""OCR output quality gates — shared by the image adapter and the F1 audit.

MiMo vision exhibits two silent-failure modes that pass a naive ``len(text) > 10``
success check and thus mix into the corpus as if they were real OCR:

1. **Refusal** — a content-safety / error message captured as OCR text, e.g.
   "The request was rejected because it was considered high risk".
2. **Hallucination** — fabricated placeholder image URLs for charts MiMo cannot
   read, e.g. ``![chart](https://via.placeholder.com/600x300?text=...)``.

This module is the single source of truth for detecting and cleaning both, so
the adapter can gate at the source (refusal → treated as extraction failure with
a real flag, not a fake success) and the audit/backfill can flag historical
envelopes with the same rules.
"""

from __future__ import annotations

import re
from typing import Optional

# Strong API refusal / safety / error markers. These effectively never occur in
# genuine Chinese investment-research OCR. Plain Chinese "无法" alone is NOT here —
# it is common in real research text ("无法预测") and would false-positive.
REFUSAL_PATTERNS = [
    r"request was rejected",
    r"considered high risk",
    r"\bI\s+(cannot|can'?t|am unable to|am not able to)\s+(assist|help|process|provide|identify|see|view|comply)",
    r"\bI'?m\s+(sorry|unable)\b",
    r"as an AI(?:\s+language model)?",
    r"content (?:policy|policies|guidelines)",
    r"抱歉[，,。\s]{0,3}(?:我)?(?:无法|不能)",
    r"无法(?:识别|查看|处理|解析)(?:这|该|此|图|图片|图像)",
    r"(?:涉及|包含).{0,8}(?:违规|敏感|不当)内容",
]
HALLUCINATION_PATTERNS = [
    r"via\.placeholder\.com",
    r"placeholder\.com",
    r"!\[[^\]]*\]\(https?://[^)]*placeholder",
    r"example\.com/[\w./-]+\.(?:png|jpe?g|gif)",
]

_REFUSAL_RE = [re.compile(p, re.I) for p in REFUSAL_PATTERNS]
_HALLU_RE = [re.compile(p, re.I) for p in HALLUCINATION_PATTERNS]

# A refusal hit inside an envelope shorter than this means the refusal IS the
# content (whole image lost). Longer text with an incidental match is left alone.
REFUSAL_DOMINATES = 400
# Below this many chars, "clean" OCR is suspiciously thin (possible partial).
THIN_CHARS = 30


def is_refusal(text: Optional[str]) -> bool:
    """True if text is dominated by an API refusal / safety message."""
    if not text:
        return False
    if len(text) >= REFUSAL_DOMINATES:
        return False
    return any(r.search(text) for r in _REFUSAL_RE)


def has_placeholder(text: Optional[str]) -> bool:
    """True if text contains a fabricated placeholder image URL."""
    if not text:
        return False
    return any(r.search(text) for r in _HALLU_RE)


def strip_placeholder_urls(text: str) -> str:
    """Drop markdown lines containing fabricated placeholder image URLs, keep the rest.

    The model often emits ``![desc](https://via.placeholder.com/...)`` on its own
    line followed by a real caption line; we remove only the fabricated-URL line.
    """
    if not text:
        return text
    kept = [ln for ln in text.splitlines() if not any(r.search(ln) for r in _HALLU_RE)]
    return "\n".join(kept)


def gate_vision_output(text: Optional[str]) -> Optional[str]:
    """Gate raw vision output before it is trusted as OCR.

    Returns cleaned text, or None to signal "treat as extraction failure" (so the
    caller emits a flagged fallback rather than a silent fake-success):
    - empty / too short → None
    - refusal / safety message → None
    - placeholder-only (nothing left after cleaning) → None
    - otherwise → text with fabricated placeholder URLs stripped
    """
    if not text or len(text.strip()) <= 10:
        return None
    if is_refusal(text):
        return None
    cleaned = strip_placeholder_urls(text)
    if len(cleaned.strip()) <= 10:
        return None
    return cleaned


def envelope_failure_tag(env: dict) -> Optional[str]:
    """Classify a STORED ContentEnvelope for audit / reprocess. None = clean.

    Returns one of: 'fallback', 'refusal', 'hallucination', 'thin', or None.
    """
    blocks = env.get("blocks", [])
    for b in blocks:
        qf = ((b.get("quality") or {}).get("quality_flags")) or []
        if "no_vision_transcript" in qf or "fallback_generated" in qf:
            return "fallback"
    txt = "\n".join((b.get("text") or "") for b in blocks)
    if is_refusal(txt):
        return "refusal"
    if has_placeholder(txt):
        return "hallucination"
    if len(txt.strip()) < THIN_CHARS:
        return "thin"
    return None
