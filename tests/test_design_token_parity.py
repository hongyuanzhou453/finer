"""跨 app 设计令牌一致性守护。

两个 Next app 各有一份 `src/app/globals.css`，**逐字节相同但没有任何机制
保证它们保持相同**。它们今天一致纯属 site 侧自 2026-06-04 拷贝后没人动过，
而 dashboard 侧此后已有多次 token 改动。

失效方式是静默的：改 dashboard 的 `--chart-up`，公开站保持旧值，同一批
券商记录在两个界面上是两个颜色，没有任何测试会红。`check_contract_drift.py`
只校验 pydantic ↔ contracts.ts 的枚举值集，CSS 完全在守护外。

这条测试的判据是**逐字节相同**——刻意不做「语义等价」的宽松比较：
一旦允许差异，就得回答「哪些差异是允许的」，而那个清单会立刻开始腐烂。
两份要么合并成共享包（正确的终局），要么严格同步。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_CSS = REPO_ROOT / "src" / "finer_dashboard" / "src" / "app" / "globals.css"
SITE_CSS = REPO_ROOT / "src" / "finer_site" / "src" / "app" / "globals.css"

#: 两个 app 共用的工具函数。同样是双份手写，同样零守护。
DASHBOARD_UTILS = REPO_ROOT / "src" / "finer_dashboard" / "src" / "lib" / "utils.ts"
SITE_UTILS = REPO_ROOT / "src" / "finer_site" / "src" / "lib" / "utils.ts"

MIRRORED_FILES = [
    ("globals.css", DASHBOARD_CSS, SITE_CSS),
    ("lib/utils.ts", DASHBOARD_UTILS, SITE_UTILS),
]


def _digest(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("label,dash_path,site_path", MIRRORED_FILES)
def test_mirrored_file_is_byte_identical(label: str, dash_path: Path, site_path: Path) -> None:
    assert dash_path.exists(), f"{label}: dashboard 侧缺失 {dash_path}"
    assert site_path.exists(), f"{label}: site 侧缺失 {site_path}"

    dash_digest, site_digest = _digest(dash_path), _digest(site_path)
    assert dash_digest == site_digest, (
        f"{label} 在两个 app 之间已分叉——\n"
        f"  dashboard {dash_path.relative_to(REPO_ROOT)}  md5={dash_digest}\n"
        f"  site      {site_path.relative_to(REPO_ROOT)}  md5={site_digest}\n"
        "两份是手写副本，没有构建期同步。改了一侧必须同步另一侧，"
        "否则同一批数据在内部工作台与公开站会呈现成两套视觉。"
    )


def test_chart_direction_tokens_follow_china_convention() -> None:
    """红涨绿跌是全仓硬约定（CLAUDE.md 定位前提 / crd primitives）。

    钉住取值本身而不只是「两边一样」：两边一起改反了也必须报错。
    """
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    assert "--chart-up: #e11b22" in css, (
        "--chart-up 必须是红色（中国惯例：红=上涨/看多）"
    )
    assert "--chart-down: #10b981" in css, (
        "--chart-down 必须是绿色（中国惯例：绿=下跌/看空）"
    )
