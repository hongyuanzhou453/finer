"""Trade Action Extractor — GLM-5.1 + Finance-Skills hybrid extraction.

Implements a confidence-based hybrid strategy:
- GLM-5.1 for initial extraction
- Finance-Skills for validation/enrichment on low confidence
- Direct output on high confidence

Confidence thresholds:
- >= 0.8: Direct output
- 0.5-0.8: Finance-Skills validation
- < 0.5: Flag for manual review
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from finer.llm import LLMClient
from finer.schemas.trade_action import (
    ActionStep,
    ActionType,
    MarketEnrichment,
    SourceInfo,
    TargetInfo,
    TradeAction,
    TradeActionBatch,
    TradeDirection,
    TriggerType,
    ValidationStatus,
)
from finer.schemas.lineage import DataLineage, VersionInfo
from finer.services.finance_skills_client import (
    FinanceSkillsClient,
    SkillName,
    get_finance_skills_client,
)
from finer.services.performance import track_performance
from finer.services.versioning import get_version_manager, VersionManager
from finer.services.lineage import get_lineage_tracker, LineageTracker

logger = logging.getLogger(__name__)


# =============================================================================
# Extraction Prompts
# =============================================================================

TRADE_ACTION_SYSTEM_PROMPT = """你是一个专业的金融交易分析助手。你的任务是从文本中提取结构化的交易操作（Trade Actions）。

## 输出格式要求
必须输出有效的 JSON 数组，每个元素包含以下字段：

```json
{
  "ticker": "股票代码（如 AAPL、TSLA、腾讯）",
  "ticker_normalized": "标准化代码（如 AAPL）",
  "market": "市场（US/HK/CN/CRYPTO）",
  "instrument_type": "类型（stock/option/etf/index_future/crypto/unspecified）",
  "company_name": "公司全名（可选）",
  "direction": "方向（bullish/bearish/neutral/watchlist/risk_warning）",
  "confidence": "置信度（0.0-1.0）",
  "action_chain": [
    {
      "action_type": "操作类型（long/short/close_long/close_short/buy_call/sell_call/buy_put/sell_put/hold/watch/buy_and_hold）",
      "trigger_condition": "触发条件描述",
      "trigger_type": "触发类型（price_threshold/breakout/support_resistance/indicator_signal/time_based/news_event/manual）",
      "target_price_low": "目标价格下限（可选）",
      "target_price_high": "目标价格上限（可选）",
      "position_size_pct": "仓位比例（0-1，可选）",
      "notes": "备注（可选）"
    }
  ],
  "time_horizon": "持仓周期（如 '1 week', 'long term'）",
  "rationale": "推理依据",
  "evidence_text": "原文证据片段"
}
```

## 方向判断规则
- bullish: 看多、买入、抄底、加仓、逢低吸纳
- bearish: 看空、卖出、做空、减仓、止损
- neutral: 中性、观望、不确定
- watchlist: 观察名单、关注、跟踪
- risk_warning: 风险提示、警示、危险信号

## 操作链拆分规则
复合操作必须拆分为有序步骤：
- "等回调买入" → [watch] + [long]
- "跌破止损" → [hold] + [close_long with trigger]
- "突破追涨" → [watch] + [long with trigger]

## 时间戳提取
务必提取精确时间信息：
- 文章发布时间
- 提及的具体日期
- 时间范围描述

## 置信度评估
- 0.9-1.0: 明确的交易指令，无歧义
- 0.7-0.9: 清晰的倾向，但可能缺少部分细节
- 0.5-0.7: 有一定信号，但需要进一步验证
- 0.3-0.5: 模糊信号，低置信度
- < 0.3: 极低置信度，几乎无明确信号

只输出 JSON 数组，不要输出其他内容。"""

TRADE_ACTION_USER_PROMPT_TEMPLATE = """请从以下文本中提取所有交易操作：

{content}

{context_section}

输出 JSON 数组格式的交易操作列表。"""


# =============================================================================
# Confidence Thresholds
# =============================================================================

class ConfidenceThreshold:
    """Confidence thresholds for extraction routing."""
    HIGH = 0.8      # Direct output
    MEDIUM = 0.5    # Finance-Skills validation
    LOW = 0.3       # Flag for review


# =============================================================================
# Extraction Result
# =============================================================================

class ExtractionResult:
    """Container for extraction result with metadata."""

    def __init__(
        self,
        success: bool,
        actions: List[TradeAction],
        raw_response: Optional[str] = None,
        error: Optional[str] = None,
        needs_validation: bool = False,
    ):
        self.success = success
        self.actions = actions
        self.raw_response = raw_response
        self.error = error
        self.needs_validation = needs_validation

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def avg_confidence(self) -> float:
        if not self.actions:
            return 0.0
        return sum(a.confidence for a in self.actions) / len(self.actions)


# =============================================================================
# Main Extractor
# =============================================================================

class TradeActionExtractor:
    """Hybrid extractor using GLM-5.1 + Finance-Skills.

    Extraction strategy:
    1. GLM-5.1 extracts TradeAction candidates
    2. Low confidence → Finance-Skills validation/enrichment
    3. High confidence → Direct output
    4. Very low confidence → Manual review flag

    Example usage:
        extractor = TradeActionExtractor()
        actions = await extractor.extract_from_text("AAPL at 180 is a good entry")
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        finance_client: Optional[FinanceSkillsClient] = None,
        model_version: str = "glm-5.1",
        enable_enrichment: bool = True,
        enable_lineage: bool = True,
        lineage_tracker: Optional[LineageTracker] = None,
        version_manager: Optional[VersionManager] = None,
    ):
        """Initialize extractor.

        Args:
            llm_client: LLM client for GLM-5.1
            finance_client: Finance-Skills client for validation
            model_version: Model version identifier
            enable_enrichment: Whether to enable Finance-Skills enrichment
            enable_lineage: Whether to enable lineage tracking
            lineage_tracker: Lineage tracker instance (uses default if None)
            version_manager: Version manager instance (uses default if None)
        """
        self.llm_client = llm_client
        self.finance_client = finance_client or get_finance_skills_client()
        self.model_version = model_version
        self.enable_enrichment = enable_enrichment
        self.enable_lineage = enable_lineage
        self.lineage_tracker = lineage_tracker or get_lineage_tracker()
        self.version_manager = version_manager or get_version_manager()

    async def _ensure_llm_client(self) -> Optional[LLMClient]:
        """Ensure LLM client is initialized."""
        if self.llm_client is None:
            # Try to create from environment/model registry
            from finer.model_config import get_text_registry
            try:
                registry = get_text_registry()
                self.llm_client = LLMClient.from_registry(registry)
            except Exception as e:
                logger.warning(f"Could not create LLM client from registry: {e}")
        return self.llm_client

    def _build_extraction_prompt(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """Build system and user prompts for extraction.

        Args:
            text: Text to analyze
            context: Optional context (source_id, timestamp, etc.)

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        context_section = ""
        if context:
            context_items = []
            if "source_id" in context:
                context_items.append(f"来源ID: {context['source_id']}")
            if "timestamp" in context:
                context_items.append(f"时间: {context['timestamp']}")
            if "author" in context:
                context_items.append(f"作者: {context['author']}")
            if context_items:
                context_section = "背景信息：\n" + "\n".join(context_items)

        user_prompt = TRADE_ACTION_USER_PROMPT_TEMPLATE.format(
            content=text,
            context_section=context_section,
        )

        return TRADE_ACTION_SYSTEM_PROMPT, user_prompt

    def _parse_llm_response(
        self,
        response: str,
        source_id: str,
        evidence_text: str,
        source_type: Optional[str] = None,
        pipeline_run_id: Optional[str] = None,
    ) -> List[TradeAction]:
        """Parse LLM JSON response into TradeAction objects.

        Args:
            response: Raw LLM response (JSON array)
            source_id: Source content ID
            evidence_text: Original text evidence
            source_type: Source system type (feishu, bilibili, wechat)
            pipeline_run_id: Pipeline run ID for grouping

        Returns:
            List of TradeAction objects
        """
        try:
            # Try to extract JSON from response
            # Handle markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            # Parse JSON
            data = json.loads(response.strip())

            if not isinstance(data, list):
                data = [data]

            actions = []
            for idx, item in enumerate(data):
                try:
                    action = self._dict_to_trade_action(
                        item,
                        source_id=source_id,
                        evidence_text=item.get("evidence_text", evidence_text),
                        source_type=source_type,
                        pipeline_run_id=pipeline_run_id,
                    )
                    actions.append(action)
                except ValidationError as e:
                    logger.warning(f"Validation error for item {idx}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error parsing item {idx}: {e}")
                    continue

            return actions

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.debug(f"Response was: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return []

    def _dict_to_trade_action(
        self,
        data: Dict[str, Any],
        source_id: str,
        evidence_text: str,
        source_type: Optional[str] = None,
        pipeline_run_id: Optional[str] = None,
    ) -> TradeAction:
        """Convert dictionary to TradeAction.

        Args:
            data: Dictionary from LLM
            source_id: Source content ID
            evidence_text: Evidence text
            source_type: Source system type (feishu, bilibili, wechat)
            pipeline_run_id: Pipeline run ID for grouping

        Returns:
            TradeAction instance
        """
        # Build TargetInfo
        target = TargetInfo(
            ticker=data.get("ticker", "UNKNOWN"),
            ticker_normalized=data.get("ticker_normalized"),
            market=data.get("market"),
            instrument_type=data.get("instrument_type", "unspecified"),
            company_name=data.get("company_name"),
        )

        # Build SourceInfo
        source = SourceInfo(
            content_id=source_id,
            evidence_text=evidence_text,
        )

        # Build ActionChain
        action_chain = []
        for idx, step_data in enumerate(data.get("action_chain", [])):
            try:
                action_type_str = step_data.get("action_type", "watch").lower()
                action_type = ActionType(action_type_str)
            except ValueError:
                action_type = ActionType.WATCH

            try:
                trigger_type_str = step_data.get("trigger_type", "manual").lower()
                trigger_type = TriggerType(trigger_type_str)
            except ValueError:
                trigger_type = TriggerType.MANUAL

            step = ActionStep(
                sequence=idx + 1,
                action_type=action_type,
                trigger_condition=step_data.get("trigger_condition"),
                trigger_type=trigger_type,
                target_price_low=step_data.get("target_price_low"),
                target_price_high=step_data.get("target_price_high"),
                position_size_pct=step_data.get("position_size_pct"),
                notes=step_data.get("notes"),
            )
            action_chain.append(step)

        if not action_chain:
            action_chain = [ActionStep(sequence=1, action_type=ActionType.WATCH)]

        # Parse direction
        try:
            direction_str = data.get("direction", "neutral").lower()
            direction = TradeDirection(direction_str)
        except ValueError:
            direction = TradeDirection.NEUTRAL

        # Build TradeAction
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

        # Create lineage if enabled
        lineage: Optional[DataLineage] = None
        if self.enable_lineage:
            lineage = self.lineage_tracker.create_lineage(
                content_id=source_id,
                source=source_type,
                pipeline_run_id=pipeline_run_id,
            )

        # Create version info
        version_info: Optional[VersionInfo] = None
        if self.enable_lineage:
            version_info = self.version_manager.create_version_info(
                model_name=self.model_version,
                prompt_template=TRADE_ACTION_SYSTEM_PROMPT,
                temperature=0.3,  # Matches the temperature used in extraction
            )

        action = TradeAction(
            source=source,
            target=target,
            direction=direction,
            action_chain=action_chain,
            confidence=confidence,
            model_version=self.model_version,
            extraction_method="hybrid",
            time_horizon=data.get("time_horizon"),
            rationale=data.get("rationale"),
            lineage=lineage,
            version_info=version_info,
        )

        # Register action with lineage tracker
        if self.enable_lineage and lineage:
            self.lineage_tracker.register_action(action.trade_action_id, lineage)

        return action

    @track_performance("trade_action_extract")
    async def extract_from_text(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Extract TradeActions from text.

        This is the main entry point for text extraction.

        Args:
            text: Text to analyze
            context: Optional context (source_id, timestamp, author, etc.)

        Returns:
            ExtractionResult with extracted actions
        """
        warnings.warn(
            "extract_from_text is deprecated — use CanonicalActionBuilder via F3→F4→F5 canonical pipeline",
            DeprecationWarning,
            stacklevel=2,
        )
        # Quarantine hard gate (P0 #1 单一真相源收口): every extract path of
        # this module funnels through here, and this is the only route to the
        # module's legacy ``TradeAction(`` construction — which bypasses F3
        # Intent / F4 Policy and the canonical composer. New code must never
        # wire it; read-only migration tooling opts in explicitly.
        if os.environ.get("FINER_ALLOW_LEGACY_PIPELINE", "").strip() != "1":
            raise RuntimeError(
                "TradeActionExtractor.extract_from_text is quarantined legacy: "
                "it constructs non-canonical TradeActions (no intent_id / "
                "policy_id / evidence trace). Use the F3→F4→F5 canonical "
                "pipeline (finer.pipeline.canonical_runner). Set "
                "FINER_ALLOW_LEGACY_PIPELINE=1 only for read-only migration "
                "tooling."
            )
        llm = await self._ensure_llm_client()
        if not llm:
            logger.error("No LLM client available")
            return ExtractionResult(
                success=False,
                actions=[],
                error="No LLM client available",
            )

        source_id = context.get("source_id", "unknown") if context else "unknown"

        # Build prompts
        system_prompt, user_prompt = self._build_extraction_prompt(text, context)

        # Call LLM
        try:
            logger.info(f"Calling {self.model_version} for extraction...")
            response = llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,  # Lower temperature for structured output
            )

            if not response:
                logger.error("Empty response from LLM")
                return ExtractionResult(
                    success=False,
                    actions=[],
                    error="Empty LLM response",
                )

            # Parse response
            source_type = context.get("source_type") if context else None
            pipeline_run_id = context.get("pipeline_run_id") if context else None

            actions = self._parse_llm_response(
                response,
                source_id=source_id,
                evidence_text=text[:500],  # First 500 chars as evidence
                source_type=source_type,
                pipeline_run_id=pipeline_run_id,
            )

            if not actions:
                logger.warning("No actions extracted from response")
                return ExtractionResult(
                    success=True,
                    actions=[],
                    raw_response=response,
                )

            # Check if validation needed
            needs_validation = any(
                a.confidence < ConfidenceThreshold.HIGH for a in actions
            )

            logger.info(
                f"Extracted {len(actions)} actions, "
                f"avg confidence: {sum(a.confidence for a in actions) / len(actions):.2f}"
            )

            return ExtractionResult(
                success=True,
                actions=actions,
                raw_response=response,
                needs_validation=needs_validation,
            )

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return ExtractionResult(
                success=False,
                actions=[],
                error=str(e),
            )

    async def extract_from_file(
        self,
        file_path: str,
        encoding: str = "utf-8",
    ) -> ExtractionResult:
        """Extract TradeActions from a file.

        Args:
            file_path: Path to file (text, markdown, etc.)
            encoding: File encoding

        Returns:
            ExtractionResult with extracted actions
        """
        warnings.warn(
            "extract_from_file is deprecated — use CanonicalActionBuilder via F3→F4→F5 canonical pipeline",
            DeprecationWarning,
            stacklevel=2,
        )
        path = Path(file_path)

        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return ExtractionResult(
                success=False,
                actions=[],
                error=f"File not found: {file_path}",
            )

        try:
            text = path.read_text(encoding=encoding)

            # Use filename as source_id
            context = {
                "source_id": str(path.absolute()),
                "filename": path.name,
            }

            # Try to extract timestamp from frontmatter or filename
            # Pattern: 2026-04-15-xxx.txt or similar
            timestamp_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
            if timestamp_match:
                context["timestamp"] = timestamp_match.group(1)

            return await self.extract_from_text(text, context=context)

        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return ExtractionResult(
                success=False,
                actions=[],
                error=str(e),
            )

    async def batch_extract(
        self,
        items: List[Dict[str, Any]],
        parallel: bool = True,
        max_concurrency: int = 5,
    ) -> List[ExtractionResult]:
        """Extract TradeActions from multiple items in batch.

        Args:
            items: List of items, each with 'text' and optional 'context'
            parallel: Whether to process in parallel
            max_concurrency: Maximum concurrent extractions

        Returns:
            List of ExtractionResult in same order as input
        """
        warnings.warn(
            "batch_extract is deprecated — use CanonicalActionBuilder via F3→F4→F5 canonical pipeline",
            DeprecationWarning,
            stacklevel=2,
        )
        if not parallel:
            # Sequential processing
            results = []
            for item in items:
                result = await self.extract_from_text(
                    item.get("text", ""),
                    context=item.get("context"),
                )
                results.append(result)
            return results

        # Parallel processing with semaphore
        semaphore = asyncio.Semaphore(max_concurrency)

        async def extract_with_semaphore(item: Dict[str, Any]) -> ExtractionResult:
            async with semaphore:
                return await self.extract_from_text(
                    item.get("text", ""),
                    context=item.get("context"),
                )

        tasks = [extract_with_semaphore(item) for item in items]
        return await asyncio.gather(*tasks)

    async def validate_and_enrich(
        self,
        action: TradeAction,
    ) -> TradeAction:
        """Validate and enrich a TradeAction using Finance-Skills.

        Enrichment includes:
        - Current market price
        - Volume data
        - 52-week high/low
        - Basic fundamentals

        Validation checks:
        - Price target validity
        - Market data availability
        - Confidence adjustment

        Args:
            action: TradeAction to enrich

        Returns:
            Enriched TradeAction
        """
        if not self.enable_enrichment:
            return action

        ticker = action.normalize_ticker()

        # Fetch market data
        try:
            market_data = await self.finance_client.get_market_data(ticker)

            if market_data:
                # Build enrichment
                enrichment = MarketEnrichment(
                    market_price_at_time=market_data.get("currentPrice"),
                    volume_avg_20d=market_data.get("averageVolume"),
                    high_52wk=market_data.get("fiftyTwoWeekHigh"),
                    low_52wk=market_data.get("fiftyTwoWeekLow"),
                    pe_ratio=market_data.get("trailingPE"),
                    market_cap=market_data.get("marketCap"),
                    data_timestamp=datetime.now(),
                )

                # Calculate relative position from 52wk
                if enrichment.market_price_at_time:
                    price = enrichment.market_price_at_time
                    if enrichment.high_52wk:
                        enrichment.pct_from_52wk_high = (
                            (price - enrichment.high_52wk) / enrichment.high_52wk * 100
                        )
                    if enrichment.low_52wk:
                        enrichment.pct_from_52wk_low = (
                            (price - enrichment.low_52wk) / enrichment.low_52wk * 100
                        )

                action.enrichment = enrichment

                # Adjust confidence based on data availability
                if action.confidence < ConfidenceThreshold.HIGH:
                    # Boost confidence if market data confirms
                    action.confidence = min(1.0, action.confidence + 0.1)
                    logger.debug(
                        f"Boosted confidence for {ticker}: {action.confidence:.2f}"
                    )

            # Fetch fundamentals for additional context
            fundamentals = await self.finance_client.get_fundamentals(ticker)
            if fundamentals and action.enrichment:
                # Add PE ratio if not already set
                if not action.enrichment.pe_ratio:
                    action.enrichment.pe_ratio = fundamentals.get("pe_ratio")

        except Exception as e:
            logger.warning(f"Enrichment failed for {ticker}: {e}")
            action.validation_warnings.append(f"Enrichment failed: {str(e)}")

        # Validate price targets
        action = self._validate_price_targets(action)

        # Update validation status
        if action.confidence >= ConfidenceThreshold.HIGH:
            action.validation_status = ValidationStatus.VERIFIED
        elif action.confidence >= ConfidenceThreshold.MEDIUM:
            action.validation_status = ValidationStatus.UNDER_REVIEW
        else:
            action.validation_status = ValidationStatus.PENDING
            action.requires_manual_review = True

        return action

    def _validate_price_targets(self, action: TradeAction) -> TradeAction:
        """Validate price targets against market data.

        Checks:
        - Target prices are reasonable (not negative, not too extreme)
        - Price ranges are valid (low < high)
        - Targets are consistent with direction

        Args:
            action: TradeAction to validate

        Returns:
            Validated TradeAction with issues flagged
        """
        if not action.enrichment or not action.enrichment.market_price_at_time:
            return action

        current_price = action.enrichment.market_price_at_time

        for step in action.action_chain:
            # Check target price range
            if step.target_price_low and step.target_price_high:
                if step.target_price_low >= step.target_price_high:
                    issue = f"Invalid price range: {step.target_price_low} >= {step.target_price_high}"
                    action.validation_issues.append(issue)

            # Check if target is consistent with direction
            if step.target_price_low:
                # For bullish/long, target should be above current price
                if action.direction == TradeDirection.BULLISH:
                    if step.target_price_low < current_price * 0.8:
                        action.validation_warnings.append(
                            f"Target price {step.target_price_low} seems low for bullish position "
                            f"(current: {current_price:.2f})"
                        )

                # For bearish/short, target should be below current price
                if action.direction == TradeDirection.BEARISH:
                    if step.target_price_low > current_price * 1.2:
                        action.validation_warnings.append(
                            f"Target price {step.target_price_low} seems high for bearish position "
                            f"(current: {current_price:.2f})"
                        )

        return action

    async def extract_with_enrichment(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
        enrich_all: bool = False,
    ) -> TradeActionBatch:
        """Extract and optionally enrich TradeActions.

        This is the full pipeline:
        1. Extract from text using GLM-5.1
        2. Route based on confidence
        3. Enrich low-confidence actions
        4. Return batch with stats

        Args:
            text: Text to analyze
            context: Optional context
            enrich_all: If True, enrich all actions (not just low confidence)

        Returns:
            TradeActionBatch with all actions
        """
        warnings.warn(
            "extract_with_enrichment is deprecated — use CanonicalActionBuilder via F3→F4→F5 canonical pipeline",
            DeprecationWarning,
            stacklevel=2,
        )
        # Step 1: Extract (suppress inner DeprecationWarning to avoid double-warn)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = await self.extract_from_text(text, context)

        if not result.success or not result.actions:
            return TradeActionBatch(
                actions=[],
                content_id=context.get("source_id") if context else None,
            )

        actions = result.actions

        # Step 2: Route and enrich
        enrichment_tasks = []

        for action in actions:
            should_enrich = enrich_all or action.confidence < ConfidenceThreshold.HIGH

            if should_enrich and self.enable_enrichment:
                enrichment_tasks.append(self.validate_and_enrich(action))
            else:
                # Mark as verified for high-confidence actions
                if action.confidence >= ConfidenceThreshold.HIGH:
                    action.validation_status = ValidationStatus.VERIFIED
                elif action.confidence < ConfidenceThreshold.LOW:
                    action.requires_manual_review = True

        # Run enrichment in parallel
        if enrichment_tasks:
            logger.info(f"Enriching {len(enrichment_tasks)} actions...")
            await asyncio.gather(*enrichment_tasks)

        # Step 3: Build batch
        batch = TradeActionBatch(
            actions=actions,
            content_id=context.get("source_id") if context else None,
            model_version=self.model_version,
        )

        logger.info(
            f"Extraction complete: {batch.total_actions} actions "
            f"({batch.bullish_count} bullish, {batch.bearish_count} bearish, "
            f"{batch.neutral_count} neutral)"
        )

        return batch


# =============================================================================
# Convenience Functions
# =============================================================================

async def extract_trade_actions(
    text: str,
    context: Optional[Dict[str, Any]] = None,
    enrich: bool = True,
) -> TradeActionBatch:
    """Convenience function for quick extraction.

    Example:
        batch = await extract_trade_actions("AAPL at 180 is a good entry")
        for action in batch.actions:
            print(f"{action.normalize_ticker()}: {action.direction.value}")

    Args:
        text: Text to analyze
        context: Optional context
        enrich: Whether to enable enrichment

    Returns:
        TradeActionBatch with extracted actions
    """
    extractor = TradeActionExtractor(enable_enrichment=enrich)
    return await extractor.extract_with_enrichment(text, context)
