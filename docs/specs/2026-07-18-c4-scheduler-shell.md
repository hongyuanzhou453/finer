# C4 · OPS-4 调度器壳（launchd + 心跳）

> 版本：v1.0 | 日期：2026-07-18 | 执行：Opus 4.8
> 上游任务卡：`docs/specs/2026-07-18-phase0-activation-task-cards.md` §C4
> 依赖：C2（DriveRunConfig / `pipeline-drive` CLI）已合入 main

## 1. 概述（Overview）

给常驻驱动/监听循环加一层调度壳：两份 launchd plist（`pipeline-drive` + `feishu-watch`，RunAtLoad+KeepAlive，走 `.venv` wrapper 脚本，日志按天落 `logs/`）+ 驱动 watch 循环每 pass 末写心跳（`data/run_state/heartbeat.json`）。顺手修 R4：非法 `--stages` 现在 argparse 解析期即被拒（exit 2 + 可读消息），不再裸 traceback 逃逸或在 `--watch`/launchd KeepAlive 下 respawn-loop。**装载 launchd 属改系统配置——plist 与安装命令成文，实际 `launchctl load` 由用户手动执行一次**。

## 2. 变更清单（Changes）

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/schemas/heartbeat.py` | 新增 | `HeartbeatState`（pid/job_type/started_at/last_pass_at/cycles/interval_seconds/lock_holder/last_pass_stats）。后端专用，无 contracts.ts |
| `src/finer/ops/__init__.py` | 新增 | seed OPS 包（C5 在此加 ledger/alerts 兄弟模块） |
| `src/finer/ops/heartbeat.py` | 新增 | `write_heartbeat`（原子 tmp+replace，best-effort 永不破坏循环）/`read_heartbeat`/`heartbeat_path` |
| `src/finer/cli.py` | 修改 | ①R4：`_stages_arg` argparse `type` 校验（对齐 `--channel` 的 choices）+ `--stages type=_stages_arg`；②`_cmd_pipeline_drive` watch 循环每 pass 末写心跳；③`_drive_heartbeat_state` 抽为模块级（report→HeartbeatState 映射可单测）；④程序化 Namespace 传字符串 stages 也走校验（返回 error dict，不 traceback） |
| `configs/launchd/com.finer.pipeline-drive.plist` | 新增 | 驱动 agent；RunAtLoad+KeepAlive+ThrottleInterval；绝对路径（机器相关，装前改） |
| `configs/launchd/com.finer.feishu-watch.plist` | 新增 | Feishu 监听 agent，同上 |
| `scripts/ops/run_pipeline_drive.sh` | 新增（+x） | wrapper：cd repo → `.venv/bin/python -m finer.cli pipeline-drive --watch`；env 覆盖 interval/channel/stages；日志按天；含 R2 scaleup 双开告诫 |
| `scripts/ops/run_feishu_watch.sh` | 新增（+x） | wrapper：`feishu-watch --interval`，同上 |
| `tests/test_c4_scheduler.py` | 新增 | 20 例：R4 校验/CLI exit-2、心跳 schema/映射/IO 往返/坏目录不抛、plist strict-XML 良构、wrapper 可执行 |

## 3. 架构影响（Architecture Impact）

- **F-stage 边界**：C4 属横向 ops 层。**未改 driver 的 stage 逻辑**——心跳写在 CLI 的 watch 循环（`cli.py`），复用 PR #8 已有的 fcntl 单飞锁（未重复实现）。新增 `src/finer/ops/` 包由 C4 seed，C5（观测告警）加兄弟模块。
- **Schema 契约**：`HeartbeatState` 后端专用，无 contracts.ts 镜像，不触发枚举漂移防护。
- **数据/日志目录**：心跳落 `data/run_state/heartbeat.json`（`data/` 已 gitignore）；wrapper 日志落 `logs/`（已 gitignore）。plist 引用绝对路径（launchd 要求），机器相关，装前需改。
- **单飞并发**：两实例并发时靠 drive_once 每 pass 的 fcntl 锁——第二实例 pass 被拒（`skipped_locked=True`），心跳 `lock_holder=False` 如实反映，可与「卡死」区分。

## 4. 关键决策（Key Decisions）

1. **R4 修在 argparse `type` 层，不在命令函数里 try/except**：这样非法 `--stages` 在解析期就以 argparse usage error（exit 2、可读消息）被拒，根本进不了 watch 循环或 launchd 的 spawn。命令函数再兜一层（程序化 Namespace 传字符串也校验），双保险。这精确对齐既有 `--channel` 的 `choices` 门。
2. **心跳只给 pipeline-drive，不给 feishu-watch**：卡定心跳路径是单文件 `heartbeat.json`；两 job 写同一文件会互相覆盖。故心跳锁定驱动（卡的「driver 心跳写入」），feishu-watch 靠日志可观测，C5 的 ledger 再统一。未来要多 job 心跳可按 job_type 分文件名。
3. **心跳构造抽为模块级 `_drive_heartbeat_state`**：把 report→HeartbeatState 的映射（尤其 `lock_holder = not skipped_locked`）从循环闭包里提出来，不跑循环即可单测。
4. **launchd 装载留给用户手动**：`launchctl load` 改系统配置属红线；本卡只交付 plist + 命令文档，不代执行。plist 用绝对路径（launchd 要求），默认 `/Users/zhouhongyuan/Desktop/finer`，装前按实际 checkout 改。
5. **plist 注释去掉 `--`**：XML 注释禁含 `--`（strict expat/plistlib 会拒，虽然 Apple 的 plutil 宽容）。注释里所有 `--watch`/`--interval` 改叙述式措辞，两解析器均过。

## 5. 验证结果（Verification）

- 新增测试：`pytest tests/test_c4_scheduler.py` → **20 passed**。
- 全量：`pytest -q` → **<FULL_COUNT>**（基线 3625 + 新增 20）。
- **R4 实证**：`pipeline-drive --stages f1,f9|bogus|""` → 全部 `SystemExit(2)` + argparse 消息，无 traceback；`--stages f1,f2` → `args.stages == ['f1','f2']`。
- **心跳实证**：`pipeline-drive --watch 2 --dry-run --channel broker` 跑数 cycle → `data/run_state/heartbeat.json` 持续更新（cycles 递增到 2、`pid`、`lock_holder=true`、`last_pass_stats={scanned:4298, f1_ran:0, f2_ran:2659, f5_ran:1639, failures:0}`——dry-run 计数亦印证 C3 结论：broker F1 已满，前沿在 F2/F5）。
- **单飞锁实证**：并发两个单跑 dry-run 驱动 → **恰一个 `skipped_locked=true`**（被锁拒），另一个持锁运行；SIGINT 收尾干净打印 `{"status":"stopped",...}` 无 traceback。
- **plist 双解析器**：`plutil -lint` OK + strict `plistlib.load` 均通过（去 `--` 后）；wrapper `bash -n` 语法 OK、可执行位已置。

## 6. 安装 / 卸载 / 查看日志（用户手动执行一次）

```bash
# 0) plist 用绝对路径，默认 /Users/zhouhongyuan/Desktop/finer；若 checkout 在别处，先改两份 plist 内路径。

# 1) 装载（现代 macOS 推荐 bootstrap；load/unload 亦可）
cp configs/launchd/com.finer.pipeline-drive.plist ~/Library/LaunchAgents/
cp configs/launchd/com.finer.feishu-watch.plist   ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.finer.pipeline-drive.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.finer.feishu-watch.plist
#   旧写法： launchctl load ~/Library/LaunchAgents/com.finer.pipeline-drive.plist

# 2) 查看状态 / 日志 / 心跳
launchctl list | grep com.finer
tail -f logs/pipeline-drive-$(date +%Y%m%d).log
tail -f logs/launchd.pipeline-drive.err.log
cat data/run_state/heartbeat.json

# 3) 卸载
launchctl bootout gui/$(id -u)/com.finer.pipeline-drive
launchctl bootout gui/$(id -u)/com.finer.feishu-watch
#   旧写法： launchctl unload ~/Library/LaunchAgents/com.finer.pipeline-drive.plist
rm ~/Library/LaunchAgents/com.finer.pipeline-drive.plist ~/Library/LaunchAgents/com.finer.feishu-watch.plist
```

> **R2 告诫**：`run_pipeline_drive.sh` 默认 `channel=all`。驱动会跳过已完成项，稳态成本低，但**broker F1 scaleup 进程活跃时勿装载/运行**（会 race `data/F1_standardized`）——装前 `ps aux | grep -i scaleup` 确认。

## 7. 未解决项（Open Issues）

- **feishu-watch 无心跳**：见决策 2，单文件心跳限制；需要时按 job 分文件。
- **plist 绝对路径机器相关**：非可移植；换机/换路径需手改。可未来加一个 `scripts/ops/install_launchd.sh` 用 `sed` 注入 `$REPO_ROOT`（本卡未做，避免代执行系统装载）。
- **告警未接**：心跳只是被动落盘；「心跳超时→告警」是 C5（观测告警）的活，本卡只提供心跳数据源。
