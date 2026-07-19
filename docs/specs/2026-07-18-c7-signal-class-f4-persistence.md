# C7 · AUD-1/2 券商链 F4 落盘 + signal_class

> 版本：v1.0 | 日期：2026-07-18（跨零点收尾 07-19）| 执行：Opus 4.8
> 上游任务卡：`docs/specs/2026-07-18-phase0-activation-task-cards.md` §C7
> 依赖：F3→F4→F5 canonical 链（单一构造点 action_composer）

## ⚠️ 现状与任务卡假设不符（先读）

任务卡写「存量 **19** 条 bri action 补写」。**实际 live 状态是 1,773 条 bri action**（并行 scorecard 会话的放量已产出，见 [[broker-scorecard-v2]]）：

- 1,773 条 bri action 全部有 `policy_id`（UUID），**0 条有 F4 artifact 落盘**，**0 条有 `signal_class`**；
- driver 对这 1,773 条是 `already_actioned` 幂等跳过 —— **不会靠重跑再生**；另有 1,835 条 bri intent 因 `no_anchor_match` 无法出 action（evidence 缺口，是 C9 F2 重锚的活）；
- F4 artifact 以 `policy_id`（UUID）命名，故任务卡验收 `ls data/F4_policy_mapped/ | grep bri` 是基于错误假设的（永不匹配）。正确口径应为「bri action 的 policy_id 有对应 F4 文件」。

**本卡拆两半**：①**前向代码**（schema/composer/F4 落盘/contracts/drift）已完成并验证；②**1,773 条存量回填**是对另一会话产物的批量数据变更（且其 1,099 条已结算结果引用这些 action），按 AGENTS.md「批量重建须先获用户确认」+ 规模 88× 于卡假设，**已交用户决策，未擅自执行**。

## 1. 概述（Overview）

给 TradeAction 增结构化 `signal_class`（kol_statement / broker_recommendation），在单一构造点从 `intent.actionability` 派生；broker driver 把 F4 `PolicyMappingResult` 落盘到 `data/F4_policy_mapped/{policy_id}.json`（audit_assembler 读取约定），使 `/audit` 能解析 policy 段。前端契约 + drift guard 同步。

## 2. 变更清单（Changes，已完成的前向代码）

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/schemas/trade_action.py` | 修改 | 模块级 `SIGNAL_CLASS_LITERAL = Literal["kol_statement","broker_recommendation"]` + `TradeAction.signal_class: Optional[SIGNAL_CLASS_LITERAL] = None`（None = 该字段之前写的 legacy action，诚实「未分类」而非误标 kol） |
| `src/finer/extraction/action_composer.py` | 修改 | 新增 `derive_signal_class(intent)`（`actionability=="recommendation"`→broker_recommendation 否则 kol_statement）；`build_action_metadata` 把 signal_class 写进 metadata；`compose_trade_action` 在 kwargs 设 top-level `signal_class`。**单一构造点 + 四要素断言不破坏** |
| `scripts/drive_broker_recommendations.py` | 修改 | `--execute` 时把 `batch.mappings`（每个 `PolicyMappingResult`）落盘 `data/F4_policy_mapped/{policy_id}.json`；report 加 `F4 PolicyMappingResults persisted` 计数 |
| `src/finer_dashboard/src/lib/contracts.ts` | 修改 | `export type SignalClass = "kol_statement" \| "broker_recommendation"` + `TradeAction.signal_class?: SignalClass` |
| `scripts/check_contract_drift.py` | 修改 | REGISTRY 登记 `"SignalClass" → SIGNAL_CLASS_LITERAL` |
| `tests/test_action_composer.py` | 修改 | +3：kol/broker signal_class + metadata；字段默认 None |
| `tests/test_c7_f4_persistence.py` | 新增 | +2：F4 PolicyMappingResult 落盘↔读取 round-trip（policy_id 即 join key）；mapped_intent.policy_id 引用 result |
| `tests/test_pipeline_driver.py` | 修改（test-hygiene） | autouse fixture 强制 broker 卷「已挂载」，使 channel/stage 测试**独立于外置盘实际挂载态**；C6 挂载测试显式覆盖 |
| `src/finer/ingestion/broker_research_intake.py` | 修改（C6 guard 精化） | intake CLI guard 改为「meta 不可达 且 卷未挂载」才跳（真外置盘拔出），不再无条件查卷 —— 修掉「tmp meta + 盘掉线时误跳合法 dry-run」的 bug（本会话外置盘中途掉线暴露） |

## 3. 架构影响（Architecture Impact）

- **F4/F5 边界**：`signal_class` 在单一构造点 `compose_trade_action` 派生 —— 每条 canonical action（KOL + broker）都被分类，下游不再解析自由文本。四要素断言（intent_id/policy_id/evidence/execution_timing）与 canonical_trace_status 校验不变。
- **Schema 契约**：`SIGNAL_CLASS_LITERAL` 是单一真相源，镜像 `contracts.ts:SignalClass`，drift guard 守护（26 mapped enums）。
- **审计可解引用**：F4 落盘补上 audit_assembler 读取的 `F4_policy_mapped/{policy_id}.json` —— 新 broker drive 起，action 的 policy 段可解引用。
- **F3「搬运 risk_notes 标记」的更优实现**：结构化 `actionability→signal_class` 派生取代了解析 policy risk_notes 自由文本 —— 更鲁棒、可测（决策见 §4）。

## 4. 关键决策（Key Decisions）

1. **signal_class 从 actionability 派生，不解析 risk_notes**：卡②说「搬运 risk_notes 中的机构建议标记」。`actionability=="recommendation"` 是 policy 层已有的 canonical 机构标记（global_base 有专用 recommendation 分支），比 string-match risk_notes 稳健得多。故用结构化派生，metadata 也带一份（供只读 metadata 的审计工具）。
2. **字段默认 None 而非 kol_statement**：1,773 条 legacy action 无该字段，加载时若默认 kol_statement 会把 broker 全部**误标**成 KOL。默认 None = 诚实「未分类」，回填后才有值。
3. **前向代码与存量回填分离**：代码对 19 或 1,773 一样；回填是对 scorecard 会话 1,773 产物 + 其 1,099 结算结果的批量变更，规模与影响远超卡假设，**必须用户拍板**（见 §5 决策项）。
4. **test 独立于外置盘挂载态**：C6 挂载 guard 让「驱动 broker 项」的测试隐性依赖 `/Volumes/NAMEZY` 是否挂载（本会话中途该盘掉线，直接暴露此隐患）。autouse fixture 默认「已挂载」，使全套测试确定性 —— 这是 C6 该带的 test-hygiene，C7 顺手补上。

## 5. 存量 1,773 条回填 —— 待用户决策（未执行）

driver 幂等跳过存量，故回填需专用路径：①给 1,773 条 F5 action 补 `signal_class="broker_recommendation"`（全部 actionability=recommendation）；②按每条 action 已有的 `policy_id` 重建 `PolicyMappingResult` 落盘 F4（PolicyMapper 重跑会生成**新** UUID，故须强制沿用 action 存量 policy_id）。

风险点：变更的是 scorecard 会话的 1,773 产物，其 1,099 条已结算结果引用这些 action_id/policy_id。与 **C9**（F2 重锚 + 重驱动）存在关系 —— 若 C9 重驱动会以**新** id 再生这批，则本回填被覆盖且旧 id 的结算结果被孤立。**故回填方式需与 C9 计划一并定**。备份 `data/F5_executed` 先行是硬前提。

## 6. 验证结果（Verification，前向代码）

- drift guard：`scripts/check_contract_drift.py` → `✓ contract enums in sync (26 mapped enums)`。
- `tsc --noEmit`：CLEAN；`npm run build`：成功（全路由预渲染）。
- 后端全量：`pytest -q` → **3686 passed, 22 skipped**（基线 3681 + 新增 5；含 test-hygiene 修复，现独立于外置盘挂载态）。
- driver dry-run 实证：1,773 already_actioned + 1,835 no_anchor_match（印证存量需回填、evidence 缺口是 C9 的活）；F4 落盘是 `--execute` 分支，dry-run 不写。

## 7. 未解决项（Open Issues）

- **存量 1,773 回填未执行**（§5）—— 待用户决策回填方式（与 C9 关系）+ 备份后执行。
- **验收口径修正**：卡的 `grep bri` 不适用（F4 按 UUID policy_id 命名）；正确口径 = bri action 的 policy_id 有对应 F4 文件 + `/audit` 三段非空。
- **1,835 no_anchor_match intent**：evidence 缺口，C9 F2 重锚后可出 action —— 不在 C7 范围。
