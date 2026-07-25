"""Card #8 F3 real-model comparison harness.

Runs the same four real Feishu ContentRecords from card #7 through F1 and then
through F3 with one selected text model at a time. The harness keeps the F3
prompt, F1 chat_message blocks, and temperature constant; only the model spec
changes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from card7_feishu_real_f5_run import (  # noqa: E402
    CHAT_ID,
    CHAT_NAME,
    SENDER_ID,
    SOURCE_TRANSCRIPT,
    _json_default,
    _selections,
    _write_json,
)
from finer.extraction.intent_extractor import LLMIntentExtractor  # noqa: E402
from finer.llm.client import LLMClient  # noqa: E402
from finer.parsing.standardization_router import StandardizationRouter  # noqa: E402
from finer.prompts.registry import PromptRegistry  # noqa: E402


MODEL_ALIASES = ("qwen", "mimo", "deepseek")


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    model: str
    api_key_env: str
    base_url: str
    api_key_header: str = "Authorization"
    api_key_scheme: str | None = "Bearer"
    max_tokens_field: str = "max_tokens"
    max_tokens: int = 4096
    timeout: float = 90.0
    extra_body: dict[str, Any] | None = None


DEFAULT_MODEL_SPECS: dict[str, ModelSpec] = {
    "qwen": ModelSpec(
        alias="qwen",
        model="qwen-plus",
        api_key_env="DASHSCOPE_API_KEY",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    "mimo": ModelSpec(
        alias="mimo",
        model="mimo-v2.5-pro",
        api_key_env="MIMO_API_KEY",
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        api_key_header="api-key",
        api_key_scheme=None,
        max_tokens_field="max_completion_tokens",
        max_tokens=8192,
        extra_body={"stream": False, "thinking": {"type": "disabled"}},
    ),
    "deepseek": ModelSpec(
        alias="deepseek",
        model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        max_tokens=8192,
    ),
}


OBVIOUS_TARGET_HINTS = {
    "绿电": {"names": {"绿电"}, "symbols": set(), "type": "sector"},
    "阿特斯": {"names": {"阿特斯"}, "symbols": {"688472.SH"}, "type": "stock"},
    "腾讯音乐": {"names": {"腾讯音乐"}, "symbols": {"TME"}, "type": "stock"},
    "黄金股": {"names": {"黄金股"}, "symbols": set(), "type": "sector"},
}


def _load_dotenv_defaults(path: Path = REPO_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _clean_json_text(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = [line for line in cleaned.splitlines() if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    return cleaned


class SingleModelJsonRouter:
    """Minimal router interface for LLMIntentExtractor.call_json()."""

    def __init__(self, spec: ModelSpec):
        self.spec = spec
        self.calls: list[dict[str, Any]] = []

    def call_json(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_model: Any | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        task_type: str = "text",
    ) -> dict[str, Any] | None:
        del response_model, task_type
        api_key = os.getenv(self.spec.api_key_env)
        call: dict[str, Any] = {
            "model_alias": self.spec.alias,
            "model": self.spec.model,
            "base_url": self.spec.base_url,
            "api_key_env": self.spec.api_key_env,
            "api_key_present": bool(api_key),
            "temperature": temperature,
            "max_tokens": max_tokens or self.spec.max_tokens,
            "started_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        self.calls.append(call)
        if not api_key:
            call["error"] = f"missing_api_key_env:{self.spec.api_key_env}"
            return None

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        client = LLMClient(
            api_key=api_key,
            base_url=self.spec.base_url,
            model=self.spec.model,
            max_tokens=self.spec.max_tokens,
            timeout=self.spec.timeout,
            api_key_header=self.spec.api_key_header,
            api_key_scheme=self.spec.api_key_scheme,
            max_tokens_field=self.spec.max_tokens_field,
            extra_body=self.spec.extra_body,
        )
        start = time.perf_counter()
        raw = client.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens or self.spec.max_tokens,
            extra_body=self.spec.extra_body,
        )
        call["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        call["client_last_error"] = client.last_error
        if raw is None:
            call["error"] = client.last_error or "empty_response"
            return None
        call["raw_response_chars"] = len(raw)
        try:
            parsed = json.loads(_clean_json_text(raw))
        except json.JSONDecodeError as exc:
            call["error"] = f"json_decode_error:{exc}"
            return None
        intents = parsed.get("intents") if isinstance(parsed, dict) else None
        call["parsed_intent_count"] = len(intents) if isinstance(intents, list) else None
        return parsed


def _stable_intent_dump(result_dump: dict[str, Any]) -> list[dict[str, Any]]:
    stable = []
    spans_by_id = {
        span["evidence_span_id"]: {
            "block_id": span["block_id"],
            "char_start": span["char_start"],
            "char_end": span["char_end"],
            "text": span["text"],
            "span_type": span.get("span_type"),
        }
        for span in result_dump.get("evidence_spans", [])
    }
    for intent in result_dump.get("intents", []):
        stable.append(
            {
                "target_name": intent.get("target_name"),
                "target_symbol": intent.get("target_symbol"),
                "target_type": intent.get("target_type"),
                "market": intent.get("market"),
                "direction": intent.get("direction"),
                "actionability": intent.get("actionability"),
                "position_delta_hint": intent.get("position_delta_hint"),
                "conviction": round(float(intent.get("conviction", 0)), 4),
                "confidence": round(float(intent.get("confidence", 0)), 4),
                "time_horizon_hint": intent.get("time_horizon_hint"),
                "ambiguity_flags": sorted(intent.get("ambiguity_flags", [])),
                "evidence": [
                    spans_by_id.get(span_id, {"missing_span_id": span_id})
                    for span_id in intent.get("evidence_span_ids", [])
                ],
            }
        )
    return sorted(stable, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _expected_hint(text: str) -> dict[str, Any]:
    for marker, hint in OBVIOUS_TARGET_HINTS.items():
        if marker in text:
            return {"marker": marker, **hint}
    return {"marker": "unknown", "names": set(), "symbols": set(), "type": "unknown"}


def _ticker_issues(result_dump: dict[str, Any], text: str) -> list[str]:
    hint = _expected_hint(text)
    names = [intent.get("target_name") for intent in result_dump.get("intents", [])]
    symbols = [
        intent.get("target_symbol")
        for intent in result_dump.get("intents", [])
        if intent.get("target_symbol")
    ]
    issues: list[str] = []
    if len(names) != len(set(names)):
        issues.append("duplicate_target_name")
    if len(symbols) != len(set(symbols)):
        issues.append("duplicate_target_symbol")
    expected_names = hint["names"]
    expected_symbols = hint["symbols"]
    if expected_names and not (set(names) & expected_names):
        issues.append(f"missing_obvious_target:{hint['marker']}")
    if expected_symbols and not (set(symbols) & expected_symbols):
        issues.append(f"missing_obvious_symbol:{','.join(sorted(expected_symbols))}")
    if expected_symbols and any(symbol not in expected_symbols for symbol in symbols):
        issues.append(f"unexpected_symbol:{','.join(sorted(set(symbols) - expected_symbols))}")
    if not expected_symbols and symbols:
        issues.append(f"unexpected_symbol_for_sector:{','.join(sorted(set(symbols)))}")
    if any(name in (None, "", "unknown") for name in names):
        issues.append("unknown_target_name")
    return issues


def _summarize_result(
    result_dump: dict[str, Any],
    text: str,
    call: dict[str, Any] | None,
) -> dict[str, Any]:
    spans = result_dump.get("evidence_spans", [])
    exact_spans = [span for span in spans if span.get("span_type") != "block_level"]
    fallback_spans = [span for span in spans if span.get("span_type") == "block_level"]
    notes = result_dump.get("processing_notes", [])
    schema_errors = [note for note in notes if "failed to construct" in note]
    ticker_issues = _ticker_issues(result_dump, text)
    return {
        "intent_count": len(result_dump.get("intents", [])),
        "valid_intent": bool(result_dump.get("intents")) and not schema_errors,
        "schema_error_count": len(schema_errors),
        "schema_errors": schema_errors,
        "evidence_span_count": len(spans),
        "exact_keyword_span_count": len(exact_spans),
        "block_level_fallback_count": len(fallback_spans),
        "grounding_mode": (
            "exact_keyword"
            if exact_spans and not fallback_spans
            else "mixed"
            if exact_spans and fallback_spans
            else "block_level_fallback"
            if fallback_spans
            else "none"
        ),
        "ticker_issue_count": len(ticker_issues),
        "ticker_issues": ticker_issues,
        "latency_ms": call.get("latency_ms") if call else None,
        "model_error": call.get("error") if call else None,
        "stable_dump": _stable_intent_dump(result_dump),
    }


def _prepare_envelopes(args: argparse.Namespace, run_root: Path) -> list[dict[str, Any]]:
    from finer.ingestion.feishu_f0_importer import import_feishu_transcript

    result = import_feishu_transcript(
        source_path=Path(args.source),
        selections=_selections(),
        chat_id=CHAT_ID,
        chat_name=CHAT_NAME,
        data_root=Path(args.data_root),
    )
    router = StandardizationRouter()
    prepared: list[dict[str, Any]] = []
    for item in result.items:
        record = item.content_record
        envelope, f1_report = router.route(record, item.raw_slice_path)
        item_root = run_root / "inputs" / record.content_id
        _write_json(item_root / "F0_content_record.json", record.model_dump(mode="json"))
        _write_json(item_root / "F1_envelope.json", envelope.model_dump(mode="json"))
        _write_json(item_root / "F1_report.json", f1_report)
        text = "\n\n".join(
            block.text
            for block in envelope.blocks
            if block.block_type == "chat_message"
            and not block.text.startswith("[Standardization fallback:")
        )
        prepared.append(
            {
                "content_id": record.content_id,
                "published_at": record.published_at,
                "raw_slice_path": str(item.raw_slice_path),
                "record_path": str(item.record_path),
                "envelope": envelope,
                "f1_chat_text": text,
                "f1_block_count": len(envelope.blocks),
                "expected_hint": _expected_hint(text),
            }
        )
    return prepared


def _run_one_model(
    spec: ModelSpec,
    prepared: list[dict[str, Any]],
    run_root: Path,
    repeats: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for repeat_index in range(1, repeats + 1):
        for item in prepared:
            router = SingleModelJsonRouter(spec)
            extractor = LLMIntentExtractor(
                router=router,  # type: ignore[arg-type]
                prompt_registry=PromptRegistry(),
                extractor_version=f"llm_v1_card8_{spec.alias}",
                temperature=0,
            )
            result = extractor.extract(item["envelope"])
            result_dump = result.model_dump(mode="json")
            call = router.calls[-1] if router.calls else None
            summary = _summarize_result(result_dump, item["f1_chat_text"], call)
            artifact_dir = (
                run_root
                / "models"
                / spec.alias
                / f"run_{repeat_index}"
                / item["content_id"]
            )
            _write_json(artifact_dir / "F3_result.json", result_dump)
            _write_json(artifact_dir / "model_call.json", call or {})
            _write_json(artifact_dir / "summary.json", summary)
            rows.append(
                {
                    "model_alias": spec.alias,
                    "model": spec.model,
                    "repeat": repeat_index,
                    "content_id": item["content_id"],
                    "published_at": item["published_at"],
                    "expected_hint": item["expected_hint"],
                    "artifact_dir": str(artifact_dir),
                    "result": result_dump,
                    "call": call,
                    "summary": summary,
                }
            )
            print(
                "F3 "
                f"model={spec.alias}:{spec.model} temp=0 "
                f"repeat={repeat_index} content_id={item['content_id']} "
                f"intents={summary['intent_count']} grounding={summary['grounding_mode']} "
                f"latency_ms={summary['latency_ms']} error={summary['model_error']}"
                ,
                flush=True,
            )
    return rows


def _determinism_by_model_content(rows: list[dict[str, Any]]) -> dict[tuple[str, str], bool]:
    grouped: dict[tuple[str, str], list[list[dict[str, Any]]]] = {}
    for row in rows:
        key = (row["model_alias"], row["content_id"])
        grouped.setdefault(key, []).append(row["summary"]["stable_dump"])
    return {key: len(values) >= 2 and values[0] == values[1] for key, values in grouped.items()}


def _aggregate_model_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    determinism = _determinism_by_model_content(rows)
    aggregates = []
    for alias in MODEL_ALIASES:
        model_rows = [row for row in rows if row["model_alias"] == alias]
        if not model_rows:
            continue
        span_total = sum(row["summary"]["evidence_span_count"] for row in model_rows)
        exact_total = sum(row["summary"]["exact_keyword_span_count"] for row in model_rows)
        schema_errors = sum(row["summary"]["schema_error_count"] for row in model_rows)
        ticker_errors = sum(row["summary"]["ticker_issue_count"] for row in model_rows)
        latencies = [
            row["summary"]["latency_ms"]
            for row in model_rows
            if row["summary"]["latency_ms"] is not None
        ]
        det_values = [
            value for (model_alias, _), value in determinism.items() if model_alias == alias
        ]
        aggregates.append(
            {
                "model_alias": alias,
                "model": model_rows[0]["model"],
                "runs": len(model_rows),
                "span_grounding_rate": round(exact_total / span_total, 4) if span_total else 0,
                "schema_error_count": schema_errors,
                "ticker_issue_count": ticker_errors,
                "deterministic_content_count": sum(1 for value in det_values if value),
                "content_count": len(det_values),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
            }
        )
    return aggregates


def _format_intents(result: dict[str, Any]) -> str:
    pieces = []
    spans_by_id = {
        span["evidence_span_id"]: span for span in result.get("evidence_spans", [])
    }
    for intent in result.get("intents", []):
        span_modes = [
            (spans_by_id.get(span_id, {}).get("span_type") or "unknown")
            for span_id in intent.get("evidence_span_ids", [])
        ]
        pieces.append(
            "{name}/{symbol} {direction} {actionability} {hint} "
            "conv={conviction} evidence={evidence}".format(
                name=intent.get("target_name"),
                symbol=intent.get("target_symbol"),
                direction=intent.get("direction"),
                actionability=intent.get("actionability"),
                hint=intent.get("position_delta_hint"),
                conviction=intent.get("conviction"),
                evidence=",".join(span_modes) or "none",
            )
        )
    return "<br>".join(pieces) if pieces else "no valid intent"


def _write_report(
    run_id: str,
    run_root: Path,
    rows: list[dict[str, Any]],
    prepared: list[dict[str, Any]],
    report_path: Path | None = None,
) -> Path:
    report_path = report_path or REPO_ROOT / "docs/specs/2026-06-03-card8-f3-model-comparison.md"
    aggregates = _aggregate_model_rows(rows)
    determinism = _determinism_by_model_content(rows)
    lines = [
        "# Card #8 F3 real-model comparison",
        "",
        "## Scope note",
        "",
        "This is a qualitative selection aid, not a benchmark: N=4 real Feishu messages, no gold labels, and ticker checks are limited to obvious target hints in the source text.",
        "",
        "## Run config",
        "",
        f"- run_id: `{run_id}`",
        f"- trace_root: `{run_root}`",
        "- pipeline: card #7 Feishu importer -> F1 StandardizationRouter -> F3 LLMIntentExtractor",
        "- golden_path only for the later selected-model F5 run; no orchestrator",
        "- F3 prompt: existing `src/finer/prompts/f3_intent_extraction/{system,user}.j2`",
        "- temperature: `0` for every model and every repeat",
        "- repeats: `2` per model per message",
        "",
        "## Objective table",
        "",
        "| Model | Runs | Span grounding rate | Schema errors | Ticker issues | Determinism | Avg latency ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for agg in aggregates:
        lines.append(
            "| {model_alias} (`{model}`) | {runs} | {span_grounding_rate:.2%} | "
            "{schema_error_count} | {ticker_issue_count} | "
            "{deterministic_content_count}/{content_count} | {avg_latency_ms} |".format(**agg)
        )

    lines.extend(["", "## Per-message side-by-side", ""])
    for item in prepared:
        lines.extend(
            [
                f"### {item['content_id']}",
                "",
                f"- published_at: `{_json_default(item['published_at'])}`",
                f"- obvious target hint: `{item['expected_hint']['marker']}`",
                "",
                "| Model | Run 1 | Run 2 | Deterministic | Reviewer judgment |",
                "|---|---|---|---:|---|",
            ]
        )
        for alias in MODEL_ALIASES:
            model_rows = [
                row
                for row in rows
                if row["model_alias"] == alias and row["content_id"] == item["content_id"]
            ]
            by_repeat = {row["repeat"]: row for row in model_rows}
            run1 = by_repeat.get(1)
            run2 = by_repeat.get(2)
            lines.append(
                "| {alias} | {run1} | {run2} | {det} |  |".format(
                    alias=alias,
                    run1=_format_intents(run1["result"]) if run1 else "missing",
                    run2=_format_intents(run2["result"]) if run2 else "missing",
                    det="yes" if determinism.get((alias, item["content_id"])) else "no",
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Evidence files",
            "",
            f"- Intent dumps and model-call logs: `{run_root / 'models'}`",
            f"- Shared F0/F1 inputs: `{run_root / 'inputs'}`",
            "",
            "## Reviewer notes",
            "",
            "- Selection rule should prioritize valid schema, exact keyword grounding over block-level fallback, no obvious ticker errors, deterministic repeats, then latency.",
            "- Fill the `Reviewer judgment` column before treating this as the first annotation batch.",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(SOURCE_TRANSCRIPT))
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--models", nargs="+", default=list(MODEL_ALIASES), choices=MODEL_ALIASES)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--qwen-model", default=DEFAULT_MODEL_SPECS["qwen"].model)
    parser.add_argument("--mimo-model", default=DEFAULT_MODEL_SPECS["mimo"].model)
    parser.add_argument("--deepseek-model", default=DEFAULT_MODEL_SPECS["deepseek"].model)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--artifact-dir-name", default="card8_f3_model_comparison")
    parser.add_argument(
        "--report-path",
        default="docs/specs/2026-06-03-card8-f3-model-comparison.md",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _load_dotenv_defaults()
    run_id = args.run_id or datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S")
    run_root = Path(args.data_root) / args.artifact_dir_name / run_id

    specs = dict(DEFAULT_MODEL_SPECS)
    specs["qwen"] = ModelSpec(
        **{**specs["qwen"].__dict__, "model": args.qwen_model, "timeout": args.timeout}
    )
    specs["mimo"] = ModelSpec(
        **{**specs["mimo"].__dict__, "model": args.mimo_model, "timeout": args.timeout}
    )
    specs["deepseek"] = ModelSpec(
        **{**specs["deepseek"].__dict__, "model": args.deepseek_model, "timeout": args.timeout}
    )

    print(f"run_id={run_id}")
    print(f"trace_root={run_root}")
    for alias in args.models:
        spec = specs[alias]
        print(
            f"configured_model alias={alias} model={spec.model} "
            f"base_url={spec.base_url} api_key_env={spec.api_key_env} "
            f"temperature=0 timeout={spec.timeout}"
            ,
            flush=True,
        )

    prepared = _prepare_envelopes(args, run_root)
    rows: list[dict[str, Any]] = []
    for alias in args.models:
        rows.extend(_run_one_model(specs[alias], prepared, run_root, args.repeats))

    summary = {
        "run_id": run_id,
        "trace_root": str(run_root),
        "models": [specs[alias].__dict__ for alias in args.models],
        "aggregates": _aggregate_model_rows(rows),
        "rows": [
            {
                key: value
                for key, value in row.items()
                if key not in {"result", "call"}
            }
            for row in rows
        ],
    }
    _write_json(run_root / "summary.json", summary)
    report_path = _write_report(run_id, run_root, rows, prepared, REPO_ROOT / args.report_path)
    print(f"summary_path={run_root / 'summary.json'}")
    print(f"report_path={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
