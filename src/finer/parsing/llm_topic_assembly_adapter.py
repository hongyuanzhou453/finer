"""LLM-assisted Topic Assembly Adapter — F1.5 constrained assembly.

This module lets F1.5 use DeepSeek JSON Output through a constrained adapter.
The LLM is deliberately constrained:

- It may only group existing ContentBlock IDs.
- It must not create investment intent fields or TradeActions.
- It does not control raw_text; raw_text is reconstructed from source blocks.
- Every block must be assigned exactly once to a TopicBlock or unassigned.

Secrets are read only from DeepSeek environment variables.
Do not pass API keys through prompts, fixtures, or committed files.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from finer.llm import DeepSeekClient, DeepSeekClientError, DeepSeekConfigurationError
from finer.schemas.content_envelope import ContentBlock, ContentEnvelope
from finer.schemas.topic_block import TOPIC_TYPE_LITERAL, TopicAssemblyResult, TopicBlock


FORBIDDEN_F1_5_FIELDS = {
    "direction",
    "actionability",
    "position_delta_hint",
    "trade_action",
    "action_chain",
    "target_price",
    "stop_loss",
    "take_profit",
    "position_size",
}


class LLMTopicAssemblyError(ValueError):
    """Raised when LLM topic assembly fails validation."""


class LLMTopicProposal(BaseModel):
    """One constrained topic proposal returned by the LLM."""

    model_config = ConfigDict(strict=True, extra="forbid")

    topic_title: str = Field(..., description="Short topic title")
    topic_type: TOPIC_TYPE_LITERAL = Field(..., description="F1.5 topic type")
    source_block_ids: List[str] = Field(..., description="Existing block IDs only")
    primary_entity_ids: List[str] = Field(default_factory=list)
    secondary_entity_ids: List[str] = Field(default_factory=list)
    summary: str = Field(default="")
    segmentation_reason: str = Field(default="")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    ambiguity_flags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_blocks(self) -> "LLMTopicProposal":
        if not self.source_block_ids:
            raise ValueError("source_block_ids must not be empty")
        return self


class LLMTopicAssemblyPayload(BaseModel):
    """Structured LLM output before reconstruction into TopicAssemblyResult."""

    model_config = ConfigDict(strict=True, extra="forbid")

    topic_blocks: List[LLMTopicProposal] = Field(default_factory=list)
    unassigned_block_ids: List[str] = Field(default_factory=list)
    reasoning_summary: str = Field(default="")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class LLMTopicAssemblyAdapter:
    """Constrained LLM adapter for F1.5 TopicAssemblyResult.

    Parameters
    ----------
    llm_fn:
        Optional test seam.  Receives ``messages`` and returns a JSON string.
        Production code uses ``DeepSeekClient.from_env()`` by default.
    deepseek_client:
        Optional configured DeepSeekClient. If omitted, environment variables are used.
    max_blocks:
        Safety cap for one LLM request.
    """

    SYSTEM_PROMPT = (
        "You are the F1.5 Topic Assembly module for an investment research pipeline. "
        "Group provided ContentBlocks into coherent topics. "
        "You may only use the provided block_id values. "
        "Every input block_id must appear exactly once in topic_blocks.source_block_ids "
        "or unassigned_block_ids. "
        "Do not infer investment intent. Do not output direction, actionability, "
        "position_delta_hint, target_price, stop_loss, take_profit, position_size, "
        "TradeAction, or action_chain. Return JSON only."
    )

    def __init__(
        self,
        llm_fn: Optional[Callable[[List[Dict[str, Any]]], Optional[str]]] = None,
        deepseek_client: Optional[DeepSeekClient] = None,
        max_blocks: int = 80,
        max_text_chars_per_block: int = 1200,
        llm_timeout: float = 180.0,
    ) -> None:
        self.llm_fn = llm_fn
        self.deepseek_client = deepseek_client
        self.max_blocks = max_blocks
        self.max_text_chars_per_block = max_text_chars_per_block
        self.llm_timeout = llm_timeout

    def is_configured(self) -> bool:
        """Return True if this adapter has a callable LLM path."""
        if self.llm_fn is not None:
            return True
        if self.deepseek_client is not None:
            return True
        try:
            DeepSeekClient.from_env(timeout=self.llm_timeout, max_retries=0)
        except DeepSeekConfigurationError:
            return False
        return True

    def assemble(self, envelope: ContentEnvelope) -> TopicAssemblyResult:
        """Assemble a ContentEnvelope into TopicBlocks using constrained LLM output."""
        blocks = sorted(envelope.blocks, key=lambda b: b.order)
        if len(blocks) > self.max_blocks:
            raise LLMTopicAssemblyError(
                f"Too many blocks for one LLM topic assembly request: "
                f"{len(blocks)} > {self.max_blocks}"
            )

        messages = self._build_messages(envelope, blocks)
        raw = self._call_llm(messages)
        payload = self._parse_payload(raw)
        return self._reconstruct_result(envelope, blocks, payload)

    def _call_llm(self, messages: List[Dict[str, Any]]) -> str:
        if self.llm_fn is not None:
            raw = self.llm_fn(messages)
        else:
            client = self.deepseek_client or DeepSeekClient.from_env(
                timeout=self.llm_timeout
            )
            try:
                data = client.chat_json(
                    messages,
                    max_tokens=8192,
                    thinking_enabled=True,
                    reasoning_effort="high",
                )
            except DeepSeekClientError as exc:
                raise LLMTopicAssemblyError(str(exc)) from exc
            raw = json.dumps(data, ensure_ascii=False)

        if not raw:
            raise LLMTopicAssemblyError("LLM returned empty response")
        return raw

    def _build_messages(
        self,
        envelope: ContentEnvelope,
        blocks: List[ContentBlock],
    ) -> List[Dict[str, Any]]:
        block_payload = [
            {
                "block_id": block.block_id,
                "order": block.order,
                "text": block.text[: self.max_text_chars_per_block],
                "metadata": {
                    "timestamp": block.metadata.get("timestamp"),
                    "mentioned_entities": block.metadata.get("mentioned_entities", []),
                },
            }
            for block in blocks
        ]

        example_json_output = {
            "topic_blocks": [
                {
                    "topic_title": "泡泡玛特 IP 国际化",
                    "topic_type": "single_stock",
                    "source_block_ids": ["block_001", "block_002"],
                    "primary_entity_ids": ["泡泡玛特"],
                    "secondary_entity_ids": ["IP", "港股"],
                    "summary": "同一标的的连续讨论应合并。",
                    "segmentation_reason": "same entity continuation",
                    "confidence": 0.9,
                    "ambiguity_flags": [],
                }
            ],
            "unassigned_block_ids": ["block_003"],
            "reasoning_summary": "Only group existing block ids.",
            "confidence": 0.88,
        }

        user_payload = {
            "task": "F1.5 topic assembly",
            "envelope_id": envelope.envelope_id,
            "allowed_topic_type_values": [
                "single_stock",
                "industry",
                "macro_policy",
                "market_commentary",
                "investment_philosophy",
                "portfolio_update",
                "news_forward",
                "other",
            ],
            "output_schema": {
                "topic_blocks": [
                    {
                        "topic_title": "string",
                        "topic_type": "one allowed topic type",
                        "source_block_ids": ["existing block_id only"],
                        "primary_entity_ids": ["string"],
                        "secondary_entity_ids": ["string"],
                        "summary": "string",
                        "segmentation_reason": "string",
                        "confidence": 0.0,
                        "ambiguity_flags": ["string"],
                    }
                ],
                "unassigned_block_ids": ["existing block_id only"],
                "reasoning_summary": "string",
                "confidence": 0.0,
            },
            "example_json_output": example_json_output,
            "json_output_requirement": (
                "Return one valid JSON object matching output_schema. "
                "Do not wrap it in markdown."
            ),
            "blocks": block_payload,
        }

        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False),
            },
        ]

    def _parse_payload(self, raw: str) -> LLMTopicAssemblyPayload:
        self._reject_forbidden_fields(raw)
        data = self._loads_json(raw)
        try:
            return LLMTopicAssemblyPayload.model_validate(data)
        except ValidationError as exc:
            raise LLMTopicAssemblyError(f"Invalid LLM topic assembly payload: {exc}") from exc

    @staticmethod
    def _loads_json(raw: str) -> Any:
        text = raw.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMTopicAssemblyError(f"LLM output is not valid JSON: {exc}") from exc

    @staticmethod
    def _reject_forbidden_fields(raw: str) -> None:
        for field in FORBIDDEN_F1_5_FIELDS:
            if re.search(rf'"{re.escape(field)}"\s*:', raw):
                raise LLMTopicAssemblyError(
                    f"Forbidden F1.5 field in LLM output: {field}"
                )

    def _reconstruct_result(
        self,
        envelope: ContentEnvelope,
        blocks: List[ContentBlock],
        payload: LLMTopicAssemblyPayload,
    ) -> TopicAssemblyResult:
        block_by_id = {block.block_id: block for block in blocks}
        input_ids = set(block_by_id)
        assigned_ids: list[str] = []

        for proposal in payload.topic_blocks:
            assigned_ids.extend(proposal.source_block_ids)

        all_output_ids = assigned_ids + payload.unassigned_block_ids
        output_set = set(all_output_ids)

        fabricated = sorted(output_set - input_ids)
        if fabricated:
            raise LLMTopicAssemblyError(f"LLM fabricated block_ids: {fabricated}")

        missing = sorted(input_ids - output_set)
        if missing:
            raise LLMTopicAssemblyError(f"LLM omitted block_ids: {missing}")

        duplicates = sorted({bid for bid in all_output_ids if all_output_ids.count(bid) > 1})
        if duplicates:
            raise LLMTopicAssemblyError(f"LLM duplicated block_ids: {duplicates}")

        topic_blocks: list[TopicBlock] = []
        for proposal in payload.topic_blocks:
            source_blocks = [block_by_id[bid] for bid in proposal.source_block_ids]
            source_blocks.sort(key=lambda b: b.order)
            start_index = source_blocks[0].order
            end_index = source_blocks[-1].order
            raw_text = "\n\n".join(block.text for block in source_blocks)

            topic_blocks.append(
                TopicBlock(
                    envelope_id=envelope.envelope_id,
                    source_block_ids=[block.block_id for block in source_blocks],
                    topic_title=proposal.topic_title,
                    topic_type=proposal.topic_type,
                    primary_entity_ids=proposal.primary_entity_ids,
                    secondary_entity_ids=proposal.secondary_entity_ids,
                    start_block_index=start_index,
                    end_block_index=end_index,
                    start_time=self._extract_boundary_time(source_blocks, first=True),
                    end_time=self._extract_boundary_time(source_blocks, first=False),
                    summary=proposal.summary,
                    raw_text=raw_text,
                    segmentation_reason=proposal.segmentation_reason,
                    confidence=proposal.confidence,
                    ambiguity_flags=proposal.ambiguity_flags,
                )
            )

        return TopicAssemblyResult(
            envelope_id=envelope.envelope_id,
            topic_blocks=topic_blocks,
            unassigned_block_ids=payload.unassigned_block_ids,
            assembly_strategy="llm_constrained_deepseek_v1",
        )

    @staticmethod
    def _extract_boundary_time(
        source_blocks: List[ContentBlock],
        *,
        first: bool,
    ) -> Optional[datetime]:
        times: list[datetime] = []
        for block in source_blocks:
            value = block.metadata.get("timestamp")
            if not value:
                continue
            if isinstance(value, datetime):
                times.append(value)
            elif isinstance(value, str):
                try:
                    times.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
                except ValueError:
                    continue
        if not times:
            return None
        return min(times) if first else max(times)
