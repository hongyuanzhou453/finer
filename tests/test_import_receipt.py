"""Contract tests for the unified F0 ImportReceipt (GATE freeze)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from finer.schemas.import_receipt import (
    ImportErrorEnvelope,
    ImportReceipt,
)

# Columns the Import Console reads from import_runs (must match f0_index route).
_IMPORT_RUN_COLUMNS = {
    "run_id",
    "source_channel",
    "started_at",
    "finished_at",
    "status",
    "records_created",
    "records_skipped",
    "error_code",
    "error_message",
    "request_id",
    "retryable",
    "fix_hint",
}

# Field-name substrings that must never appear anywhere in a serialized receipt.
_FORBIDDEN_KEY_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "cookie",
    "authorization",
    "api_key",
)


def _success_receipt(**overrides) -> ImportReceipt:
    defaults = dict(
        run_id="run_abc",
        request_id="req_abc",
        source_channel="wechat_channels",
        source_kind="wechat_channels_video",
        status="completed",
        content_id="cnt_001",
        external_source_id="export_xyz",
        dedupe_fingerprint="fp_123",
        started_at=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 10, 0, 5, tzinfo=timezone.utc),
        raw_sha256={"video": "a" * 64, "profile": "b" * 64},
        raw_paths={"video": "data/raw/wechat/v.mp4", "profile": "data/raw/wechat/p.json"},
        record_path="data/F0_intake/wechat/cnt_001.json",
        records_created=1,
        records_skipped=0,
    )
    defaults.update(overrides)
    return ImportReceipt(**defaults)


# ---------------------------------------------------------------------------
# 1. Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_roundtrip(self) -> None:
        receipt = _success_receipt()
        data = receipt.model_dump()
        restored = ImportReceipt.model_validate(data)
        assert restored.run_id == "run_abc"
        assert restored.content_id == "cnt_001"
        assert restored.source_channel == "wechat_channels"
        assert restored.stage == "F0"
        assert restored.records_created == 1

    def test_json_roundtrip(self) -> None:
        receipt = _success_receipt()
        restored = ImportReceipt.model_validate_json(receipt.model_dump_json())
        assert restored.dedupe_fingerprint == "fp_123"
        assert restored.raw_sha256["video"] == "a" * 64

    def test_stage_is_always_f0(self) -> None:
        assert _success_receipt().stage == "F0"

    def test_defaults_are_aware_utc(self) -> None:
        receipt = ImportReceipt(
            run_id="r", source_channel="feishu", source_kind="feishu_chat", status="running"
        )
        assert receipt.started_at.tzinfo is not None
        assert receipt.collected_at.tzinfo is not None

    def test_naive_timestamp_coerced_to_aware(self) -> None:
        receipt = _success_receipt(
            started_at=datetime(2026, 6, 1, 10, 0, 0),  # naive
            finished_at=None,
        )
        assert receipt.started_at.tzinfo is not None
        # non-destructive: wall-clock fields preserved
        assert receipt.started_at.hour == 10


# ---------------------------------------------------------------------------
# 2. Projection onto ImportRun row
# ---------------------------------------------------------------------------

class TestImportRunProjection:
    def test_keys_match_import_runs_columns_exactly(self) -> None:
        run = _success_receipt().to_import_run()
        assert set(run.keys()) == _IMPORT_RUN_COLUMNS

    def test_success_projection_values(self) -> None:
        run = _success_receipt().to_import_run()
        assert run["run_id"] == "run_abc"
        assert run["source_channel"] == "wechat_channels"
        assert run["status"] == "completed"
        assert run["records_created"] == 1
        assert run["records_skipped"] == 0
        assert run["request_id"] == "req_abc"
        # No error envelope -> retryable False, error fields None
        assert run["retryable"] is False
        assert run["error_code"] is None
        assert run["error_message"] is None
        assert run["fix_hint"] is None
        assert run["started_at"].startswith("2026-06-01T10:00:00")
        assert run["finished_at"].startswith("2026-06-01T10:00:05")

    def test_failed_projection_carries_error_envelope(self) -> None:
        receipt = _success_receipt(
            status="failed",
            content_id=None,
            records_created=0,
            finished_at=datetime(2026, 6, 1, 10, 0, 2, tzinfo=timezone.utc),
            error=ImportErrorEnvelope(
                code="F0_INDEX_002",
                message="Import runs query failed",
                request_id="req_err",
                operation="record_imported",
                retryable=True,
                fix_hint="Retry after checking the source archive",
                source_channel="wechat_channels",
            ),
        )
        run = receipt.to_import_run()
        assert run["status"] == "failed"
        assert run["error_code"] == "F0_INDEX_002"
        assert run["error_message"] == "Import runs query failed"
        assert run["retryable"] is True
        assert run["fix_hint"] == "Retry after checking the source archive"

    def test_request_id_falls_back_to_error_envelope(self) -> None:
        receipt = _success_receipt(
            request_id=None,
            status="failed",
            error=ImportErrorEnvelope(
                code="F0_INDEX_001",
                message="boom",
                request_id="req_from_error",
                operation="record_imported",
                retryable=False,
            ),
        )
        run = receipt.to_import_run()
        assert run["request_id"] == "req_from_error"
        assert run["retryable"] is False

    def test_finished_at_none_projects_none(self) -> None:
        run = _success_receipt(finished_at=None, status="running").to_import_run()
        assert run["finished_at"] is None


# ---------------------------------------------------------------------------
# 3. Security — no sensitive fields
# ---------------------------------------------------------------------------

class TestNoSensitiveFields:
    def _walk_keys(self, obj) -> list[str]:
        keys: list[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.append(str(k))
                keys.extend(self._walk_keys(v))
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                keys.extend(self._walk_keys(item))
        return keys

    def test_model_fields_have_no_forbidden_names(self) -> None:
        for name in ImportReceipt.model_fields:
            lowered = name.lower()
            for forbidden in _FORBIDDEN_KEY_SUBSTRINGS:
                assert forbidden not in lowered, f"forbidden field name: {name}"

    def test_serialized_success_has_no_forbidden_keys(self) -> None:
        keys = self._walk_keys(_success_receipt().model_dump())
        for key in keys:
            lowered = key.lower()
            for forbidden in _FORBIDDEN_KEY_SUBSTRINGS:
                assert forbidden not in lowered, f"forbidden key in payload: {key}"

    def test_error_envelope_has_no_forbidden_keys(self) -> None:
        for name in ImportErrorEnvelope.model_fields:
            lowered = name.lower()
            for forbidden in _FORBIDDEN_KEY_SUBSTRINGS:
                assert forbidden not in lowered, f"forbidden field name: {name}"


# ---------------------------------------------------------------------------
# 4. Channel coverage — all six channels accepted
# ---------------------------------------------------------------------------

class TestChannelCoverage:
    @pytest.mark.parametrize(
        "channel",
        ["feishu", "local_upload", "notebooklm", "wechat", "wechat_channels", "bilibili"],
    )
    def test_all_channels_valid(self, channel: str) -> None:
        receipt = ImportReceipt(
            run_id="r", source_channel=channel, source_kind="k", status="completed"
        )
        assert receipt.source_channel == channel
        assert receipt.to_import_run()["source_channel"] == channel
