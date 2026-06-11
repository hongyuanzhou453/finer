"""DPO Trainer — Direct Preference Optimization for TradeAction Extraction.

This module provides:
- Dataset export from RLHF feedback data
- Prompt template design for financial domain
- DPO hyperparameter configuration
- Incremental training support
- Data validation utilities

References:
- https://huggingface.co/docs/trl/main/en/dpo_trainer
- https://arxiv.org/abs/2305.18290
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ConfigDict, field_validator

logger = logging.getLogger(__name__)


# ============================================================================
# DPO Configuration
# ============================================================================

@dataclass
class DPOConfig:
    """DPO training hyperparameters.

    Based on HuggingFace TRL research and empirical tuning for financial domain.

    Key insights:
    - Lower beta (0.01-0.1) works better for structured output tasks
    - Lower learning rate (5e-7 to 5e-6) prevents catastrophic forgetting
    - Sigmoid loss type is standard for DPO
    - Single epoch often sufficient for domain adaptation
    """
    # DPO-specific
    beta: float = 0.01  # KL penalty coefficient — lower for structured outputs
    loss_type: str = "sigmoid"  # Options: sigmoid, hinge, ipt

    # Training
    learning_rate: float = 5e-7  # Conservative LR for fine-tuning
    num_train_epochs: int = 1
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0

    # Model
    model_name_or_path: str = "Qwen/Qwen2.5-14B-Instruct"  # Base model
    use_peft: bool = True  # Use LoRA for efficient fine-tuning
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05

    # Data
    max_prompt_length: int = 2048
    max_response_length: int = 1024
    min_rating: int = 3  # Only use high-quality feedback

    # Paths
    output_dir: str = "models/dpo_finetuned"

    def to_huggingface_args(self) -> Dict[str, Any]:
        """Convert to HuggingFace TrainingArguments format."""
        return {
            "output_dir": self.output_dir,
            "num_train_epochs": self.num_train_epochs,
            "per_device_train_batch_size": self.per_device_train_batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "learning_rate": self.learning_rate,
            "warmup_ratio": self.warmup_ratio,
            "weight_decay": self.weight_decay,
            "max_grad_norm": self.max_grad_norm,
            "bf16": True,  # Use bfloat16 for efficiency
            "logging_steps": 10,
            "save_steps": 100,
            "save_total_limit": 3,
        }


# ============================================================================
# Prompt Templates
# ============================================================================

TRADE_ACTION_SYSTEM_PROMPT = """你是一位专业的金融分析师助手，擅长从文本中提取结构化的交易观点。

你的任务是从给定的文本中识别并提取交易信号，包括：
1. 交易标的（股票代码）
2. 方向（看多/看空/中性/观望/风险警示）
3. 具体的交易动作链（入场、加仓、减仓、离场等）
4. 触发条件和目标价格区间
5. 时间周期

输出必须严格遵循指定的 JSON Schema 格式。"""

TRADE_ACTION_USER_TEMPLATE = """从以下文本提取 TradeAction：

## 原文
{evidence_text}

## 提取要求
1. 准确识别交易标的（ticker）
2. 判断整体方向：bullish（看多）/ bearish（看空）/ neutral（中性）/ watchlist（观望）/ risk_warning（风险警示）
3. 提取动作链（action_chain），每个动作包含：
   - action_type: long/short/close_long/close_short/buy_call/sell_call/buy_put/sell_put/hold/watch/buy_and_hold
   - instrument_type: stock/option/etf/index_future/unspecified
   - trigger_condition: 触发条件（自然语言或数值）
   - target_price_low/target_price_high: 目标价格区间
   - sequence_order: 执行顺序
4. 判断时间周期（time_horizon）
5. 判断整体信念强度 conviction（0-1）：证据充分/语气强烈≈0.7-0.9；谨慎/证据有限≈0.2-0.4。
   证据不足时应**降低 conviction**，而非强行给中性——保留方向、用低 conviction 表达谨慎。
6. 给出提取置信度 confidence（0-1）

## 输出格式
严格按照以下 JSON Schema 输出：

```json
{{
  "ticker": "股票代码",
  "direction": "方向",
  "conviction": 信念强度0到1,
  "action_chain": [
    {{
      "action_type": "动作类型",
      "instrument_type": "工具类型",
      "trigger_condition": "触发条件",
      "target_price_low": 价格下限,
      "target_price_high": 价格上限,
      "sequence_order": 顺序,
      "confidence": 置信度
    }}
  ],
  "time_horizon": "时间周期",
  "rationale": "提取理由"
}}
```"""

TRADE_ACTION_JSON_SCHEMA = """{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["ticker", "direction"],
  "properties": {
    "ticker": {
      "type": "string",
      "description": "股票代码，必须是大写标准格式（如 AAPL, TSLA）"
    },
    "direction": {
      "type": "string",
      "enum": ["bullish", "bearish", "neutral", "watchlist", "risk_warning"],
      "description": "整体方向判断"
    },
    "conviction": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "整体信念强度（0-1）。证据充分/强烈≈0.7-0.9，谨慎/证据有限≈0.2-0.4。证据不足时降低 conviction 而非清空方向"
    },
    "action_chain": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["action_type"],
        "properties": {
          "action_type": {
            "type": "string",
            "enum": ["long", "short", "close_long", "close_short", "buy_call", "sell_call", "buy_put", "sell_put", "hold", "watch", "buy_and_hold"]
          },
          "instrument_type": {
            "type": "string",
            "enum": ["stock", "option", "etf", "index_future", "unspecified"],
            "default": "unspecified"
          },
          "trigger_condition": {
            "type": ["string", "null"],
            "description": "触发条件，如 'price < 480', 'breakout confirmed'"
          },
          "target_price_low": {
            "type": ["number", "null"],
            "minimum": 0
          },
          "target_price_high": {
            "type": ["number", "null"],
            "minimum": 0
          },
          "sequence_order": {
            "type": "integer",
            "minimum": 1,
            "default": 1
          },
          "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "default": 1.0
          }
        }
      }
    },
    "time_horizon": {
      "type": ["string", "null"],
      "description": "时间周期，如 '1 week', 'long term'"
    },
    "rationale": {
      "type": ["string", "null"],
      "description": "提取理由简述"
    }
  }
}"""


def format_dpo_prompt(evidence_text: str, include_schema: bool = False) -> str:
    """Format a DPO training prompt.

    Args:
        evidence_text: The original text to extract from
        include_schema: Whether to include JSON schema in prompt

    Returns:
        Formatted prompt string
    """
    prompt = TRADE_ACTION_USER_TEMPLATE.format(evidence_text=evidence_text)

    if include_schema:
        prompt += f"\n\n## JSON Schema 参考\n```json\n{TRADE_ACTION_JSON_SCHEMA}\n```"

    return prompt


def to_bailian_record(
    prompt: str,
    chosen: Any,
    rejected: Any,
    system: Optional[str] = TRADE_ACTION_SYSTEM_PROMPT,
) -> Dict[str, Any]:
    """Convert an internal (prompt, chosen, rejected) triple into Alibaba Bailian
    (Model Studio) DPO ChatML format.

    百炼 DPO 要求 ChatML，且 chosen/rejected 是 {role, content} **对象**（非字符串）。
    映射：system=抽取系统提示，user=prompt，chosen/rejected.content=对应 JSON 串。
    详见 docs/specs/2026-06-07-dpo-bailian-training-line.md §6 与 §14。
    """
    def _content(x: Any) -> str:
        return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)

    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return {
        "messages": messages,
        "chosen": {"role": "assistant", "content": _content(chosen)},
        "rejected": {"role": "assistant", "content": _content(rejected)},
    }


# ============================================================================
# DPO Data Models
# ============================================================================

class DPOTrainingItem(BaseModel):
    """Single DPO training example.

    Format compatible with HuggingFace DPO Trainer.
    """
    model_config = ConfigDict(strict=True)

    prompt: str = Field(..., description="The input prompt")
    chosen: str = Field(..., description="The preferred/correct response")
    rejected: str = Field(..., description="The rejected/incorrect response")

    # Metadata for tracking
    feedback_id: Optional[str] = Field(None, description="Source feedback ID")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Feedback rating")
    ticker: Optional[str] = Field(None, description="Ticker for filtering")
    quick_tags: List[str] = Field(default_factory=list, description="Issue tags")
    created_at: datetime = Field(default_factory=datetime.now)

    @field_validator('chosen', 'rejected')
    @classmethod
    def validate_json(cls, v: str) -> str:
        """Ensure chosen/rejected are valid JSON."""
        try:
            json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        return v


class DPODatasetStats(BaseModel):
    """Statistics for DPO dataset."""
    model_config = ConfigDict(strict=True)

    total_items: int = 0
    unique_tickers: int = 0
    avg_rating: float = 0.0
    rating_distribution: Dict[str, int] = Field(default_factory=dict)
    tag_distribution: Dict[str, int] = Field(default_factory=dict)
    date_range: Optional[Tuple[str, str]] = None
    validation_errors: int = 0
    skipped_no_preference: int = 0
    skipped_low_rating: int = 0


# ============================================================================
# DPO Data Export
# ============================================================================

class DPOExporter:
    """Export RLHF feedback data to DPO training format.

    Usage:
        exporter = DPOExporter()

        # Export full dataset
        items = exporter.export_dataset(min_rating=3)
        exporter.save_jsonl(items, "dpo_train.jsonl")

        # Export incremental (new feedbacks since date)
        new_items = exporter.export_incremental(since="2026-04-01")
    """

    def __init__(
        self,
        rlhf_dir: Optional[Path] = None,
        config: Optional[DPOConfig] = None,
    ):
        """Initialize exporter.

        Args:
            rlhf_dir: Path to RLHF data directory
            config: DPO configuration
        """
        if rlhf_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            rlhf_dir = repo_root / "data" / "rlhf"

        self.rlhf_dir = rlhf_dir
        self.feedbacks_dir = rlhf_dir / "feedbacks"
        self.index_path = rlhf_dir / "index.json"
        self.config = config or DPOConfig()

    def load_index(self) -> Dict[str, Any]:
        """Load feedback index."""
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"feedbacks": {}, "stats": {}}
        return {"feedbacks": {}, "stats": {}}

    def load_feedback(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Load a single feedback file."""
        path = self.feedbacks_dir / f"{feedback_id}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning(f"Failed to load feedback: {feedback_id}")
                return None
        return None

    def validate_dpo_item(self, item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate a DPO training item.

        Checks:
        1. chosen and rejected are valid JSON
        2. chosen contains required fields (ticker, direction)
        3. rejected differs from chosen
        4. No duplicate prompts in same batch

        Returns:
            (is_valid, error_message)
        """
        # Check required fields
        if "prompt" not in item or "chosen" not in item or "rejected" not in item:
            return False, "Missing required fields"

        # Validate JSON
        try:
            chosen = json.loads(item["chosen"])
            rejected = json.loads(item["rejected"])
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"

        # Check chosen has required fields
        if "ticker" not in chosen or "direction" not in chosen:
            return False, "Chosen missing ticker or direction"

        # Check chosen differs from rejected
        if chosen == rejected:
            return False, "Chosen identical to rejected (no preference signal)"

        # Check ticker format
        ticker = chosen.get("ticker", "")
        if not ticker or not isinstance(ticker, str):
            return False, "Invalid ticker format"

        return True, None

    def feedback_to_dpo_item(
        self,
        feedback: Dict[str, Any],
        include_schema: bool = False,
    ) -> Optional[DPOTrainingItem]:
        """Convert a feedback record to DPO training item.

        Selection criteria:
        - rating >= min_rating
        - preference exists
        - is_original_correct = False (need correction signal)
        - chosen and rejected both present

        Args:
            feedback: The feedback record
            include_schema: Whether to include JSON schema in prompt

        Returns:
            DPOTrainingItem or None if not suitable
        """
        # Check rating
        rating = feedback.get("rating", 0)
        if rating < self.config.min_rating:
            return None

        # Check preference data
        preference = feedback.get("preference")
        if not preference:
            return None

        # Skip if original was correct (no learning signal)
        if preference.get("is_original_correct", True):
            return None

        # Get chosen and rejected
        chosen = preference.get("chosen")
        rejected = preference.get("rejected")

        if not chosen or not rejected:
            return None

        # Get evidence text
        original_extraction = feedback.get("original_extraction", {})
        evidence_text = original_extraction.get("evidence_text", "")

        if not evidence_text:
            logger.warning(f"Feedback {feedback.get('feedback_id')} missing evidence text")
            return None

        # Build prompt
        prompt = format_dpo_prompt(evidence_text, include_schema=include_schema)

        # Create DPO item
        return DPOTrainingItem(
            prompt=prompt,
            chosen=chosen,
            rejected=rejected,
            feedback_id=feedback.get("feedback_id"),
            rating=rating,
            ticker=original_extraction.get("ticker"),
            quick_tags=feedback.get("quick_tags", []),
        )

    def export_dataset(
        self,
        min_rating: Optional[int] = None,
        tickers: Optional[List[str]] = None,
        include_schema: bool = False,
        validate: bool = True,
    ) -> List[DPOTrainingItem]:
        """Export full DPO dataset.

        Args:
            min_rating: Minimum rating to include (overrides config)
            tickers: Filter to specific tickers (None = all)
            include_schema: Include JSON schema in prompts
            validate: Validate each item

        Returns:
            List of DPOTrainingItem
        """
        if min_rating is None:
            min_rating = self.config.min_rating

        index = self.load_index()
        feedbacks = index.get("feedbacks", {})

        items: List[DPOTrainingItem] = []
        stats = DPODatasetStats()

        for fb_id, fb_meta in feedbacks.items():
            # Load full feedback
            feedback = self.load_feedback(fb_id)
            if not feedback:
                continue

            # Check rating
            rating = feedback.get("rating", 0)
            if rating < min_rating:
                stats.skipped_low_rating += 1
                continue

            # Check ticker filter
            if tickers:
                original = feedback.get("original_extraction", {})
                ticker = original.get("ticker", "")
                if ticker not in tickers:
                    continue

            # Convert to DPO item
            item = self.feedback_to_dpo_item(feedback, include_schema=include_schema)

            if item is None:
                if not feedback.get("preference"):
                    stats.skipped_no_preference += 1
                continue

            # Validate
            if validate:
                is_valid, error = self.validate_dpo_item(item.model_dump())
                if not is_valid:
                    stats.validation_errors += 1
                    logger.debug(f"Validation failed for {fb_id}: {error}")
                    continue

            items.append(item)

        # Update stats
        stats.total_items = len(items)
        logger.info(f"Exported {stats.total_items} DPO items "
                   f"(skipped: low_rating={stats.skipped_low_rating}, "
                   f"no_pref={stats.skipped_no_preference}, "
                   f"invalid={stats.validation_errors})")

        return items

    def export_incremental(
        self,
        since: str,
        include_schema: bool = False,
        validate: bool = True,
    ) -> List[DPOTrainingItem]:
        """Export only feedbacks created after a date.

        Args:
            since: ISO date string (e.g., "2026-04-01")
            include_schema: Include JSON schema in prompts
            validate: Validate each item

        Returns:
            List of new DPOTrainingItem
        """
        since_dt = datetime.fromisoformat(since)

        index = self.load_index()
        feedbacks = index.get("feedbacks", {})

        items: List[DPOTrainingItem] = []

        for fb_id, fb_meta in feedbacks.items():
            # Check date
            reviewed_at = fb_meta.get("reviewed_at", "")
            if not reviewed_at:
                continue

            try:
                fb_dt = datetime.fromisoformat(reviewed_at)
                if fb_dt <= since_dt:
                    continue
            except ValueError:
                continue

            # Load and convert
            feedback = self.load_feedback(fb_id)
            if not feedback:
                continue

            item = self.feedback_to_dpo_item(feedback, include_schema=include_schema)

            if item is None:
                continue

            # Validate
            if validate:
                is_valid, error = self.validate_dpo_item(item.model_dump())
                if not is_valid:
                    continue

            items.append(item)

        logger.info(f"Exported {len(items)} incremental DPO items since {since}")
        return items

    def save_jsonl(
        self,
        items: List[DPOTrainingItem],
        output_path: Path,
        include_metadata: bool = False,
    ) -> int:
        """Save DPO items to JSONL format.

        Args:
            items: DPO training items
            output_path: Output file path
            include_metadata: Include metadata fields (for debugging)

        Returns:
            Number of items written
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        for item in items:
            data = {
                "prompt": item.prompt,
                "chosen": item.chosen,
                "rejected": item.rejected,
            }

            if include_metadata:
                data["metadata"] = {
                    "feedback_id": item.feedback_id,
                    "rating": item.rating,
                    "ticker": item.ticker,
                    "quick_tags": item.quick_tags,
                    "created_at": item.created_at.isoformat(),
                }

            lines.append(json.dumps(data, ensure_ascii=False))

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Saved {len(items)} items to {output_path}")

        return len(items)

    def save_huggingface_format(
        self,
        items: List[DPOTrainingItem],
        output_dir: Path,
    ) -> Dict[str, Path]:
        """Save in HuggingFace dataset format.

        Creates:
        - train.jsonl: Training data
        - metadata.json: Dataset metadata

        Args:
            items: DPO training items
            output_dir: Output directory

        Returns:
            Dict of created file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save training data
        train_path = output_dir / "train.jsonl"
        self.save_jsonl(items, train_path, include_metadata=False)

        # Generate metadata
        tickers = set()
        ratings = []
        tags: Dict[str, int] = {}

        for item in items:
            if item.ticker:
                tickers.add(item.ticker)
            if item.rating:
                ratings.append(item.rating)
            for tag in item.quick_tags:
                tags[tag] = tags.get(tag, 0) + 1

        metadata = {
            "total_examples": len(items),
            "unique_tickers": len(tickers),
            "avg_rating": sum(ratings) / len(ratings) if ratings else 0,
            "tickers": sorted(tickers),
            "tag_distribution": dict(sorted(tags.items(), key=lambda x: -x[1])),
            "created_at": datetime.now().isoformat(),
            "config": {
                "min_rating": self.config.min_rating,
                "beta": self.config.beta,
                "learning_rate": self.config.learning_rate,
            },
        }

        metadata_path = output_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "train": train_path,
            "metadata": metadata_path,
        }

    def save_bailian_format(
        self,
        items: List[DPOTrainingItem],
        output_path: Path,
        system: Optional[str] = TRADE_ACTION_SYSTEM_PROMPT,
    ) -> int:
        """Save DPO items in Bailian (Model Studio) DPO ChatML format (data.jsonl).

        与 save_huggingface_format 的区别：输出百炼 ChatML（chosen/rejected 为
        {role, content} 对象），可直接上传百炼做 DPO LoRA（qwen3-8b）。
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                rec = to_bailian_record(item.prompt, item.chosen, item.rejected, system=system)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
        logger.info(f"Saved {n} Bailian DPO ChatML items to {output_path}")
        return n

    def compute_stats(self, items: List[DPOTrainingItem]) -> DPODatasetStats:
        """Compute statistics for a dataset.

        Args:
            items: DPO training items

        Returns:
            Dataset statistics
        """
        if not items:
            return DPODatasetStats()

        tickers = set()
        ratings = []
        tags: Dict[str, int] = {}
        dates = []

        for item in items:
            if item.ticker:
                tickers.add(item.ticker)
            if item.rating:
                ratings.append(item.rating)
            for tag in item.quick_tags:
                tags[tag] = tags.get(tag, 0) + 1
            dates.append(item.created_at)

        rating_dist = {}
        for r in range(1, 6):
            rating_dist[str(r)] = ratings.count(r)

        date_range = None
        if dates:
            dates_sorted = sorted(dates)
            date_range = (
                dates_sorted[0].isoformat(),
                dates_sorted[-1].isoformat(),
            )

        return DPODatasetStats(
            total_items=len(items),
            unique_tickers=len(tickers),
            avg_rating=sum(ratings) / len(ratings) if ratings else 0,
            rating_distribution=rating_dist,
            tag_distribution=dict(sorted(tags.items(), key=lambda x: -x[1])[:20]),
            date_range=date_range,
        )


# ============================================================================
# Training Script Template
# ============================================================================

DPO_TRAIN_SCRIPT = '''#!/usr/bin/env python3
"""DPO Training Script for TradeAction Extraction.

Usage:
    python train_dpo.py --data_dir ./dpo_data --output_dir ./models/dpo_finetuned

Requires:
    pip install transformers trl peft accelerate bitsandbytes
"""

import argparse
from pathlib import Path
from dataclasses import dataclass

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from trl import DPOTrainer, DPOConfig
from peft import LoraConfig, get_peft_model

from finer.ml.dpo_trainer import DPOConfig as FinerDPOConfig, DPOExporter


def load_dataset(data_dir: Path):
    """Load DPO dataset from JSONL."""
    import json

    train_path = data_dir / "train.jsonl"
    items = []

    with open(train_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))

    return items


def main():
    parser = argparse.ArgumentParser(description="DPO Training for TradeAction")
    parser.add_argument("--data_dir", type=str, required=True)
    parser.add_argument("--output_dir", type=str, default="models/dpo_finetuned")
    parser.add_argument("--model_name", type=str, default="Qwen/Qwen2.5-14B-Instruct")
    parser.add_argument("--beta", type=float, default=0.01)
    parser.add_argument("--lr", type=float, default=5e-7)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch_size", type=int, default=4)
    args = parser.parse_args()

    # Load dataset
    data_dir = Path(args.data_dir)
    dataset = load_dataset(data_dir)
    print(f"Loaded {len(dataset)} training examples")

    # Load model and tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )

    # Apply LoRA
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)

    # DPO config
    dpo_config = DPOConfig(
        output_dir=args.output_dir,
        beta=args.beta,
        learning_rate=args.lr,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        warmup_ratio=0.1,
        bf16=True,
        logging_steps=10,
        save_steps=100,
    )

    # Create trainer
    trainer = DPOTrainer(
        model=model,
        ref_model=None,  # Will use the same model as reference
        args=dpo_config,
        train_dataset=dataset,
        tokenizer=tokenizer,
    )

    # Train
    trainer.train()

    # Save
    trainer.save_model()
    print(f"Model saved to {args.output_dir}")


if __name__ == "__main__":
    main()
'''


# ============================================================================
# Convenience Functions
# ============================================================================

def export_dpo_dataset(
    output_path: str,
    min_rating: int = 3,
    include_schema: bool = False,
) -> int:
    """Export DPO dataset to file.

    Args:
        output_path: Output file path
        min_rating: Minimum rating to include
        include_schema: Include JSON schema in prompts

    Returns:
        Number of items exported
    """
    config = DPOConfig(min_rating=min_rating)
    exporter = DPOExporter(config=config)

    items = exporter.export_dataset(
        min_rating=min_rating,
        include_schema=include_schema,
    )

    return exporter.save_jsonl(items, Path(output_path))


def validate_dpo_data(item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate a DPO data item.

    Args:
        item: DPO data dictionary

    Returns:
        (is_valid, error_message)
    """
    exporter = DPOExporter()
    return exporter.validate_dpo_item(item)


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example: Export DPO dataset
    print("=== DPO Dataset Export ===")

    exporter = DPOExporter()

    # Export full dataset
    items = exporter.export_dataset(min_rating=3)
    print(f"Exported {len(items)} items")

    if items:
        # Show example
        print("\n=== Example DPO Item ===")
        example = items[0]
        print(f"Prompt (first 200 chars): {example.prompt[:200]}...")
        print(f"Chosen: {example.chosen}")
        print(f"Rejected: {example.rejected}")
        print(f"Rating: {example.rating}")

        # Compute stats
        stats = exporter.compute_stats(items)
        print(f"\n=== Dataset Stats ===")
        print(f"Total: {stats.total_items}")
        print(f"Unique tickers: {stats.unique_tickers}")
        print(f"Avg rating: {stats.avg_rating:.2f}")

        # Save to file
        output_path = Path("data/dpo/train.jsonl")
        exporter.save_huggingface_format(items, output_path.parent)
        print(f"\nSaved to {output_path.parent}")
