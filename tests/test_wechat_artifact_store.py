"""Tests for WeChat artifact store."""

import hashlib
import json
import pytest
from pathlib import Path

from finer.services.wechat_artifact_store import WeChatArtifactStore, ArticleArtifacts


@pytest.fixture
def artifact_store(tmp_path):
    return WeChatArtifactStore(tmp_path)


class TestSaveArtifacts:
    def test_save_markdown_only(self, artifact_store):
        md = "# Test Article\n\nContent here."
        artifacts = artifact_store.save_article_artifacts(
            account_id="acc_001",
            article_id="art_001",
            html=b"",
            markdown=md,
        )
        assert artifacts.raw_md_path.exists()
        assert artifacts.raw_md_path.read_text(encoding="utf-8") == md
        assert artifacts.raw_html_path is None
        assert artifacts.html_sha256 is None

    def test_save_html_and_markdown(self, artifact_store):
        html = b"<html><body><h1>Test</h1></body></html>"
        md = "# Test"
        artifacts = artifact_store.save_article_artifacts(
            account_id="acc_001",
            article_id="art_002",
            html=html,
            markdown=md,
        )
        assert artifacts.raw_html_path is not None
        assert artifacts.raw_html_path.exists()
        assert artifacts.raw_html_path.read_bytes() == html

    def test_sha256_hash_correct(self, artifact_store):
        md = "Hello, world!"
        artifacts = artifact_store.save_article_artifacts(
            account_id="acc_001",
            article_id="art_003",
            html=b"",
            markdown=md,
        )
        expected = hashlib.sha256(md.encode("utf-8")).hexdigest()
        assert artifacts.md_sha256 == expected

    def test_html_sha256_correct(self, artifact_store):
        html = b"<p>test</p>"
        artifacts = artifact_store.save_article_artifacts(
            account_id="acc_001",
            article_id="art_004",
            html=html,
            markdown="test",
        )
        expected = hashlib.sha256(html).hexdigest()
        assert artifacts.html_sha256 == expected

    def test_sidecar_json_structure(self, artifact_store):
        artifacts = artifact_store.save_article_artifacts(
            account_id="acc_001",
            article_id="art_005",
            html=b"<html></html>",
            markdown="# Test",
        )
        assert artifacts.sidecar_path.exists()
        sidecar = json.loads(artifacts.sidecar_path.read_text(encoding="utf-8"))
        assert sidecar["article_id"] == "art_005"
        assert sidecar["account_id"] == "acc_001"
        assert sidecar["raw_md_sha256"] == artifacts.md_sha256
        assert sidecar["raw_html_sha256"] == artifacts.html_sha256
        assert "saved_at" in sidecar

    def test_account_dir_created(self, artifact_store, tmp_path):
        artifact_store.save_article_artifacts(
            account_id="new_account",
            article_id="art_006",
            html=b"",
            markdown="test",
        )
        assert (tmp_path / "data" / "raw" / "wechat" / "new_account").exists()


class TestSyncState:
    def test_load_empty_sync_state(self, artifact_store):
        ids = artifact_store.load_sync_state("acc_empty")
        assert ids == set()

    def test_save_and_load_sync_state(self, artifact_store):
        ids = {"art_001", "art_002", "art_003"}
        artifact_store.save_sync_state("acc_001", ids)
        loaded = artifact_store.load_sync_state("acc_001")
        assert loaded == ids

    def test_sync_state_persists(self, artifact_store):
        artifact_store.save_sync_state("acc_001", {"a", "b"})
        # Create new store with same root
        store2 = WeChatArtifactStore(artifact_store._root)
        loaded = store2.load_sync_state("acc_001")
        assert loaded == {"a", "b"}

    def test_sync_state_sorted(self, artifact_store):
        ids = {"c", "a", "b"}
        artifact_store.save_sync_state("acc_001", ids)
        path = artifact_store._sync_state_path("acc_001")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["synced_article_ids"] == ["a", "b", "c"]
