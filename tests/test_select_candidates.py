"""select_dpo_hq_candidates 筛选契约测试：根因2——非投资内容剔除 + 无标的 committal 降级。

守护候选池质量：committal 类别必须有可锚标的；飞书闲聊等非投资内容（旧逻辑因链接
英文串被 TICKER_RE 误命中而漏过）必须被剔除，避免下游 harvest 对其硬配/幻觉 ticker。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from select_dpo_hq_candidates import (  # noqa: E402
    classify,
    collect_candidates,
    groundable_entity_hits,
)


def test_groundable_excludes_bare_letters_from_links():
    # 飞书链接里的英文串不该算标的；严格 A股/港股代码才算
    assert groundable_entity_hits("整理的文档见 https://feishu.cn/docx/X26udWqtHo6nv") == []
    assert "601899" in groundable_entity_hits("紫金矿业 601899 超跌")
    assert "0700.HK" in groundable_entity_hits("腾讯 0700.HK 目标价")


def test_groundless_committal_downgraded_to_abstain():
    # 有 bullish 词「配置」但无可锚标的 → 降级 abstain，不进 bullish_action
    category, signals = classify("当前行情逢低配置，长期看好，注意分散持仓不要过度集中")
    assert category == "abstain"
    assert signals["groundable_hits"] == []


def test_grounded_committal_kept_as_action():
    # 有严格代码标的 + bullish 词 → 保留 bullish_action
    category, signals = classify("紫金矿业 601899 这次超跌，金价4500，逢低配置长期看好")
    assert category == "bullish_action"
    assert "601899" in signals["groundable_hits"]


def test_chitchat_filtered_grounded_kept(tmp_path):
    # 飞书闲聊（无标的/无价/无多空）应被 collect_candidates 剔除；有标的的投资段落保留
    chat = tmp_path / "chat_history_test.md"
    chat.write_text(
        "### [2026-03-01] maodaren (text)\n"
        "实验了一下飞书的小龙虾，感觉体验还不错，整理的文档可阅读性比之前更好了呢 "
        "https://feishu.cn/docx/X26udWqtHo6nv\n"
        "\n"
        "### [2026-03-02] maodaren (text)\n"
        "紫金矿业 601899 这次超跌，金价维持4500悲观情况净利润也有700亿，逢低配置长期看好基本面\n",
        encoding="utf-8",
    )
    rows, _ = collect_candidates(tmp_path, min_len=20, max_len=1600, exclude_ids=set())
    texts = [r["evidence_text"] for r in rows]
    assert not any("小龙虾" in t for t in texts), "闲聊段落应被剔除"
    assert any("紫金矿业" in t for t in texts), "有标的的投资段落应保留"
