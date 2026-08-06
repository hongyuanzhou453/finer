"""进程启动时把仓库 ``.env`` 载入环境（标准库实现，无新依赖）。

来历：2026-08-06 跑 2026 段 F1 时报 ``No available models in registry``——
`.env` 就在仓库根目录，但整条流水线路径里没有任何地方加载它（``load_dotenv``
只出现在几个独立分析脚本里）。此前能跑通，靠的是启动 shell 恰好 export 过。
换个 shell、换个 launchd 任务就跑不起来，而报错信息指向「模型没配」，
与真实原因（环境没加载）隔着一层。

设计约束：

* **已存在的环境变量优先。** 显式 ``FOO=bar finer ...`` 或 CI secret 必须
  压过文件——文件是兜底，不是权威。
* **不打印任何值。** 只在 debug 级别记录「载入了几个键」。
* **坏行跳过，不抛异常。** 缺一个键的后果是下游报错，而整个 CLI 因为
  `.env` 里一行笔误就起不来，代价不成比例。
* 不引 ``python-dotenv``：它没在 ``pyproject.toml`` 里声明，靠它等于依赖
  一个隐式传递依赖。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_QUOTES = ("'", '"')


def _unquote(value: str) -> str:
    """去掉成对的首尾引号；不成对就原样返回（别猜用户的意图）。"""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in _QUOTES:
        return value[1:-1]
    return value


def load_env_file(path: Optional[Path] = None) -> int:
    """把 ``.env`` 里尚未设置的键载入 ``os.environ``，返回载入条数。

    找不到文件是正常情形（CI 用真实环境变量），返回 0。
    """
    if path is None:
        from finer.paths import REPO_ROOT

        path = Path(REPO_ROOT) / ".env"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    loaded = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        if not key or key in os.environ:
            continue          # 显式环境变量优先
        os.environ[key] = _unquote(value.strip())
        loaded += 1

    if loaded:
        logger.debug("loaded %d key(s) from %s", loaded, path.name)
    return loaded
