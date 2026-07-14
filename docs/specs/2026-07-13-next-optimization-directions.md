# 下一步项目优化方向（2026-07-13）

## 概述（Overview）

对 `docs/specs/2026-07-11-architecture-priorities.md` 的 P0/P1/P2 backlog 做一轮**只读核实**，对照真实代码/磁盘数据判定"已完成声明"的落地程度，产出按依赖排序的下一步优化方向。**核心结论：整条 F0–F8 已"编码 + 测试"齐备，但从未跑出过一次真实的新鲜活水（1 个真实 KOL、42 条陈旧 action、增量驱动器真实吞吐为 0）。下一阶段主轴是"激活"而非写新特性——把已建好但从不自动运行的链路真正跑起来，产生可见的持续产出，再谈放量与产品纵深。**

本轮为分析型任务，未改动任何代码 / schema / 契约。本文档即交付物。

## 变更清单（Changes）

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `docs/specs/2026-07-13-next-optimization-directions.md` | 新增 | 本文档（下一步方向 roadmap） |
| 代码 / schema / contracts.ts | 无 | 只读评估，零改动 |

> 落地后续实现时，每条方向对应的 owning files 见下方「下一步方向」的「第一步落点」。

## 架构影响（Architecture Impact）

本轮不改架构，但下一步方向会触及以下边界，实现时须遵守：

- **F0→F8 增量驱动器（方向①②）**：新增自动触发点属 cross-stage 编排，只能落在 `pipeline/driver.py` + 触发层（`api/server.py` lifespan 或调度器），**不得**在触发层写业务逻辑，`drive_once` 仍是唯一编排单元。per-envelope 隔离失败按 Line F envelope 上报。
- **数据 materialize（方向③⑥）**：`scripts/regen_canonical_f5.py` 会**清写** `data/F3_intents/`、`data/F4_policy_mapped/`、`data/F5_executed/`、F2_evidence sidecar —— 踩 CLAUDE.md 删除红线，每次执行前必须获得用户确认。
- **F2 实体注入（方向⑥）**：批量 LLM proposal + `entity_registry.py` 写入，踩批量 LLM 与 registry 写红线，需显式授权。
- **F4 可调面（方向⑧）**：`configs/skills/f3f4-policy.yaml` 接入 policy loader，把 `policy/global_base.py` 的硬编码阈值升级为分层 hint —— 属 F4 owning，不跨层。
- **前端导航（方向⑦）**：`src/finer_dashboard/**` 属前端 surface，改导航 + 让 `api/routes/kol.py` 改读 `F5_executed`，不动 F0-F8 后端契约。
- **契约同步纪律**：任何 schema 改动仍须同步 `contracts.ts`，由 `scripts/check_contract_drift.py` 守护（须在 `.venv` 内运行，见验证结果）。

## 关键决策（Key Decisions）

1. **主轴定为"激活"而非"加特性"**。核实发现瓶颈不是缺功能，而是**已建成的链路从未真实运行**：增量驱动器非事件驱动、真实吞吐为 0；sector-proxy 改进只在 spec 离线叙事里、磁盘未 materialize。在"代码已 landed、数据未 materialize、驱动器没真跑过"的分裂状态上做任何自动化/批量动作 = 批量生产不一致（07-05 regen 已实证过一次）。因此顺序必须先激活再放量。
2. **依赖链严格串行**：①自动触发 → ②真实 E2E + 修 F0 原子性 → ③materialize 质量改进 → ④多 KOL 放量 → ⑤放量前验证 F1.5（llm 共识模式）→ ⑥抬 F2 天花板。⑦前端导航、⑧F4 可调面无数据依赖，可与主轴并行。
3. **P2 判定为时过早**：持仓簿（`position_delta_pct` 全语料 0/42、6 个加减仓事件跨 1 个 KOL）与 DPO 实训（`data/rlhf/feedbacks/` 为 0 文件）前置未满足，roadmap 自身已把 P2 门控在"P0 出活水后"，而现在 P0 出的是一滩不是流。
4. **F5 legacy 死代码不物理删除**：collar 已逻辑闭环，`trade_action_extractor.py:417` 是门后死代码；物理删除踩删除红线且 spec 明确保留为只读迁移工具，留待下一轮判定迁移价值耗尽后经确认再删。

## 已收口 vs 有残留（核实结论）

| 项 | 07-11 声称 | 核实结论（file:line 佐证见下方验证） |
|---|---|---|
| P0#1 F5 单一真相源 | 完成 | ✅ **真闭环**。canonical 只经 `extraction/action_composer.py:215`；legacy `extract_from_text`/`orchestrator` 无逃生门即运行时 raise；消费者已清零 |
| P0#3 F8 settle owner | 部分 | ✅ **真实且跑过真数据**。`backtest/settle.py:123` 完整状态机；磁盘 42 action = 9 verified/23 failed/10 pending，被收益榜真实消费 |
| P1#6 F1.5 接线 | 完成 | 🟡 **确在生产路径**（`pipeline/canonical_runner.py:558` + `pipeline/driver.py:147`），但只在 rule extractor 下验证；**现役 llm 共识模式下对方向的影响 0 测试** |
| P1#5 F2 sector proxy | 完成 | 🟡 **代码真、数据假**。`configs/sector_proxies.yaml` + 门都 wire，但 live `F5_executed` 仍 42 条、**零 sector_proxy 元数据、无 159566.SZ**；42→44 只是离线叙事 |
| 契约漂移防护 | 完成 | ✅ 完全落地，`.venv` 内 exit 0 / 21 mapped enums / 8 tests passed |
| **P0#2 增量驱动器** | 部分 | 🔴 **最大残留**。`drive_once` 逻辑齐全，但**非事件驱动**（全仓无 scheduler/startup hook，唯一自动化是 `--watch` 前台循环需人肉常驻），且**从未在真实新导入上跑通**（真实运行 f1/f2/f5_ran=0） |

## 下一步方向（按依赖 × 价值排序）

### 主轴：激活链路（必须串行）

**① 给增量驱动器接自动触发** — 工作量 M，无依赖
下游全就绪，只差触发器。第一步落点：`api/server.py` 加 FastAPI lifespan 后台任务按间隔调 `pipeline/driver.py:381 drive_once()`（或 `ingestion/f0_index_writer.py` commit 后 enqueue，或 launchd 跑 `finer.cli pipeline-drive` + `settle --apply`）。把 `--watch` 手动前台变成真正刷新周期。

**② 跑通一次真实 E2E + 修 F0 写原子性** — 工作量 S，依赖①
导入 1 条真实内容，确认走完 F1→F1.5→F2→F5→F8→settle 并在 `/api/opinions/timeline` 出现 verificationStatus。同一次修掉 `content_id f8f70a…`（`stage_status` 有 F0=ready 但 `F0_intake` 下无 ContentRecord）这个每轮 drive 都报的孤儿失败——改 `f0_index_writer.py` 让记录文件与索引行原子写入，或加 reconciler 清孤儿行。

**③ 把 sector-proxy 改进 materialize 到 live 数据** — 工作量 S，需红线确认
跑 `scripts/regen_canonical_f5.py` 从当前代码重生成 canonical F5（⚠️ 清写 F3/F4/F5/F2_evidence sidecar，删除红线，先确认）。随后把 `scripts/check_f2_coverage_regression.py` 的 all-local `min_hit_rate` 从 0.165 提到 ~0.222 锁住增益。

**④ 多 KOL 放量：从 1 扩到 3+** — 工作量 L，依赖①②
绑定约束是体量不是接线（42 action / 6 加减仓 / 本质只 trader_ji）。P1#4 registry 已把 onboarding 变成"加一份 YAML"。补 2–3 个创作者 `configs/creators/*.yaml`（含 trading_style 块，参照 `trader_ji.yaml`）+ 导入真实内容，靠①的驱动器推过全链。

**⑤ 放量前：在 llm 共识模式验证 F1.5** — 工作量 M，依赖①④
F1.5 唯一安全性证据是 rule extractor 的 parity，但现役生产 F3 是 llm 3-run 共识。在 `FINER_F3_EXTRACTOR=llm` 下跑 whole-envelope vs per-topic 离线对比，测 direction-flip 率与共识稳定性；补一条 `FINER_F15_ASSEMBLER=llm` 的 runner 集成测试（mock adapter）。**必须在④放量前完成**，否则自动化会把长内容质量问题批量化。

**⑥ 抬 F2 中文命中率天花板** — 工作量 L，依赖③，需红线确认
22.2% 增益来自手工 registry 编辑；已验证的 `enrichment/llm_entity_proposal.py`（conf≥0.8 precision 100%）在生产里完全 idle（仅插了 地平线/吉利 2 个实体）。用 `scripts/eval_f2_llm_proposals.py` 对 all-local gap cohort 全量 propose，只收 conf≥0.8、人工核验后批量写入 `entity_registry.py`。

### 可与主轴并行的独立项（无数据依赖）

**⑦ 把 live `/radar` 接进导航** — 工作量 S
单点最高杠杆 UI 修复：live 流水线已渲染真实数据，但导航（`src/finer_dashboard/src/components/layout/header.tsx:19`）指向读**空** `L5_candidate/L6_annotated` 目录的 `/kol`。加 `/radar` 导航项（或 repoint `/kol`），顺带把 `api/routes/kol.py` 的 `/list/enriched` + `/rating` 改读 `F5_executed`（复用 `opinions.py:_load_all_actions`）。

**⑧ 造 F4 分层调参地基** — 工作量 S
P2#8 的"止损/止盈按风格分层"挂在不存在的可调面上：`configs/skills/f3f4-policy.yaml` 未被任何代码加载，F4 阈值仍硬编码在 `policy/global_base.py:342-344`。把 yaml 接进 policy loader，纯确定性、零烧钱、零数据依赖。

## 明确不做 / 为时过早

- **P2#7 持仓簿连续模拟**：`position_delta_pct` 全语料 0/42（composer 按设计不编数字），真实数据只有 6 个加减仓事件跨 1 个 KOL，做不出仓位轨迹/成本价；全仓零 portfolio-sim 雏形。须等④放量出真实加减仓流；若必须切入只能做不需幅度的"方向态时间线"最小薄片。
- **P2#8 DPO 实训 / 奖励回路**：环 B 反馈飞轮 100% 卡在 `data/rlhf/feedbacks/` 为空（0 文件），`ml/rewards.py`（446 行）全就绪但 sink 空、`score_extraction`/`pair_preference` 无生产调用方。真正前置是用 RLHFReviewPanel 对已结算 42 条 action 做人工审核积累偏好对；上百条前不启动实训。
- **F5 legacy 死代码物理删除**（`trade_action_extractor.py:417` + 逃生门 + 死 shim `src/finer/pipeline.py`）：collar 已逻辑闭环，物理删除踩删除红线，下轮判定迁移价值耗尽后经确认再删。
- **F1.5 LLM assembler 默认开启**：rule/anchor 路径已在真实语料达成 parity 无 recall loss，默认开会增成本/延迟/非确定性且有 anchor-seed 盲点（`topic_routing.py:136` 未传 extra_rules），保持 opt-in。

## 验证结果（Verification）

方法学：6 个只读评估 agent 并行核实各优先级轴（709k tokens / 137 tool calls），每条结论 file:line 佐证；下方为落文档前在本机新鲜复跑的关键数字（`.venv/bin/python`，2026-07-13）。

```
[1] F5 action 计数 + 结算态
    files=12 actions=42
    validation_status={'failed':23,'pending':10,'verified':9}
    position_delta_pct non-null = 0/42
    sector_proxy-tagged = 0            ← 证实 sector-proxy 未 materialize

[2] TradeAction( 物理构造点（P0#1 验收）
    action_composer.py:215      ← canonical 唯一构造点
    trade_action_extractor.py:417 ← legacy，门后死代码（extract_from_text 无逃生门即 raise）
    golden_path.py:214 / action_composer.py:20 ← 日志串 / 注释（非构造）

[3] 真实 KOL / 反馈 sink / 自动触发
    creators yaml = 3 (trader_ji / 9you / maodaren；后两者仅壳)
    rlhf feedbacks files = 0          ← 环 B 飞轮无数据
    scheduler/startup hooks = 0        ← 驱动器非事件驱动

[4] 契约漂移防护（.venv/bin/python）
    scripts/check_contract_drift.py → EXIT=0，✓ 21 mapped enums
    pytest tests/test_contract_drift.py → 8 passed
```

> 注：`check_contract_drift.py` / 依赖 `finer` 包的脚本必须在 `.venv/bin/python`（`pip install -e` 环境）内运行；用系统 homebrew Python 3.14 会 `ModuleNotFoundError: No module named 'finer'`，是环境问题非真实 drift。

## 未解决项（Open Issues）

- 本轮为只读评估，未实际执行任何方向；①–⑧ 的实现验收待各自落地时补。
- F5 legacy 物理删除、F1.5 LLM 默认开启的最终判定留待下一轮（见「明确不做」）。
- 漏斗 rejection 明细（F3 consensus-validator drop + F5 RejectedIntent）目前散落在 per-envelope `notes.json` 且 in-memory，未持久化为单一报告——决定下一轮质量投入优先级前值得先 instrument（评估轴 P1-f2-funnel 的中优先级建议）。
