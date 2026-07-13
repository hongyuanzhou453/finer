"""Daily-close price fetching via the Yahoo chart API (F8 price source).

Key-less public endpoint, verified 2026-07-02 to resolve every real ticker in
the live F5 set across US/HK/CN stocks and CN indexes. The two pre-existing
price paths are dead ends for this data (tushare: no token, empty parquet, no
index/US/HK coverage; finance-skills: no key and the remote service redirects
to a static page), so this is the pragmatic real-data source until a formal
provider lands in prices.py.

Caching: one JSON per ticker per day under ``data/cache/yahoo_prices/`` (the
cache tier is safe to clear per CLAUDE.md). Pass a different cache_dir to keep
dry-runs out of data/.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

from finer.paths import DATA_ROOT

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = DATA_ROOT / "cache" / "yahoo_prices"


def yahoo_symbol(ticker: str) -> str:
    """Map Finer tickers to Yahoo symbols (.SH -> .SS, DXY -> DX-Y.NYB)."""
    if ticker == "DXY":
        return "DX-Y.NYB"
    if ticker.endswith(".SH"):
        return ticker[:-3] + ".SS"
    return ticker


def fetch_daily_closes(
    ticker: str,
    cache_dir: Optional[Path] = None,
    range_: str = "1y",
    timeout: float = 20.0,
) -> List[Tuple[date, float]]:
    """Daily closes (ascending by date). Empty list when unresolvable.

    Results are cached per ticker per calendar day, so repeated pipeline runs
    within a day cost one request per ticker.
    """
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    cache_file = cache_dir / f"{ticker.replace('/', '_')}-{stamp}.json"

    if cache_file.exists():
        raw = json.loads(cache_file.read_text())
    else:
        sym = yahoo_symbol(ticker)
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{urllib.parse.quote(sym)}?range={range_}&interval=1d"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # 404 for pseudo-tickers, network errors, …
            logger.warning("yahoo fetch failed for %s (%s): %s", ticker, sym, e)
            raw = {"error": str(e)}
        cache_file.write_text(json.dumps(raw))

    try:
        result = raw["chart"]["result"][0]
        ts = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return []

    out: List[Tuple[date, float]] = []
    for t, c in zip(ts, closes):
        if c is not None:
            out.append((datetime.fromtimestamp(t).date(), float(c)))
    out.sort(key=lambda x: x[0])
    return out
