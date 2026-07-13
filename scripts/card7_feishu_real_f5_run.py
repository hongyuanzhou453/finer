"""Card #7 acceptance runner for the clean Feishu F0-only import path.

The script imports a small set of real exported Feishu messages, freezes a raw
pack manifest, routes each record through F1, and runs the canonical golden
path to F5.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

SOURCE_TRANSCRIPT = (
    REPO_ROOT
    / "data/raw/maodaren/transcripts/chat_history_20260312_1434_to_20260420_1919.md"
)
CHAT_ID = "oc_6ff7bde4c69b7ca19f3a2f7fda426885"
CHAT_NAME = "猫大人会员内容体验同步-4.27截止"
SENDER_ID = "ou_4b89fb1c91dee0c54ae4a2bb1643aaa9"
PROOF_TIMESTAMP = "2026-03-12 15:36:00"


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


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


def _fixture_intent_for_prompt(prompt: str) -> dict[str, Any]:
    if "绿电" in prompt:
        return {
            "target_name": "绿电",
            "target_symbol": None,
            "target_type": "sector",
            "direction": "bearish",
            "actionability": "explicit_action",
            "position_delta_hint": "reduce",
            "conviction": 0.78,
            "confidence": 0.86,
            "market": "CN",
            "evidence_text": "涨多了该卖就卖就好",
            "time_horizon": "short_term",
        }
    if "阿特斯" in prompt:
        return {
            "target_name": "阿特斯",
            "target_symbol": "688472.SH",
            "target_type": "stock",
            "direction": "bullish",
            "actionability": "explicit_action",
            "position_delta_hint": "open",
            "conviction": 0.82,
            "confidence": 0.88,
            "market": "CN",
            "evidence_text": "15元以下都是还不错的入场机会",
            "time_horizon": "medium_term",
        }
    if "腾讯音乐" in prompt:
        return {
            "target_name": "腾讯音乐",
            "target_symbol": "TME",
            "target_type": "stock",
            "direction": "bullish",
            "actionability": "explicit_action",
            "position_delta_hint": "open",
            "conviction": 0.72,
            "confidence": 0.84,
            "market": "US",
            "evidence_text": "我觉得埋伏没问题",
            "time_horizon": "short_term",
        }
    if "黄金股" in prompt:
        return {
            "target_name": "黄金股",
            "target_symbol": None,
            "target_type": "sector",
            "direction": "bullish",
            "actionability": "explicit_action",
            "position_delta_hint": "hold",
            "conviction": 0.76,
            "confidence": 0.82,
            "market": "CN",
            "evidence_text": "并不会构成我减仓的理由",
            "time_horizon": "medium_term",
        }
    return {
        "target_name": "unknown",
        "target_symbol": None,
        "target_type": "sector",
        "direction": "neutral",
        "actionability": "watch",
        "position_delta_hint": "none",
        "conviction": 0.5,
        "confidence": 0.6,
        "market": "CN",
        "evidence_text": "",
        "time_horizon": "unknown",
    }


class _LocalLLMHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request_body = self.rfile.read(length)
        try:
            request_json = json.loads(request_body.decode("utf-8"))
            prompt = json.dumps(request_json.get("messages", []), ensure_ascii=False)
        except Exception:
            prompt = request_body.decode("utf-8", errors="ignore")

        llm_payload = {"intents": [_fixture_intent_for_prompt(prompt)]}
        body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(llm_payload, ensure_ascii=False)
                    }
                }
            ]
        }
        response = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        return


def _start_local_llm() -> tuple[HTTPServer, threading.Thread]:
    server = HTTPServer(("127.0.0.1", 0), _LocalLLMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _configure_fixture_llm(base_url: str) -> dict[str, str | None]:
    keys = [
        "FINER_LLM_MODEL",
        "FINER_LLM_API_KEY_ENV",
        "FINER_LLM_BASE_URL",
        "FINER_LLM_API_KEY_HEADER",
        "FINER_LLM_API_KEY_SCHEME",
        "FINER_LLM_MAX_TOKENS_FIELD",
        "FINER_LLM_MAX_TOKENS",
        "FINER_LLM_EXTRA_BODY_JSON",
        "CARD7_LOCAL_LLM_API_KEY",
    ]
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["FINER_LLM_MODEL"] = "card7-local-llm"
    os.environ["FINER_LLM_API_KEY_ENV"] = "CARD7_LOCAL_LLM_API_KEY"
    os.environ["FINER_LLM_BASE_URL"] = base_url
    os.environ["CARD7_LOCAL_LLM_API_KEY"] = "local-test-key"
    return previous


def _model_alias_config(alias: str) -> dict[str, str]:
    configs = {
        "qwen": {
            "model": "qwen-plus",
            "api_key_env": "DASHSCOPE_API_KEY",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key_header": "Authorization",
            "api_key_scheme": "Bearer",
            "max_tokens_field": "max_tokens",
            "max_tokens": "4096",
        },
        "mimo": {
            "model": "mimo-v2.5-pro",
            "api_key_env": "MIMO_API_KEY",
            "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
            "api_key_header": "api-key",
            "api_key_scheme": "",
            "max_tokens_field": "max_completion_tokens",
            "max_tokens": "8192",
        },
        "deepseek": {
            "model": "deepseek-chat",
            "api_key_env": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com",
            "api_key_header": "Authorization",
            "api_key_scheme": "Bearer",
            "max_tokens_field": "max_tokens",
            "max_tokens": "8192",
        },
    }
    return configs[alias]


def _configure_real_llm(args: argparse.Namespace) -> dict[str, str | None]:
    keys = [
        "FINER_LLM_MODEL",
        "FINER_LLM_API_KEY_ENV",
        "FINER_LLM_BASE_URL",
        "FINER_LLM_API_KEY_HEADER",
        "FINER_LLM_API_KEY_SCHEME",
        "FINER_LLM_MAX_TOKENS_FIELD",
        "FINER_LLM_MAX_TOKENS",
        "FINER_LLM_EXTRA_BODY_JSON",
    ]
    previous = {key: os.environ.get(key) for key in keys}
    config = _model_alias_config(args.model_alias) if args.model_alias else {}
    model = args.model or config.get("model")
    api_key_env = args.api_key_env or config.get("api_key_env")
    base_url = args.base_url or config.get("base_url")
    api_key_header = args.api_key_header or config.get("api_key_header")
    api_key_scheme = args.api_key_scheme
    if api_key_scheme is None:
        api_key_scheme = config.get("api_key_scheme")
    max_tokens_field = args.max_tokens_field or config.get("max_tokens_field")
    max_tokens = str(args.max_tokens) if args.max_tokens else config.get("max_tokens")

    if model:
        os.environ["FINER_LLM_MODEL"] = model
    if api_key_env:
        os.environ["FINER_LLM_API_KEY_ENV"] = api_key_env
    if base_url:
        os.environ["FINER_LLM_BASE_URL"] = base_url
    if api_key_header:
        os.environ["FINER_LLM_API_KEY_HEADER"] = api_key_header
    if api_key_scheme is not None:
        os.environ["FINER_LLM_API_KEY_SCHEME"] = api_key_scheme
    if max_tokens_field:
        os.environ["FINER_LLM_MAX_TOKENS_FIELD"] = max_tokens_field
    if max_tokens:
        os.environ["FINER_LLM_MAX_TOKENS"] = max_tokens
    return previous


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _reset_text_registry() -> None:
    import finer.model_config as model_config

    model_config._text_registry = None


def _selections():
    from finer.ingestion.feishu_f0_importer import FeishuMessageSelection

    return [
        FeishuMessageSelection(PROOF_TIMESTAMP, SENDER_ID, "text"),
        FeishuMessageSelection("2026-03-12 16:43:00", SENDER_ID, "text"),
        FeishuMessageSelection("2026-03-12 19:51:00", SENDER_ID, "text"),
        FeishuMessageSelection("2026-03-13 18:14:00", SENDER_ID, "text"),
    ]


def _run_card7(args: argparse.Namespace) -> int:
    from finer.ingestion.feishu_f0_importer import (
        BEIJING_TZ,
        freeze_feishu_f0_pack,
        import_feishu_transcript,
    )
    from finer.parsing.standardization_router import StandardizationRouter
    from finer.pipeline.golden_path import run_golden_path

    data_root = Path(args.data_root)
    run_id = args.run_id or datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%dT%H%M%S")
    trace_root = data_root / "card7_feishu_real_f5" / run_id
    pack_dir = data_root / "packs" / "maodaren" / f"feishu_f0_real_{run_id}"

    result = import_feishu_transcript(
        source_path=Path(args.source),
        selections=_selections(),
        chat_id=CHAT_ID,
        chat_name=CHAT_NAME,
        data_root=data_root,
    )
    manifest_path = freeze_feishu_f0_pack(result=result, pack_dir=pack_dir)

    router = StandardizationRouter()
    traces: list[dict[str, Any]] = []
    proof_ok = False
    non_fallback_ok = True
    total_f1_block_count = 0
    total_meaningful_chat_blocks = 0
    friday_observation: dict[str, Any] | None = None

    for item in result.items:
        record = item.content_record
        item_trace_dir = trace_root / record.content_id
        envelope, f1_report = router.route(record, item.raw_slice_path)
        fallback_blocks = [
            block.text
            for block in envelope.blocks
            if block.text.startswith("[Standardization fallback:")
        ]
        non_fallback_ok = non_fallback_ok and not fallback_blocks
        total_f1_block_count += len(envelope.blocks)
        total_meaningful_chat_blocks += sum(
            1
            for block in envelope.blocks
            if block.block_type == "chat_message"
            and not block.text.startswith("[Standardization fallback:")
        )

        _write_json(item_trace_dir / "F1_envelope.json", envelope.model_dump(mode="json"))
        _write_json(item_trace_dir / "F1_report.json", f1_report)

        trace_entry: dict[str, Any] = {
            "content_id": record.content_id,
            "record_path": item.record_path,
            "raw_slice_path": item.raw_slice_path,
            "published_at": record.published_at,
            "timestamp_source": record.metadata.get("timestamp_source"),
            "f1_adapter": f1_report["adapter"],
            "f1_block_count": f1_report["block_count"],
            "f1_blocks": [
                {
                    "block_id": block.block_id,
                    "block_type": block.block_type,
                    "timestamp": block.timestamp,
                    "speaker": block.speaker,
                    "text": block.text,
                    "metadata": block.metadata,
                }
                for block in envelope.blocks
            ],
            "f1_fallback_blocks": fallback_blocks,
        }

        try:
            gp_result = run_golden_path(envelope, data_root=item_trace_dir)
            action = gp_result.primary_action
            _write_json(item_trace_dir / "F5_trade_action.json", action.model_dump(mode="json"))
            timing = action.execution_timing
            trace_entry["f5_status"] = "ok"
            trace_entry["f5_action_count"] = gp_result.action_count
            trace_entry["trade_action"] = action.model_dump(mode="json")
            trace_entry["trade_actions"] = [
                a.model_dump(mode="json") for a in gp_result.trade_actions
            ]
            trace_entry["execution_timing"] = timing.model_dump(mode="json") if timing else None

            if (
                record.published_at
                and record.published_at.astimezone(BEIJING_TZ)
                == datetime(2026, 3, 12, 15, 36, 0, tzinfo=BEIJING_TZ)
                and timing
                and timing.intent_published_at.astimezone(BEIJING_TZ)
                == record.published_at.astimezone(BEIJING_TZ)
            ):
                proof_ok = True

            if (
                record.published_at
                and record.published_at.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
                == "2026-03-13 18:14:00"
                and timing
            ):
                friday_observation = {
                    "market": timing.market,
                    "intent_published_at": timing.intent_published_at,
                    "action_executable_at": timing.action_executable_at,
                    "execution_delay_reason": timing.execution_delay_reason,
                }
        except Exception as exc:
            trace_entry["f5_status"] = "error"
            trace_entry["f5_error"] = f"{type(exc).__name__}: {exc}"

        _write_json(item_trace_dir / "trace.json", trace_entry)
        traces.append(trace_entry)

    summary = {
        "run_id": run_id,
        "llm_mode": args.llm_mode,
        "source": str(Path(args.source)),
        "manifest_path": str(manifest_path),
        "trace_root": str(trace_root),
        "item_count": len(result.items),
        "as_3a_any_f5_action": any(t.get("f5_status") == "ok" for t in traces),
        "as_3b_proof_timestamp_preserved": proof_ok,
        "as_3c_non_fallback_f1": non_fallback_ok,
        "total_f1_block_count": total_f1_block_count,
        "total_meaningful_chat_blocks": total_meaningful_chat_blocks,
        "friday_observation": friday_observation,
        "traces": traces,
    }
    _write_json(trace_root / "summary.json", summary)

    print(f"manifest_path={manifest_path}")
    print(f"trace_root={trace_root}")
    print(f"AS-3a any_f5_action={summary['as_3a_any_f5_action']}")
    print(f"AS-3b proof_timestamp_preserved={proof_ok}")
    print(
        "AS-3c non_fallback_f1="
        f"{non_fallback_ok} total_blocks={total_f1_block_count} "
        f"chat_blocks={total_meaningful_chat_blocks}"
    )
    if friday_observation:
        print(
            "friday_observation="
            + json.dumps(friday_observation, ensure_ascii=False, default=_json_default)
        )

    return 0 if summary["as_3a_any_f5_action"] and proof_ok and non_fallback_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(SOURCE_TRANSCRIPT))
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--llm-mode",
        choices=("real", "fixture"),
        default="real",
        help="real uses configured model env; fixture uses a local HTTP endpoint via env config.",
    )
    parser.add_argument("--model-alias", choices=("qwen", "mimo", "deepseek"), default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-header", default=None)
    parser.add_argument("--api-key-scheme", default=None)
    parser.add_argument("--max-tokens-field", default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    args = parser.parse_args()

    _load_dotenv_defaults()
    server: HTTPServer | None = None
    thread: threading.Thread | None = None
    previous_env: dict[str, str | None] | None = None
    if args.llm_mode == "fixture":
        server, thread = _start_local_llm()
        host, port = server.server_address
        previous_env = _configure_fixture_llm(f"http://{host}:{port}")
        _reset_text_registry()
    elif any(
        [
            args.model_alias,
            args.model,
            args.api_key_env,
            args.base_url,
            args.api_key_header,
            args.api_key_scheme is not None,
            args.max_tokens_field,
            args.max_tokens,
        ]
    ):
        previous_env = _configure_real_llm(args)
        _reset_text_registry()
        print(
            "real_llm_config "
            f"model={os.environ.get('FINER_LLM_MODEL')} "
            f"base_url={os.environ.get('FINER_LLM_BASE_URL')} "
            f"api_key_env={os.environ.get('FINER_LLM_API_KEY_ENV')}"
        )

    try:
        return _run_card7(args)
    finally:
        if previous_env is not None:
            _restore_env(previous_env)
            _reset_text_registry()
        if server is not None and thread is not None:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
