"""LLM-assisted Entity Proposal Adapter — F2 constrained candidate generation.

This module lets F2 use DeepSeek JSON Output through a constrained adapter to
propose Chinese/English entity candidates that the deterministic rule paths
(upper-token / cn-cue in ``scripts/backfill_f2_anchor.py``) cannot recover from
conversational KOL text. It mirrors the F1.5 ``LLMTopicAssemblyAdapter``.

The LLM is deliberately constrained and **never trusted**:

- It may only propose entities that appear verbatim in the block text.
- Every proposal is hard-checked by a deterministic validator before becoming a
  candidate: evidence substring, registry de-dup, stoplist rejection, and
  ticker/market format checks.
- It proposes; it does not decide. Human review + registry insertion stay
  deterministic. Any proposal that fails the validator is dropped silently.

Output candidates are dicts that align with the first 8 fields of
``GAP_CANDIDATE_REVIEW_FIELDS`` (the shared gap-review contract), so they feed
the existing ``build_f2_gap_review_batch`` → ``apply_f2_gap_reviews`` loop
unchanged. The LLM's ticker/market suggestions ride along as extra keys that
downstream whitelisting ignores until the review/registry-insertion step needs
them.

Secrets are read only from DeepSeek environment variables. Do not pass API keys
through prompts, fixtures, or committed files.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from finer.enrichment.entity_stoplist import (
    CN_GENERIC_CANDIDATE_TERMS,
    CN_SECTOR_THEME_TERMS,
    NOISY_UPPER_TOKENS,
)
from finer.entity_registry import resolve
from finer.llm import DeepSeekClient, DeepSeekClientError, DeepSeekConfigurationError

CANDIDATE_TYPE = "llm_entity_proposal"

# Markets / entity types accepted by the F2 registry (see entity_registry.py).
ALLOWED_MARKETS = frozenset({"US", "HK", "CN", "TW", "KR", "COMMODITY", "CRYPTO"})
ALLOWED_ENTITY_TYPES = frozenset(
    {"ticker", "index", "etf", "sector", "commodity", "crypto"}
)

# Ticker format gates (task card §4.Phase1.2).
_CN_HK_TICKER_RE = re.compile(r"^\d{4,6}\.(HK|SH|SZ)$")
_US_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")

# An alias shorter than this is almost always noise (single CJK char, single
# English letter ticker like "V"/"F" that mis-anchors more than it helps).
_MIN_ALIAS_LEN = 2
# An alias longer than this is almost always a phrase/sentence, not an entity.
_MAX_ALIAS_LEN = 20

_CONTEXT_RADIUS = 32

# Optional finance-skills cross-check: (ticker, market) -> bool (exists).
FinanceSkillsValidator = Callable[[str, str], bool]


class LLMEntityProposalError(ValueError):
    """Raised when LLM entity proposal parsing/validation fails."""


class LLMEntityProposal(BaseModel):
    """One constrained entity candidate returned by the LLM.

    ``extra="forbid"`` rejects hallucinated structure (the LLM inventing fields).
    ``strict`` is intentionally *not* set: the deterministic validator below is
    the real gate, so we accept e.g. an integer ``confidence`` rather than
    failing the whole batch on a benign type coercion.
    """

    model_config = ConfigDict(extra="forbid")

    alias: str = Field(..., description="Entity name; must appear verbatim in block text")
    suggested_ticker: str = Field(
        default="", description="Suggested ticker; leave empty if unsure"
    )
    market: str = Field(
        default="", description="One of ALLOWED_MARKETS; leave empty if unsure"
    )
    entity_type: str = Field(
        default="ticker", description="One of ALLOWED_ENTITY_TYPES"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_quote: str = Field(
        ..., description="Exact substring of block text that contains the alias"
    )


class LLMEntityProposalPayload(BaseModel):
    """Structured LLM output before deterministic validation."""

    model_config = ConfigDict(extra="forbid")

    proposals: List[LLMEntityProposal] = Field(default_factory=list)
    reasoning_summary: str = Field(default="")


class LLMEntityProposalAdapter:
    """Constrained LLM adapter for F2 entity candidate proposal.

    Parameters
    ----------
    llm_fn:
        Optional test seam. Receives ``messages`` and returns a JSON string.
        Production code uses ``DeepSeekClient.from_env()`` by default.
    deepseek_client:
        Optional configured DeepSeekClient. If omitted, env vars are used.
    max_text_chars:
        Safety cap on block text length sent to the LLM.
    finance_skills_validator:
        Optional ``(ticker, market) -> bool`` callback (P1). When provided, a
        suggested ticker that fails the check is blanked (alias still proposed
        for manual ticker fill) rather than trusted.
    """

    SYSTEM_PROMPT = (
        "You are the F2 Entity Anchoring candidate proposer for an investment "
        "research pipeline. From the provided block text, propose ONLY named "
        "entities that (a) appear verbatim in the text and (b) are publicly "
        "tradable instruments: listed companies, ETFs, indices, tradable "
        "commodities, or crypto assets. "
        "DO NOT propose: financial metrics or ratios (EPS, PB, ROE, CAGR, 毛利率), "
        "time or date tokens, currency codes (USD, RMB), generic market nouns "
        "(大盘, 指数, 板块), non-tradable organizations (OPEC, 美联储, 证监会, 发改委), "
        "usernames or social handles, fund or strategy names, or generic phrases "
        "and emphasis quotes (倒春寒, 隐性承诺). "
        "For each proposal, set evidence_quote to an exact substring of the block "
        "text that contains the alias. If you are not sure of the ticker, leave "
        "suggested_ticker empty rather than guessing. Set entity_type to one of "
        "ticker/index/etf/sector/commodity/crypto. Return JSON only."
    )

    def __init__(
        self,
        llm_fn: Optional[Callable[[List[Dict[str, Any]]], Optional[str]]] = None,
        deepseek_client: Optional[DeepSeekClient] = None,
        max_text_chars: int = 4000,
        llm_timeout: float = 180.0,
        finance_skills_validator: Optional[FinanceSkillsValidator] = None,
    ) -> None:
        self.llm_fn = llm_fn
        self.deepseek_client = deepseek_client
        self.max_text_chars = max_text_chars
        self.llm_timeout = llm_timeout
        self.finance_skills_validator = finance_skills_validator

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

    def propose_for_block(
        self,
        *,
        text: str,
        block_id: str,
        source_record_id: str = "",
        raw_path: str = "",
        reason: str = "",
    ) -> List[Dict[str, Any]]:
        """Propose validated entity candidates for one block's text.

        Returns a list of candidate dicts aligned with the gap-review contract.
        Returns ``[]`` for empty text. Raises ``LLMEntityProposalError`` on
        unparseable / malformed LLM output (caller decides skip vs. retry).
        """
        text = text or ""
        if not text.strip():
            return []

        messages = self._build_messages(text)
        raw = self._call_llm(messages)
        payload = self._parse_payload(raw)
        return self._validate_and_build_candidates(
            text=text,
            payload=payload,
            block_id=block_id,
            source_record_id=source_record_id,
            raw_path=raw_path,
            reason=reason,
        )

    # ------------------------------------------------------------------ LLM I/O

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
                raise LLMEntityProposalError(str(exc)) from exc
            raw = json.dumps(data, ensure_ascii=False)

        if not raw:
            raise LLMEntityProposalError("LLM returned empty response")
        return raw

    def _build_messages(self, text: str) -> List[Dict[str, Any]]:
        example_json_output = {
            "proposals": [
                {
                    "alias": "地平线",
                    "suggested_ticker": "9660.HK",
                    "market": "HK",
                    "entity_type": "ticker",
                    "confidence": 0.86,
                    "evidence_quote": "地平线被纳入港股通",
                },
                {
                    "alias": "高盛",
                    "suggested_ticker": "GS",
                    "market": "US",
                    "entity_type": "ticker",
                    "confidence": 0.8,
                    "evidence_quote": "高盛把目标价上调",
                },
            ],
            "reasoning_summary": "Only propose tradable named entities present verbatim.",
        }

        user_payload = {
            "task": "F2 entity candidate proposal",
            "allowed_markets": sorted(ALLOWED_MARKETS),
            "allowed_entity_types": sorted(ALLOWED_ENTITY_TYPES),
            "ticker_format_hint": {
                "cn_hk": "4-6 digits + .HK/.SH/.SZ, e.g. 3908.HK, 601995.SH, 002891.SZ",
                "us": "1-5 uppercase letters, e.g. GS, NVDA",
                "unknown": "leave empty",
            },
            "output_schema": {
                "proposals": [
                    {
                        "alias": "string (verbatim substring of block text)",
                        "suggested_ticker": "string or empty",
                        "market": "one allowed market or empty",
                        "entity_type": "one allowed entity type",
                        "confidence": 0.0,
                        "evidence_quote": "exact substring of block text",
                    }
                ],
                "reasoning_summary": "string",
            },
            "example_json_output": example_json_output,
            "json_output_requirement": (
                "Return one valid JSON object matching output_schema. "
                "Do not wrap it in markdown."
            ),
            "block_text": text[: self.max_text_chars],
        }

        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]

    def _parse_payload(self, raw: str) -> LLMEntityProposalPayload:
        data = self._loads_json(raw)
        try:
            return LLMEntityProposalPayload.model_validate(data)
        except ValidationError as exc:
            raise LLMEntityProposalError(
                f"Invalid LLM entity proposal payload: {exc}"
            ) from exc

    @staticmethod
    def _loads_json(raw: str) -> Any:
        text = raw.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMEntityProposalError(f"LLM output is not valid JSON: {exc}") from exc

    # ------------------------------------------------- deterministic validator

    def _validate_and_build_candidates(
        self,
        *,
        text: str,
        payload: LLMEntityProposalPayload,
        block_id: str,
        source_record_id: str,
        raw_path: str,
        reason: str,
    ) -> List[Dict[str, Any]]:
        """Hard-check every proposal; only fully-valid ones become candidates."""
        candidates: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for proposal in payload.proposals:
            alias = proposal.alias.strip()
            if not self._alias_is_valid(alias, proposal.evidence_quote, text):
                continue
            if alias in seen:
                continue

            ticker, market = self._validate_ticker_market(
                proposal.suggested_ticker, proposal.market
            )
            entity_type = (
                proposal.entity_type
                if proposal.entity_type in ALLOWED_ENTITY_TYPES
                else "ticker"
            )

            seen.add(alias)
            candidates.append(
                {
                    # --- gap-review contract (first 8 of GAP_CANDIDATE_REVIEW_FIELDS) ---
                    "alias_candidate": alias,
                    "source_record_id": source_record_id,
                    "block_id": block_id,
                    "raw_path": raw_path,
                    "context_snippet": self._context_snippet(text, alias),
                    "reason": reason,
                    "candidate_type": CANDIDATE_TYPE,
                    "score": round(min(proposal.confidence, 0.95), 2),
                    # --- LLM extras (ignored by downstream whitelist; used at
                    #     review / registry-insertion time) ---
                    "suggested_ticker": ticker,
                    "suggested_market": market,
                    "suggested_entity_type": entity_type,
                    "llm_confidence": round(proposal.confidence, 2),
                    "evidence_quote": proposal.evidence_quote,
                }
            )
        return candidates

    def _alias_is_valid(self, alias: str, evidence_quote: str, text: str) -> bool:
        # Length sanity: reject single chars (noise) and sentence-length spans.
        if not (_MIN_ALIAS_LEN <= len(alias) <= _MAX_ALIAS_LEN):
            return False
        # Anti-hallucination: alias + evidence must appear verbatim, and the
        # alias must sit inside its own evidence quote (self-consistency).
        if evidence_quote not in text:
            return False
        if alias not in text:
            return False
        if alias not in evidence_quote:
            return False
        # De-dup: already-registered entities are not re-proposed (case-insensitive,
        # so an alias like "Nvidia"/"tsla" still matches NVIDIA/TSLA in the registry).
        if self._is_registered(alias):
            return False
        # Stoplist: known non-entity noise.
        if self._is_stoplisted(alias):
            return False
        return True

    @staticmethod
    def _is_registered(alias: str) -> bool:
        return resolve(alias) is not None or resolve(alias.upper()) is not None

    @staticmethod
    def _is_stoplisted(alias: str) -> bool:
        if alias.upper() in NOISY_UPPER_TOKENS:
            return True
        # Sector / theme 泛称 — exact match only (新华保险 != 保险 survives).
        if alias in CN_SECTOR_THEME_TERMS:
            return True
        if any(term in alias for term in CN_GENERIC_CANDIDATE_TERMS):
            return True
        return False

    def _validate_ticker_market(self, ticker: str, market: str) -> tuple[str, str]:
        """Validate ticker format and reconcile with market.

        A malformed ticker is blanked (alias still proposed for manual fill)
        rather than dropping the whole candidate — the alias may be a real
        entity the LLM just couldn't ticker. The ticker suffix is authoritative
        for market to defeat LLM ticker/market mismatch.
        """
        t = (ticker or "").strip().upper()
        m = market if market in ALLOWED_MARKETS else ""

        if not t:
            return "", m
        if _CN_HK_TICKER_RE.match(t):
            if t.endswith(".HK"):
                m = "HK"
            else:  # .SH / .SZ
                m = "CN"
        elif _US_TICKER_RE.match(t):
            m = m or "US"
        else:
            # Malformed ticker (hallucinated format) -> blank it.
            return "", m

        # Optional P1 cross-check against finance-skills.
        if t and self.finance_skills_validator is not None:
            try:
                exists = self.finance_skills_validator(t, m)
            except Exception:
                exists = True  # never let a flaky check drop a real alias
            if not exists:
                return "", m
        return t, m

    @staticmethod
    def _context_snippet(text: str, needle: str, *, radius: int = _CONTEXT_RADIUS) -> str:
        if not text:
            return ""
        idx = text.find(needle)
        if idx < 0:
            return text[: radius * 2].strip()
        start = max(0, idx - radius)
        end = min(len(text), idx + len(needle) + radius)
        return text[start:end].strip()
