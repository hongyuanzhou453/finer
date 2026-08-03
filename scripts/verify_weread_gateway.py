#!/usr/bin/env python3
"""Probe whether WeRead's official Agent Gateway can drive F0 WeChat discovery.

Background
----------
On 2026-07-29 WeChat closed the official-account article-search endpoint that
every self-hosted bridge depended on. Finer's WeChat channel now separates
*discovery* (which articles exist) from *fetch* (get one article's body), and
needs a discovery source that is neither dying nor account-risky.

The WeRead Agent Gateway is the only candidate that is officially sanctioned:
Tencent hands out a personal API key, so there is no reverse-engineered cookie
and no account to get banned. Its docs (github.com/Tencent/WeChatReading)
document official-account support — an account is a "book" and its articles are
"chapters":

    /store/search  scope=2  搜索公众号        → bookId
    /store/search  scope=4  搜索公众号文章
    /book/chapterinfo       chapters[].isMPChapter=1
    /shelf/sync             books[] 含公众号类书籍

What the docs do **not** say is whether any of that carries an
``mp.weixin.qq.com`` URL. Without one, discovery cannot hand anything to the
fetch leg and the gateway is useless for this pipeline no matter how well it
lists articles. That single question is what this script exists to answer, so
it dumps every response verbatim rather than trusting field names.

Usage
-----
    export WEREAD_API_KEY=wrk-...        # from https://weread.qq.com/r/weread-skills
    python scripts/verify_weread_gateway.py --account 肖小跑

The key is never printed or written to the dump files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

GATEWAY = "https://i.weread.qq.com/api/agent/gateway"
SKILL_VERSION = "1.0.4"

# The decisive signal: anything that can be turned into a fetchable article.
_URL_RE = re.compile(r"https?://mp\.weixin\.qq\.com/[^\s\"']+")
_BIZ_RE = re.compile(r"__biz=[A-Za-z0-9+/=]+|MP_WXS_[A-Za-z0-9+/=_-]+")


class GatewayError(RuntimeError):
    def __init__(self, status: int, payload: str) -> None:
        super().__init__(f"HTTP {status}: {payload[:200]}")
        self.status = status
        self.payload = payload


def call(api_name: str, key: str, **params: Any) -> Any:
    """POST one gateway call and return the decoded JSON."""
    body = {"api_name": api_name, "skill_version": SKILL_VERSION, **params}
    request = urllib.request.Request(
        GATEWAY,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "finer-f0/1.0 (+weread-gateway-probe)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise GatewayError(exc.code, exc.read().decode("utf-8", "replace")) from exc


def scan_for_fetchables(blob: Any) -> tuple[list[str], list[str]]:
    """Find anything in a response that could become a fetchable article.

    Searched over the serialized JSON rather than named fields, because the
    whole point is that we do not know which field (if any) carries a link.
    """
    text = json.dumps(blob, ensure_ascii=False)
    return sorted(set(_URL_RE.findall(text))), sorted(set(_BIZ_RE.findall(text)))


def dump(outdir: Path, name: str, blob: Any) -> Path:
    path = outdir / f"{name}.json"
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _walk_books(blob: Any) -> list[dict]:
    """Collect dicts that look like book entries, wherever they are nested."""
    found: list[dict] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if "bookId" in node:
                found.append(node)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(blob)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--account",
        action="append",
        default=[],
        help="Official-account name to search for (repeatable). Use accounts you follow.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("weread-gateway-probe"),
        help="Where to write the raw response dumps",
    )
    parser.add_argument("--interval", type=float, default=1.5, help="Seconds between calls")
    args = parser.parse_args()

    key = os.environ.get("WEREAD_API_KEY", "").strip()
    if not key:
        print(
            "WEREAD_API_KEY is not set.\n"
            "  1. open https://weread.qq.com/r/weread-skills and sign in to WeRead\n"
            "  2. copy the key (looks like wrk-...)\n"
            "  3. export WEREAD_API_KEY=wrk-...\n",
            file=sys.stderr,
        )
        return 2
    if not key.startswith("wrk-"):
        print(f"Key does not look like a gateway key (expected wrk-…): {key[:4]}…", file=sys.stderr)

    accounts = args.account or ["肖小跑"]
    args.outdir.mkdir(parents=True, exist_ok=True)
    verdict: dict[str, Any] = {"fetchable_urls": [], "biz_ids": [], "steps": []}

    def record(step: str, ok: bool, note: str, blob: Any = None) -> None:
        if blob is not None:
            urls, bizzes = scan_for_fetchables(blob)
            verdict["fetchable_urls"].extend(urls)
            verdict["biz_ids"].extend(bizzes)
        verdict["steps"].append({"step": step, "ok": ok, "note": note})
        print(f"  {'OK ' if ok else 'ERR'} {step}: {note}")

    print("\n=== 1. /_list — what does this key actually expose? ===")
    try:
        listing = call("/_list", key)
        path = dump(args.outdir, "00_list", listing)
        text = json.dumps(listing, ensure_ascii=False)
        names = sorted(set(re.findall(r'"(/[a-z_]+/[a-z_]+)"', text)))
        content_like = [n for n in names if re.search(r"content|read|text|body|article|mp", n)]
        record(
            "/_list",
            True,
            f"{len(names)} endpoints -> {path.name}; content-ish: {content_like or 'NONE'}",
            listing,
        )
        print(f"      endpoints: {', '.join(names) or '(could not parse names; see dump)'}")
    except GatewayError as exc:
        record("/_list", False, str(exc))
        if exc.status == 401:
            print("\nKey rejected. Re-copy it from the WeRead page and retry.", file=sys.stderr)
            return 1

    mp_book_ids: list[tuple[str, str]] = []

    for account in accounts:
        time.sleep(args.interval)
        print(f"\n=== 2. /store/search scope=2 — find 公众号 {account!r} ===")
        try:
            found = call("/store/search", key, keyword=account, scope=2)
            path = dump(args.outdir, f"10_search_scope2_{account}", found)
            books = _walk_books(found)
            for book in books[:5]:
                bid = str(book.get("bookId", ""))
                title = book.get("title") or book.get("name") or ""
                mp_book_ids.append((bid, title))
                print(f"      bookId={bid!r}  title={title!r}")
            record(
                f"/store/search scope=2 [{account}]",
                bool(books),
                f"{len(books)} book-like entries -> {path.name}",
                found,
            )
        except GatewayError as exc:
            record(f"/store/search scope=2 [{account}]", False, str(exc))

        time.sleep(args.interval)
        print(f"\n=== 3. /store/search scope=4 — 公众号文章 for {account!r} ===")
        try:
            found = call("/store/search", key, keyword=account, scope=4)
            path = dump(args.outdir, f"11_search_scope4_{account}", found)
            urls, _ = scan_for_fetchables(found)
            record(
                f"/store/search scope=4 [{account}]",
                True,
                f"-> {path.name}; mp.weixin URLs in payload: {len(urls)}",
                found,
            )
        except GatewayError as exc:
            record(f"/store/search scope=4 [{account}]", False, str(exc))

    time.sleep(args.interval)
    print("\n=== 4. /shelf/sync — do subscribed 公众号 appear as books? ===")
    try:
        shelf = call("/shelf/sync", key)
        path = dump(args.outdir, "20_shelf_sync", shelf)
        books = _walk_books(shelf)
        mp_like = [b for b in books if str(b.get("bookId", "")).startswith("MP_")]
        for book in mp_like[:10]:
            mp_book_ids.append((str(book["bookId"]), book.get("title", "")))
            print(f"      MP book: {book['bookId']!r}  {book.get('title', '')!r}")
        record(
            "/shelf/sync",
            True,
            f"{len(books)} books, {len(mp_like)} MP_* -> {path.name}",
            shelf,
        )
    except GatewayError as exc:
        record("/shelf/sync", False, str(exc))

    print("\n=== 5. /book/chapterinfo — is the chapter list an article list? ===")
    probed = 0
    for bid, title in mp_book_ids:
        if not bid or probed >= 2:
            continue
        probed += 1
        time.sleep(args.interval)
        try:
            info = call("/book/chapterinfo", key, bookId=bid)
            path = dump(args.outdir, f"30_chapterinfo_{bid.replace('/', '_')[:40]}", info)
            chapters = info.get("chapters") or []
            mp_chapters = [c for c in chapters if str(c.get("isMPChapter", "")) == "1"]
            urls, _ = scan_for_fetchables(info)
            record(
                f"/book/chapterinfo [{title or bid}]",
                True,
                f"{len(chapters)} chapters, {len(mp_chapters)} isMPChapter=1, "
                f"{len(urls)} mp.weixin URLs -> {path.name}",
                info,
            )
            for chapter in mp_chapters[:3]:
                print(f"      chapter: {chapter.get('title', '')!r} keys={sorted(chapter)[:12]}")
        except GatewayError as exc:
            record(f"/book/chapterinfo [{title or bid}]", False, str(exc))

    urls = sorted(set(verdict["fetchable_urls"]))
    bizzes = sorted(set(verdict["biz_ids"]))
    short_links = [u for u in urls if "/s/" in u]

    print("\n" + "=" * 68)
    print("VERDICT — can this gateway feed the F0 fetch leg?")
    print("=" * 68)
    print(f"  mp.weixin URLs anywhere in any response : {len(urls)}")
    print(f"    of which fetchable /s/<token> form    : {len(short_links)}")
    print(f"  __biz / MP_WXS identifiers             : {len(bizzes)}")
    if short_links:
        print("\n  USABLE. Discovery can hand short links straight to the fetch leg.")
        for u in short_links[:5]:
            print(f"    {u}")
    elif urls:
        print(
            "\n  PARTIAL. Article URLs exist but only in the long form, which WeChat\n"
            "  challenges unconditionally — the fetch leg cannot use them directly."
        )
        for u in urls[:5]:
            print(f"    {u}")
    elif bizzes:
        print(
            "\n  PARTIAL. Account identifiers are exposed but no article URLs, so\n"
            "  article titles could be listed but never fetched."
        )
    else:
        print(
            "\n  NOT USABLE for this pipeline. Nothing in any response can be turned\n"
            "  into a fetchable article. The gateway may still list article titles,\n"
            "  but titles alone cannot produce a ContentRecord with a body."
        )
    print(f"\n  Raw dumps for inspection: {args.outdir.resolve()}")
    dump(args.outdir, "99_verdict", verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
