# 契约漂移防护：pydantic ↔ contracts.ts 枚举一致性检查（2026-07-12）

## 概述（Overview）

Roadmap 横切纪律项落地：pydantic Literal/Enum 与前端 `contracts.ts` 字符串枚举的**值集**一致性此前靠人工纪律 + 零散钉子测试，现由 `scripts/check_contract_drift.py` 自动守护。首跑即暴露 10 个核心领域枚举（ActionType/TradeDirection/IntentTargetType…）在 contracts.ts 有定义但无自动化比对——现已全部入册，21 个镜像枚举全部在同步（手工纪律实际守住了，检查确认并锁死）。检查经 `pytest tests/test_contract_drift.py` 自动纳入现有测试门，无需额外 CI 配置。

## 变更清单（Changes）

| 文件 | 类型 | 内容 |
|---|---|---|
| `scripts/check_contract_drift.py` | 新增 | 解析 contracts.ts 字符串枚举 union（单行/多行/前导管道），对 curated `REGISTRY` 映射的 pydantic Literal/Enum 双向 diff 值集；漂移非零退出；未映射 TS 枚举提示登记 |
| `tests/test_contract_drift.py` | 新增 | 8 条：钉活契约零漂移 + REGISTRY 源可导入；证明守护能咬（值漂移/缺 TS 类型/未映射/stale 源检测）；parser 纯度（跳过 object/reference/mixed 类型） |
| `src/finer/schemas/trade_action.py` | 修改 | 提两个模块级 `*_LITERAL` 常量（`CANONICAL_TRACE_STATUS_LITERAL`、`INSTRUMENT_TYPE_LITERAL`）作单一真相源；`instrument_type` 字段引用常量 |
| `CLAUDE.md` | 修改 | §2 前后端契约同步段落加自动防护说明 |

## 架构影响（Architecture Impact）

- **CLAUDE.md §2 纪律自动化**：schema 是唯一真相源、contracts.ts 必须镜像——枚举值这一最脆弱面（精确字符串匹配，漂移静默丢数据）现由脚本兜底。字段名不在范围内（跨 snake_case↔camelCase 约定，由类型化 API 测试覆盖）。
- **单一真相源强化**：`canonical_trace_status` / `instrument_type` 的取值集此前散在 validator 体 / 内联 Literal 中，无法被检查诚实引用；提为模块级常量后，schema 定义本身成为脚本比对的唯一来源（脚本不硬编码任何值列表）。
- **CI 门**：`test_live_contracts_have_no_enum_drift` 使检查随 `pytest tests/` 运行——现有测试套件即 CI 门，零新增基建。脚本也可独立跑（`python scripts/check_contract_drift.py [--json]`）供 pre-commit / 前端流水线调用。
- **覆盖 21 个镜像枚举**：F0 SourceType、F3 intent 四枚举（direction/target_type/time_horizon/risk_preference/position_delta）、F5 TradeAction 七枚举（direction/action_type/trigger/exit_reason/market_session/instrument_type/validation_status/canonical_trace）、KOL EntryStyle、annotation 四枚举、WorkflowStage/ReviewDirection。

## 关键决策（Key Decisions）

1. **curated REGISTRY 而非自动发现**：「哪个 TS union 镜像哪个 pydantic 类型」自动推断脆弱（命名不严格对齐）。显式登记 `{ts_name: (module, attr, kind)}`，Python 侧 live import 取值——映射显式、值集单源。
2. **只查枚举值，不查字段名**：枚举值是精确字符串匹配、漂移后果最重且检测可靠；字段名跨命名约定，误报率高，交给类型化 API 测试。
3. **未映射 TS 枚举 = 提示而非失败**：纯前端枚举（WeChatLoginStatus 轮询态）合法无 pydantic 镜像，登记进 `UI_ONLY_TS_ENUMS`；新出现的未映射枚举触发提示，逼迫决策（登记映射 or UI-only），不静默放过。
4. **负向测试与正向同等重要**：绿灯只在「能抓漂移」时有价值——注入假 TS/假 REGISTRY 验证值漂移、缺类型、未映射、stale 源四类都被检出。
5. **提常量是最小单源改动**：不改字段类型语义（validator 仍自赋值），只把取值集从「散落」变「单点」，让检查有诚实来源。

## 验证结果（Verification）

```bash
python scripts/check_contract_drift.py
# ✓ contract enums in sync (21 mapped enums)   exit 0

pytest tests/test_contract_drift.py -q   # 8 passed
pytest tests/ -q                         # 3253 passed, 15 skipped
```

## 未解决项（Open Issues）

1. **字段名/可选性/嵌套结构漂移未覆盖**：本检查只管枚举值集。字段增删、optional 变必填、嵌套 shape 变化仍靠人工 + API 测试；若未来漂移频发，可扩展为从 pydantic `model_json_schema()` 生成期望 TS 并 diff（成本高，暂不做）。
2. **contracts.ts 侧靠正则解析**：只认 `export type X = "a" | "b";` 纯字符串 union；若前端改用 `enum {}` 或 `as const` 数组表达枚举，parser 需相应扩展。
3. **未接入前端 npm 流水线**：当前只在 Python 测试门运行；如需前端 `npm run build` 前也拦，可在 dashboard package.json 加 prebuild 调用（`python ../../scripts/check_contract_drift.py`）。
