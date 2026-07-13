# P0 #1 收尾：F5 构造单一真相源收口 + legacy 隔离（2026-07-12）

## 概述（Overview）

Roadmap P0 #1（`docs/specs/2026-07-11-architecture-priorities.md`）的最后一段收尾。F5 TradeAction 的 canonical 构造已在此前收敛到单一 composer（`compose_trade_action`，见 [[p0-collar-driver-settle]]），本次补上 legacy 路径的**硬隔离门**：绕过 F3/F4 的 `trade_action_extractor.extract_from_text` 与 deprecated L0-L8 `pipeline/orchestrator.py` 现在在无逃生门时直接报错，杜绝新代码误挂 non-canonical 构造。全量测试 3245 通过（+2 gate 测试）。

## 变更清单（Changes）

| 文件 | 类型 | 内容 |
|---|---|---|
| `src/finer/extraction/trade_action_extractor.py` | 修改 | `extract_from_text`（所有 extract 路径的唯一漏斗、唯一通往本模块 legacy `TradeAction(` 构造的入口）在 deprecation warning 后加硬门：无 `FINER_ALLOW_LEGACY_PIPELINE=1` 则 `raise RuntimeError`；`import os` |
| `src/finer/pipeline/orchestrator.py` | 修改 | 模块顶部加导入门：无逃生门则 `raise ImportError`（deprecated L0-L8 编排器懒加载 legacy 直提器 + L0-L8 命名，新代码禁止导入） |
| `tests/test_extraction.py` | 修改 | autouse fixture 为既有 legacy 测试开逃生门（它们是迁移参考的钉子）；新增 `test_extract_from_text_raises_without_escape_hatch` + `test_orchestrator_import_raises_without_escape_hatch` 钉住门本身 |
| `AGENTS.md` | 修改 | 「最严重架构断点」从「F3→F4→F5 未闭环」更新为「已闭环」 |

## 架构影响（Architecture Impact）

- **单一真相源**：F5 canonical TradeAction 只经 `action_composer.compose_trade_action`（validate_structured_inputs 强制 intent_id/policy_id/evidence/timing）。`grep "TradeAction(" src/finer --type py`（schemas/tests 外）剩两处：composer（canonical 唯一点）+ legacy extractor line 417（`_action_from_data` 内，仅 `extract_from_text` 可达，gate 之后不可达 → 死代码）。验收的**意图**（无新代码路径能构造 non-canonical action）由运行时门保证，而非物理删除——roadmap 明确保留 legacy 为「只读迁移工具」。
- **live 消费者早已清零**：`POST /api/extraction/batch` 2026-07-11 已 410 退役（最后一个 legacy 直提消费者）；`execution/timing_policy.py` 仅文档提及；`pipeline/__init__.py` 不再 re-export orchestrator。本次是补上「入口报错」这道主动防线，而非移除仍在用的东西。
- **逃生门语义**：`FINER_ALLOW_LEGACY_PIPELINE=1` 仅供只读迁移工具显式开启（与既有 deprecation 纪律一致）；生产/测试默认关闭。gate 触发前仍发 DeprecationWarning，便于定位误用点。
- **F-stage 边界**：无跨层调用变更；纯粹是 F5 owning module 的入口收紧。

## 关键决策（Key Decisions）

1. **门而非删除**：roadmap 要求 legacy「隔离为只读迁移工具」，物理删除会丢掉迁移参考且属删除红线。硬门（raise + 逃生门）在保留代码的同时让它对新路径不可达——等价于「死代码 + 显式解锁」。
2. **门下在 `extract_from_text`**：该方法是 `extract_from_file` / `batch_extract` / `extract_with_enrichment` 全部路径的漏斗，也是唯一通往 line 417 legacy 构造的路。单点设门即封死整个模块的 non-canonical 出口。
3. **orchestrator 导入即报错**：编排器在导入时就懒加载 legacy 直提器，故把门设在模块顶部（import-time）而非某个方法，避免「导入成功但用时才炸」的半吊子状态。
4. **测试用逃生门开门 + 独立门测试**：既有 30 条 legacy 测试是迁移参考钉子，用 autouse fixture 开门保留；门本身由 2 条专门测试（关门态）钉住，双向都有覆盖。

## 验证结果（Verification）

```bash
pytest tests/test_extraction.py -q   # 30 passed（含 2 条新 gate 测试）
pytest tests/ -q                     # 3245 passed, 15 skipped

# 验收 grep（schemas/tests 外的真实构造点）
rg -n "[^_a-zA-Z]TradeAction\(" src/finer --type py | grep -v schemas/
#   action_composer.py:215   ta = TradeAction(**kwargs)      ← canonical 唯一点
#   trade_action_extractor.py:417  action = TradeAction(     ← gate 之后死代码
#   （其余命中为日志字符串 / 注释）
```

## 未解决项（Open Issues）

1. **grep 仍显 2 处而非 1 处**：legacy 构造物理存在（gate 之后死代码）。若未来判定迁移参考价值耗尽，可整体删除 `trade_action_extractor.py` 使 grep 归一；当前按 roadmap「保留为迁移工具」不删。
2. **逃生门无使用者**：`FINER_ALLOW_LEGACY_PIPELINE=1` 目前只有测试在用；若长期无真实迁移需求，可在下一轮直接删除 legacy 模块。
