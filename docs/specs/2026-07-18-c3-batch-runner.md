# C3 · OPS-3 batch_runner 并发批量执行池

> 版本：v1.0 | 日期：2026-07-18 | 执行：Opus 4.8
> 上游任务卡：`docs/specs/2026-07-18-phase0-activation-task-cards.md` §C3
> 依赖：C0（LLM usage 计量）/ C1（broker stage_status 回填）/ C2（DriveRunConfig）已合入 main

## 1. 概述（Overview）

新建一个 F-stage 无关的并发批量执行池（asyncio semaphore + 逐条失败隔离 + checkpoint 断点续传 + token 预算硬顶 + quota-strikes 熔断），把本轮 scratchpad 的 broker 放量逻辑收编为仓内可复现入口 `scripts/drive_broker_scaleup.py`（写 stage_status）。circuit-breaker 语义迁移自 NAS `rag_system/structured_extract.py`（迁语义不迁依赖）。顺手带上外部审查的 R2（预算护栏）与 R3（COALESCE 语义措辞）。

## 2. 变更清单（Changes）

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/schemas/batch_run.py` | 新增 | `BatchRunManifest`（run_id/total/done/failed/skipped/budget_spent_tokens/checkpoint_cursor/started_at/finished_at + stage/concurrency/quota_strikes/status/stop_reason/resume_command/failures）+ `BatchItemOutcome`。Backend-only，无 contracts.ts 镜像（同 DriveRunConfig 口径） |
| `src/finer/pipeline/batch_runner.py` | 新增 | `run_batch`（async 核心）/`run_batch_sync`（wrapper）；semaphore 池、逐条失败隔离、append-only checkpoint（`<batch_id>.checkpoint.jsonl`）、token 预算硬顶、`QuotaTripped`/`BudgetExceeded` 熔断；manifest 原子快照（tmp+replace）。**不 import driver 主逻辑，仅靠注入的 `process_item`/`usage_reader`/`quota_reader` 协作** |
| `src/finer/llm/client.py` | 修改 | ①`_extract_usage_tokens`：total 缺失时由 parts 计算、reasoning_tokens 兜底、类型强转，修 reasoning 模型 usage 解析；②进程内 usage 累加器（`reset_usage_counter`/`get_usage_counter`）；③quota-strike 追踪器（chat() 200→`record_quota_success`，401/402/403/429→`record_quota_error`；`get/reset_quota_state`） |
| `scripts/drive_broker_scaleup.py` | 新增 | 仓内可复现 F1 放量入口：从 stage_status 发现 broker F0-ready 且缺 F1 的内容，走 batch_runner 池，**逐条落 stage_status F1='ready'**（每条独立短连接 + 30s busy_timeout，避开共享池连接的跨线程写危险）；`--budget/--concurrency/--quota-strikes/--max-items/--batch-id/--no-resume/--execute`，默认 dry-run，熔断→非零退出 + resume 命令 |
| `src/finer/ingestion/f0_index_writer.py` | 修改（R3） | 仅改注释：COALESCE 语义如实描述为「receipt.source_channel 必填 → excluded 永不为 NULL → 新值恒胜；existing 兜底只守不可达的 NULL-receipt；也让 re-register 回填 legacy NULL 行」。**无 SQL/行为变更** |
| `tests/test_batch_runner.py` | 新增 | 8 例：全量处理+manifest 字段、失败隔离、SKIPPED 语义、checkpoint 续跑不重复、预算硬顶熔断、quota 熔断、dry-run、并发上界。注入 reader，全 deterministic 无真实 LLM |
| `tests/test_llm_usage_log.py` | 修改 | +7 例：total 由 parts 计算、reasoning 兜底、null 兜底、累加器跨调用、provider 缺 total 端到端、quota strike/reset、非 quota(500) 不熔断 |
| `tests/test_f0_index_writer.py` | 修改（R3） | +3 例：首次 register 落渠道、re-register 新值覆盖、legacy NULL 行回填 |

## 3. 架构影响（Architecture Impact）

- **F-stage 边界**：batch_runner 是横向公共层（`pipeline/`），不属任何单一 F-stage；通过 `process_item` 注入与 `pipeline/driver.py` 协作，**未改 driver 主循环**（卡约束「禁改 driver.py 主逻辑」满足）。scaleup 脚本只读复用 driver 的 `_default_f1_executor`/`_find_content_record`/`_is_excluded`/`_discover_ready_content`。
- **Schema 契约**：`BatchRunManifest` 后端专用，无 contracts.ts 镜像，不触发枚举漂移防护（同 DriveRunConfig）。
- **数据目录**：新增 `data/run_state/`（manifest + checkpoint）；gitignore 覆盖 `data/`。
- **LLM 计量层**：`llm/client.py` 新增进程内 telemetry（usage 累加器 + quota 追踪器），是预算/熔断的真相源；进程本地设计——同进程多线程共享，独立进程（并行 scaleup）各自计数。所有 telemetry best-effort，永不影响 LLM 调用本身。
- **circuit-breaker 层级**：把 HTTP-status 可见性留在 `chat()` 边界（quota strike 在此判定），batch_runner 只读 `get_quota_state()`——避免上层需要 HTTP 访问，符合分层。

## 4. 关键决策（Key Decisions）

1. **telemetry 放在 llm/client.py 而非 batch_runner**：executor 返回 `Path`/`int`，token 数深埋在 StandardizationRouter→LLMClient 内。与其让 batch_runner 去 scrape JSONL 日志（并发+跨进程脆弱），不如在调用边界维护进程内累加器 + quota 追踪器，batch_runner 只读快照。既拿到真实 token，又不破坏 driver 注入式协作。
2. **预算单位=token（非 call 数）**：卡明确要 token 预算硬顶；NAS 原版是 call-count 预算，本实现迁其熔断/续跑语义但改为 token 口径。
3. **R3 取「改措辞」不「翻转 COALESCE」**：卡的首选处置即「修正措辞」，翻转仅在「产品要求首次归属不可变」时。无证据要求该语义；new-wins 无实害（内容来源渠道稳定，新值=旧值）且照样回填 legacy NULL 行。故只改注释使其如实，行为零变。**留待用户否决**：若日后要首次归属不可变，翻 COALESCE 参数序 + 改测试即可。
4. **验收改走 mock 机制 + 真形状 usage 单测，不跑真实 broker F1 放量**：核对时另一并行会话的 `broker_scaleup_runner.py --workers 8`（PID 78792，7h+ CPU）在活跃写 `data/F1_standardized`。真跑 20 条 broker F1 会双烧 MiMo 配额并 race。故 batch_runner 全部用注入的 process_item/reader deterministic 验证并发/续跑/预算/熔断/manifest；用真实 MiMo 响应形状（`{prompt_tokens,completion_tokens}`，NAS 已证）的 `_log_usage` 单测证明 tokens 非 null，不发真调用。
5. **scaleup 脚本 stage_status 写用「每条独立短连接」**：项目连接池 `get_connection` 返回跨路径共享连接（`check_same_thread=False`），8 线程并发 execute/commit 同一连接不安全。脚本改为每条 upsert 开短连接 + `busy_timeout=30000` 骑过 WAL 写竞争（含并行 scaleup 进程）。

## 5. 验证结果（Verification）

- 新增/受影响测试单跑：`pytest tests/test_batch_runner.py tests/test_llm_usage_log.py tests/test_f0_index_writer.py` → **40 passed**。
- 全量：`pytest -q` → **3625 passed, 22 skipped**（基线 3607 + 新增 18，零回归）。
- 脚本真实 dry-run（只读，写 manifest 到 scratch）：`drive_broker_scaleup.py --run-state-dir <scratch>` → discovered=0、status=completed、manifest 字段齐全。**实况核查**：4298 条 broker F0-ready **全部已有 F1 envelope**（0 record-not-found、0 excluded、0 needs；磁盘 4723 个 F1 dir），即 7 小时 scaleup 已把 broker F1 backlog 抽干——discovery 逻辑正确，非空转 bug。
- import 无循环：`batch_run` / `batch_runner` / `llm.client` / `scripts.drive_broker_scaleup` 全部干净导入。

## 6. 未解决项（Open Issues）

- **R2 只在 batch_runner/脚本侧落地**：batch_runner 有 `budget_tokens`+`max_items` 护栏，脚本 `--max-items` 提示 + 熔断非零退出；但 driver 的 `drive_once` 无参全量扫描风险未动（卡定 driver.py 主逻辑禁改）——按卡「或至少写进操作纪律」，已在任务卡 §C3 ✅ 行与 §1 执行规则记「scaleup 在跑时禁止无参 pipeline-drive」。
- **真实 F1 放量未跑**：broker F1 backlog 实况已抽干（0 needs），故 `--execute` 路径未在真数据上跑过；机制由 mock 测试全覆盖。pool 的前瞻价值转向：可续传/带预算的未来导入，以及 F2/F5 阶段（pool 已足够通用，脚本可平移）。
- **manifest 每条一写**：`_write_manifest` 每条 item 原子重写，数千条时是数千次小文件写；当前规模可接受，未来大批可加节流（每 N 条或按时间）。
- **F1 executor 的 `_ROUTER` 全局无锁懒建**：8 线程首调可能并发建多个 StandardizationRouter（最后一个胜，多余 client 被丢），良性无数据损坏；若在意可在起池前串行预热一条。
