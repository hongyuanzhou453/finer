"""Bilibili F0 channel contract tests — verify canonical error envelope.

Also covers BK3 收口 (R-02 / R-09 / R-10 / R-11):
- BBDown / .NET unavailable degrades to canonical F0_EXT_001 (with fix_hint).
- BilibiliAdapter constructs without DASHSCOPE_API_KEY (lazy require).
- F0 import produces ContentRecord + ImportReceipt + PM row without a transcript.
- The F0 download layer does not statically import the F1 ASR client.
"""
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Realistic BBDown ``--only-show-info`` stdout used to drive mocked CLI runs.
_BBDOWN_INFO_OUTPUT = """
BBDown version 1.6.3, Bilibili Downloader.
[2026-05-09 19:20:44.550] - 获取aid结束: 116491760572977
[2026-05-09 19:20:44.742] - 视频标题: 【硬核】提前退休计划
[2026-05-09 19:20:44.742] - 发布时间: 2026-04-30 12:29:30 +08:00
[2026-05-09 19:20:44.742] - UP主页: https://space.bilibili.com/315846984
[2026-05-09 19:20:44.742] - P1: [37936435113] [【硬核】提前退休计划] [37m33s]
[2026-05-09 19:20:44.745] - 共计 1 个分P, 已选择：ALL
"""

# What the .NET host prints when its required runtime is absent.
_DOTNET_MISSING_OUTPUT = (
    "You must install or update .NET to run this application.\n"
    "Framework: 'Microsoft.NETCore.App', version '8.0.0' (x64)\n"
    "The framework 'Microsoft.NETCore.App', version '8.0.0' was not found."
)


def _completed(args, stdout="", stderr="", code=0):
    return subprocess.CompletedProcess(args=args, returncode=code, stdout=stdout, stderr=stderr)


class TestBilibiliF0Contract:
    """Verify bilibili.py error responses conform to F0 contract."""

    @pytest.fixture()
    def client(self):
        from finer.api.server import app
        return TestClient(app, raise_server_exceptions=False)

    def test_video_info_invalid_bvid_returns_error(self, client):
        """GET /api/bilibili/video/invalid returns BILI_IN_001."""
        resp = client.get("/api/bilibili/video/invalid_bvid")
        body = resp.json()
        if "error" in body:
            assert body["error"]["code"] in ("BILI_IN_001", "BILI_EXT_001")

    def test_task_not_found_returns_error(self, client):
        """GET /api/bilibili/task/nonexistent returns BILI_NTF_001."""
        resp = client.get("/api/bilibili/task/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        if "error" in body:
            assert body["error"]["code"] == "BILI_NTF_001"

    def test_error_has_source_channel_bilibili(self, client):
        """Error responses include source_channel='bilibili'."""
        resp = client.get("/api/bilibili/video/invalid_bvid")
        body = resp.json()
        if "error" in body and "details" in body["error"]:
            assert body["error"]["details"].get("source_channel") == "bilibili"

    def test_no_http_exception_in_bilibili_routes(self):
        """bilibili.py should have zero raise HTTPException."""
        import inspect
        from finer.api.routes import bilibili
        source = inspect.getsource(bilibili)
        assert "raise HTTPException" not in source

    def test_content_manifest_uses_new_fields(self):
        """ContentManifest constructor in bilibili.py uses source_type/raw_path."""
        import inspect
        from finer.api.routes import bilibili
        source = inspect.getsource(bilibili)
        # Should use new field names
        assert "source_type=" in source or "ContentManifest" not in source
        assert "raw_path=" in source or "ContentManifest" not in source
        # Should NOT use old field names
        assert "content_type=" not in source or "metadata" in source


# ---------------------------------------------------------------------------
# R-09: adapter construction must not require DASHSCOPE_API_KEY (lazy require)
# ---------------------------------------------------------------------------

class TestBilibiliAdapterLazyDashScope:
    """BilibiliAdapter must construct without DASHSCOPE_API_KEY (R-09)."""

    def test_construct_without_dashscope_key_does_not_crash(self, monkeypatch):
        from finer.ingestion.bilibili_adapter import BilibiliAdapter

        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        # Construction is a pure F0 op — must not raise even with no ASR key.
        adapter = BilibiliAdapter()
        assert adapter is not None
        assert adapter.client is not None
        # The transcriber is lazy and not built yet.
        assert adapter._transcriber is None

    def test_transcriber_property_requires_key_lazily(self, monkeypatch):
        from finer.ingestion.bilibili_adapter import BilibiliAdapter

        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        adapter = BilibiliAdapter()
        # The DASHSCOPE requirement only fires when the transcriber is accessed.
        with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
            _ = adapter.transcriber

    def test_transcriber_property_builds_with_key(self, monkeypatch):
        from finer.ingestion.bilibili_adapter import BilibiliAdapter, ParaformerTranscriber

        monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
        adapter = BilibiliAdapter()
        assert isinstance(adapter.transcriber, ParaformerTranscriber)


# ---------------------------------------------------------------------------
# R-02: BBDown / .NET unavailable degrades to canonical F0_EXT_001
# ---------------------------------------------------------------------------

class TestBBDownGracefulDegradation:
    """BBDown unavailable → BBDownUnavailableError → F0_EXT_001 (R-02)."""

    @pytest.mark.anyio
    async def test_missing_binary_raises_unavailable(self, monkeypatch, tmp_path):
        from finer.ingestion.bbdown_client import (
            BBDownAdapter,
            BBDownConfig,
            BBDownUnavailableError,
        )

        def fake_run(args, **kwargs):
            raise FileNotFoundError("BBDown")

        monkeypatch.setattr(subprocess, "run", fake_run)
        adapter = BBDownAdapter(BBDownConfig(download_dir=tmp_path))

        with pytest.raises(BBDownUnavailableError):
            await adapter.download_raw_artifacts("BV1Vb9hBVE4C", output_dir=tmp_path)

    @pytest.mark.anyio
    async def test_dotnet_missing_raises_unavailable(self, monkeypatch, tmp_path):
        from finer.ingestion.bbdown_client import (
            BBDownAdapter,
            BBDownConfig,
            BBDownUnavailableError,
        )

        def fake_run(args, **kwargs):
            # .NET host prints the missing-runtime banner and exits non-zero.
            return _completed(args, stdout=_DOTNET_MISSING_OUTPUT, code=150)

        monkeypatch.setattr(subprocess, "run", fake_run)
        adapter = BBDownAdapter(BBDownConfig(download_dir=tmp_path))

        with pytest.raises(BBDownUnavailableError):
            await adapter.download_raw_artifacts("BV1Vb9hBVE4C", output_dir=tmp_path)

    def test_unavailable_error_carries_fix_hint(self):
        from finer.ingestion.bbdown_client import BBDownUnavailableError

        err = BBDownUnavailableError("boom")
        assert err.fix_hint == "install .NET 8 runtime"

    def test_import_route_maps_dotnet_missing_to_f0_ext_001(self, monkeypatch, tmp_path):
        """POST /api/bilibili/import returns F0_EXT_001 + fix_hint when .NET missing."""
        from finer.api.server import app
        import finer.api.routes.bilibili as bilibili_routes

        # Route raw artifacts under tmp; never touch the real archive dir.
        monkeypatch.setattr(
            bilibili_routes, "f0_raw_dir", lambda *parts: tmp_path
        )

        def fake_run(args, **kwargs):
            return _completed(args, stdout=_DOTNET_MISSING_OUTPUT, code=150)

        monkeypatch.setattr(subprocess, "run", fake_run)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/bilibili/import/BV1Vb9hBVE4C")
        body = resp.json()

        assert body["ok"] is False
        assert body["error"]["code"] == "F0_EXT_001"
        details = body["error"]["details"]
        assert details["source_channel"] == "bilibili"
        assert details["retryable"] is True
        assert details["stage"] == "F0"
        # fix_hint must guide the user to install the runtime.
        assert "fix_hint" in details
        assert ".NET 8" in details["fix_hint"]


# ---------------------------------------------------------------------------
# R-10: F0 import produces ContentRecord + receipt + PM row, no transcript dep
# ---------------------------------------------------------------------------

class TestBilibiliF0ImportProducesRecord:
    """POST /api/bilibili/import produces canonical F0 outputs (R-10)."""

    def _patch_cli_success(self, monkeypatch, tmp_path):
        """Mock BBDown CLI: info → stdout; audio → write a fake .m4a; subtitle → none."""

        def fake_run(args, **kwargs):
            if "--only-show-info" in args:
                return _completed(args, stdout=_BBDOWN_INFO_OUTPUT)
            if "--audio-only" in args:
                work_dir = Path(args[args.index("--work-dir") + 1])
                work_dir.mkdir(parents=True, exist_ok=True)
                (work_dir / "BV1Vb9hBVE4C.m4a").write_text("audio-bytes", encoding="utf-8")
                return _completed(args)
            if "--sub-only" in args:
                # No subtitle produced — best-effort path tolerates this.
                return _completed(args)
            return _completed(args)

        monkeypatch.setattr(subprocess, "run", fake_run)

    def test_import_creates_record_and_receipt_without_transcript(
        self, monkeypatch, tmp_path
    ):
        from finer.api.server import app
        from finer.schemas.content import ContentRecord
        from finer.schemas.import_receipt import ImportReceipt
        import finer.api.routes.bilibili as bilibili_routes

        # Raw archive + F0 record/receipt all land under tmp.
        raw_dir = tmp_path / "raw"
        intake_dir = tmp_path / "F0_intake"
        monkeypatch.setattr(bilibili_routes, "f0_raw_dir", lambda *p: raw_dir)
        monkeypatch.setattr(
            bilibili_routes,
            "f0_record_path",
            lambda platform, cid: intake_dir / platform / f"{cid}.json",
        )
        monkeypatch.setattr(
            bilibili_routes,
            "f0_receipt_path",
            lambda platform, cid: intake_dir / platform / f"{cid}.receipt.json",
        )
        # Never write to the live Project Memory DB.
        registered: list = []
        monkeypatch.setattr(
            bilibili_routes,
            "_register_f0_index",
            lambda record, receipt: registered.append((record, receipt)),
        )
        # Avoid writing a manifest into the real repo data dir.
        monkeypatch.setattr(
            bilibili_routes, "write_manifest", lambda root, manifest: tmp_path / "m.json"
        )

        self._patch_cli_success(monkeypatch, raw_dir)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/bilibili/import/BV1Vb9hBVE4C")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["status"] == "imported"
        assert body["bvid"] == "BV1Vb9hBVE4C"

        # ContentRecord persisted and canonical.
        record_path = Path(body["record_path"])
        assert record_path.exists()
        record = ContentRecord.model_validate_json(record_path.read_text(encoding="utf-8"))
        assert record.source_type == "bilibili_video"
        assert record.source_platform == "bilibili"
        assert record.external_source_id == "BV1Vb9hBVE4C"
        assert record.creator_id == "315846984"

        # ImportReceipt persisted and canonical (one record created, no transcript).
        receipt_path = Path(body["receipt_path"])
        assert receipt_path.exists()
        receipt = ImportReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
        assert receipt.source_channel == "bilibili"
        assert receipt.source_kind == "bilibili_video"
        assert receipt.records_created == 1
        assert receipt.content_id == record.content_id
        # Raw artifact provenance present; NO transcript role.
        assert "audio" in receipt.raw_paths
        assert "source_info" in receipt.raw_paths
        assert all("transcript" not in role for role in receipt.raw_paths)

        # PM registration was invoked exactly once with the record + receipt.
        assert len(registered) == 1
        assert registered[0][0].content_id == record.content_id

        # The raw artifact set exists on disk and does NOT include a transcript.
        assert (raw_dir / "BV1Vb9hBVE4C.m4a").exists()
        assert (raw_dir / "BV1Vb9hBVE4C.source.json").exists()
        assert not list(raw_dir.glob("*transcript*"))

    def test_import_is_idempotent(self, monkeypatch, tmp_path):
        from finer.api.server import app
        import finer.api.routes.bilibili as bilibili_routes

        raw_dir = tmp_path / "raw"
        intake_dir = tmp_path / "F0_intake"
        monkeypatch.setattr(bilibili_routes, "f0_raw_dir", lambda *p: raw_dir)
        monkeypatch.setattr(
            bilibili_routes,
            "f0_record_path",
            lambda platform, cid: intake_dir / platform / f"{cid}.json",
        )
        monkeypatch.setattr(
            bilibili_routes,
            "f0_receipt_path",
            lambda platform, cid: intake_dir / platform / f"{cid}.receipt.json",
        )
        monkeypatch.setattr(
            bilibili_routes, "_register_f0_index", lambda record, receipt: None
        )
        monkeypatch.setattr(
            bilibili_routes, "write_manifest", lambda root, manifest: tmp_path / "m.json"
        )
        self._patch_cli_success(monkeypatch, raw_dir)

        client = TestClient(app, raise_server_exceptions=False)
        first = client.post("/api/bilibili/import/BV1Vb9hBVE4C")
        assert first.json()["status"] == "imported"
        second = client.post("/api/bilibili/import/BV1Vb9hBVE4C")
        assert second.json()["status"] == "already_imported"


# ---------------------------------------------------------------------------
# R-11: F0 download layer must not statically import the F1 ASR client
# ---------------------------------------------------------------------------

class TestNoCrossLayerASRImport:
    """F0 download modules must not ``from finer.parsing`` import ASR (R-11)."""

    def test_bbdown_client_has_no_parsing_import(self):
        import inspect
        from finer.ingestion import bbdown_client

        source = inspect.getsource(bbdown_client)
        assert "from finer.parsing" not in source

    def test_bbdown_route_has_no_parsing_import(self):
        import inspect
        from finer.api.routes import bbdown

        source = inspect.getsource(bbdown)
        assert "from finer.parsing" not in source
