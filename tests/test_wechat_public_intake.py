"""F0 · credential-free WeChat article path: parser, discovery, and intake.

All offline. The page shapes below are minimal reconstructions of what
``mp.weixin.qq.com`` actually serves — the identifier block (``__biz`` /
``user_name`` / ``mid`` / ``idx`` / ``ct``), the ``#js_content`` body, and the
three interstitials that arrive as HTTP 200 with a short body.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from finer.errors import FinerError
from finer.ingestion.wechat_discovery import (
    RssDiscovery,
    StaticUrlDiscovery,
    extract_article_urls,
)
from finer.ingestion.wechat_public_article import (
    ArticleState,
    RateLimiter,
    fetch_public_article,
    identity_from_url,
    is_short_link,
    parse_bridge_article,
    parse_public_article,
    sanitize_path_component,
    validate_article_url,
)
from finer.ingestion.wechat_discovery import DiscoveredArticle
from finer.ingestion.wechat_url_intake import (
    import_article,
    import_article_urls,
    import_discovered,
)

ARTICLE_URL = "https://mp.weixin.qq.com/s/0IEaqpJIBGykHFKqj-7xqw"
LONG_FORM_URL = (
    "https://mp.weixin.qq.com/s?__biz=MzA3NTg4MDUzNQ=="
    "&mid=2657093642&idx=1&sn=d50dd36e9b3661ec17df4818ee53a240"
)


def _page(body: str, *, ct: int = 1717063839, extra_vars: str = "") -> str:
    return f"""<!DOCTYPE html><html><head>
<meta property="og:title" content="资本家真的能拯救地球吗？" />
</head><body>
<h1 class="rich_media_title" id="activity-name">资本家真的能拯救地球吗？</h1>
<a id="js_name">肖小跑</a>
<span id="js_author_name">肖小跑</span>
<script>
  var biz = "MzA3NTg4MDUzNQ==" || "";
  var mid = "2657093642" || "";
  var idx = "1" || "";
  var user_name = "gh_1652e0dbaabd";
  var author = "肖小跑";
  var msg_title = '资本家真的能拯救地球吗？'.html(false);
  var ct = "{ct}";
  {extra_vars}
</script>
<div class="rich_media_content " id="js_content">{body}</div>
</body></html>"""


ARTICLE_BODY = (
    "<p>最近刚忙完一件挺重要的事。</p>"
    "<p><strong>01</strong></p>"
    "<p>泰国有个地方叫Nan。楠府森林占土地面积85%，是泰国最大的水源林。</p>"
    '<p><img data-src="https://mmbiz.qpic.cn/sz_mmbiz_png/abc/640?wx_fmt=png" /></p>'
    '<p>详见<a href="https://example.com/report">这份报告</a>。</p>'
)


class TestUrlValidation:
    def test_accepts_public_article_url(self):
        assert validate_article_url(ARTICLE_URL) == ARTICLE_URL

    @pytest.mark.parametrize(
        "url",
        [
            "https://mp.weixin.qq.com.evil.test/s/abc",  # suffix-confusion host
            "http://example.com/s/abc",
            "ftp://mp.weixin.qq.com/s/abc",
            "not-a-url",
        ],
    )
    def test_rejects_non_wechat_urls(self, url):
        with pytest.raises(FinerError) as exc:
            validate_article_url(url)
        assert exc.value.retryable is False
        assert exc.value.stage == "F0"
        assert exc.value.source_channel == "wechat"


class TestParser:
    def test_extracts_identity_and_body(self):
        article = parse_public_article(_page(ARTICLE_BODY), ARTICLE_URL)

        assert article.state is ArticleState.OK
        assert article.ghid == "gh_1652e0dbaabd"
        assert article.biz == "MzA3NTg4MDUzNQ=="
        assert article.mid == "2657093642"
        assert article.idx == "1"
        # Identity keys on (mid, idx), never on the /s/ short-link token, which
        # is not unique per article.
        assert article.article_id == "2657093642_1"
        assert article.account_id == "gh_1652e0dbaabd"
        assert article.title == "资本家真的能拯救地球吗？"
        assert article.account_name == "肖小跑"
        assert article.author == "肖小跑"
        assert article.published_at == datetime(2024, 5, 30, 10, 10, 39, tzinfo=timezone.utc)

    def test_converts_body_to_markdown(self):
        article = parse_public_article(_page(ARTICLE_BODY), ARTICLE_URL)

        assert "**01**" in article.markdown
        assert "[这份报告](https://example.com/report)" in article.markdown
        assert "![](https://mmbiz.qpic.cn/sz_mmbiz_png/abc/640?wx_fmt=png)" in article.markdown
        assert article.image_urls == (
            "https://mmbiz.qpic.cn/sz_mmbiz_png/abc/640?wx_fmt=png",
        )
        assert "<p>" not in article.markdown

    def test_falls_back_to_short_link_token_without_mid(self):
        page = _page(ARTICLE_BODY).replace('var mid = "2657093642" || "";', "")
        article = parse_public_article(page, ARTICLE_URL)
        assert article.article_id == "0IEaqpJIBGykHFKqj-7xqw"

    @pytest.mark.parametrize(
        "marker,expected",
        [
            ("该内容已被发布者删除", ArticleState.DELETED),
            ("此内容因违规无法查看", ArticleState.VIOLATION),
            ("当前环境异常，完成验证后即可继续访问", ArticleState.BLOCKED),
        ],
    )
    def test_classifies_interstitials(self, marker, expected):
        page = f'<html><body><div class="weui-msg__title">{marker}</div></body></html>'
        assert parse_public_article(page, ARTICLE_URL).state is expected

    def test_blocked_wins_over_other_markers(self):
        # An interstitial that happens to mention deletion must still read as
        # BLOCKED — misreading it as DELETED would mark a live article dead.
        page = "<html><body>访问过于频繁 该内容已被发布者删除</body></html>"
        assert parse_public_article(page, ARTICLE_URL).state is ArticleState.BLOCKED

    def test_empty_body_is_not_ok(self):
        assert parse_public_article(_page("<p>  </p>"), ARTICLE_URL).state is ArticleState.EMPTY

    def test_missing_publish_time_is_none_not_now(self):
        page = _page(ARTICLE_BODY).replace('var ct = "1717063839";', "")
        assert parse_public_article(page, ARTICLE_URL).published_at is None


class TestFetch:
    def test_blocked_page_raises_rather_than_returning_data(self, monkeypatch):
        # Handing an interstitial downstream as if it were an article is the
        # "导入成功 ≠ 解析成功" failure the F0 contract forbids.
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.urllib.request.urlopen",
            _fake_urlopen("<html>访问过于频繁</html>".encode("utf-8")),
        )
        monkeypatch.setattr("finer.ingestion.wechat_public_article.time.sleep", lambda s: None)

        with pytest.raises(FinerError) as exc:
            fetch_public_article(ARTICLE_URL, attempts=2, limiter=None)
        assert exc.value.retryable is True
        assert exc.value.source_channel == "wechat"

    def test_deleted_page_is_returned_not_raised(self, monkeypatch):
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.urllib.request.urlopen",
            _fake_urlopen("<html>该内容已被发布者删除</html>".encode("utf-8")),
        )
        article = fetch_public_article(ARTICLE_URL, limiter=None)
        assert article.state is ArticleState.DELETED

    def test_carries_raw_html_for_archival(self, monkeypatch):
        raw = _page(ARTICLE_BODY).encode("utf-8")
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.urllib.request.urlopen",
            _fake_urlopen(raw),
        )
        assert fetch_public_article(ARTICLE_URL, limiter=None).html == raw

    def test_js_rendered_captcha_shell_is_blocked_not_empty(self, monkeypatch):
        # The captcha has a JS-rendered variant whose served HTML contains no
        # visible "环境异常" text at all. Reading it as EMPTY would be terminal,
        # silently retiring an article that is merely rate-limited.
        shell = (
            "<html><head><title></title></head><body><script>"
            "var PAGE_MID='mmbizwap:secitptpage/verify.html';</script></body></html>"
        ).encode("utf-8")
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.urllib.request.urlopen",
            _fake_urlopen(shell),
        )
        monkeypatch.setattr("finer.ingestion.wechat_public_article.time.sleep", lambda s: None)

        with pytest.raises(FinerError):
            fetch_public_article(ARTICLE_URL, attempts=2, limiter=None)

    def test_captcha_detected_from_redirect_url_alone(self):
        article = parse_public_article(
            "<html><body>nothing telling here</body></html>",
            ARTICLE_URL,
            final_url="https://mp.weixin.qq.com/mp/wappoc_appmsgcaptcha?poc_token=X",
        )
        assert article.state is ArticleState.BLOCKED

    def test_long_form_url_fails_fast_without_retrying(self, monkeypatch):
        # WeChat challenges long-form URLs unconditionally, so retrying only
        # burns the backoff window.
        slept: list[float] = []
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.urllib.request.urlopen",
            _fake_urlopen(
                "<html>访问过于频繁</html>".encode("utf-8"),
                final_url="https://mp.weixin.qq.com/mp/wappoc_appmsgcaptcha?poc_token=X",
            ),
        )
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.time.sleep", lambda s: slept.append(s)
        )

        with pytest.raises(FinerError) as exc:
            fetch_public_article(LONG_FORM_URL, attempts=3, limiter=None)

        assert exc.value.retryable is False
        assert slept == [], "must not back off on a permanently-unfetchable form"


class TestPathSafety:
    """Identifiers reach us from untrusted input and become path components.

    ``__biz`` is read straight out of a URL query supplied by a third-party RSS
    bridge; ``user_name``/``mid``/``idx`` are scraped from a remote page. All of
    them end up as directory and file names under ``data/raw/wechat/``.
    """

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("gh_1652e0dbaabd", "gh_1652e0dbaabd"),
            ("MzA3NTg4MDUzNQ==", "MzA3NTg4MDUzNQ=="),
            # base64's alphabet includes '/', which would silently split one
            # account across nested directories even with no attacker involved.
            ("MjM5N/Tc2MDYxMw==", "MjM5N_Tc2MDYxMw=="),
            ("../../../../tmp/pwned", ".._.._.._.._tmp_pwned"),
            ("..", "FB"),
            (".", "FB"),
            ("", "FB"),
            ("   ", "FB"),
            ("a/b\\c:d*e?f", "a_b_c_d_e_f"),
        ],
    )
    def test_sanitizer_never_yields_a_traversal_component(self, raw, expected):
        assert sanitize_path_component(raw, fallback="FB") == expected

    def test_sanitizer_bounds_length(self):
        assert len(sanitize_path_component("a" * 500, fallback="FB")) == 120

    def test_hostile_biz_cannot_escape_the_raw_archive(self, tmp_path):
        evil = (
            "https://mp.weixin.qq.com/s?__biz=../../../../tmp/pwned&mid=9&idx=1"
        )
        article = parse_bridge_article(ARTICLE_BODY, evil, title="t")
        assert "/" not in article.account_id

        outcome = import_article(
            evil,
            root=tmp_path,
            article=article,
            acquired_via="bridge_content",
            register_index=False,
        )

        assert outcome.status == "imported"
        raw_root = (tmp_path / "data" / "raw" / "wechat").resolve()
        assert raw_root in outcome.raw_md_path.resolve().parents
        for written in tmp_path.rglob("*"):
            assert tmp_path.resolve() in written.resolve().parents

    def test_short_link_tail_of_dotdot_does_not_become_the_article_id(self):
        article = parse_public_article(
            _page(ARTICLE_BODY).replace('var mid = "2657093642" || "";', ""),
            "https://mp.weixin.qq.com/s/..",
        )
        assert article.article_id == "unknown"

    def test_containment_guard_fires_if_the_sanitizer_ever_regresses(self, tmp_path):
        # Guard the guard: bypass sanitization the way a future refactor might,
        # and confirm the write is refused rather than silently escaping.
        from finer.ingestion.wechat_url_intake import _assert_contained

        with pytest.raises(FinerError) as exc:
            _assert_contained(tmp_path, "../../..", "x", url=ARTICLE_URL)
        assert exc.value.retryable is False
        assert exc.value.stage == "F0"


class TestUrlForm:
    def test_recognizes_fetchable_short_links(self):
        assert is_short_link(ARTICLE_URL)
        assert not is_short_link(LONG_FORM_URL)
        assert not is_short_link("https://example.com/s/abc")

    def test_identity_survives_in_the_long_url(self):
        assert identity_from_url(LONG_FORM_URL) == ("MzA3NTg4MDUzNQ==", "2657093642", "1")

    def test_identity_of_a_short_link_is_not_in_the_url(self):
        assert identity_from_url(ARTICLE_URL) == ("", "", "")


class TestRateLimiter:
    def test_paces_successive_acquires(self, monkeypatch):
        slept: list[float] = []
        clock = {"t": 100.0}
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.time.monotonic", lambda: clock["t"]
        )
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.time.sleep", lambda s: slept.append(s)
        )

        limiter = RateLimiter(6.0)
        limiter.acquire()
        limiter.acquire()

        assert slept == [6.0]

    def test_zero_interval_never_sleeps(self, monkeypatch):
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.time.sleep",
            lambda s: pytest.fail("should not sleep"),
        )
        RateLimiter(0).acquire()


class TestDiscovery:
    def test_extracts_urls_from_arbitrary_text(self):
        text = (
            "see https://mp.weixin.qq.com/s/AAA111 and "
            "https://mp.weixin.qq.com/s?__biz=X&amp;mid=1&amp;idx=1, plus "
            "https://example.com/not-wechat and a repeat "
            "https://mp.weixin.qq.com/s/AAA111"
        )
        urls = extract_article_urls(text)
        assert urls[0] == "https://mp.weixin.qq.com/s/AAA111"
        assert any("__biz=X" in u for u in urls)
        assert not any("example.com" in u for u in urls)
        assert len(urls) == 2, "duplicates must collapse"

    def test_rss_feed_yields_articles(self, monkeypatch):
        feed = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>肖小跑</title>
<item>
  <title>资本家真的能拯救地球吗？</title>
  <link>https://mp.weixin.qq.com/s/0IEaqpJIBGykHFKqj-7xqw</link>
  <pubDate>Thu, 30 May 2024 18:10:39 +0800</pubDate>
</item>
<item>
  <title>正文里才有链接的一篇</title>
  <link>https://bridge.example.com/redirect/2</link>
  <description>全文见 https://mp.weixin.qq.com/s/BBB222 谢谢</description>
</item>
</channel></rss>"""
        monkeypatch.setattr(RssDiscovery, "_fetch", lambda self: feed)

        found = RssDiscovery("https://feeds.example.com/x.xml", name="test-feed").discover()

        assert [a.url for a in found] == [
            "https://mp.weixin.qq.com/s/0IEaqpJIBGykHFKqj-7xqw",
            "https://mp.weixin.qq.com/s/BBB222",
        ]
        assert found[0].published_at is not None
        assert found[0].published_at.tzinfo is not None
        assert found[0].discovery_source == "test-feed"

    def test_malformed_feed_degrades_to_url_scan(self, monkeypatch):
        monkeypatch.setattr(
            RssDiscovery,
            "_fetch",
            lambda self: "<rss><item><link>https://mp.weixin.qq.com/s/CCC333</link></rss",
        )
        found = RssDiscovery("https://feeds.example.com/broken.xml").discover()
        assert [a.url for a in found] == ["https://mp.weixin.qq.com/s/CCC333"]

    def test_unreachable_feed_raises_retryable_error(self, monkeypatch):
        import urllib.error

        def boom(*args, **kwargs):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(
            "finer.ingestion.wechat_discovery.urllib.request.urlopen", boom
        )
        with pytest.raises(FinerError) as exc:
            RssDiscovery("https://feeds.example.com/down.xml").discover()
        assert exc.value.retryable is True
        assert exc.value.stage == "F0"

    def test_static_url_file_skips_comments_and_blanks(self, tmp_path):
        path = tmp_path / "queue.txt"
        path.write_text(
            "# 本周待抓\nhttps://mp.weixin.qq.com/s/AAA111\n\n"
            "  https://mp.weixin.qq.com/s/BBB222  \n",
            encoding="utf-8",
        )
        found = StaticUrlDiscovery.from_file(path).discover()
        assert [a.url for a in found] == [
            "https://mp.weixin.qq.com/s/AAA111",
            "https://mp.weixin.qq.com/s/BBB222",
        ]


def _fetched_article(url: str = ARTICLE_URL, body: str = ARTICLE_BODY):
    """Parse a page the way ``fetch_public_article`` does — carrying raw bytes.

    Passing ``raw`` matters: it is what makes the byte-exact HTML archive (and
    therefore the ``public_html`` receipt entry) exist.
    """
    source = _page(body)
    return parse_public_article(source, url, raw=source.encode("utf-8"))


class TestIntake:
    def test_produces_the_full_f0_four_piece_set(self, tmp_path):
        article = _fetched_article()

        outcome = import_article(
            ARTICLE_URL,
            root=tmp_path,
            article=article,
            discovery_source="test-feed",
            register_index=False,
        )

        assert outcome.status == "imported"
        record = json.loads(outcome.record_path.read_text(encoding="utf-8"))
        receipt = json.loads(outcome.receipt_path.read_text(encoding="utf-8"))

        assert record["source_type"] == "wechat_article"
        assert record["source_platform"] == "wechat"
        assert record["creator_id"] == "gh_1652e0dbaabd"
        assert record["external_source_id"] == "2657093642_1"
        assert record["metadata"]["discovery_source"] == "test-feed"
        assert record["metadata"]["acquired_via"] == "public_url"
        assert record["metadata"]["published_at_missing"] is False

        assert receipt["stage"] == "F0"
        assert receipt["source_channel"] == "wechat"
        assert receipt["status"] == "completed"
        assert receipt["records_created"] == 1
        assert set(receipt["raw_paths"]) == {"public_markdown", "public_html"}
        assert receipt["content_id"] == record["content_id"]

        raw_md = (tmp_path / "data" / "raw" / "wechat" / "gh_1652e0dbaabd" / "2657093642_1.md")
        assert raw_md.exists()
        assert "原文链接：" in raw_md.read_text(encoding="utf-8")

    def test_raw_archive_hashes_match_receipt(self, tmp_path):
        import hashlib

        article = _fetched_article()
        outcome = import_article(
            ARTICLE_URL, root=tmp_path, article=article, register_index=False
        )
        receipt = json.loads(outcome.receipt_path.read_text(encoding="utf-8"))

        for role, path in receipt["raw_paths"].items():
            actual = hashlib.sha256(open(path, "rb").read()).hexdigest()
            assert actual == receipt["raw_sha256"][role], f"{role} hash drifted"

    def test_reimport_is_idempotent(self, tmp_path):
        article = _fetched_article()
        first = import_article(
            ARTICLE_URL, root=tmp_path, article=article, register_index=False
        )
        second = import_article(
            ARTICLE_URL, root=tmp_path, article=article, register_index=False
        )

        assert first.status == "imported"
        assert second.status == "duplicate"
        assert second.content_id == first.content_id

    def test_force_overwrites_existing_record(self, tmp_path):
        article = _fetched_article()
        import_article(ARTICLE_URL, root=tmp_path, article=article, register_index=False)
        again = import_article(
            ARTICLE_URL, root=tmp_path, article=article, force=True, register_index=False
        )
        assert again.status == "imported"

    def test_content_id_is_stable_across_short_links(self, tmp_path):
        # The same article reached through a different /s/ token must land on
        # one record, not two, because identity keys on (account, mid, idx).
        page = _page(ARTICLE_BODY)
        first = import_article(
            ARTICLE_URL,
            root=tmp_path,
            article=parse_public_article(page, ARTICLE_URL),
            register_index=False,
        )
        other_url = "https://mp.weixin.qq.com/s/TOTALLY-DIFFERENT-TOKEN"
        second = import_article(
            other_url,
            root=tmp_path,
            article=parse_public_article(page, other_url),
            register_index=False,
        )
        assert second.status == "duplicate"
        assert second.content_id == first.content_id

    @pytest.mark.parametrize(
        "marker", ["该内容已被发布者删除", "此内容因违规无法查看"]
    )
    def test_dead_articles_are_skipped_without_writing_records(self, tmp_path, marker):
        article = parse_public_article(f"<html>{marker}</html>", ARTICLE_URL)
        outcome = import_article(
            ARTICLE_URL, root=tmp_path, article=article, register_index=False
        )

        assert outcome.status == "skipped"
        assert outcome.content_id is None
        assert not list(tmp_path.rglob("*.json")), "no record for a non-article page"

    def test_bridge_content_import_is_labelled_as_second_hand(self, tmp_path):
        # Wechat2RSS-class bridges emit only long-form URLs, which WeChat will
        # not serve. Their feed body is the usable payload — but the record has
        # to say so, never passing it off as a direct fetch.
        discovered = DiscoveredArticle(
            url=LONG_FORM_URL,
            title="资本家真的能拯救地球吗？",
            account_name="肖小跑",
            published_at=datetime(2024, 5, 30, 10, 10, 39, tzinfo=timezone.utc),
            discovery_source="wechat2rss:test",
            content_html=ARTICLE_BODY,
        )
        assert discovered.fetchable is False

        outcome = import_discovered(discovered, root=tmp_path, register_index=False)

        assert outcome.status == "imported"
        record = json.loads(outcome.record_path.read_text(encoding="utf-8"))
        receipt = json.loads(outcome.receipt_path.read_text(encoding="utf-8"))

        assert record["metadata"]["acquired_via"] == "bridge_content"
        assert record["metadata"]["discovery_source"] == "wechat2rss:test"
        # Identity still comes from the WeChat URL, not from the bridge.
        assert record["metadata"]["account_biz"] == "MzA3NTg4MDUzNQ=="
        assert record["external_source_id"] == "2657093642_1"
        assert list(receipt["raw_paths"]) == ["bridge_markdown"]
        assert "public_html" not in receipt["raw_paths"], "no page was served to archive"

    def test_unfetchable_url_without_bridge_content_is_skipped(self, tmp_path):
        discovered = DiscoveredArticle(url=LONG_FORM_URL, discovery_source="feed")
        outcome = import_discovered(discovered, root=tmp_path, register_index=False)
        assert outcome.status == "skipped"
        assert "not fetchable" in outcome.reason

    def test_bridge_content_can_be_refused_when_first_hand_is_required(self, tmp_path):
        discovered = DiscoveredArticle(
            url=LONG_FORM_URL, content_html=ARTICLE_BODY, discovery_source="feed"
        )
        outcome = import_discovered(
            discovered, root=tmp_path, register_index=False, allow_bridge_content=False
        )
        assert outcome.status == "skipped"

    def test_bridge_parse_produces_markdown_without_raw_html(self):
        article = parse_bridge_article(ARTICLE_BODY, LONG_FORM_URL, title="t")
        assert "**01**" in article.markdown
        assert article.html == b"", "there is no served page to archive"
        assert article.ghid == "", "a long-form URL identifies its account by __biz"
        assert article.account_id == "MzA3NTg4MDUzNQ=="

    def test_batch_keeps_going_after_one_failure(self, tmp_path, monkeypatch):
        good = _fetched_article()

        def fake_fetch(url, **kwargs):
            if "BAD" in url:
                raise FinerError("F0_EXT_001", "boom", stage="F0", source_channel="wechat")
            return good

        monkeypatch.setattr(
            "finer.ingestion.wechat_url_intake.fetch_public_article", fake_fetch
        )
        outcomes = import_article_urls(
            [
                "https://mp.weixin.qq.com/s/BAD000",
                ARTICLE_URL,
            ],
            root=tmp_path,
            register_index=False,
        )
        assert [o.status for o in outcomes] == ["failed", "imported"]


def _fake_urlopen(payload: bytes, final_url: str = ARTICLE_URL):
    """Build a urlopen stand-in returning *payload* from a context manager.

    ``url`` mirrors the post-redirect URL that ``urlopen`` exposes — the field
    that reveals a bounce to the captcha endpoint.
    """

    class _Response:
        status = 200
        url = final_url

        class headers:  # noqa: N801 - mirrors http.client.HTTPMessage surface
            @staticmethod
            def get_content_charset():
                return "utf-8"

        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return lambda request, timeout=None: _Response()
