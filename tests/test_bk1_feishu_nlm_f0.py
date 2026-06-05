"""BK1 — Feishu + NotebookLM F0 收口 tests.

Covers:
- R-01: lark-cli token/permission failure -> canonical FinerError(FEISHU_AUTH_001)
  with fix_hint, no stderr leak; generic/missing-binary failures classified too.
- R-12: feishu F0 import produces ContentRecord + ImportReceipt + PM row, and the
  F0 path no longer references Vision/Summary/NLM inline (decoupled seam).
- R-14: nlm CLI path resolves via shutil.which with config override.
- R-15/R-29: /nlm/fetch produces a canonical nlm_note ContentRecord, dedupes by
  nlm source id, and counts per-source errors instead of printing.
- R-13: sources.py raises no bare HTTPException.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from finer.errors import ErrorCode, FinerError


# ---------------------------------------------------------------------------
# Shared: a real, fully-migrated Project Memory DB (same helper backfill uses)
# ---------------------------------------------------------------------------

@pytest.fixture()
def pm_conn(tmp_path: Path) -> sqlite3.Connection:
    from finer.scripts.project_memory_migrate import discover_migrations, _apply_migration

    db_path = tmp_path / "pm.sqlite3"
    connection = sqlite3.connect(str(db_path))
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.row_factory = sqlite3.Row
    for migration in discover_migrations():
        _apply_migration(connection, migration)
    return connection


def _count(conn: sqlite3.Connection, table: str, where: str = "", params: tuple = ()) -> int:
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return conn.execute(sql, params).fetchone()[0]


# ---------------------------------------------------------------------------
# R-01: lark-cli graceful degradation
# ---------------------------------------------------------------------------

class TestLarkGracefulDegradation:
    def _fake_run(self, returncode: int, stderr: str):
        def _run(*args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=returncode, stdout="", stderr=stderr)
        return _run

    def test_token_failure_raises_auth_finer_error_with_fix_hint(self, monkeypatch):
        from finer.ingestion import feishu_poller

        monkeypatch.setattr(
            feishu_poller.subprocess,
            "run",
            self._fake_run(1, "Error 99991663: invalid access token, please re-login"),
        )

        with pytest.raises(FinerError) as exc_info:
            feishu_poller._run_lark_cli("/opt/homebrew/bin/lark-cli", ["im", "+chat-messages-list"])

        err = exc_info.value
        assert err.code == ErrorCode.FEISHU_AUTH_001
        assert err.stage == "F0"
        assert err.source_channel == "feishu"
        assert err.retryable is True
        assert err.details.get("fix_hint") == "run lark-cli auth login"

    def test_token_failure_does_not_leak_stderr(self, monkeypatch):
        from finer.ingestion import feishu_poller

        secret_stderr = "token=SUPER_SECRET_abc123 unauthorized"
        monkeypatch.setattr(
            feishu_poller.subprocess, "run", self._fake_run(1, secret_stderr)
        )

        with pytest.raises(FinerError) as exc_info:
            feishu_poller._run_lark_cli("lark-cli", ["im", "+chat-messages-list"])

        err = exc_info.value
        blob = json.dumps({"msg": err.message, "details": err.details})
        assert "SUPER_SECRET_abc123" not in blob
        assert "token=SUPER_SECRET" not in blob

    def test_generic_failure_classified_as_upstream(self, monkeypatch):
        from finer.ingestion import feishu_poller

        monkeypatch.setattr(
            feishu_poller.subprocess, "run", self._fake_run(1, "rate limited, try later")
        )

        with pytest.raises(FinerError) as exc_info:
            feishu_poller._run_lark_cli("lark-cli", ["im", "+chat-messages-list"])

        assert exc_info.value.code == ErrorCode.FEISHU_EXT_001

    def test_missing_binary_is_not_retryable(self, monkeypatch):
        from finer.ingestion import feishu_poller

        def _raise(*args, **kwargs):
            raise FileNotFoundError("no such file: lark-cli")

        monkeypatch.setattr(feishu_poller.subprocess, "run", _raise)

        with pytest.raises(FinerError) as exc_info:
            feishu_poller._run_lark_cli("/nope/lark-cli", ["im", "+chat-messages-list"])

        err = exc_info.value
        assert err.code == ErrorCode.FEISHU_EXT_001
        assert err.retryable is False


# ---------------------------------------------------------------------------
# R-12: feishu attachment F0 import -> ContentRecord + receipt + PM row
# ---------------------------------------------------------------------------

class TestFeishuAttachmentF0:
    def test_emit_attachment_record_writes_contentrecord_receipt_and_pm_row(
        self, tmp_path: Path, monkeypatch, pm_conn: sqlite3.Connection
    ):
        from finer.ingestion import orchestrator
        from finer.ingestion.classifier import ClassificationResult
        from finer.ingestion.f0_index_writer import F0IndexWriter
        from finer.ingestion.feishu_poller import DownloadedFile
        from finer.schemas.content import ContentRecord

        # Route F0 path output under tmp_path/data/F0_intake/feishu via the GATE helpers.
        monkeypatch.setattr(
            orchestrator, "f0_record_path",
            lambda platform, cid: tmp_path / "data" / "F0_intake" / platform / f"{cid}.json",
        )
        monkeypatch.setattr(
            orchestrator, "f0_receipt_path",
            lambda platform, cid: tmp_path / "data" / "F0_intake" / platform / f"{cid}.receipt.json",
        )
        # Register into the migrated in-memory PM DB rather than the live project DB.
        monkeypatch.setattr(
            orchestrator,
            "_register_f0_index",
            lambda record, receipt: F0IndexWriter(pm_conn).record_imported(record, receipt),
        )

        archived = tmp_path / "data" / "raw" / "maodaren" / "weekly_strategy" / "deck.pdf"
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes(b"%PDF-1.4 fake")

        file = DownloadedFile(
            local_path=archived,
            original_name="deck.pdf",
            message_id="om_123",
            chat_id="oc_chat",
            sender_id="ou_sender",
            sent_at=datetime(2026, 3, 12, 15, 36, 0, tzinfo=timezone.utc),
            msg_type="file",
            context_text="weekly deck",
        )
        classification = ClassificationResult(
            creator_id="maodaren",
            source_type="weekly_strategy",
            published_at=datetime(2026, 3, 12, 9, 0, 0, tzinfo=timezone.utc),
            confidence=0.8,
            matched_rule="rule:weekly",
        )

        record = orchestrator._emit_attachment_f0_record(tmp_path, file, classification, archived)

        # ContentRecord on disk is canonical feishu_chat
        assert isinstance(record, ContentRecord)
        assert record.source_type == "feishu_chat"
        assert record.source_platform == "feishu"
        record_path = tmp_path / "data" / "F0_intake" / "feishu" / f"{record.content_id}.json"
        receipt_path = tmp_path / "data" / "F0_intake" / "feishu" / f"{record.content_id}.receipt.json"
        assert record_path.exists()
        assert receipt_path.exists()
        on_disk = ContentRecord.model_validate_json(record_path.read_text(encoding="utf-8"))
        assert on_disk.source_type == "feishu_chat"
        assert on_disk.external_source_id == record.external_source_id
        assert on_disk.metadata["classified_source_type"] == "weekly_strategy"

        # Receipt projects onto the import_runs row shape with the feishu channel
        from finer.schemas.import_receipt import ImportReceipt

        receipt = ImportReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
        assert receipt.source_channel == "feishu"
        assert receipt.to_import_run()["source_channel"] == "feishu"

        # PM row exists (asset_index + contents)
        assert _count(pm_conn, "contents", "content_id = ?", (record.content_id,)) == 1
        assert _count(pm_conn, "asset_index", "content_id = ? AND stage = 'F0'", (record.content_id,)) == 1

    def test_f0_import_path_has_no_inline_vision_summary_nlm(self):
        """The F0 orchestrator must not call Vision/Summary/NLM inline (R-12).

        Checks for actual import/instantiation/call forms, not the documentary
        mentions in the decoupling seam comment.
        """
        source = Path("src/finer/ingestion/orchestrator.py").read_text(encoding="utf-8")
        forbidden_forms = [
            "import VisionDescriptor",
            "VisionDescriptor(",
            ".describe_image(",
            "import SummaryGenerator",
            "SummaryGenerator(",
            ".generate_summary(",
            "import NLMSync",
            "NLMSync(",
            ".sync_file(",
        ]
        for form in forbidden_forms:
            assert form not in source, f"inline F0 coupling found: {form!r}"
        # Seam is documented
        assert "F1_HANDOFF_SEAM" in source


# ---------------------------------------------------------------------------
# R-14: nlm CLI path resolution
# ---------------------------------------------------------------------------

class TestNlmCliResolution:
    def test_config_path_wins(self):
        from finer.ingestion.nlm_sync import resolve_nlm_cli

        assert resolve_nlm_cli("/custom/bin/nlm") == "/custom/bin/nlm"

    def test_uses_shutil_which_when_no_config(self, monkeypatch):
        from finer.ingestion import nlm_sync

        monkeypatch.setattr(nlm_sync.shutil, "which", lambda name: "/opt/found/nlm")
        assert nlm_sync.resolve_nlm_cli(None) == "/opt/found/nlm"

    def test_falls_back_when_which_returns_none(self, monkeypatch):
        from finer.ingestion import nlm_sync

        monkeypatch.setattr(nlm_sync.shutil, "which", lambda name: None)
        assert nlm_sync.resolve_nlm_cli(None) == nlm_sync._FALLBACK_NLM_CLI

    def test_nlmsync_init_resolves_via_which(self, monkeypatch):
        from finer.ingestion import nlm_sync

        monkeypatch.setattr(nlm_sync.shutil, "which", lambda name: "/opt/found/nlm")
        sync = nlm_sync.NLMSync({})
        assert sync.nlm_cli_path == "/opt/found/nlm"


# ---------------------------------------------------------------------------
# R-15 / R-29: /nlm/fetch -> canonical nlm_note ContentRecord + dedupe
# ---------------------------------------------------------------------------

class TestNlmFetchCore:
    def _patch_paths(self, monkeypatch, tmp_path: Path):
        from finer.api.routes import integrations

        monkeypatch.setattr(
            integrations, "f0_record_path",
            lambda platform, cid: tmp_path / "F0_intake" / platform / f"{cid}.json",
        )
        monkeypatch.setattr(
            integrations, "f0_receipt_path",
            lambda platform, cid: tmp_path / "F0_intake" / platform / f"{cid}.receipt.json",
        )
        monkeypatch.setattr(
            integrations, "f0_raw_dir",
            lambda platform, *sub: tmp_path / "raw" / platform / Path(*sub) if sub else tmp_path / "raw" / platform,
        )
        # Do not touch the live PM DB.
        monkeypatch.setattr(integrations, "_register_f0_index", lambda record, receipt: None)
        # config load returns no nlm_cli_path so resolve_nlm_cli -> which (patched below)
        monkeypatch.setattr(integrations, "load_feishu_config", lambda root: {"notebooklm": {}})
        monkeypatch.setattr(integrations, "resolve_nlm_cli", lambda cfg: "/fake/nlm")

    def _fake_subprocess(self, sources, content_value):
        def _run(cmd, **kwargs):
            if "list" in cmd:
                out = json.dumps(sources)
            else:  # source content
                out = json.dumps({"value": {"content": content_value, "source_type": "text"}})
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=out, stderr="")
        return _run

    def test_fetch_produces_nlm_note_record_and_dedupes(self, tmp_path: Path, monkeypatch):
        from finer.api.routes import integrations
        from finer.schemas.content import ContentRecord

        self._patch_paths(monkeypatch, tmp_path)
        monkeypatch.setattr(
            integrations.subprocess, "run",
            self._fake_subprocess([{"id": "src_1", "title": "Cat Lord note"}], "hello world body"),
        )

        result = integrations._fetch_nlm_notebook_core("nb_abc")
        assert result["status"] == "ok"
        assert result["downloaded"] == 1
        assert result["errors"] == 0

        # Exactly one nlm_note ContentRecord written
        record_dir = tmp_path / "F0_intake" / "nlm"
        files = list(record_dir.glob("*.json"))
        record_files = [f for f in files if not f.name.endswith(".receipt.json")]
        assert len(record_files) == 1
        record = ContentRecord.model_validate_json(record_files[0].read_text(encoding="utf-8"))
        assert record.source_type == "nlm_note"
        assert record.source_platform == "nlm"
        assert record.external_source_id == "nlm:nb_abc:src_1"
        assert record.dedupe_fingerprint

        # Receipt written with notebooklm channel + nlm_note kind
        from finer.schemas.import_receipt import ImportReceipt

        receipt_files = [f for f in files if f.name.endswith(".receipt.json")]
        assert len(receipt_files) == 1
        receipt = ImportReceipt.model_validate_json(receipt_files[0].read_text(encoding="utf-8"))
        assert receipt.source_channel == "notebooklm"
        assert receipt.source_kind == "nlm_note"

        # Re-fetch dedupes (record already on disk -> skipped, not re-created)
        result2 = integrations._fetch_nlm_notebook_core("nb_abc")
        assert result2["downloaded"] == 0
        assert result2["skipped"] == 1

    def test_per_source_error_is_counted_not_raised(self, tmp_path: Path, monkeypatch):
        from finer.api.routes import integrations

        self._patch_paths(monkeypatch, tmp_path)

        def _run(cmd, **kwargs):
            if "list" in cmd:
                out = json.dumps([{"id": "src_bad", "title": "Bad"}])
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=out, stderr="")
            # source content fails
            raise subprocess.CalledProcessError(1, cmd, stderr="boom")

        monkeypatch.setattr(integrations.subprocess, "run", _run)

        result = integrations._fetch_nlm_notebook_core("nb_abc")
        assert result["status"] == "ok"
        assert result["errors"] == 1
        assert result["downloaded"] == 0

    def test_missing_nlm_binary_raises_finer_error(self, tmp_path: Path, monkeypatch):
        from finer.api.routes import integrations

        self._patch_paths(monkeypatch, tmp_path)

        def _run(cmd, **kwargs):
            raise FileNotFoundError("nlm missing")

        monkeypatch.setattr(integrations.subprocess, "run", _run)

        with pytest.raises(FinerError) as exc_info:
            integrations._fetch_nlm_notebook_core("nb_abc")
        err = exc_info.value
        assert err.code == ErrorCode.NLM_EXT_001
        assert err.source_channel == "notebooklm"
        assert err.retryable is False


# ---------------------------------------------------------------------------
# R-13: sources.py has no bare HTTPException
# ---------------------------------------------------------------------------

def test_sources_route_has_no_bare_httpexception():
    source = Path("src/finer/api/routes/sources.py").read_text(encoding="utf-8")
    assert "HTTPException" not in source
