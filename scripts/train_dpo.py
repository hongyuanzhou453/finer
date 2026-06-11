#!/usr/bin/env python3
"""DPO Training Script for TradeAction Extraction (local TRL path).

本地 TRL/LoRA 训练线。注意：卡①的**真实训练**走百炼云端 Qwen3-8B，本脚本主要价值是
`--smoke-test`：用极小 Qwen 模型在 CPU 上跑通 DPO 训练循环，证明训练代码是真的、可运行。
详见 docs/specs/2026-06-07-dpo-bailian-training-line.md（地基阶段③）。

用法:
    # 冒烟自检（极小模型 + CPU + 2 步，零 GPU；会从 HF 拉一个 tiny 模型）
    python scripts/train_dpo.py --smoke-test

    # 真实本地训练（需 GPU；导出数据集后）
    python -m finer.ml.export_dpo --output_dir ./data/dpo
    python scripts/train_dpo.py --data_dir ./data/dpo --output_dir ./models/dpo_finetuned

依赖:
    pip install transformers trl peft accelerate datasets torch
    （bitsandbytes 仅 CUDA 4bit 量化需要，Mac/CPU 不装）

已适配 trl 1.x API：DPOTrainer(processing_class=..., peft_config=...)、DPOConfig(use_cpu=...)。
"""

import argparse
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import DPOConfig as TRLDPOConfig, DPOTrainer
from peft import LoraConfig, TaskType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# trl 自测用的极小 Qwen 模型（Qwen 族，匹配 Qwen3-8B 目标；保证与 trl DPOTrainer 兼容）
SMOKE_MODEL = "trl-internal-testing/tiny-Qwen2ForCausalLM-2.5"


def load_dpo_dataset(data_dir: Path) -> List[Dict[str, Any]]:
    """Load DPO dataset from JSONL (train.jsonl). 每行 {prompt, chosen, rejected}。"""
    train_path = data_dir / "train.jsonl"
    if not train_path.exists():
        raise FileNotFoundError(f"Dataset not found: {train_path}")

    items: List[Dict[str, Any]] = []
    with open(train_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if not all(k in item for k in ("prompt", "chosen", "rejected")):
                    logger.warning(f"Line {i} missing required fields, skipping")
                    continue
                items.append({"prompt": item["prompt"], "chosen": item["chosen"], "rejected": item["rejected"]})
            except json.JSONDecodeError as e:
                logger.warning(f"Line {i} invalid JSON: {e}, skipping")
    logger.info(f"Loaded {len(items)} training examples from {train_path}")
    return items


def build_lora_config(lora_r: int = 16, lora_alpha: int = 32, lora_dropout: float = 0.05) -> LoraConfig:
    return LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )


def setup_model_and_tokenizer(model_name: str, cpu: bool = False):
    """Load model + tokenizer. cpu=True 时强制 CPU/fp32（smoke-test 用）。"""
    logger.info(f"Loading model: {model_name} (cpu={cpu})")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    load_kwargs: Dict[str, Any] = {"trust_remote_code": True}
    if not cpu:
        # GPU 路径（本机不跑；trl 1.x / transformers 5.x 用 dtype 而非 torch_dtype）
        load_kwargs["device_map"] = "auto"
        load_kwargs["dtype"] = torch.bfloat16
    model = AutoModelForCausalLM.from_pretrained(model_name, **load_kwargs)
    return model, tokenizer


def train_dpo(
    dataset: List[Dict[str, Any]],
    output_dir: Path,
    model_name: str,
    *,
    beta: float = 0.01,
    learning_rate: float = 5e-7,
    num_epochs: int = 1,
    batch_size: int = 4,
    gradient_accumulation_steps: int = 4,
    lora_r: int = 16,
    lora_alpha: int = 32,
    warmup_ratio: float = 0.1,
    max_grad_norm: float = 1.0,
    logging_steps: int = 10,
    save_steps: int = 100,
    max_steps: int = -1,
    cpu: bool = False,
    max_length: int = 1024,
) -> None:
    """Run DPO training via trl 1.x API."""
    if not dataset:
        raise ValueError("No training data found.")

    from datasets import Dataset

    model, tokenizer = setup_model_and_tokenizer(model_name, cpu=cpu)
    train_ds = Dataset.from_list(dataset)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dpo_config = TRLDPOConfig(
        output_dir=str(output_dir),
        beta=beta,
        learning_rate=learning_rate,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        warmup_ratio=warmup_ratio,
        max_grad_norm=max_grad_norm,
        logging_steps=logging_steps,
        save_steps=save_steps,
        save_total_limit=2,
        max_steps=max_steps,
        max_length=max_length,
        bf16=False if cpu else True,
        fp16=False,
        use_cpu=cpu,
        report_to=[],  # 不上报 wandb 等
        remove_unused_columns=False,
    )

    logger.info(f"DPO Config: beta={beta}, lr={learning_rate}, "
                f"{'max_steps='+str(max_steps) if max_steps > 0 else 'epochs='+str(num_epochs)}")

    trainer = DPOTrainer(
        model=model,
        ref_model=None,  # PEFT 下以禁用 adapter 的同模型作 reference
        args=dpo_config,
        train_dataset=train_ds,
        processing_class=tokenizer,
        peft_config=build_lora_config(lora_r, lora_alpha),
    )

    logger.info("Starting DPO training...")
    result = trainer.train()
    logger.info(f"Training finished. metrics={result.metrics}")

    if max_steps <= 0:  # 真实训练才落盘 final
        trainer.save_model(str(output_dir / "final"))
        tokenizer.save_pretrained(str(output_dir / "final"))
        logger.info(f"Model saved to {output_dir / 'final'}")


def smoke_dataset() -> List[Dict[str, Any]]:
    """极小玩具偏好数据：证据对齐的克制（chosen 克制/挂证据，rejected 过度承诺）。"""
    def aj(**kw) -> str:
        return json.dumps(kw, ensure_ascii=False)

    samples = [
        ("苹果 AAPL 在 150 附近支撑，回踩 148-152 可建仓。",
         aj(ticker="AAPL", direction="bullish", action_chain=[{"action_type": "long", "target_price_low": 148, "target_price_high": 152}]),
         aj(ticker="AAPL", direction="bullish", action_chain=[{"action_type": "long", "target_price_low": 200, "target_price_high": 210}])),
        ("大盘震荡，没明确机会，注意风险。",
         aj(ticker="NONE", direction="watchlist", action_chain=[{"action_type": "watch"}]),
         aj(ticker="TSLA", direction="bullish", action_chain=[{"action_type": "long", "target_price_low": 250}])),
        ("腾讯 0700.HK 跌破 380，短线偏弱可减仓。",
         aj(ticker="0700.HK", direction="bearish", action_chain=[{"action_type": "close_long", "trigger_condition": "price < 380"}]),
         aj(ticker="0700.HK", direction="bullish", action_chain=[{"action_type": "long"}])),
        ("周末无消息，下周再看。",
         aj(ticker="NONE", direction="watchlist", action_chain=[{"action_type": "watch"}]),
         aj(ticker="BABA", direction="bullish", action_chain=[{"action_type": "buy_call", "target_price_low": 90}])),
    ]
    prompt_tpl = "从以下文本提取 TradeAction（证据不足应观望，勿编造）：\n{}"
    return [{"prompt": prompt_tpl.format(t), "chosen": c, "rejected": r} for t, c, r in samples]


def run_smoke_test(model_name: str) -> None:
    """极小模型 + CPU + 2 步，跑通 DPO 训练循环。"""
    logger.info("=== SMOKE TEST: tiny model + CPU + 2 steps ===")
    dataset = smoke_dataset()
    logger.info(f"Smoke dataset: {len(dataset)} preference pairs")
    with tempfile.TemporaryDirectory() as tmp:
        train_dpo(
            dataset=dataset,
            output_dir=Path(tmp),
            model_name=model_name,
            beta=0.1,
            learning_rate=5e-5,
            batch_size=1,
            gradient_accumulation_steps=1,
            lora_r=4,
            lora_alpha=8,
            logging_steps=1,
            max_steps=2,
            cpu=True,
            max_length=256,
        )
    logger.info("=== SMOKE TEST PASSED: DPO 训练循环可运行 ===")


def main():
    parser = argparse.ArgumentParser(
        description="DPO Training for TradeAction Extraction (local TRL path)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--smoke-test", action="store_true",
                        help="极小模型 + CPU + 2 步跑通训练循环（零 GPU）")
    parser.add_argument("--data_dir", type=str, help="目录含 train.jsonl（真实训练用）")
    parser.add_argument("--output_dir", type=str, default="models/dpo_finetuned")
    parser.add_argument("--model_name", type=str, default="Qwen/Qwen2.5-14B-Instruct",
                        help="真实训练基座；smoke-test 默认改用 tiny 模型")
    parser.add_argument("--beta", type=float, default=0.01)
    parser.add_argument("--lr", type=float, default=5e-7)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--gradient_accumulation_steps", type=int, default=4)
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    args = parser.parse_args()

    if args.smoke_test:
        model = args.model_name if args.model_name != "Qwen/Qwen2.5-14B-Instruct" else SMOKE_MODEL
        run_smoke_test(model)
        return

    if not args.data_dir:
        parser.error("真实训练需 --data_dir（或用 --smoke-test）")

    dataset = load_dpo_dataset(Path(args.data_dir))
    train_dpo(
        dataset=dataset,
        output_dir=Path(args.output_dir),
        model_name=args.model_name,
        beta=args.beta,
        learning_rate=args.lr,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
    )


if __name__ == "__main__":
    main()
