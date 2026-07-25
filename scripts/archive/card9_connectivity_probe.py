"""Card #9 sanitized live connectivity probe for Qwen, MiMo, and DeepSeek."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from card8_f3_model_comparison import DEFAULT_MODEL_SPECS, _load_dotenv_defaults  # noqa: E402
from finer.llm.client import LLMClient  # noqa: E402


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _probe_one(alias: str, timeout: float) -> dict[str, Any]:
    spec = DEFAULT_MODEL_SPECS[alias]
    api_key = os.getenv(spec.api_key_env)
    result: dict[str, Any] = {
        "model_alias": alias,
        "model": spec.model,
        "base_url": spec.base_url,
        "api_key_env": spec.api_key_env,
        "api_key_present": bool(api_key),
        "temperature": 0,
        "timeout": timeout,
        "started_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "status": "not_started",
    }
    if not api_key:
        result["status"] = "missing_env"
        result["error"] = f"环境变量未配置: {spec.api_key_env}"
        return result

    client = LLMClient(
        api_key=api_key,
        base_url=spec.base_url,
        model=spec.model,
        max_tokens=spec.max_tokens,
        timeout=timeout,
        api_key_header=spec.api_key_header,
        api_key_scheme=spec.api_key_scheme,
        max_tokens_field=spec.max_tokens_field,
        extra_body=spec.extra_body,
    )
    messages = [
        {
            "role": "user",
            "content": "Return exactly this JSON object: {\"ok\":true}",
        }
    ]
    started = time.perf_counter()
    content = client.chat(
        messages,
        temperature=0,
        max_tokens=96,
        extra_body=spec.extra_body,
    )
    result["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    result["client_last_error"] = client.last_error
    result["content_chars"] = len(content) if content else 0
    result["status"] = "ok" if content else "error"
    if not content:
        result["error"] = client.last_error or "empty_response"
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["qwen", "mimo", "deepseek"],
        choices=["qwen", "mimo", "deepseek"],
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _load_dotenv_defaults()
    run_id = args.run_id or datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S")
    run_root = Path(args.data_root) / "card9_connectivity" / run_id

    rows = []
    for alias in args.models:
        row = _probe_one(alias, args.timeout)
        rows.append(row)
        _write_json(run_root / f"{alias}.json", row)
        print(
            "probe "
            f"alias={row['model_alias']} model={row['model']} base_url={row['base_url']} "
            f"api_key_env={row['api_key_env']} status={row['status']} "
            f"latency_ms={row.get('latency_ms')} content_chars={row.get('content_chars')} "
            f"error={row.get('error')}",
            flush=True,
        )

    summary = {
        "run_id": run_id,
        "trace_root": str(run_root),
        "all_ok": all(row["status"] == "ok" for row in rows),
        "rows": rows,
    }
    _write_json(run_root / "summary.json", summary)
    print(f"summary_path={run_root / 'summary.json'}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
