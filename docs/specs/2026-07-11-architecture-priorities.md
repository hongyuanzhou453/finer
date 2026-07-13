# 架构优先级 Roadmap（2026-07-11）

## 概述（Overview）

从产品本质出发排定 F0-F8 架构的后续优先级。产品 = **持续的 KOL 内容流 → 可回测可审计的投资事件 → 多 KOL 决策台**。当前架构已把「形」跑通（12 envelope / 42 canonical action / 全链路 demo + live 前端），但它是一个**手工触发的单 KOL 批处理系统**。所有缺口归为三类：真相源纪律、流动性（自动增量）、规模化（多 KOL + 质量漏斗）。排序原则：**先收口真相源，再自动化，再放量**——在分裂的构造路径上做自动化，等于批量生产不一致（07-05 regen 已经实证过一次）。

## 现状事实基础（核实于 2026-07-11）

- `pipeline/canonical_runner.py` 是现役 F3→F4→F5 路径，但仍自行构造 TradeAction（本周刚修掉一次映射/metadata 漂移，靠钉子测试压住）；`extraction/trade_action_extractor.py`（legacy 直提）仍被 `orchestrator.py`、`execution/timing_policy.py`、`api/routes/extraction.py` 引用；`orchestrator.py` 已标 DEPRECATED（L0-L8 命名）。
- **无任何增量/调度驱动器**：全链路靠手工脚本（`regen_f5_llm.py`、`backfill_f8_backtest.py`…）和单次 API 调用；scripts/ 无 cron/watch/daemon。
- F8 auto-backtest 只在提取时刻跑一次（fail-open）；价格缺失或当时太新的 action **永远停在 pending**，无人翻牌。现役语料结算时点全在 2026-04 前，收益榜 live 空态。
- F1.5 Topic Assembly 未接入 canonical runner / golden_path（grep 零命中）；长内容直接整文进 F3。
- KOL 元数据无注册表服务：live adapter 里 style/specialties=未知，靠 action 反推 KOL；declared trading_style 已落 YAML 但只有 trader_ji 一个真实 creator。
- F2 是漏斗最窄处：56 intent → 42 action，被拒主因 sector 不可交易/symbol 未解析；中文实体命中率 ~18.6%。

## P0 — 地基（决定其他一切是否白做）

### 1. F5 构造单一真相源收口（F3→F4→F5 断点的最后一段）
AGENTS.md 头号断点的收尾。runner 与 builder 的重复已经咬过一次（ADD/REDUCE + metadata 丢失），当前靠 `test_canonical_runner_mapping.py` 钉住，但结构性重复还在。
- runner 的 TradeAction 构造下沉/委托 `CanonicalActionBuilder`（builder 增加 F2-grounding 证据、tier、direction 解析的注入点，或抽共享构造层）。
- `trade_action_extractor.py` 隔离为只读迁移工具：从 `extraction.py` 路由和 `timing_policy.py` 摘除引用，入口加 deprecation 报错。
- `pipeline/orchestrator.py`（deprecated L0-L8）删除或移入 quarantine 目录，杜绝新代码误挂。
验收：`rg "TradeAction\(" src/finer --type py` 在 schemas/tests 之外只剩一个构造点。

### 2. 增量数据流水线（事件驱动的 F0→F8 驱动器）
把 demo 变产品的那根轴；收益榜空、live 静态、「新语料入库」永远靠人的根因。
- **处理账本**：per-envelope 幂等状态（imported → standardized → anchored → extracted → backtested），落 project memory SQLite（热索引定位 + 文件为真相，符合既有 F0 纪律）。
- **驱动器**：F0 导入完成事件（或轮询新 ContentRecord）→ 自动 F1→F1.5→F2→F3(consensus)→F4→F5→F8，per-envelope 隔离失败（Line F envelope 上报，不阻塞批次）。
- **入口统一**：现有 `canonical_runner.run_canonical_from_envelope` 就是单元，缺的是 driver + 账本 + 触发，不需要新管线。
验收：飞书/B站导入一条新内容，不碰任何脚本，observed 画像、雷达、收益榜在下个刷新周期出现它。

### 3. 结算生命周期归属（F8 settle owner）
「pending 谁翻牌」目前无主：auto-backtest 一次性、fail-open，价格晚到/持有期未满的 action 永久 pending。
- 定义 validation_status 状态机归属：F8 定期 settle job 重评所有 pending + 持有期内 action（价格数据到位/持有期届满 → verified/failed），复用 `exit_rules_of` 与现有 per-action 评估。
- 价格数据获取从「脚本顺手拉」升级为有 owner 的数据层（现 yahoo_prices + 手工 backfill）。
- 挂在 #2 的调度器上（每日一次即可）。
验收：一条今天发布的观点在持有期结束后自动出现在收益榜，无人工介入。

## P1 — 规模与质量（多 KOL 成立的前提）

### 4. KOL Profile Registry 服务化
schema（`kol_profile.py`）有、存储与服务无。把 configs/creators YAML + 平台身份 + declared trading_style 收进一个注册表服务（文件真相 + 只读 API + TTL 缓存），radar/snapshot 的 KOL 元数据（style/specialties/平台）从「未知/action 反推」换成注册表真值。这是 onboarding 第二、第三个真实 KOL 的前置件——加一个 KOL 应该只是加一份 YAML + 渠道映射。

### 5. F2 实体锚定质量（漏斗最窄处）
56→42 的损耗和伪 ticker、同日反向对的根治点都在这里。延续 constrained-LLM proposal + validator 路线（M1 自进化模式），扩 entity registry 覆盖（sector→ETF proxy 映射规则化，trader_ji 的 creator 配置里已有此意图）；把「sector 不可交易」从拒绝升级为可配置的代理映射。

### 6. F1.5 接入 canonical pipeline
Mandatory sub-stage 仍游离。直播转写/长视频一进来，F3 整文提取的方向稳定性全靠 prompt 硬扛（1b 规则）。在 runner 的 F1→F3 之间接 TopicBlock 组装（规则版 fast-path + LLM constrained proposal），F3 按 topic 提取。新语料放量前必须接上，否则 #2 的自动化会把长内容质量问题批量化。

## P2 — 产品纵深（依赖 P0 出活水后才有意义）

7. **持仓簿连续模拟**：ADD/REDUCE 语义与 `position_delta_pct` 已就位；等增量流跑起来，做每 KOL 虚拟持仓簿（成本价/仓位占比/资金约束），把加减仓从标签变成仓位轨迹。per-action 口径保留做逐条归因，两套并行。
8. **F6→F+ 反馈闭环**：RLHF/审核结果回流（DPO grounding rewards 已有雏形）驱动 F3 prompt 与 F4 policy 分层调参（止损/止盈按 KOL 风格分层就挂在这）。
9. **前端面补齐**：live 标的横截面页（消掉 TickerConsensus 的降级态）、OpinionTimeline 上页。

## 横切纪律（不排期，随手执行）

- **契约漂移防护自动化**：pydantic ↔ contracts.ts 一致性目前靠人工纪律 + 两个钉子测试；值得一个 CI 检查脚本（字段名/枚举值 diff）。
- Line F 错误封装按「新改必用、旧的渐进」继续收敛。
- SQLite 热索引重建纪律：聚合读已绕过索引直读文件（正确），但索引刷新时机无 owner，#2 的账本落地时一并收编。

## 明确不做（现在）

- 不重写 BacktestEngine（组合级引擎问题多，per-action + 未来持仓簿绕开它）。
- 不做 F+ 训练基建（contract-only 维持，等 F6 数据量）。
- 不追求 L0-L8 目录改名迁移（磁盘目录映射已文档化，改名是纯风险）。

## 依赖关系

```
#1 真相源收口 ──┐
                ├──> #2 增量驱动器 ──> #3 settle owner ──> 收益榜/雷达活水
#6 F1.5 接线 ───┘         │
#4 KOL 注册表 ────────────┴──> 多 KOL 放量 ──> #7 持仓簿 / #8 反馈闭环
#5 F2 质量 ──（并行迭代，决定漏斗产出率）
```
