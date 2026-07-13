"""Tushare fetcher behavior that does not require live network access."""

from __future__ import annotations

import pandas as pd

from finer.market_data.fetcher import BASIC_COLS, TushareFetcher


def _basic_row(ts_code: str, list_status: str) -> dict:
    return {
        "ts_code": ts_code,
        "symbol": ts_code[:6],
        "name": f"name-{ts_code}",
        "area": "深圳",
        "industry": "银行",
        "fullname": f"fullname-{ts_code}",
        "enname": f"en-{ts_code}",
        "cnspell": "spell",
        "market": "主板",
        "exchange": "SZSE",
        "curr_type": "CNY",
        "list_status": list_status,
        "list_date": "20200101",
        "delist_date": None,
        "is_hs": "N",
        "act_name": "act",
        "act_ent_type": "民营企业",
    }


class _FakePro:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def stock_basic(self, *, exchange: str, list_status: str, fields: str) -> pd.DataFrame:
        assert exchange == ""
        assert fields == ",".join(BASIC_COLS)
        self.calls.append(list_status)
        if list_status == "L":
            return pd.DataFrame([_basic_row("000001.SZ", "L")])
        if list_status == "D":
            return pd.DataFrame([_basic_row("000002.SZ", "D")])
        return pd.DataFrame(columns=BASIC_COLS)


def test_fetch_basic_queries_supported_statuses_separately() -> None:
    fetcher = TushareFetcher.__new__(TushareFetcher)
    fake = _FakePro()
    fetcher._pro = fake

    df = fetcher.fetch_basic()

    assert fake.calls == ["L", "D", "P"]
    assert list(df["ts_code"]) == ["000001.SZ", "000002.SZ"]
    assert list(df["list_status"]) == ["L", "D"]
    assert df.iloc[0]["list_date"].isoformat() == "2020-01-01"
