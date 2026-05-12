"""Tests for WeChat ContentRecord builder."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from finer.services.wechat_artifact_store import ArticleArtifacts
from finer.services.wechat_content_record_builder import (
    build_content_record,
    _derive_content_id,
)


class _FakeArticle:
    """Minimal article object for testing."""
    def __init__(self, **kwargs):
        self.article_id = kwargs.get("article_id", "art_001")
        self.title = kwargs.get("title", "Test Article")
        self.author = kwargs.get("author", "Author")
        self.digest = kwargs.get("digest", "A digest")
        self.content_url = kwargs.get("content_url", "https://mp.weixin.qq.com/s/abc")
        self.publish_time = kwargs.get("publish_time", datetime(2025, 1, 15, tzinfo=timezone.utc))
        self.cover_url = kwargs.get("cover_url", "")


@pytest.fixture
def artifacts(tmp_path):
    md_path = tmp_path / "art_001.md"
    md_path.write_text("# Test", encoding="utf-8")
    html_path = tmp_path / "art_001.html"
    html_path.write_bytes(b"<h1>Test</h1>")
    sidecar_path = tmp_path / "art_001.sidecar.json"
    sidecar_path.write_text("{}", encoding="utf-8")
    return ArticleArtifacts(
        raw_html_path=html_path,
        raw_md_path=md_path,
        html_sha256="abc123",
        md_sha256="def456",
        sidecar_path=sidecar_path,
    )


class TestDeriveContentId:
    def test_stable_id(self):
        id1 = _derive_content_id("acc1", "art1")
        id2 = _derive_content_id("acc1", "art1")
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        id1 = _derive_content_id("acc1", "art1")
        id2 = _derive_content_id("acc1", "art2")
        assert id1 != id2

    def test_length(self):
        cid = _derive_content_id("acc", "art")
        assert len(cid) == 32


class TestBuildContentRecord:
    def test_basic_fields(self, artifacts):
        article = _FakeArticle()
        record = build_content_record(
            article=article,
            account_id="acc_001",
            account_name="测试公众号",
            artifacts=artifacts,
        )
        assert record.source_platform == "wechat"
        assert record.source_type == "wechat_article"
        assert record.creator_name == "测试公众号"
        assert record.title == "Test Article"
        assert record.source_url == "https://mp.weixin.qq.com/s/abc"

    def test_content_id_is_stable(self, artifacts):
        article = _FakeArticle()
        r1 = build_content_record(article, "acc_001", "name", artifacts)
        r2 = build_content_record(article, "acc_001", "name", artifacts)
        assert r1.content_id == r2.content_id

    def test_source_path_is_md_path(self, artifacts):
        article = _FakeArticle()
        record = build_content_record(article, "acc_001", "name", artifacts)
        assert record.raw_path == str(artifacts.raw_md_path)

    def test_metadata_fields(self, artifacts):
        article = _FakeArticle()
        record = build_content_record(
            article, "acc_001", "测试", artifacts,
            exporter_session_id="sess_123",
            exporter_request_id="req_456",
        )
        m = record.metadata
        assert m["account_id"] == "acc_001"
        assert m["account_name"] == "测试"
        assert m["article_id"] == "art_001"
        assert m["article_url"] == "https://mp.weixin.qq.com/s/abc"
        assert m["exporter_session_id"] == "sess_123"
        assert m["exporter_request_id"] == "req_456"
        assert m["raw_md_path"] == str(artifacts.raw_md_path)
        assert m["raw_html_path"] == str(artifacts.raw_html_path)
        assert m["raw_md_sha256"] == "def456"
        assert m["raw_html_sha256"] == "abc123"
        assert m["acquisition_status"] == "success"
        assert m["published_at_missing"] is False

    def test_published_at_fallback(self, artifacts):
        article = _FakeArticle(publish_time=None)
        record = build_content_record(article, "acc_001", "name", artifacts)
        assert record.metadata["published_at_missing"] is True
        assert record.published_at is not None

    def test_published_at_int_timestamp(self, artifacts):
        article = _FakeArticle(publish_time=1700000000)
        record = build_content_record(article, "acc_001", "name", artifacts)
        assert record.published_at.year == 2023
        assert record.metadata["published_at_missing"] is False

    def test_serialization_roundtrip(self, artifacts):
        article = _FakeArticle()
        record = build_content_record(article, "acc_001", "name", artifacts)
        json_str = record.model_dump_json()
        from finer.schemas.content import ContentRecord
        restored = ContentRecord.model_validate_json(json_str)
        assert restored.content_id == record.content_id
        assert restored.source_platform == "wechat"

    def test_source_url_uses_normalized_article_url(self, artifacts):
        """source_url should use the normalized article_url, not raw content_url."""
        from finer.ingestion.wechat_exporter_client import WeChatArticleInfo
        article = WeChatArticleInfo(
            aid="art_001",
            title="Test",
            link="https://mp.weixin.qq.com/s/normalized",
            create_time=1700000000,
        )
        record = build_content_record(article, "acc_001", "name", artifacts)
        assert record.source_url == "https://mp.weixin.qq.com/s/normalized"

    def test_source_url_none_when_no_link(self, artifacts):
        from finer.ingestion.wechat_exporter_client import WeChatArticleInfo
        article = WeChatArticleInfo(aid="art_001", title="Test", link="", create_time=0)
        record = build_content_record(article, "acc_001", "name", artifacts)
        assert record.source_url is None

    def test_article_id_from_aid(self, artifacts):
        """Builder should normalize WeChatArticleInfo.aid to article_id."""
        from finer.ingestion.wechat_exporter_client import WeChatArticleInfo
        article = WeChatArticleInfo(
            aid="aid_12345",
            title="Test",
            link="https://example.com",
            create_time=1700000000,
        )
        record = build_content_record(article, "acc_001", "name", artifacts)
        assert record.metadata["article_id"] == "aid_12345"
