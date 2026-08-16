"""已发布的 /records 快照必须自身守住比率纪律。

这条测试**对真实发布物跑全量扫描**，不是喂构造 fixture。教训来自本项目两次
同型事故：单测全绿、linter 退出码 0，而真文件里的违规原样发出去了
（见 memory/xhs-cold-start-buildout「测试钉行为钉不住内容」）。

红线（`docs/specs/2026-08-02-positioning-pivot-proposal.md` §3.2、CLAUDE.md
「定位前提」第 1 条）：任何比率离开后端必须携带 sufficiency；前端按
`display_policy` 呈现，``count_only`` 时**不得渲染任何比率**。

快照是冻结档案：它一旦发布就不再重跑流水线，所以纪律必须钉在**快照文件本身**，
而不只是钉在渲染它的组件上。组件的门可以被绕过（曾经就是：门开在了门外），
但只要快照里 count_only 的卡不带比率字段实值，就没有东西可以泄漏。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "src" / "finer_site" / "public" / "records-data" / "manifest.json"

#: count_only 的卡上不得出现实值的比率字段。
_RATIO_FIELDS = ("mean_return", "median_return", "expected_win_rate")


def _cards():
    if not MANIFEST.is_file():
        pytest.skip(f"未导出快照：{MANIFEST}")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for signal_class, cards in (data.get("cards") or {}).items():
        for card in cards:
            yield signal_class, card


def test_count_only_cards_carry_no_ratio_values():
    """样本不足的卡不得携带任何比率实值。

    回归：2026-08-10 发布的快照里 34 张 count_only 卡有 24 张带 mean_return
    实值——其中 KeyBanc 只有 1 条已结算，卡面印着 +58.0%。
    """
    offenders = []
    for signal_class, card in _cards():
        if card["sufficiency"]["display_policy"] != "count_only":
            continue
        for field in _RATIO_FIELDS:
            if card.get(field) is not None:
                offenders.append(
                    f"{signal_class}/{card['creator_id']}"
                    f"(n_settled={card['n_settled']}) {field}={card[field]}"
                )
    assert not offenders, (
        "count_only 的卡带了比率实值，前端任何一处漏门都会把它印出去：\n  "
        + "\n  ".join(offenders)
    )


def test_every_card_declares_sufficiency():
    """比率纪律的前提：每张卡都必须带 sufficiency 与 display_policy。"""
    for signal_class, card in _cards():
        s = card.get("sufficiency")
        assert s, f"{signal_class}/{card['creator_id']} 缺 sufficiency"
        assert s.get("display_policy") in {"show", "show_with_warning", "count_only"}
        assert s.get("tier") in {"sufficient", "provisional", "insufficient"}


#: 已知的越窗信源（棘轮基线）。这些是 **F3 里的 report_date 抽取错误**，
#: 不是历史：抽检 n=150 抓到巴克莱那条，回原 PDF 实为 2025-11-13，claim 记成
#: 2023-11-13，差整两年；全语料共 5 条 2023 年日期 + 1 条 2026-12-16（未来）。
#: 修数据需用户授权，未修之前先钉住不许变多。修完请清空本集合。
_KNOWN_OUT_OF_WINDOW = {"摩根士丹利", "花旗", "巴克莱"}


def test_no_new_record_window_outside_the_corpus():
    """记录窗口越出语料覆盖窗的信源**不得增加**（棘轮）。

    落在窗外的日期是抽取错误，会让卡面的「记录窗口」凭空长出两年
    （花旗卡面现在写着「2023-11-27 起」）。
    """
    lo, hi = "2025-06-01", "2026-09-01"   # 语料窗前后各留足余量
    offenders = {
        c["creator_id"]: f"{c['first_action_at'][:10]} – {c['last_action_at'][:10]}"
        for _, c in _cards()
        if not (lo <= c["first_action_at"][:10] <= hi)
        or not (lo <= c["last_action_at"][:10] <= hi)
    }
    new = set(offenders) - _KNOWN_OUT_OF_WINDOW
    assert not new, (
        "新增了记录窗口越出语料覆盖窗的信源（抽取错误，非历史）：\n  "
        + "\n  ".join(f"{k} {offenders[k]}" for k in sorted(new))
    )
    if not offenders and _KNOWN_OUT_OF_WINDOW:
        pytest.fail(
            "越窗信源已清零——请清空 _KNOWN_OUT_OF_WINDOW，让这条恢复为硬门。"
        )
