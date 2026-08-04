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
    AlbumDiscovery,
    RssDiscovery,
    StaticUrlDiscovery,
    extract_article_urls,
)
from finer.ingestion.wechat_public_article import (
    ArticleState,
    RateLimiter,
    fetch_public_article,
    identity_from_url,
    is_fetchable_url,
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

        with pytest.raises(FinerError) as exc:
            fetch_public_article(ARTICLE_URL, attempts=2, limiter=None)
        # Lock the substance of the finding, not just "something was raised":
        # the shell must classify as BLOCKED (retryable), never EMPTY (terminal).
        assert exc.value.retryable is True
        assert (
            parse_public_article(shell.decode("utf-8"), ARTICLE_URL).state
            is ArticleState.BLOCKED
        )

    def test_unknown_charset_does_not_escape_the_line_f_envelope(self, monkeypatch):
        raw = _page(ARTICLE_BODY).encode("utf-8")
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.urllib.request.urlopen",
            _fake_urlopen(raw, charset="x-nonexistent-charset"),
        )
        article = fetch_public_article(ARTICLE_URL, limiter=None)
        assert article.state is ArticleState.OK
        assert article.title == "资本家真的能拯救地球吗？"

    def test_declared_charset_is_honoured(self, monkeypatch):
        raw = _page(ARTICLE_BODY).encode("gbk")
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.urllib.request.urlopen",
            _fake_urlopen(raw, charset="gbk"),
        )
        assert fetch_public_article(ARTICLE_URL, limiter=None).account_name == "肖小跑"

    def test_default_pacing_applies_when_no_limiter_is_named(self, monkeypatch):
        # import_article forwards no limiter, and must not thereby disable it.
        acquired = []
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.DEFAULT_RATE_LIMITER.acquire",
            lambda: acquired.append(1),
        )
        monkeypatch.setattr(
            "finer.ingestion.wechat_public_article.urllib.request.urlopen",
            _fake_urlopen(_page(ARTICLE_BODY).encode("utf-8")),
        )
        fetch_public_article(ARTICLE_URL)
        assert acquired == [1]

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


class TestBodyIsolation:
    """The body must end where ``#js_content`` ends.

    Python's HTMLParser is not HTML5-aware, so an unbalanced void tag inflates
    the nesting depth and the page footer bleeds into the article.
    """

    FOOTER = (
        '</div><div id="js_pc_qr_code">微信扫一扫关注该公众号</div>'
        '<div class="rich_media_area_extra">阅读原文 赞赏作者 预览时标签不可点</div>'
    )

    @pytest.mark.parametrize(
        "img",
        [
            '<img data-src="https://mmbiz.qpic.cn/a/640" />',  # self-closing
            '<img data-src="https://mmbiz.qpic.cn/a/640">',  # HTML5 void
            '<img data-src="https://mmbiz.qpic.cn/a/640"></img>',  # stray close
        ],
    )
    def test_footer_never_leaks_regardless_of_img_form(self, img):
        page = (
            f'<html><body><div id="js_content"><p>正文第一段</p><p>{img}</p>'
            f"<p>正文第二段。</p>{self.FOOTER}</body></html>"
        )
        article = parse_public_article(page, ARTICLE_URL)

        assert "微信扫一扫" not in article.markdown
        assert "预览时标签不可点" not in article.markdown
        assert "正文第二段。" in article.markdown
        assert article.image_urls == ("https://mmbiz.qpic.cn/a/640",)

    @pytest.mark.parametrize("br", ["<br>", "<br/>", "<br></br>"])
    def test_footer_never_leaks_regardless_of_br_form(self, br):
        page = (
            f'<html><body><div id="js_content"><p>正文{br}换行</p>{self.FOOTER}'
            "</body></html>"
        )
        assert "微信扫一扫" not in parse_public_article(page, ARTICLE_URL).markdown

    def test_leaked_footer_cannot_rescue_a_body_that_failed_to_render(self):
        # The worst consequence of the leak: boilerplate pushes a non-rendered
        # page past the length guard, so it is archived as a real article.
        page = (
            f'<html><body><div id="js_content"><p>加载中</p>'
            f'<p><img src="https://x/1"></p>{self.FOOTER}</body></html>'
        )
        assert parse_public_article(page, ARTICLE_URL).state is ArticleState.EMPTY

    def test_void_tag_in_the_title_does_not_swallow_the_metadata_block(self):
        page = (
            '<html><body><h1 class="rich_media_title" id="activity-name">标题<br>副标</h1>'
            '<a id="js_name">肖小跑</a>'
            f'<div id="js_content"><p>{"z" * 40}</p></div></body></html>'
        )
        article = parse_public_article(page, ARTICLE_URL)
        assert article.account_name == "肖小跑"
        assert "微信" not in article.title

    def test_whitespace_trimming_stays_linear(self):
        # The old `[ \t]+\n` post-pass backtracked quadratically, and WeChat
        # bodies carry multi-KB runs of &nbsp; padding.
        import time

        body = "<p>" + ("&nbsp;" * 40000) + "尾</p>"
        page = f'<html><body><div id="js_content">{body}</div></body></html>'
        started = time.perf_counter()
        parse_public_article(page, ARTICLE_URL)
        assert time.perf_counter() - started < 2.0


class TestStateVsProse:
    """State markers are ordinary Chinese sentences a real article may quote."""

    def test_article_quoting_the_deletion_notice_is_kept(self):
        body = (
            "<p>上周这家公司的文章被删了，页面显示「该内容已被发布者删除」。"
            "此内容因违规无法查看的情况也在增多，我们据此判断监管在收紧。</p>"
        )
        article = parse_public_article(
            f'<html><body><div id="js_content">{body}</div></body></html>', ARTICLE_URL
        )
        assert article.state is ArticleState.OK
        assert "该内容已被发布者删除" in article.markdown

    def test_genuine_interstitials_are_still_caught(self):
        for marker, expected in (
            ("该内容已被发布者删除", ArticleState.DELETED),
            ("此内容因违规无法查看", ArticleState.VIOLATION),
            ("当前环境异常，完成验证后即可继续访问", ArticleState.BLOCKED),
        ):
            page = f'<html><body><div class="weui-msg__title">{marker}</div></body></html>'
            assert parse_public_article(page, ARTICLE_URL).state is expected

    def test_captcha_shell_wins_even_when_a_body_is_present(self):
        # Structural markers cannot occur in prose, so they stay trusted.
        page = (
            "<html><script>var PAGE_MID='mmbizwap:secitptpage/verify.html';</script>"
            f'<div id="js_content"><p>{"x" * 50}</p></div></html>'
        )
        assert parse_public_article(page, ARTICLE_URL).state is ArticleState.BLOCKED


class TestIdentityIntegrity:
    """A fabricated id is worse than no import: it loses articles silently."""

    def test_long_form_urls_without_mid_do_not_collapse_onto_one_id(self):
        pages = [
            parse_bridge_article(
                ARTICLE_BODY, f"https://mp.weixin.qq.com/s?__biz=AAA&sn={sn}"
            )
            for sn in ("deadbeef", "cafebabe")
        ]
        # The path tail of a long-form URL is the bare "s"; using it would give
        # both articles the same content_id and lose the second as a duplicate.
        assert all(p.article_id != "s" for p in pages)
        assert all(not p.has_identity for p in pages)

    def test_import_skips_a_page_with_no_usable_identity(self, tmp_path):
        url = "https://mp.weixin.qq.com/s?__biz=AAA&sn=deadbeef"
        article = parse_bridge_article(ARTICLE_BODY, url)
        outcome = import_article(
            url, root=tmp_path, article=article, register_index=False
        )
        assert outcome.status == "skipped"
        assert "identity" in outcome.reason
        assert not list(tmp_path.rglob("*.json"))

    def test_two_distinct_long_form_articles_get_distinct_ids(self, tmp_path):
        urls = [
            f"https://mp.weixin.qq.com/s?__biz=AAA&mid=100{n}&idx=1&sn=x{n}"
            for n in (1, 2)
        ]
        outcomes = [
            import_article(
                u,
                root=tmp_path,
                article=parse_bridge_article(ARTICLE_BODY, u),
                acquired_via="bridge_content",
                register_index=False,
            )
            for u in urls
        ]
        assert [o.status for o in outcomes] == ["imported", "imported"]
        assert outcomes[0].content_id != outcomes[1].content_id


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
        # No id at all, rather than a placeholder every such page would share.
        assert article.article_id == ""
        assert not article.has_identity

    def test_containment_guard_fires_if_the_sanitizer_ever_regresses(self, tmp_path):
        # Guard the guard: bypass sanitization the way a future refactor might,
        # and confirm the write is refused rather than silently escaping.
        from finer.ingestion.wechat_url_intake import _assert_contained

        with pytest.raises(FinerError) as exc:
            _assert_contained(tmp_path, "../../..", "x", url=ARTICLE_URL)
        assert exc.value.retryable is False
        assert exc.value.stage == "F0"


SIGNED_LONG_URL = (
    "https://mp.weixin.qq.com/s?__biz=MzIyNjMxOTY0NA==&mid=2247506207&idx=1"
    "&sn=db096b2c1899da39180877c527a1ce7b&chksm=e870d56cdf075c7a496d3e9c0de6#rd"
)


class TestAlbumDiscovery:
    """A 合集 is the one bulk route that needs no credentials."""

    ALBUM_PAGE_1 = {
        "base_resp": {"ret": 0},
        "getalbum_resp": {
            "base_info": {"title": "AI技术与AI编程", "article_count": "3"},
            "continue_flag": "1",
            "article_list": [
                {
                    "title": "第一篇",
                    "url": "http://mp.weixin.qq.com/s?__biz=B&mid=101&idx=1&sn=a&chksm=c1",
                    "msgid": "101",
                    "itemidx": "1",
                    "create_time": "1785204245",
                },
                {
                    "title": "第二篇",
                    "url": "http://mp.weixin.qq.com/s?__biz=B&mid=100&idx=1&sn=b&chksm=c2",
                    "msgid": "100",
                    "itemidx": "1",
                    "create_time": "1785104245",
                },
            ],
        },
    }
    ALBUM_PAGE_2 = {
        "base_resp": {"ret": 0},
        "getalbum_resp": {
            "base_info": {"title": "AI技术与AI编程"},
            "continue_flag": "0",
            "article_list": [
                {
                    "title": "第三篇",
                    "url": "http://mp.weixin.qq.com/s?__biz=B&mid=99&idx=1&sn=c&chksm=c3",
                    "msgid": "99",
                    "itemidx": "1",
                    "create_time": "1785004245",
                }
            ],
        },
    }

    def _paged(self, monkeypatch, pages):
        calls: list[tuple[str, str]] = []

        def fake_page(self, begin_msgid="", begin_itemidx=""):
            calls.append((begin_msgid, begin_itemidx))
            return pages[len(calls) - 1]["getalbum_resp"]

        monkeypatch.setattr(AlbumDiscovery, "_page", fake_page)
        return calls

    def test_pages_to_the_end_of_the_album(self, monkeypatch):
        calls = self._paged(monkeypatch, [self.ALBUM_PAGE_1, self.ALBUM_PAGE_2])

        found = AlbumDiscovery("345788").discover()

        assert [a.title for a in found] == ["第一篇", "第二篇", "第三篇"]
        # Page 2 must resume from the last item of page 1, not restart.
        assert calls == [("", ""), ("100", "1")]

    def test_album_urls_are_directly_fetchable(self, monkeypatch):
        # This is what makes the album route self-sufficient: the listing hands
        # back chksm-signed URLs, and those fetch without a captcha.
        self._paged(monkeypatch, [self.ALBUM_PAGE_1, self.ALBUM_PAGE_2])
        found = AlbumDiscovery("345788").discover()
        assert all(a.fetchable for a in found)
        assert all(a.url.startswith("https://") for a in found)

    def test_account_name_comes_from_the_album_base_info(self, monkeypatch):
        self._paged(monkeypatch, [self.ALBUM_PAGE_1, self.ALBUM_PAGE_2])
        assert AlbumDiscovery("345788").discover()[0].account_name == "AI技术与AI编程"

    def test_stops_when_continue_flag_clears(self, monkeypatch):
        calls = self._paged(monkeypatch, [self.ALBUM_PAGE_2])
        assert len(AlbumDiscovery("345788").discover()) == 1
        assert len(calls) == 1

    def test_missing_album_is_not_retryable(self, monkeypatch):
        def fake_urlopen(request, timeout=None):
            class _R:
                def read(self):
                    return b'{"base_resp":{"ret":10004}}'

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

            return _R()

        monkeypatch.setattr(
            "finer.ingestion.wechat_discovery.urllib.request.urlopen", fake_urlopen
        )
        with pytest.raises(FinerError) as exc:
            AlbumDiscovery("does-not-exist").discover()
        assert exc.value.retryable is False


class TestUrlForm:
    def test_recognizes_fetchable_short_links(self):
        assert is_short_link(ARTICLE_URL)
        assert not is_short_link(LONG_FORM_URL)
        assert not is_short_link("https://example.com/s/abc")

    def test_chksm_signed_long_urls_are_fetchable(self):
        # Corrects an earlier belief that long-form URLs are always challenged:
        # the signature is what decides. Verified live — the same URL fetched a
        # 3.1MB article with chksm and the 17KB captcha shell without it.
        assert is_fetchable_url(SIGNED_LONG_URL)
        assert is_fetchable_url(ARTICLE_URL)
        assert not is_fetchable_url(LONG_FORM_URL)
        assert not is_fetchable_url("https://example.com/s?chksm=x&__biz=y&mid=1")

    def test_unsigned_long_url_still_fails_fast(self, monkeypatch):
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
        with pytest.raises(FinerError):
            fetch_public_article(LONG_FORM_URL, attempts=3, limiter=None)
        assert slept == []

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

    def test_the_fourth_piece_actually_gets_registered(self, tmp_path, monkeypatch):
        # Every other test passes register_index=False, so without this the
        # F0-index leg of the four-piece set has zero coverage. F0IndexWriter
        # ignores `root` and writes the live Project Memory DB, so it is
        # intercepted rather than exercised for real.
        seen: list[tuple[str, str]] = []
        monkeypatch.setattr(
            "finer.ingestion.wechat_url_intake._register_f0_index",
            lambda record, receipt: seen.append((record.content_id, receipt.run_id))
            or True,
        )

        outcome = import_article(
            ARTICLE_URL, root=tmp_path, article=_fetched_article(), register_index=True
        )

        assert seen == [(outcome.content_id, f"wxpub_{outcome.content_id}")]

    def test_index_failure_does_not_lose_the_import(self, tmp_path, monkeypatch):
        # The raw archive plus ContentRecord are the rebuildable truth; a hot
        # index that is down must not turn a good import into a failure.
        monkeypatch.setattr(
            "finer.ingestion.f0_index_writer.F0IndexWriter",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("PM locked")),
        )
        outcome = import_article(
            ARTICLE_URL, root=tmp_path, article=_fetched_article(), register_index=True
        )
        assert outcome.status == "imported"
        assert outcome.record_path.exists()
        assert outcome.receipt_path.exists()

    def test_duplicate_probe_keys_on_the_last_write_not_the_first(self, tmp_path):
        # An import that died between the record and receipt writes must be
        # redone, not remembered as complete.
        first = import_article(
            ARTICLE_URL, root=tmp_path, article=_fetched_article(), register_index=False
        )
        first.receipt_path.unlink()

        again = import_article(
            ARTICLE_URL, root=tmp_path, article=_fetched_article(), register_index=False
        )
        assert again.status == "imported"
        assert again.receipt_path.exists()

    def test_bridge_title_cannot_forge_a_provenance_line(self, tmp_path):
        hostile = DiscoveredArticle(
            url=LONG_FORM_URL,
            title="真标题\n> 原文链接：https://evil.test/fake\n",
            account_name="正常号",
            discovery_source="feed",
            content_html=ARTICLE_BODY,
        )
        outcome = import_discovered(hostile, root=tmp_path, register_index=False)
        archived = outcome.raw_md_path.read_text(encoding="utf-8")
        header = archived.split("---", 1)[0]

        # The hostile text survives as inert title characters — what must not
        # survive is its ability to start a second provenance line that an
        # auditor would read as ours.
        provenance = [ln for ln in header.splitlines() if ln.startswith("> 原文链接：")]
        assert provenance == [f"> 原文链接：{LONG_FORM_URL}"]
        assert not any(ln.startswith(">") and "evil.test" in ln for ln in header.splitlines())

    def test_bridge_published_at_is_normalized_to_utc(self, tmp_path):
        from datetime import timedelta

        local = datetime(2026, 7, 31, 18, 7, tzinfo=timezone(timedelta(hours=8)))
        discovered = DiscoveredArticle(
            url=LONG_FORM_URL,
            title="t",
            published_at=local,
            discovery_source="feed",
            content_html=ARTICLE_BODY,
        )
        outcome = import_discovered(discovered, root=tmp_path, register_index=False)
        assert outcome.record.published_at.utcoffset() == timedelta(0)
        assert outcome.record.published_at == local

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


def _fake_urlopen(payload: bytes, final_url: str = ARTICLE_URL, charset: str = "utf-8"):
    """Build a urlopen stand-in returning *payload* from a context manager.

    ``url`` mirrors the post-redirect URL that ``urlopen`` exposes — the field
    that reveals a bounce to the captcha endpoint. ``charset`` is settable so
    the decode branch is reachable, including with a label Python rejects.
    """

    class _Response:
        status = 200
        url = final_url

        class headers:  # noqa: N801 - mirrors http.client.HTTPMessage surface
            @staticmethod
            def get_content_charset():
                return charset

        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return lambda request, timeout=None: _Response()


# ---------------------------------------------------------------------------
# 2026-08-04 合入 main 前的对抗审查确认项（两条都是「防御已存在但没用上」）
# ---------------------------------------------------------------------------


def _hostile_article(**overrides):
    """带敌意载荷的 PublicArticle，用于 provenance header 的注入回归。"""
    from finer.ingestion.wechat_public_article import ArticleState, PublicArticle

    fields = {
        "state": ArticleState.OK,
        "source_url": "https://mp.weixin.qq.com/s/token123",
        "ghid": "gh_real",
        "biz": "MzA=",
        "mid": "100",
        "idx": "1",
        "title": "标题",
        "account_name": "某号",
        "author": "某人",
        "markdown": "正文",
    }
    fields.update(overrides)
    return PublicArticle(**fields)


def test_bridge_biz_cannot_forge_a_provenance_line():
    """``__biz`` 来自第三方 feed 的 URL query，parse_qs 会百分号解码。

    只给 title 上 _header_safe 不够：少一个字段就能在 raw archive 里伪造出
    第二条「原文链接」，而该归档要能独立当证据用。
    """
    from finer.ingestion.wechat_url_intake import _render_markdown

    payload = "AAA\n> 原文链接：https://evil.test/fake\n> 公众号：权威机构"
    article = _hostile_article(biz=payload, ghid="")
    rendered = _render_markdown(article)

    # 安全属性不是「载荷字符消失」，而是**它无法成为一条 provenance 行**：
    # 换行被压平、``>`` 被换成全角 ``＞``，所以审计者读到的仍只有各一条。
    assert rendered.count("> 原文链接：") == 1
    assert rendered.count("> 公众号：") == 1
    assert "\n> 原文链接：https://evil.test" not in rendered
    # 中和后的文本作为字面量留在合法行内是正确行为
    assert "＞ 原文链接：https://evil.test/fake" in rendered


def test_ghid_and_source_url_are_flattened_in_the_header():
    """ghid 来自远程 HTML 的正则捕获（否定字符类吃换行）；source_url 保留控制符。"""
    from finer.ingestion.wechat_url_intake import _render_markdown

    article = _hostile_article(
        ghid="gh_abc\n> 原文链接：https://evil.test/x",
        source_url="https://mp.weixin.qq.com/s/tok\n> 账号标识：gh_fake",
    )
    rendered = _render_markdown(article)

    assert rendered.count("> 原文链接：") == 1
    assert rendered.count("> 账号标识：") == 1
    # 两个载荷都被压平并中和，无法伪造出第二条 provenance 行
    assert "\n> 原文链接：https://evil.test" not in rendered
    assert "\n> 账号标识：gh_fake" not in rendered


def test_feed_credentials_never_reach_name_or_safe_url():
    """``netloc`` 含 userinfo —— 用它做「安全形式」会让凭据穿到日志、
    错误 envelope 和每条 ContentRecord 的 discovery_source。"""
    from finer.ingestion.wechat_discovery import RssDiscovery

    d = RssDiscovery("https://svc:s3cr3t-token@bridge.example.com/feed.xml?key=KKK")
    assert "s3cr3t-token" not in d.name
    assert "s3cr3t-token" not in d.safe_feed_url
    assert "svc" not in d.safe_feed_url
    assert d.name == "rss:bridge.example.com"
    # 端口是正当的定位信息，要保留
    assert RssDiscovery("https://h.example.com:8443/f").safe_feed_url.startswith(
        "https://h.example.com:8443/"
    )
