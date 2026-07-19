# C5 · OPS-5 观测与告警（与 C4 绑定交付）

> 版本：v1.0 | 日期：2026-07-18（跨零点收尾 07-19）| 执行：Opus 4.8
> 上游任务卡：`docs/specs/2026-07-18-phase0-activation-task-cards.md` §C5
> 依赖：C4（heartbeat.json）已合入 main；消费 C4 的心跳做「心跳超时→告警」

## 1. 概述（Overview）

给 driver/settle 加观测面：①每轮落一行 run ledger JSONL；②三类告警（心跳超时 / 单轮失败率超阈 / 预算超限）经飞书 webhook 发出，URL 只从 `.env` `FINER_ALERT_WEBHOOK` 读、代码不落 token；③日志按天轮转 + 保留 14 天；④告警自测 CLI。心跳超时由**独立的** `alert-check` 周期任务检测（崩溃的 driver 无法给自己报警）。顺带补上 C4 wrapper 的 `.env` 加载缺口——launchd 任务不继承交互 shell 环境，没有它 F1 连 `MIMO_API_KEY` 都拿不到。

## 2. 变更清单（Changes）

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/schemas/ops.py` | 新增 | `RunLedgerEntry`（run_id/job_type/ts/status/duration_s/tokens_spent/stats/errors[]）+ `LedgerErrorEntry`（复用 Line F 信封字段 code/message/stage/operation/retryable/request_id/fix_hint/content_id）+ `AlertEvent` + type/severity 字面量。后端专用 |
| `src/finer/ops/ledger.py` | 新增 | `write_ledger_entry`（append `data/run_state/ledger/<YYYY-MM-DD>.jsonl`，best-effort）+ `build_drive_ledger_entry`/`build_settle_ledger_entry`（report→row，drive failures 映射为 canonical error 条目） |
| `src/finer/ops/alerts.py` | 新增 | 三 check（`check_heartbeat_stale` >2×interval / `check_failure_rate` >阈值 / `check_budget` budget_exceeded）→ 带 fix_hint 的 `AlertEvent`；`send_alert`（飞书 webhook，URL 从 env、never logged，未设→no-op False，永不抛）；`format_alert`；`self_test_event` |
| `src/finer/ops/log_rotation.py` | 新增 | `prune_old_logs(keep_days=14)`（按 mtime，缺目录 no-op，逐文件容错） |
| `src/finer/cli.py` | 修改 | drive 每轮 `_ledger_and_alert_drive`（ledger + 失败率告警；tokens 用 `get_usage_counter` 前后差，非破坏）；settle 落 ledger；新增 `alert-test`/`alert-check`/`prune-logs` 三子命令 |
| `scripts/ops/run_pipeline_drive.sh`、`run_feishu_watch.sh` | 修改 | **source `.env`**（补 launchd 环境缺口：keys + webhook）+ 起始 `prune-logs --keep-days 14` |
| `scripts/ops/run_alert_check.sh` | 新增（+x） | 心跳看门狗 wrapper（source .env + `finer alert-check`） |
| `configs/launchd/com.finer.alert-check.plist` | 新增 | StartInterval 300s 周期任务（非 KeepAlive）跑 alert-check |
| `tests/test_c5_observability.py` | 新增 | 22 例：ledger schema/append/映射、三 check（含 fix_hint/边界）、webhook mock（收到 payload / 不泄 URL / 未设 no-op / 非 200 False）、log 轮转、三 CLI 子命令 |

## 3. 架构影响（Architecture Impact）

- **F-stage 边界**：C5 全在横向 ops 层（`src/finer/ops/`，C4 seed 的包）。**未改业务提取逻辑**——ledger/告警挂在 CLI 的 drive/settle 命令（与 C4 心跳同层），不进 driver stage 逻辑。
- **Schema 契约**：`RunLedgerEntry`/`AlertEvent` 后端专用，无 contracts.ts；error 条目复用 Line F 信封字段集（不另造错误格式）。
- **数据/日志目录**：ledger 落 `data/run_state/ledger/<day>.jsonl`（`data/` gitignore）；日志 `logs/`（gitignore）按天 + 14 天保留。
- **密钥安全**：webhook URL 仅从 `FINER_ALERT_WEBHOOK` 读，代码与日志都不落；告警 payload 只含自产统计，无 token/secret。
- **告警拓扑**：失败率/预算告警在 driver 循环内联发（循环活着）；心跳超时由独立 `alert-check`（StartInterval）发（崩溃循环无法自检）。

## 4. 关键决策（Key Decisions）

1. **心跳超时用独立周期任务，不在 driver 内联**：一个卡死/崩溃的 driver 循环无法给自己发「我死了」。故 `alert-check` 是单独的 launchd StartInterval 任务，读 heartbeat.json 判 stale。失败率/预算这类「循环还活着但有问题」的告警才内联。
2. **补 C4 wrapper 的 `.env` 加载**：核查发现仓库无 dotenv 自动加载，env 靠环境注入。launchd 任务不继承交互 shell → C4 wrapper 原样跑连 `MIMO_API_KEY` 都没有（F1 直接废）。故 wrapper 加 `set -a; . ./.env; set +a`——既是 C5 告警 webhook 的需要，也补上 C4 的隐性缺口。
3. **tokens_spent 用累加器前后差（非破坏）**：C3 的进程内 usage 累加器是全局的，driver 不 reset。ledger 需要单轮 token → 在 CLI 里 `before/after get_usage_counter()` 差值，不 reset 全局（别的地方可能在读）。
4. **error 条目复用 Line F 信封字段**：ledger 的 errors[] 不另造格式，用 code/message/stage/operation/retryable/request_id/fix_hint/content_id——与项目 canonical error envelope 一致，DriveReport.failures 映射进去。
5. **`self_test_event` 而非 `test_event`**：生产代码里 `test_` 前缀函数会被 pytest 误收集为用例（且返回非 None 触发 warning）。改名避坑。
6. **告警全 best-effort**：send_alert 未设 URL→log+False、HTTP 非 200/异常→False，永不抛；ledger 写失败只 log。观测面绝不破坏它观测的 drive。

## 5. 验证结果（Verification）

- 新增测试：`pytest tests/test_c5_observability.py` → **22 passed**。
- 全量：`pytest -q` → **<FULL_COUNT>**（基线 3645 + 新增 22）。
- **CLI 实证**（真跑）：`alert-test`（未设 webhook）→ `{ok:false, error:FINER_ALERT_WEBHOOK 未设}`；`prune-logs --keep-days 14` → removed 0（日志皆新）；`alert-check` 读**真实** heartbeat.json（C4 smoke 遗留、interval=2s、age≈36114s）→ 正确判 stale、产 critical 事件（webhook 未设故未发）——看门狗对真实数据有效。
- **plist**：`com.finer.alert-check.plist` plutil + strict plistlib 双过；三 wrapper `bash -n` OK、可执行位已置。
- **不泄密**：webhook mock 测试断言 payload 文本不含 URL token；env 未设时告警 no-op。

## 6. 安装（追加到 C4 的 launchd 说明）

```bash
# 心跳看门狗（周期任务）
cp configs/launchd/com.finer.alert-check.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.finer.alert-check.plist

# 配置告警 webhook（飞书自定义机器人）：写进 .env（不进 git）
echo 'FINER_ALERT_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/XXXX' >> .env
# 自测
.venv/bin/python -m finer.cli alert-test
# 查看 ledger
cat data/run_state/ledger/$(date -u +%Y-%m-%d).jsonl
```

## 7. 未解决项（Open Issues）

- **预算告警只在脚本/batch 侧有意义**：driver 本身不设 token 预算硬顶（那是 C3 batch_runner），故 `check_budget` 主要给 scaleup/batch 用；已提供函数与单测，driver CLI 未内联（drive 无 budget_exceeded 状态）。
- **失败率告警可能重复**：内联发，连续多轮高失败率会重复告警；Phase 0 可接受，未来可加去重/静默窗口。
- **`.env` source 依赖 shell 兼容格式**：wrapper 用 `. ./.env`，要求 .env 是 KEY=value 形式（含引号/空格值可能出错）；当前 .env 兼容。
- **ledger 无轮转/归档**：按天分文件但不自动删；未来可复用 `prune_old_logs` 思路加 ledger 保留策略。
