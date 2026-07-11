# P0 三件 + 两件轻量事：composer 收口 / 增量驱动器 / settle owner / RLHF 版本锚定 / eval gold 纪律

## 概述（Overview）

按 `docs/specs/2026-07-11-architecture-priorities.md` 的 P0 优先级一次性落地：①F5 构造收口为单一 composer（含版本盖章）；②F0→F8 增量驱动器（复用既有 stage_status/pipeline_runs 表，零 DDL）；③F8 settle 生命周期 owner（validation_status 首次翻牌，42 条现役 action 已结算 9 VERIFIED / 23 FAILED）；④RLHF 反馈服务端版本锚定 + 修复 DPO export 零产出问题；⑤eval gold 抽样纪律。全量 3172 tests 通过，前端 build 通过，settle/driver 均已在真实数据上端到端验证。

## 变更清单（Changes）

| 批次 | 文件 | 类型 | 说明 |
|---|---|---|---|
| A | `src/finer/extraction/action_composer.py` | 新增 | 全仓唯一 TradeAction 构造点：canonical 不变量 + `build_action_metadata` + 版本章（model_version/version_info，来源 = F3 extractor_version）；`allow_empty_evidence` 区分 runner（F2 门在上游）与 builder（严格） |
| A | `src/finer/extraction/canonical_action_builder.py` | 修改 | build() 委托 composer；异常类与 metadata 函数迁至 composer 并反向 re-export |
| A | `src/finer/pipeline/canonical_runner.py` | 修改 | programmatic/LLM 两路径委托 composer；`extractor_version` 从 F3 结果下传（str 守卫防 mock 污染）；LLM 路径首次获得 metadata |
| A | `src/finer/api/routes/extraction.py` | 修改 | `POST /batch`（legacy 直提最后活消费点）→ 410 + Line F fix_hint；`/pipeline` 逐文件委托共享核心 |
| A | `src/finer/pipeline/__init__.py` | 修改 | 摘除 deprecated orchestrator re-export（零消费者） |
| A | `tests/test_action_composer.py` / `tests/test_single_constructor.py` | 新增 | composer 不变量/版本章；AST 钉子（TradeAction( 只允许 composer + quarantine legacy） |
| A | `tests/test_legacy_quarantine.py` | 修改 | 白名单摘除 lineage/extraction.py（perception/action_interpreter 因仍引其他 deprecated 模块保留） |
| B | `src/finer/backtest/settle.py` | 新增 | 状态机：PENDING+terminal→VERIFIED(>0)/FAILED(≤0)；END_OF_PERIOD/None 重评；UNDER_REVIEW 人审优先；终态不复翻。首次调用零消费者的 `repository.update_validation_status()` |
| B | `tests/test_settle.py` | 新增 | 13 例（状态机全分支/dry-run 零写入/limit） |
| C | `src/finer/pipeline/driver.py` | 新增 | `drive_once()`：扫 stage_status F0-ready → 补缺 F1/F2/F5(+F8) → settle；文件真值幂等；F1 永不重跑（uuid churn 钉子）；`cnt_*` 旧投影行静默计数；失败写 stage_status error 两列 + pipeline_runs 汇总（仅新增写入，无 DDL）；`execute_f5_for_envelope` 为与 route 共享的单一 per-envelope 实现 |
| C | `src/finer/cli.py` | 修改 | `pipeline-drive [--watch N] [--limit] [--dry-run] [--no-settle]`、`settle [--apply] [--limit]`（--apply 先整目录备份） |
| C | `tests/test_pipeline_driver.py` | 新增 | 13 例（幂等/缺哪补哪/失败隔离/legacy 跳过/嵌套 creator 目录/dry-run 零写入） |
| D1 | `src/finer/schemas/trade_action.py` | 修改 | 新增 `PipelineSnapshot`（f5_model/extractor_version/prompt_version/schema_version/config_hash/source_file/action_snapshot） |
| D1 | `src/finer/services/rlhf_assembler.py` | 修改 | `build_pipeline_snapshot()`（版本真值顺序：action.version_info → wrapper model → 全局常量）+ `action_to_extraction_dict()`（含 evidence_text） |
| D1 | `src/finer/api/routes/rlhf.py` | 修改 | submit 服务端回填 snapshot 与 original_extraction（不信 client；action 缺失降级不阻塞）；修复 `load_feedback` strict-datetime 回读潜伏 bug |
| D1 | `src/finer_dashboard/src/lib/contracts.ts` | 修改 | PipelineSnapshot 类型镜像 |
| D1 | `tests/test_rlhf_snapshot.py` | 新增 | 16 例（锚定/降级/submit 集成） |
| D2 | `scripts/eval_compare.py` | 修改 | `--eval-set` 默认指 `data/dpo/hq_v1/eval/`（唯一真身） |
| D2 | `scripts/sample_eval_gold.py` | 新增 | creator 分层确定性抽样 → `data/dpo/eval_queue/queue_<ts>.jsonl`，每行带版本章 |
| D2 | `docs/specs/2026-07-11-eval-gold-discipline.md` | 新增 | 抽样纪律 spec |

数据写回（非 git）：`finer.cli settle --apply` 两次（--limit 5 试跑 + 全量），备份于 `data/F5_executed.bak-20260711-124441` 与 `-124514`。

## 架构影响（Architecture Impact）

- **F5 单一真相源成立**：`rg 'TradeAction\('` 在 src/finer 只剩 schema 类定义、composer、quarantined legacy 三处，由 AST 测试钉住。AGENTS.md 所述「F3→F4→F5 未闭环」的构造侧断点收口（legacy extractor 仅剩 deprecated orchestrator 的 lazy import，无任何 API 面）。
- **版本章闭环起点**：composer 起新构造的 action 携带 `model_version`（F3 extractor 版本）+ `version_info`（schema/prompt/config hash + f5_strategy）；RLHF snapshot 与 eval gold 版本章均以此为真值源。存量 42 条 action version_info 仍为 null（不迁移，新旧共存）。
- **「settled」语义统一**：settled := `validation_status ∈ {VERIFIED, FAILED}`（settle.py docstring 为准）；opinions 信誉计算的「backtest_result 存在」口径标注为过渡期兼容。前端 verificationStatus 由恒 pending 激活为真实三态，映射代码零改动。
- **账本激活**：stage_status（原仅 F0 写）现在承载 F1/F2/F5 的 ready/failed + Line F error 两列；pipeline_runs（原零使用）记录每次 drive 汇总。表结构零变更。
- **API 面变化**：`POST /api/extraction/batch` → 410 Gone（前端零调用已核实）。

## 关键决策（Key Decisions）

1. **composer 放新文件而非 builder**：builder 已 402 行，追加会破 500 行红线；builder 反向 re-export 保住既有 import 路径。
2. **单一化的是构造点与不变量，不是各路径字段策略**：trigger_type（MANUAL vs NEWS_EVENT）、rationale 风格、证据口径差异原样保留——避免为统一而破坏 golden_path/runner 的既有测试契约。
3. **空证据的诚实语义**：composer 断言 evidence 存在时必须 canonical、显式允许的空 evidence 必须 partial（不是 canonical 也不是崩溃）——runner 的无 F2 索引路径由此保留。
4. **settle 去掉 incremental 参数**（方案预授权简化）：终态不复翻 + UNDER_REVIEW 不碰 + 无数据下轮再试，天然增量，模式开关不增加行为；terminal 但 return_pct 为 None 路由到重评分支防误翻。
5. **driver 对 `cnt_*` 行静默跳过**：368 行是 2026-06-04 manifest backfill 的 PM 身份投影（从未有 F0_intake record），按失败处理会把每次 run 的报告刷成噪音；前缀启发式 + 专项计数。
6. **F1 永不重跑写死**：envelope/block/span/intent id 均为 uuid，重跑即全链 churn；needs_reprocess 修复语义留给人工 regen 脚本。
7. **RLHF 版本锚定服务端回填**：client 提交的版本信息不可信；action 找不到时 snapshot=None 降级不阻塞提交。

## 验证结果（Verification）

```bash
pytest tests/ -q         # 3172 passed, 15 skipped（基线 3123 → 新增 49 测试）
cd src/finer_dashboard && npm run build   # exit 0
rg -P '(?<![A-Za-z0-9_])TradeAction\(' src/finer --type py
# schemas 类定义 / action_composer / trade_action_extractor(quarantined) / golden_path(日志字符串) 4 处命中，真实构造点 2 处
```

端到端（真实数据）：
- `pipeline-drive --dry-run`：scanned=370 → skipped_legacy_identity=368、excluded=1、genuine failure=1（f8f70a…只写索引未落 record 的真实缺档，见未解决项）。
- `settle --apply --limit 5` → 1 VERIFIED + 3 FAILED 落盘核对无误；全量 `--apply` → **9 VERIFIED / 23 FAILED / 10 pending**（6 非方向性 + 4 缺价）。
- `curl /api/opinions/timeline` → verificationStatus = `{success: 9, failed: 23, pending: 10}`（此前恒 pending）。
- `eval_compare --demo` 自检通过；`sample_eval_gold --dry-run` 分层计划 sandbox 5→3 / trader_ji 37→4。

提交：`fda68118`(A) `c0bf8ad3`(B) `9c2584b4`(C) `8918e14e`(D1) `b23389cc`(D2)。

## 未解决项（Open Issues）

1. **f8f70a… 缺档**：2026-07-11 03:18 某次 F0 导入只写了索引未落 ContentRecord 文件（stable_key 还是 16 位截断）——F0 写入原子性待查。
2. **存量 action version_info=null**：新构造起才有版本章；下次 regen 自然补齐（不做迁移）。
3. **golden_path 的 F3 自证 span**：仍未过 F2 硬门（既有 open issue，本轮不修）。
4. **RLHF /pending 读 legacy L0 extractions**：与 canonical F5 口径错位，留 F6 面板迭代（估 1.5 天含前端联调）。
5. **F3 四轴 gold 只有 cat_lord 4 条 fixture**：sample_eval_gold 队列跑起来后积累。
6. **driver 未挂常驻调度**：v1 = CLI `--watch`；server startup hook / cron 待 P1。
7. **verificationStatus 激活后的前端观感**：23 failed 会让雷达/时间线大面积红——是 3 月历史语料的真实胜率，非缺陷；等新语料进入后自然稀释。
