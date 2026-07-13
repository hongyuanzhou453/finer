"""File Classifier — intelligent routing of downloaded files to the finer archive.

Classification priority:
1. Explicit tags in message context text (e.g., #trader_ji, #weekly)
2. Chat-level default creator from config
3. Regex rules from feishu.yaml
4. AI-assisted classification (via Gemini CLI)
5. Fallback to _inbox/unclassified
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of classifying a downloaded file."""
    creator_id: str
    source_type: str
    published_at: datetime
    confidence: float       # 0.0 ~ 1.0
    matched_rule: str       # which rule or method produced this result
    ai_reasoning: str = ""  # AI's reasoning if AI classification was used


# ── Tag extraction from message text ─────────────────────────

_TAG_PATTERN = re.compile(r"#(\w+)", re.UNICODE)

_TAG_TO_CREATOR: dict[str, str] = {
    "trader_ji": "trader_ji",
    "trader韭": "trader_ji",
    "韭": "trader_ji",
    "maodaren": "maodaren",
    "猫大人": "maodaren",
    "9you": "9you",
    "9友": "9you",
    "research": "_research",
    "研报": "_research",
}

_TAG_TO_TYPE: dict[str, str] = {
    "weekly": "weekly_strategy",
    "周策略": "weekly_strategy",
    "daily": "daily_pre",
    "日": "daily_pre",
    "strategy": "weekly_strategy",
    "report": "research_report",
    "研报": "research_report",
    "chat": "chat_export",
    "聊天": "chat_export",
}


def _merged_creator_tags() -> dict[str, str]:
    """Static tag map merged with KOL registry aliases (registry wins).

    The static ``_TAG_TO_CREATOR`` stays as the baseline: it routes
    pseudo-creators (研报 → _research) that will never have a registry
    profile, and it is the safety net when the registry is unavailable —
    F0 ingestion must never go down because a services import failed.
    Registry aliases layer on top so onboarding a creator (one YAML) makes
    its hashtags classify correctly without touching this module.
    """
    mapping = dict(_TAG_TO_CREATOR)
    try:
        from finer.services.kol_registry import get_registry

        for profile in get_registry().list_profiles():
            mapping[profile.creator_id] = profile.creator_id
            for alias in profile.aliases:
                if alias:
                    mapping[alias] = profile.creator_id
    except Exception:
        logger.warning("kol_registry unavailable, using static tag map", exc_info=True)
    return mapping


def _extract_tags(
    text: str,
    tag_map: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Extract creator_id and source_type from hashtags in text."""
    creator_map = tag_map if tag_map is not None else _TAG_TO_CREATOR
    tags = _TAG_PATTERN.findall(text)
    creator_id = None
    source_type = None

    for tag in tags:
        tag_lower = tag.lower()
        if tag in creator_map:
            creator_id = creator_map[tag]
        elif tag_lower in creator_map:
            creator_id = creator_map[tag_lower]

        if tag in _TAG_TO_TYPE:
            source_type = _TAG_TO_TYPE[tag]
        elif tag_lower in _TAG_TO_TYPE:
            source_type = _TAG_TO_TYPE[tag_lower]

    return creator_id, source_type


# ── Date inference ───────────────────────────────────────────

_DATE_PATTERNS = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "%Y-%m-%d"),
    (re.compile(r"(\d{4})(\d{2})(\d{2})"), "%Y%m%d"),
    (re.compile(r"(\d{4})\.(\d{2})\.(\d{2})"), "%Y.%m.%d"),
]


def _infer_date(filename: str, sent_at: datetime) -> datetime:
    """Infer publication date from filename, falling back to send time."""
    for pattern, fmt in _DATE_PATTERNS:
        match = pattern.search(filename)
        if match:
            try:
                date_str = match.group()
                # Normalize separators
                normalized = date_str.replace(".", "-")
                if len(normalized) == 8 and normalized.isdigit():
                    normalized = f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:]}"
                return datetime.strptime(normalized, "%Y-%m-%d").replace(
                    hour=9, minute=0, second=0
                )
            except ValueError:
                continue
    return sent_at


# ── Rule matching ────────────────────────────────────────────

def _match_rules(
    filename: str,
    context_text: str,
    rules: list[dict[str, str]],
) -> tuple[str | None, str | None, str]:
    """Match filename and context against classification rules.
    
    Returns (creator_id, source_type, rule_name) or (None, None, "").
    """
    # Try matching against both filename and context text
    combined = f"{filename} {context_text}"
    
    for rule in rules:
        pattern = rule.get("pattern", "")
        if re.search(pattern, combined):
            return (
                rule.get("creator_id"),
                rule.get("content_type"),
                rule.get("name", pattern),
            )
    return None, None, ""


# ── AI classification ────────────────────────────────────────

def _ai_classify(
    filename: str,
    context_text: str,
    chat_name: str,
) -> tuple[str | None, str | None, str]:
    """Use Gemini CLI for AI-assisted file classification.
    
    Returns (creator_id, source_type, reasoning).
    """
    prompt = f"""你是一个金融研究文件分类助手。请根据以下信息对文件进行分类。

文件名: {filename}
消息上下文: {context_text or '无'}
来源群组: {chat_name}

请返回JSON格式，包含以下字段：
- creator_id: 文件关联的创作者ID（可选值：trader_ji, maodaren, 9you, _research, _inbox）
- content_type: 内容类型（可选值：weekly_strategy, daily_pre, daily_post, research_report, chat_export, bilibili_video, livestream, unclassified）
- reasoning: 你的分类推理过程（一句话）
- confidence: 置信度 0.0-1.0

仅返回JSON，不要其他内容。"""

    gemini_bin = shutil.which("gemini")
    if not gemini_bin:
        logger.warning("Gemini CLI not found in PATH, skipping AI classification")
        return None, None, ""

    try:
        result = subprocess.run(
            [gemini_bin, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Gemini CLI error: %s", result.stderr)
            return None, None, ""
        
        # Parse the JSON response
        output = result.stdout.strip()
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", output, re.DOTALL)
        if json_match:
            output = json_match.group(1)
        
        parsed = json.loads(output)
        return (
            parsed.get("creator_id"),
            parsed.get("content_type"),
            parsed.get("reasoning", ""),
        )
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning("AI classification failed: %s", e)
        return None, None, ""


# ── Main classifier ──────────────────────────────────────────

class FileClassifier:
    """Classifies downloaded files into the finer archive structure."""

    def __init__(self, config: dict[str, Any]):
        self.rules = config.get("classification", {}).get("rules", [])
        self.default = config.get("classification", {}).get("default", {})
        self.ai_enabled = config.get("classification", {}).get("ai_enabled", False)
        # Static baseline + registry aliases (see _merged_creator_tags).
        self._tag_to_creator = _merged_creator_tags()

    def classify(
        self,
        filename: str,
        context_text: str,
        sent_at: datetime,
        chat_name: str = "",
        chat_default_creator: str = "",
    ) -> ClassificationResult:
        """Classify a file through the priority chain.
        
        Priority:
        1. Explicit hashtags in context_text
        2. Regex rules
        3. Chat-level default creator
        4. AI classification (if enabled)
        5. Fallback default
        """
        published_at = _infer_date(filename, sent_at)

        # ── Priority 1: Explicit tags ──
        tag_creator, tag_type = _extract_tags(context_text, self._tag_to_creator)
        if tag_creator and tag_type:
            return ClassificationResult(
                creator_id=tag_creator,
                source_type=tag_type,
                published_at=published_at,
                confidence=0.95,
                matched_rule="explicit_tag",
            )

        # ── Priority 2: Regex rules ──
        rule_creator, rule_type, rule_name = _match_rules(
            filename, context_text, self.rules
        )
        if rule_creator and rule_type:
            return ClassificationResult(
                creator_id=rule_creator,
                source_type=rule_type,
                published_at=published_at,
                confidence=0.80,
                matched_rule=f"rule:{rule_name}",
            )

        # ── Priority 3: Chat-level default ──
        if chat_default_creator:
            # Use partial match for content type
            partial_creator = rule_creator or chat_default_creator
            partial_type = rule_type or tag_type or "unclassified"
            if partial_creator != self.default.get("creator_id"):
                return ClassificationResult(
                    creator_id=partial_creator,
                    source_type=partial_type,
                    published_at=published_at,
                    confidence=0.60,
                    matched_rule=f"chat_default:{chat_default_creator}",
                )

        # ── Priority 4: AI classification ──
        if self.ai_enabled:
            ai_creator, ai_type, ai_reasoning = _ai_classify(
                filename, context_text, chat_name
            )
            if ai_creator and ai_type:
                return ClassificationResult(
                    creator_id=ai_creator,
                    source_type=ai_type,
                    published_at=published_at,
                    confidence=0.70,
                    matched_rule="ai_classification",
                    ai_reasoning=ai_reasoning,
                )

        # ── Priority 5: Fallback ──
        return ClassificationResult(
            creator_id=self.default.get("creator_id", "_inbox"),
            source_type=self.default.get("source_type", self.default.get("content_type", "unclassified")),
            published_at=published_at,
            confidence=0.10,
            matched_rule="default_fallback",
        )
