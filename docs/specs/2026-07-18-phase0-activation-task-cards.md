# Phase 0 激活收口 —— 执行任务卡（交 Opus 4.8 执行）

> 版本：v1.0 | 日期：2026-07-18 | 状态：待执行
> 上游规划：`docs/specs/2026-07-18-product-north-star-architecture-roadmap.md`（§6 模块注册表、§7 Phase 0 验收门）
> 执行模型：**Opus 4.8（claude-opus-4-8）**。规划由 Fable 完成，本文档即交接物；执行 agent 不需要读规划会话的聊天记录，本文档自包含。
> 执行规范：必须遵守仓库 `AGENTS.md` / `CLAUDE.md`、`docs/specs/2026-05-parallel-agent-execution.md`（并行规范）与 `docs/specs/2026-05-verification-snapshot-gate.md`（Line V 只读门控）。

---

## 0. 用户决策记录（2026-07-18，已拍板，执行时不需再问）

| # | 决策 | 结论 | 执行含义 |
|---|---|---|---|
| D1 | R8 外置盘归属 | **保持外置盘 + 护栏** | 不迁移 73GB raw；必须交付：挂载健康检查（未挂载 → 跳过 broker 渠道并告警，不报错）+ 关键中间产物备份策略（F0 receipt / F1 envelope / T3 JSONL 均在内置盘，确保永不因盘拔而需重 OCR） |
| D2 | SQLite 变更 | **一次性授权全部** | stage_status 补 `source_channel` 列 + broker 存量回填、（Phase 1 的）projections.sqlite3 新表均已授权；**条件：每次变更前自动备份 DB**（沿用 `finer.project.sqlite3.bak-*` 模式） |
| D3 | git 真相源合流 | **全部合流** | 授权 push `chore/quality-collar` 并开 PR 合入 main；合并 PR #8；25 个 broker untracked + 13 个 modified 文件在新分支提交开 PR。push 仅限上述分支 |
| D4 | 批量重跑与删除 | **三项全部授权** | ① F2 全量重锚（broker envelope）；② F8 存量窗口回填重结算 + trader_ji 42 条 llm-consensus 重提取（**前提见 C11：先移植 F3 护栏到 llm prompt 层**）；③ 删除《20260315课代表整理.pdf》对 trader_ji 的归属并重算。**条件：执行前均自动备份** |

**仍需回来问用户的事**（执行中遇到必须停）：
- 全量放量导入（2.2 万份）——本轮只授权了 1,000 份金丝雀批（C10），全量需带金丝雀报告回来确认；
- 上表之外的任何删除、任何新 SQLite 表/列、向上表之外分支的 push、`.env`/密钥/CI 配置改动；
- 任何与本文档任务卡冲突的现场发现（先报告再动）。

---

## 1. 执行规则（每个执行 agent 开工前必读）

1. **Line V 先行**：每轮实现型并行任务启动前，先跑一次只读 baseline（`pytest tests/ -v` 计数、`git status`、关键目录清点），输出 baseline report。发现与本文档「现状假设」不符 → 先报告，不要硬改。
2. **一卡一 agent 一 F-stage**：每张卡声明了 owning files 与禁改文件；多卡并行时用独立 worktree/分支，禁止两个 agent 改重叠文件。`pipeline/driver.py` 是本轮最大共享热点——C2/C4/C6 三卡都碰它，**必须串行**（同一 agent 顺做或依次交接）。
3. **验证纪律**：改完必跑该卡「验收命令」；依赖 `finer` 包的脚本必须用 `.venv/bin/python`（系统 python3.14 会 ModuleNotFoundError）。前端涉卡加跑 `cd src/finer_dashboard && npm run build && npx tsc --noEmit`；worktree 里前端验证需从主仓 `cp -R node_modules`（Turbopack 拒 symlink）。
4. **红线内动作也要留痕**：每次备份写明路径；每张卡完成后在本文档对应卡下追加一行 `✅ YYYY-MM-DD 完成 + 关键证据`（commit hash / 测试计数 / 报告路径）。
5. **不碰正在跑的放量进程**：可能有并行会话的 broker F1 scaleup 脚本在写 `data/F1_standardized`；它不碰代码文件，git 操作安全，但 C10 开工前先确认该进程状态（`ps aux | grep broker_scaleup`），避免双开重复烧 OCR。
6. **commit 规范**：`type(scope): description`；不提交 `data/`、`.env`、`__pycache__`。

### 依赖 DAG

```
C0 git合流 ─┬─→ C1 broker索引注册 ─┐
            ├─→ C2 driver渠道控制 ──┼─→ C10 金丝雀放量
            ├─→ C3 batch_runner ────┘        │
            ├─→ C4 调度壳 ←─(依赖C2) ────────┤（C4/C5/C6 与 C10 并行）
            ├─→ C5 观测告警（与C4绑定交付）
            ├─→ C6 外置盘护栏（碰driver，排C2/C4后）
            ├─→ C7 F4落盘+honesty ─→ C8 三向引用审计 ─→ C9 F2重锚+重驱动
            └─→ C11 KOL存量清理（独立线，可全程并行）
```

建议排期：第 1 天 C0（单 agent 串行）；第 2-4 天 C1+C2 串行完成后，C3 / C7 / C11(a,b) 三线并行；第 4-6 天 C4+C5+C6（driver 线）与 C8、C9 并行；第 6 天起 C10；C11(c) 最后（工作量最大且独立）。

---

## 2. 任务卡

### C0 · git 真相源合流【全线前置，单 agent 串行执行】

- **parallel line**: infra / git；**F-stage**: cross-stage（不改业务语义）
- **现状假设**：当前分支 `chore/quality-collar`（13 commits，off main `98c6e74d`，未 push）；PR #8 `feat/pipeline-autodrive`（7 commits，已 rebase 到最新 main，3216 passed）；工作树有 13 个 modified + ~25 个 untracked 文件（= broker research 波：`llm/client.py`、`model_config.py`、`schemas/import_receipt.py`、`schemas/investment_intent.py`、`policy/global_base.py`、`policy/policy_mapper.py`、`enrichment/entity_*`、`backtest/per_action.py`、`contracts.ts`、`intent-card.tsx`、`scripts/check_contract_drift.py` + `broker_*`/`ticker_normalization`/`configs/creators/*券商*.yaml`/`configs/entity_registry_broker.yaml`/新测试等）
- **步骤**：
  1. Line V baseline（记录当前 `pytest` 计数与 git 状态快照）。
  2. 工作树 broker 波先提交：基于 `chore/quality-collar` 顶端，按逻辑分组做 conventional commits（如 `feat(ingestion): broker research intake channel`、`feat(extraction): declarative broker recommendation adapter`、`feat(enrichment): broker entity registry + ticker normalization`、`fix(llm): usage logging + vision registry cooldown`、`feat(schemas): recommendation semantics + target_price + horizon`）。提交前全量 `pytest`。
  3. push `chore/quality-collar` → 开 PR → 全绿后合入 main（授权见 D3）。
  4. 合并 PR #8（autodrive 默认 OFF，与后续 launchd 方案不冲突；policy 可调面、F0 原子性门、/radar 接入随之进 main）。若合并冲突>轻微，停下报告。
  5. 合流后在 main 跑全量验证；删除已合并本地分支（被 worktree 占用的跳过）。
- **owning**: git 操作本身；**禁改**: 任何业务代码（冲突解决除外）
- **验收**：main 上 `pytest tests/ -v` 全绿且计数 ≥ 合流前两分支各自计数的合理并集；`git status` 干净；`gh pr list` 无遗留 OPEN（除有意保留）；main 上能 `grep -r "broker_research_intake" src/` 命中。
- ✅ **2026-07-18 完成**：broker 波拆为 8 个 conventional commit（`b0b1eb2b`…`41ff5160`）→ PR #10 合入 main（merge `1d8d6885`）；PR #8 经本地冲突解决合入 main（merge `4495a412`，GitHub 已标 MERGED）。冲突仅 2 文件：`policy/global_base.py`（exit hint = horizon-tier 主路 + PR#8 tunable `base_exit` 作无-horizon 回退，`base_exit` 默认值与旧 `_LEGACY_FLAT_EXIT` 逐位相同 → 回测不变；删除死常量）与 `tests/test_pipeline_driver.py`（两分支测试并集）。main 全量 **3580 passed, 22 skipped**（合流前 quality-collar 3548 + PR#8 新增 32）。`git status` 干净；仅 PR #9(kol-check) 有意保留 OPEN。**留待用户确认**：已合并本地分支 `chore/quality-collar` 未删（删除本地分支属红线，未单独授权）。
  - ⚠️ **给 C1/C2/C6 的现场校正**：① 项目 DB 真实路径是 `data/project_memory/finer.project.sqlite3`（非本卡原写的 `data/finer.project.sqlite3`），WAL 模式在用，备份需连 `-wal/-shm` 或先 `PRAGMA wal_checkpoint`；② broker F1 输出是扁平 `data/F1_standardized/<每文档目录>/`（~2009 个 broker 前缀目录），**无 `broker/` 子目录**，C2 渠道过滤必须靠 `source_channel`/ContentRecord，不能靠路径段；③ 另有并行会话在跑 `broker_scaleup_runner.py --workers 8`（不写 stage_status），C10 前先确认不双开。

### C1 · OPS-1 broker F0 索引注册 + 存量回填

- **parallel line**: F0 Intake Repair；**F-stage**: F0
- **输入/输出 schema**: `ContentRecord`（已有）→ stage_status 行（补 `source_channel` 列）
- **做法**：①`src/finer/ingestion/broker_research_intake.py` 成功建档路径补 `F0IndexWriter` 注册 + stage_status 写入（对齐 feishu/local 渠道的既有注册语义）；②迁移：stage_status 加 `source_channel TEXT` 列（**先 `cp data/finer.project.sqlite3 → .bak-$(date +%Y%m%d)-prebroker`**，迁移幂等：列存在则跳过）；③新增 `scripts/backfill_broker_stage_status.py`：扫 `data/F0_intake/broker/` 全部 record 幂等回填（INSERT OR IGNORE 键 content_id+stage），dry-run 默认；④**不要动 cnt_* 遗留投影行与「F1 永不重跑」保护逻辑**。
- **owning**: `src/finer/ingestion/broker_research_intake.py`、`src/finer/ingestion/f0_index_writer.py`、`scripts/backfill_broker_stage_status.py`、新测试；**禁改**: `pipeline/driver.py`（那是 C2）、schemas/
- **验收**：`.venv/bin/python scripts/backfill_broker_stage_status.py --execute` 后，`sqlite3` 查 stage_status 中 source_channel='broker' 行数 == `ls data/F0_intake/broker/*.json | wc -l`（±既有失败记录）；新导入 1 条 broker 内容自动出现在 stage_status；`pytest tests/ -v` 全绿。
- ✅ **2026-07-18 完成**（commit `938932ef`，本地未推，待推送节奏确认）：迁移 005 `stage_status_source_channel` 上线（live DB apply 8ms，checksum verified）；`F0IndexWriter` 从 receipt 写 `source_channel`（全渠道受益，COALESCE 保留既有）；`broker_research_intake` 注入式 opt-in 注册（CLI 默认注册 + `--no-register`；库/测试不注入 writer 就永不碰 live DB —— 避开 PR #8 修的「测试写 live DB」孤儿类）；`backfill_broker_stage_status.py` 幂等、dry-run 默认。**live 回填 4298/4298（0 失败）**，`stage_status` broker F0 = **4298 == 磁盘 record 文件数**。测试：6 backfill + 2 intake 注册；migration 计数断言 4→5；full suite **3588 passed / 22 skipped**。
  - 校正：② 备份路径实为 `data/project_memory/finer.project.sqlite3`，已用 `sqlite3 .backup` 热备份至 `.bak-20260718-prebroker`（WAL 在线，非裸 cp）；③ 验收公式 `ls .../*.json` 含 receipt（8706），真实 record 数 = **4298**（已排除 `*.receipt*.json`），口径以 record 文件为准。既有 394 条非 broker F0 行 `source_channel` 仍为 NULL（不在 C1 broker 范围；各渠道下次 F0 注册会自填）。

### C2 · OPS-2 驱动器渠道/阶段控制

- **parallel line**: pipeline driver；**F-stage**: cross-stage（driver）
- **schema**: 新增 `DriveRunConfig`（channel 过滤、stages 白名单、并发度、max_items；每轮参数落盘可重放）
- **做法**：`pipeline-drive` CLI 与 `drive_once` 加 `--channel broker|feishu|local|all` 与 `--stages f1,f2,f5,settle`（默认值 = 现行为，零破坏兼容）；解除每轮强制 F5+settle（由 --stages 决定）；移除 `driver.py` 对 `/bilibili/` 与 local pdf 的硬编码排除，改为渠道能力声明表（broker pdf 必须可驱动——现排除规则会让研报 100% 蒸发，即 R1 风险）。**注意 PR #8 合入后 drive_once 已有 fcntl 单飞锁与孤儿 reconcile，别破坏**。
- **owning**: `src/finer/pipeline/driver.py`、`src/finer/cli.py`、`src/finer/schemas/`(DriveRunConfig)、测试；**禁改**: ingestion/、backtest/
- **验收**：`pipeline-drive --channel broker --stages f1,f2 --limit 2 --dry-run` 能发现 C1 回填的 broker 内容且不触发 F5/settle；`--channel feishu` 不含 broker 行；全量 pytest 绿。
- ✅ **2026-07-18 完成**（commit `3a63e4bf`，已推 main）：新增 `DriveRunConfig`（channel / stages 白名单 / concurrency / max_items；落 `report.config` 与 `pipeline_runs.summary_json` 可重放，默认=旧行为零破坏）；`drive_once` + CLI 加 `--channel {all,broker,feishu,…}`（过滤 `stage_status.source_channel`）与 `--stages f1,f2,f5,settle`（逐阶段门控）；`_is_excluded` 由 raw_path 字符串匹配改为 **source_platform 声明式表** `_NON_DRIVEABLE_CHANNELS={bilibili}`，broker pdf 显式可驱动（R1）；PR#8 fcntl 单飞锁 + F0 orphan reconcile 原样保留。实测 live dry-run：`--channel broker --stages f1,f2 --limit 2` → scanned=2、f5_ran=0、settle=null；`--channel feishu` → scanned=0（不含 broker，settle 是全局非渠道）。测试 +7 driver +8 drive_config；full suite **3603 passed / 22 skipped**。
  - 注：feishu/local 历史 F0 行 `source_channel` 仍为 NULL → `--channel feishu` 暂时找不到自身内容（但确实不含 broker，验收成立）；`--channel all`（默认）仍驱动全部含 NULL。C1 的 F0IndexWriter 已让**新导入**自填渠道；要让存量 feishu/local 可按渠道过滤，需一次性回填其 `source_channel`（未来小任务，非 activation 主线）。

### C3 · OPS-3 batch_runner 并发批量执行池

- **parallel line**: pipeline throughput；**F-stage**: 横向公共层
- **schema**: `BatchRunManifest`（run_id/total/done/failed/skipped/budget_spent_tokens/checkpoint_cursor/started_at/finished_at，落 `data/run_state/`）
- **做法**：新建 `src/finer/pipeline/batch_runner.py`：asyncio semaphore 并发池（F1 默认 8，对齐实测）+ 逐条失败隔离 + checkpoint 文件断点续传 + token 预算硬顶与 quota-strikes 熔断（参照 NAS `/Volumes/NAMEZY/外资研报/rag_system/structured_extract.py` 已实战验证的模式，**迁移语义不迁移代码依赖**）；driver 的 `_default_f1/f2_executor` 与 backfill 脚本共用；把本轮会话的 scratchpad 放量逻辑收编为 `scripts/drive_broker_scaleup.py`（仓内可复现入口，写 stage_status）。预算读数依赖 C0 合入的 LLM usage 计量——若 usage token 字段仍为 null（MiMo 响应未解析），**先修 `llm/client.py` 的 usage 解析再接预算**。
- **owning**: `src/finer/pipeline/batch_runner.py`、`scripts/drive_broker_scaleup.py`、`src/finer/llm/client.py`（仅 usage 解析）、测试；**禁改**: driver.py 主逻辑（通过 executor 注入协作）
- **验收**：对 20 条 broker 内容跑 F1 批量：中断后重跑从 checkpoint 续、不重复处理；manifest 落盘字段齐全且 tokens 非 null；模拟预算超限触发熔断（exit code 非 0 + manifest 记录原因）；pytest 绿。

### C4 · OPS-4 调度器壳（launchd + 心跳）

- **parallel line**: ops；**F-stage**: 横向（configs/launchd/ + driver 心跳）
- **schema**: `HeartbeatState`（pid/last_pass_at/last_pass_stats/lock_holder → `data/run_state/heartbeat.json`）
- **做法**：`configs/launchd/com.finer.pipeline-drive.plist` 与 `com.finer.feishu-watch.plist`（调用 wrapper 脚本激活 `.venv`；RunAtLoad+KeepAlive；日志落 `logs/` 按天）；driver watch 循环每 pass 末写 heartbeat；复用 PR #8 的 fcntl 单飞锁（勿重复实现）。**装载 launchd 属修改系统配置——生成 plist 与安装命令文档，实际 `launchctl load` 由用户手动执行一次**（写清命令即可）。
- **owning**: `configs/launchd/`、`scripts/ops/run_pipeline_drive.sh`、driver 心跳写入、docs；**禁改**: driver 的 stage 逻辑
- **验收**：手动跑 wrapper 脚本 → heartbeat.json 持续更新、双开第二实例被锁拒绝（`skipped_locked`）；plist `plutil -lint` 通过；安装/卸载/查看日志命令写进文档。

### C5 · OPS-5 观测与告警（与 C4 绑定交付）

- **parallel line**: ops；**F-stage**: 横向 `src/finer/ops/`
- **schema**: `RunLedgerEntry`（run_id/job_type/stats/errors[]（复用 canonical error envelope）/tokens_spent/duration_s）、`AlertEvent`
- **做法**：①run ledger：drive/settle 每轮落一行 JSONL（`data/run_state/ledger/`）；②告警：`ops/alerts.py` 飞书 webhook（URL 走 `.env` `FINER_ALERT_WEBHOOK`，**代码不落 token**），三类触发：心跳超时（>2×轮询间隔）、单轮失败率>阈值、预算超限；③日志轮转（按天 + 保留 14 天）；④告警自测 CLI（`--test` 发一条测试消息）。
- **owning**: `src/finer/ops/`、driver/settle 的 ledger 挂点、测试（webhook mock）；**禁改**: 业务提取逻辑
- **验收**：模拟心跳超时/失败率超阈 → mock webhook 收到 payload（含 fix_hint）；ledger 行 schema 校验通过；pytest 绿。

### C6 · OPS-6 外置盘护栏（D1 决议的落地）

- **parallel line**: ops；**F-stage**: F0/横向
- **做法**：①挂载健康检查：driver 与 broker intake 在 `/Volumes/NAMEZY` 未挂载时**跳过 broker 渠道 + 发 AlertEvent（警告级）**，绝不报错中断其他渠道；②确认并成文「关键中间产物全在内置盘」清单（F0 receipt/manifest、F1 envelope、F2 anchor、T3 JSONL）——盘拔最坏损失 = 不能重跑 F1 原文，已有 envelope 不受影响；③`.bak` 保留策略成文 + `scripts/prune_backups.py`（保留最近 3 份 + 结算前快照；**dry-run 默认，实际清删列清单请用户过目**——删除类红线，D4 未覆盖 .bak 清理）。
- **owning**: driver/intake 的挂载检查、`scripts/prune_backups.py`、spec 段落；**禁改**: raw 归档路径语义
- **验收**：模拟未挂载（临时改路径）→ broker 渠道 skipped + 告警、feishu/local 渠道正常；prune dry-run 输出清单。

### C7 · AUD-1/2 券商链 F4 落盘 + honesty note + signal_class

- **parallel line**: F3-F4-F5 canonical path；**F-stage**: F4/F5 边界
- **schema**: `TradeAction` 增 `signal_class: Literal['kol_statement','broker_recommendation']`（模块级 `*_LITERAL` 常量 → 同步 `contracts.ts` → `scripts/check_contract_drift.py` REGISTRY 登记）
- **做法**：①`scripts/drive_broker_recommendations.py` 把 `PolicyMappingResult` 落盘 `data/F4_policy_mapped/{policy_id}.json`（对齐 `services/audit_assembler.py` 的读取约定）；②`extraction/action_composer.py::build_action_metadata` 搬运 risk_notes 中的机构建议标记（**不破坏单一构造点与四要素断言**）；③存量 19 条 bri action 补写 F4 artifact + signal_class 回填（备份 `data/F5_executed` 先行；bri_ 前缀文件不会被 regen 覆盖）。
- **owning**: `scripts/drive_broker_recommendations.py`、`src/finer/extraction/action_composer.py`、TradeAction schema 文件、`src/finer_dashboard/src/lib/contracts.ts`、测试；**禁改**: `trade_action_extractor.py`（legacy 隔离带）
- **验收**：任取一条 bri action，`/audit` bundle 三段（intent/policy/action）全非空；`ls data/F4_policy_mapped/ | grep bri | wc -l` ≥ 19；drift guard 绿（`.venv/bin/python scripts/check_contract_drift.py`）；pytest + `npm run build` + `tsc --noEmit` 绿。

### C8 · AUD-3 三向引用完整性审计（只读，进 CI）

- **parallel line**: Line V 扩展；**F-stage**: 横向审计
- **做法**：`scripts/audit_trace_integrity.py`：遍历全部 F5 action，验证 `intent_id`→F3 文件、`policy_id`→F4 文件、`evidence_span_ids`→F2 span 三向可解引用，输出完整率报告（JSON+人读）；包一个 `tests/test_audit_trace_integrity.py`（对完整率设门槛断言，初始门槛按 C7 完成后的真实值设定，C9 完成后收紧到 100%）。**只读，不修数据**。
- **owning**: 上述两文件；**禁改**: 一切数据与业务代码
- **验收**：脚本对当前数据出报告并列出每一条断链的 action_id 与断链类型；pytest 绿。

### C9 · AUD-4 F2 收口 + 全量重锚 + 重驱动（D4-① 已授权）

- **parallel line**: F2 Anchor；**F-stage**: F2（+重驱动 F3-F5）
- **做法**：①注册表收口：`enrichment/ticker_normalization.py` 补 `.PA/.FP/.B/NSDQ` 等后缀；裸 EW 撞 MSCI OW/EW/UW 评级术语修复（进 `entity_stoplist` 上下文门）；②**备份 `data/F2_anchored/`（broker 部分）**后对已 F1 的 broker envelope 全量重跑 F2（用 C3 batch_runner）；③重跑 A3 适配器（content-derived intent_id 幂等覆盖写，敢跑）→ 重驱动 F4/F5（`drive_broker_recommendations.py --execute`）；④出 evidence 覆盖率前后对比报告。
- **owning**: `enrichment/ticker_normalization.py`、`entity_stoplist.py`、`entity_registry_broker.yaml`（再生成）、执行脚本调用；**禁改**: KOL 策展注册表语义（策展优先原则不动）
- **验收**：bri intent 的 evidence_span_ids 覆盖 10/28 → ≥80%（新批次口径）；C8 审计脚本对 bri action 完整率 100%；假阳性抽检 ≤5%（沿用毒词战役抽检法）；pytest 绿。

### C10 · 金丝雀放量（1,000 份）+ 吞吐/成本校准报告

- **parallel line**: broker activation；**F-stage**: F0→F5 全链驱动（不改代码，纯执行+报告）
- **前置**: C1/C2/C3/C6 完成；确认无并行 scaleup 进程双开
- **做法**：①`broker_research_intake.py --execute --limit 1000`（护栏内，无需额外授权）导入下一批未建档研报；②batch_runner 驱动 F1（8 并发）→F2→A3→F4/F5；③全程记录：单份耗时、失败率与原因分布、MiMo token 消耗（usage 计量真实值）、磁盘增量；④产出 `docs/specs/2026-07-XX-broker-canary-1k-report.md`（吞吐外推 2.2 万份的墙钟与成本估算 + 失败模式清单）。
- **⛔ 停止点**：金丝雀完成后**停下**，把报告交用户决策全量放量（解除 --limit 未授权）。
- **验收**：报告落盘；新增 bri action 全部过 C8 审计；settle 对新 action 正常排期（PENDING 而非误翻）。

### C11 · KOL 存量清理（D4-②③ 已授权；独立线）

- **parallel line**: KOL data hygiene；**F-stage**: F3/F5/F8 数据 + F3 llm 路径代码
- **(a) 删除课代表误归属**：定位《20260315课代表整理.pdf》的 content_id 及其 4 条 action（含 0700.HK/GOOGL 2 条已结算败绩）。做法：**移入 `data/_quarantine/`（带 manifest 记录原路径与原因）而非物理删除**——达成「不再给 trader_ji 记账」且可逆；重算受影响记分（opinions/episode 口径）。备份先行。
- **(b) F8 窗口回填重结算**：备份 `data/F5_executed/` 后，对存量 action（trader_ji 61 条旧 30d 窗口等）按 R5 horizon 分档窗口重结算，统一口径；`BacktestResult` 若 C0 后仍无 `evaluation_window_days/window_truncated` 结构化字段，则本卡顺带补（schema+contracts.ts+drift 登记）。**settle 终态不回翻的既有纪律保持**——只对未终态与窗口口径不一致者重算，已 VERIFIED/FAILED 的终态翻转需逐条列出差异请用户过目。
- **(c) F3 护栏移植到 llm prompt 层 + 42 条重提取**：⚠️ **禁止用 rule 提取器重跑这 42 条**（直播转写语料，2026-07-15 已判定该做法错误）。正确顺序：①把 rule 路径已验证的护栏语义（DIRECTIONAL_BEARISH vs RISK_CAUTION 词表分离、监控表/配置框架非方向性降级、对冲语境）移植进 consensus llm 提取器的 prompt + 确定性 validator；②小样本（3-5 个 PDF）验证方向分布合理后，重提取 12 个转写 PDF 的 42 条 → 重驱动 F4/F5 → 重结算；③前后对比报告（bearish 比例、settled 结果变化）。
- **owning**: (a)(b) 数据操作脚本 + 备份；(c) `extraction/intent_extractor.py` llm 路径/consensus prompt、validator、测试；**禁改**: rule 路径已修好的护栏
- **验收**：(a) trader_ji 记分卡不再含课代表 4 条，quarantine manifest 可追溯；(b) 全部非终态 action 带结构化窗口字段、口径统一报告落盘；(c) 重提取后方向分布 sanity（参照周策略图修复后 bullish/neutral/bearish 比例量级）+ 人工抽检 10 条 + pytest 绿。

---

## 2.5 外部审查记录（Fable，2026-07-18，覆盖 C0/C1/C2）

只读对抗审查（4 路审查 + major 发现逐条对抗验证，工作流 wf_b644be54-e32）。**总判定：三卡质量高，可检验声明全部属实**——全量测试独立重跑 `3603 passed / 22 skipped` 与声明逐字一致；live DB（source_channel 列、broker 4298 行 F0/ready、迁移 005 账、cnt_* 未动）、热备份（.bak-20260718-prebroker 经只读打开实证为迁移前快照）、PR #8/#10 MERGED、每卡已推 main 全部核实。两个最重的事前担忧均被数据驳倒：① driver F1 幂等路径与 scaleup 产物布局逐位一致（4174 个 broker envelope 全扫无缺失，不会重烧 OCR）；② local pdf「解禁」方向反了——新 source_platform 规则对 4692 条 F0-ready 行逐条 diff 与旧规则零差异，且 12 个直播转写/课代表 PDF 根本不在 stage_status，新规则把该类路径关得更死。

**裁决后的发现清单（按处置归属）**：

| # | 严重度 | 发现 | 处置建议 |
|---|---|---|---|
| R1 | **major（CONFIRMED）** | `DRIVE_CHANNELS`（drive_config.py:20-29）手写 `'local'/'nlm'`，与 canonical `SourceChannel` Literal（import_receipt.py 的 `'local_upload'/'notebooklm'`）值集漂移：`--channel local` 永远静默 scanned=0，而正确名 `local_upload` 被 validator+argparse 双双拒绝——该旋钮对这两渠道出厂即死。正是项目枚举漂移防护要防的模式，但 drift guard 只守 pydantic↔contracts.ts | **C10 前修**（顺手级）：`DRIVE_CHANNELS = ("all", *get_args(SourceChannel))` 派生 + 补 drift 断言测试。可并入 C3 |
| R2 | minor（major 经对抗验证降级） | 回填后 4298 条 broker 行进入默认 `channel='all'` 工作集：一次无参 `pipeline-drive` 或开 autodrive 即全量扫描驱动。降级理由：F3 默认 rule-based、F2 确定性（无 LLM），真实 LLM 暴露仅 ~94-124 份 F1 OCR 缺口，且会与在跑的 scaleup 进程双烧（drive 锁不覆盖它） | C3 给 batch/drive 补默认 max_items 或至少把「scaleup 在跑时禁止无参 drive」写进操作纪律；C10 前置检查已含 ps 确认 |
| R3 | minor | C1 的 COALESCE 语义与声明相反：代码是**新值覆盖既有**（f0_index_writer.py:214，且 receipt.source_channel 必填使「保留既有」分支不可达），commit message 与本卡 ✅ 行写「保留既有」。当前无实害 | 修正措辞，或如果产品语义要求首次归属不可变则翻转 COALESCE 参数序+补测试。领 C3 的 agent 顺手 |
| R4 | minor | 非法 `--stages` 值以裸 pydantic traceback 逃逸 CLI；`--watch` 下首轮即砸死守护循环（cli.py:207-215 无校验，对照 --channel 有 argparse choices） | C4（调度壳）前必修——launchd 常驻场景下参数错误应拒绝启动而非循环崩溃 |
| R5 | minor | C0 合并组合出的潜在优先级冲突：`_apply_style_exit_overlay` 只查 hint is None 不辨来源，未来 by_style 非空时会覆盖 horizon-tier 退出参数（R5「30 天秒表量长线」回归通道）。当前 by_style={} 惰性零影响 | 挂 C7：定义 style overlay 与 horizon-tier 的优先级（建议 horizon 主导）并写进 f3f4-policy.yaml 注释 |
| R6 | info | `--channel bilibili` 合法但保证空转（渠道过滤键是 source_channel、排除表键是 source_platform，两处 'bilibili' 相等是巧合非契约）；stage 门控下 skipped_complete 语义悄变（--stages f1,f2 轮该计数归 0）；dry-run 不落 pipeline_runs（C2 的 live dry-run 声明无法事后独立复核，设计如此） | 随 C5 ledger 落地一并覆盖：dry-run 落 ledger、加 skipped_stage_gated 计数、DRIVE_CHANNELS 剔除或提示不可驱动渠道 |

无 blocker。R1 是唯一必修项（C10 金丝雀会用到渠道旋钮，值集漂移属「同类病防护缺口」）；其余按处置列归入后续卡顺手完成即可，不单开卡。

## 3. Phase 0 总验收门（对照路线图 §7）

全部满足才算 Phase 0 关闭、Phase 1 开工：

1. pipeline-drive 以 launchd 常驻，无人值守连续 ≥72h：心跳持续、失败有 ledger 与告警记录、零人工干预；
2. broker 存量全部注册进 stage_status，`--channel broker` 可发现可驱动；
3. F1 完成 ≥4,000 份、F2 批量锚定完成、A3 全量执行、券商 canonical action 过百条（金丝雀批 + 既有存量合计）；
4. `audit_trace_integrity.py` 报告 100% 三向引用可解引用；
5. LLM 花费真实计量（token 非 null）+ 预算硬顶生效；
6. KOL 存量口径统一（课代表隔离、窗口回填、42 条重提取完成）；
7. 金丝雀报告落盘并已交用户（全量放量等待用户决策）。

## 4. 交接启动方式（给用户）

新开 Opus 4.8 会话，粘贴：

```
读 docs/specs/2026-07-18-phase0-activation-task-cards.md 并按其执行规则推进 Phase 0。
从 C0 开始，先跑 Line V 只读 baseline。用户决策记录（§0）内的授权有效，
遇到「仍需回来问用户」清单内的事项必须停下来问我。
```

多卡并行时可分会话领卡（每会话声明领哪张卡），但 C0 必须最先单独完成，driver 三卡（C2/C4/C6）串行。

## 5. 验证结果

本文档为规划交接物，无代码变更。任务卡内容依据：路线图 spec §6-§8、9-agent 只读调查（wf_dff24837-273）、项目 memory（含 2026-07-15 「re-materialize 老转写是错的动作」结论——已纠正到 C11(c) 的执行顺序中）、用户 2026-07-18 四项决策。

## 6. 未解决项

- 全量放量（2.2 万份）授权——等 C10 金丝雀报告；
- Phase 1 任务卡（MKT/CRD/PRT/PROJ 各模块）——Phase 0 验收门通过后另行撰写（届时带着 Phase 0 的真实吞吐/成本数据写，避免现在拍脑袋）；
- tushare token（Phase 1 前用户提供）；
- `.bak` 清理的实际执行（C6 只出 dry-run 清单）。
