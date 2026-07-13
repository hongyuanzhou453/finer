"""Acceptance check for task card #5 shared foundation fixes.

Runs the real ``finer.pipeline.golden_path.run_golden_path`` entrypoint against
a minimal envelope while routing LLM traffic to a local HTTP test double via
environment configuration. This avoids external API keys without monkey-patching
the golden path, extractor, policy mapper, or timing builder.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


LLM_INTENT_OUTPUT = {
    "intents": [
        {
            "target_name": "宁德时代",
            "target_symbol": "300750.SZ",
            "target_type": "stock",
            "direction": "bullish",
            "actionability": "explicit_action",
            "position_delta_hint": "add",
            "conviction": 0.82,
            "confidence": 0.9,
            "market": "CN",
            "evidence_text": "看好宁德时代，准备加仓",
        }
    ]
}


class _LocalLLMHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)

        body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            LLM_INTENT_OUTPUT,
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def _start_local_llm() -> tuple[HTTPServer, threading.Thread]:
    server = HTTPServer(("127.0.0.1", 0), _LocalLLMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _configure_local_llm(base_url: str) -> dict[str, str | None]:
    keys = [
        "FINER_LLM_MODEL",
        "FINER_LLM_API_KEY_ENV",
        "FINER_LLM_BASE_URL",
        "CARD5_LOCAL_LLM_API_KEY",
    ]
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["FINER_LLM_MODEL"] = "card5-local-llm"
    os.environ["FINER_LLM_API_KEY_ENV"] = "CARD5_LOCAL_LLM_API_KEY"
    os.environ["FINER_LLM_BASE_URL"] = base_url
    os.environ["CARD5_LOCAL_LLM_API_KEY"] = "local-test-key"
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


def _build_minimal_envelope():
    from finer.schemas.content_envelope import BlockQuality, ContentBlock, ContentEnvelope
    from finer.schemas.quality import QualityCard
    from finer.schemas.temporal import TemporalAnchor

    published_at = datetime(2026, 3, 12, 15, 36, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    return (
        ContentEnvelope(
            envelope_id="env_card5_acceptance",
            source_type="feishu_chat",
            creator_id="card5-fixture",
            creator_name="Card5 Fixture",
            published_at=published_at,
            quality_card=QualityCard(
                readability_score=0.95,
                semantic_completeness_score=0.9,
                financial_relevance_score=0.95,
                entity_resolution_score=0.9,
                temporal_resolution_score=0.9,
                evidence_traceability_score=0.9,
            ),
            blocks=[
                ContentBlock(
                    block_id="blk_card5_001",
                    block_type="paragraph",
                    text="看好宁德时代，准备加仓",
                    order_index=0,
                    quality=BlockQuality(
                        readability=0.95,
                        extraction_confidence=0.95,
                        structural_confidence=0.9,
                        completeness=0.95,
                        noise_score=0.0,
                    ),
                )
            ],
            temporal_anchors=[
                TemporalAnchor(
                    anchor_type="effective_trade_at",
                    raw_text="发布时点即生效",
                    resolved_time=published_at,
                    confidence=1.0,
                    resolution_strategy="explicit_date",
                    timezone="Asia/Shanghai",
                )
            ],
        ),
        published_at,
    )


def main() -> int:
    from finer.llm.client import LLMClient
    from finer.pipeline.golden_path import run_golden_path
    from finer.services.quality_gate import evaluate_envelope_quality

    server, thread = _start_local_llm()
    host, port = server.server_address
    previous_env = _configure_local_llm(f"http://{host}:{port}")

    try:
        _reset_text_registry()

        client = LLMClient(model="card5-property-model")
        assert client.model == "card5-property-model"
        print(f"AS-5a PASS client.model={client.model}")

        envelope, published_at = _build_minimal_envelope()
        gate = evaluate_envelope_quality(envelope)
        assert gate.status != "reject"
        print(f"AS-5b PASS quality_gate_status={gate.status} score={gate.score:.3f}")

        with tempfile.TemporaryDirectory(prefix="card5-golden-path-") as data_root:
            gp_result = run_golden_path(envelope, data_root=Path(data_root))
            trade_action = gp_result.primary_action

        timing = trade_action.execution_timing
        assert timing is not None
        assert timing.intent_published_at == published_at
        assert timing.intent_effective_at == published_at
        assert timing.action_decision_at == published_at

        diagnostic_date = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        clocks = {
            "intent_published_at": timing.intent_published_at,
            "intent_effective_at": timing.intent_effective_at,
            "action_decision_at": timing.action_decision_at,
            "action_executable_at": timing.action_executable_at,
        }
        assert all(value.date() != diagnostic_date for value in clocks.values())

        print("AS-5c PASS execution_timing")
        for name, value in clocks.items():
            print(f"  {name}={value.isoformat()}")
        print(f"  diagnostic_run_date={diagnostic_date.isoformat()}")

        assert trade_action.canonical_trace_status == "canonical"
        print(
            "AS-5d PASS run_golden_path completed without monkey-patching "
            f"action_count={gp_result.action_count} "
            f"trade_action_id={trade_action.trade_action_id}"
        )
    finally:
        _restore_env(previous_env)
        _reset_text_registry()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
