# 架构收口与整合轮（2026-07-25）

分支：`consolidation/2026-07-round`（自 main `c4236f19` 分出；合回 main 待用户确认）

## 概述

一轮四批次的架构收口：把 main↔未合并分支的代码/数据不一致修复到测试全绿（A）、
清掉 F3-F8 主链四项契约债（B）、把 broker 声明式路径从脚本层收编进 canonical
pipeline 并落 R2/R6 护栏（C）、落地 T9 板块适配器与 T6 schema 设计稿（D）。
起点：main 上 `test_audit_trace_integrity` 红（evidence 82.7%）、~830 条国际票
action 无法由 main 代码复现；终点：**3,921+ passed、audit 三路 100%、券商链
单一执行器、驱动器全渠道幂等**。

## 变更清单

### Batch A — 主链和解与止血
| 变更 | 类型 |
|---|---|
| cherry-pick `0f1f269a`（persist_dir sidecar）/ `fc66c9fa`（国际 ticker 解锁）/ `60485a26`（Bloomberg 方言） | 合流 |
| `tests/test_ticker_bridge_normalization.py` — .OL canonical 化断言对账 | 修改 |
| `scripts/backfill_bri_evidence_sidecars.py` — 573 条断链回填（**已执行**：24,463 sidecar 写入，0 不可恢复） | 新增+已执行 |
| `src/finer/pipeline/driver.py` — R2 护栏：broker F5 走声明式；`skipped_broker_declarative` 计数；`bri_*` 幂等双保险 | 修改 |

### Batch B — 契约债务四清
| 变更 | 类型 |
|---|---|
| `broker_recommendation_adapter.infer_market/infer_currency` → 委托 `normalize_broker_ticker`（修 `.SH` bug；28 市场货币表） | 修改（B1，worktree agent） |
| `execution/timing_policy.MARKET_SESSIONS` — 30 市场时区/时段单一真值表（含合并后补的 BE/PL）；`timing_builder` 删静默上海兜底，未知市场显式降级 | 修改（B1） |
| `anchor_bridge` L2/L3 命中回写 `intent.market` | 修改（B1） |
| `schemas/trade_action.py` — `time_horizon` → `Optional[HOLDING_PERIOD_HINT_LITERAL]` + before-validator 归一 legacy 自由文本；存量普查全 canonical（long_term 2327 / review_required 939 / short_term 36 / medium_term 11） | 修改（B2） |
| `backtest/per_action.evaluate_action` — `review_required` 拒绝结算（`SkipInfo("review_required_horizon")`）；`settle.SettleReport.skipped_review_required` | 修改（B2） |
| `check_contract_drift.py` REGISTRY +3 policy literal（26→29）；`contracts.ts` 三个 hint 内联 union 提为 export type；`TradeAction.time_horizon` 类型化 | 修改（B2） |
| `action_composer.build_action_metadata` — `risk_notes` 直通 metadata（honesty note 落 F5） | 修改（B3） |
| `BacktestResult` + `evaluation_window_days`/`window_truncated`（双写过渡）；`backfill_f8_backtest.py` split 修复；`finer_site` BacktestLite 同步 | 修改（B4） |

### Batch C — 驱动器/脚本整合
| 变更 | 类型 |
|---|---|
| `src/finer/enrichment/anchor_bridge.py` — bridge 三层规则单一真值（消 reanchor 脚本 2/3 层漂移副本） | 新增（C1） |
| `src/finer/pipeline/broker_runner.py` — 声明式 F4→F5 执行器（load/bridge/policy/canonical/persist/index/stage_status；`intent_glob`/`output_prefix` 参数化） | 新增（C2） |
| `scripts/drive_broker_recommendations.py` → 薄 CLI 壳 | 重写（C2） |
| `driver.py` — broker 记录正式路由进 `run_broker_declarative_f5_sync`（干跑仍廉价计数）；`_upsert_stage_status` + `source_channel`（COALESCE 防抹除），F1/F2/F5/failure 全落渠道 | 修改（C2/C3） |
| `scripts/reconcile_stage_status_channels.py` — 存量对账（dry-run 实测：3,187 条 bri F5 行待插、97 条 NULL→local、369 条 `cnt_*` 遗留无法解析属诚实保留）；**--execute 待确认** | 新增（C3） |
| `api/routes/opinions.py` — R6 隔离门：`broker_recommendation`/`superseded_by` 排除出 credibility/leaderboard/stats，timeline 透出 `signalClass` | 修改（C4，worktree agent） |
| `configs/creators/` +19 券商 YAML（注册表 11→30） | 新增（C6，worktree agent） |

### Batch D — 烧录成果整合
| 变更 | 类型 |
|---|---|
| `src/finer/extraction/sector_transmission_adapter.py` — T9→sector intent（cycle_view 方向、外盘主题拒绝、`t9i_` 稳定 id） | 新增（D1） |
| `scripts/drive_t9_sector_intents.py` — 干跑漏斗默认 / `--execute` 只写 F3 / `--drive-f5` 小样本门 | 新增（D1） |
| `docs/specs/2026-07-25-t6-estimate-revision-design.md` — T6 schema-first 设计稿（绑 CRD-1 轮） | 新增（D2） |

## 架构影响

- **F5 单一构造点不变**：broker_runner 仍经 `run_canonical_from_artifacts` → composer；t9i 家族共用同一执行器、独立幂等命名空间。
- **两条平行管道合一**：driver 是唯一自动入口，broker F3+ 语义由声明式路径独占；`pipeline-drive` 全渠道无参运行不再有 R2 误重驱风险（护栏 + stage_status + bri 幂等三重）。
- **契约同步**：pydantic↔contracts.ts 枚举映射 26→29；`time_horizon` 两侧同为 Literal；BacktestResult 结构化窗口双写一轮后可摘字符串后缀。
- **R6 落地**：`derived_lookup` 券商信号与 `superseded_by` 重复标记不再进 KOL credibility/榜单。

## 关键决策

1. **cherry-pick 而非重写**：data/ 产物由分支代码产出，合流是唯一能让「代码复现数据」成立的路径；三处预判冲突全部自动合并。
2. **存量 830 条国际票不重结算**（用户拍板）：代码前向修复；重结算属批量重建红线，独立授权。
3. **review_required 拒绝结算而非映射 180d**：路由裁决 ≠ 持仓周期声明；939 条存量今后停在 `skipped_review_required` 计数下，可审计。
4. **T9 只做 sector 信号**：beneficiaries/losers 是公司级信号，归 T6/EstimateRevision 设计（拒绝在 sector 适配器里夹带股票 intent）。
5. **T6 defer + schema-first 设计稿**（用户拍板）：无 CRD-1 消费方时落库是负债；metadata 塞列表重蹈 key_thesis 覆辙。
6. **B1 worktree 基线偏差的处理**：agent 基于 main（无 cherry-pick）工作，合并后 4 处断言翻转（.OL canonical 化、BE/PL 缺口）按「更严格行为是提升」原则对账，而非迁就旧断言。

## 验证结果

| 检查 | 结果 |
|---|---|
| `pytest tests/ -q`（A 后 / B 后 / C 后 / D 后终验） | 3,845 / 3,890 / 3,910 / **3,921 passed，0 failed** |
| `settle --limit 400` 干跑（收尾追加，解冻验证） | `skipped_review_required=4`、`errors=[]`；护栏在真实数据上生效。**但量级需更正**：939 条 `review_required` 中 908 条是 `neutral` 方向，本就先被 `non_directional` 拦截；真正受本护栏保护的是 **4 条 directional-pending**。另 27 条早已带 R5 前的 flat-30d 结果且状态终态（settle 不再翻牌），**并未发生「按 180d 错结算」**——B2 是防患，不是救火 |
| `python scripts/audit_trace_integrity.py` | intent/policy/evidence 三路 100%（3,313/3,313；span 级 114,110/114,110） |
| `python scripts/check_contract_drift.py` | ✓ 29 mapped enums in sync |
| `cd src/finer_dashboard && npx tsc --noEmit && npm run build` | 均通过 |
| driver 干跑（broker channel, limit 50） | `skipped_broker_declarative=50, f5_ran=0`（R2 护栏实证） |
| sidecar 回填 | dry-run 与 execute 数字逐位一致：573 action / 24,463 span / 0 不可恢复 |
| T9 干跑（21,231 行） | no_f0=21,218 — T9 池（宏观/行业）与已导入 F0 子集（个股）几乎不相交 |
| T3/T9/F0 全量对账（收尾追加） | T3 池 6,631 中 **6,441 已在 F0（97.1%）**；T9 池 18,747 中 **仅 13 在 F0（0.07%）**；**T3 ∩ T9 = 0**；未导入候选池 18,924，抽样 300/300 磁盘存在 |
| 券商 creator 覆盖（收尾追加） | 数据中 28 个 distinct creator_id，27 个已有 YAML；唯一缺档是占位值 `未知券商`（3 条）。**`creator_id=None` 实测为 0 条**——调研阶段的「171 条」有误 |

## 未解决项

1. **合回 main** 待用户确认（只 merge 不 push）。
2. **C3 对账 `--execute`** 待确认（3,187 F5 行 + 97 渠道回填）。
3. **C5 脚本归档**：候选 `c9_evidence_reanchor.py` / `reanchor_broker_f2_dryrun.py` / `backfill_bri_signal_class_f4.py` / `backfill_broker_stage_status.py` / `backfill_bri_evidence_sidecars.py`（本轮新增，已执行完毕）/ `probe_*.py` / `card*_*.py` — `git mv` 到 `scripts/archive/`，逐项待确认。
4. **T9 量产前置**：T9 池 PDF 的 F0 导入波。**已并入 C10**——`docs/specs/2026-07-18-phase0-activation-task-cards.md` 的 C10 卡追加了「2026-07-25 选批策略修正」小节：金丝雀须显式按 T9 池选批（否则构成不可控、外推失真）、并跑 D1 适配器、报告新增 theme→sector 命中率与 `sector_proxy_not_configured` 拒绝分布（即 sector_proxies.yaml 待补清单）、验收扩展到 t9i action。
5. **陈旧 worktree/分支清理**（删除红线）：6 个已并 worktree + `chore/quality-collar` / `claude/sad-gagarin-db0af5` / `feat/pipeline-autodrive` / cherry-pick 后的 `claude/dreamy-vaughan-90a5d0`、两个 B1/C4/C6 agent worktree 分支 — 待用户逐项确认。
6. Defer 清单其余项（收尾复核后的分类）：
   - **需用户执行/授权**：SQLite `superseded` 列（DDL 红线）、launchd `launchctl load`（改系统配置）、`.env` BBDOWN_COOKIE 引号（红线）、830 条国际存量重结算（批量重建）。
   - **等时机的代码项**：`backtest_period` 后缀摘除（双写兼容期满一轮后）、`DRIVE_STAGES` 增 f3/f4 token、T3 content_id 索引持久化、leaderboard UI `signal_class` 徽章（后端隔离已就位）。
   - **已核销**：~~creator_id=None 171 条~~ —— 实测 0 条，调研数字有误；真实缺档只有占位值 `未知券商`（3 条），保持无 YAML 是正确行为。~~time_horizon 完全 Literal 化~~ —— B2 普查后已直接完成，无需分期。
