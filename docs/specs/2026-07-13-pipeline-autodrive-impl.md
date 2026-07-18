# 增量流水线自动驱动器（roadmap ①实现）（2026-07-13）

## 概述（Overview）

实现 `docs/specs/2026-07-13-next-optimization-directions.md` 方向①：把手工的 `finer.cli pipeline-drive --watch` 前台循环，升级为 API 服务器托管的**可选后台刷新周期**——新导入的 F0 内容在下个周期自动流过 F1→F1.5→F2→F5→(F8 auto-backtest)→settle 并出现在收益榜/雷达，无需人肉跑脚本。默认关闭，`FINER_PIPELINE_AUTODRIVE=1` 显式开启。全部逻辑复用既有 `pipeline/driver.py:drive_once` 唯一编排单元，本次只加"调度 + 生命周期 + 状态暴露"。

## 变更清单（Changes）

| 文件 | 变更 | 说明 |
|------|------|------|
| `src/finer/config.py` | 修改 | 新增 `PipelineAutoDriveConfig` dataclass + `load_pipeline_autodrive_config()`（读 `FINER_PIPELINE_*` env，默认 OFF）+ `_env_flag` 辅助 |
| `src/finer/pipeline/autodrive.py` | 新增 | `PipelineAutoDriver`：可中断 async 循环，`asyncio.to_thread` 跑 `drive_once`，串行不重叠、错误隔离、`status()` 暴露 |
| `src/finer/api/server.py` | 修改 | 加 `lifespan` async context manager，启动时 `driver.start()`、关闭时 `driver.stop()`，`app.state.autodriver` 挂载 |
| `src/finer/api/routes/system.py` | 修改 | 新增 `GET /api/system/autodrive` 返回驱动器状态（enabled/running/runs/last_report）；import 加 `Request` |
| `tests/test_pipeline_autodrive.py` | 新增 | 7 测：disabled no-op / run_pass 记录 / 错误隔离 / 循环生命周期 / 双启幂等 / status 形状 / TestClient 真实 lifespan 端点（默认 disabled） |

## 架构影响（Architecture Impact）

- **分层守规**：编排真值仍在 `pipeline/driver.py:drive_once`；`autodrive.py` 只调度，`server.py` 只接线，`system.py` 端点只读状态——无业务逻辑下沉到 route（守 CLAUDE.md §3）。
- **数据流**：自动驱动器是 P0#2「增量数据流水线」的触发器落点。`drive_once` 非 dry_run 时 `settle_actions` 会真实 apply，故开启后同时满足 P0#3「F8 settle owner 定期翻牌」——两条 P0 残留由同一循环收口。
- **契约**：无 schema / contracts.ts 改动，不涉及前后端契约同步。
- **SQLite**：每个 pass 经 `drive_once` 写一行 `pipeline_runs` 运行日志（既有行为，非新表非迁移）；不新增表结构。
- **成本/副作用边界**：开启后服务器会按周期发起真实 LLM(F1/F2/F3/F5) 调用并 settle 写盘。因此**默认关闭**，仅 `FINER_PIPELINE_AUTODRIVE=1` 显式 opt-in，保证测试/CI/普通启动完全 inert。

## 关键决策（Key Decisions）

1. **默认 OFF、env opt-in**，而非默认自动跑。自动跑 = 一起服务器就烧 token + 改数据，属需谨慎的副作用；`.env` 里一行开关既满足「不碰脚本」意图，又不制造意外。验收标准的「不碰脚本」指不每次手跑，而非零配置。
2. **FastAPI lifespan 托管**（方案 a），而非 F0 commit 事件入队（方案 b）或 launchd（方案 c）。理由：单进程、无外部调度依赖、只要服务器在跑就自驱；F0 导入可能在别的进程（CLI feishu-sync），事件入队够不到服务器。
3. **`asyncio.to_thread` 跑同步 drive_once**：`drive_once` 是同步重活，丢 worker 线程，事件循环与请求处理永不阻塞。
4. **串行 + 错误隔离**：单循环 await 每个 pass 再 sleep，两次 drive 不会 race 同一 envelope；一个 pass 抛错只记 `last_error` 不杀循环。
5. **可中断 sleep**：用 `asyncio.wait_for(self._stopping.wait(), timeout=…)` 实现 sleep，stop() 能立即打断，关停不等满一个周期。

## 配置（env）

| 变量 | 默认 | 说明 |
|------|------|------|
| `FINER_PIPELINE_AUTODRIVE` | `false` | 开启后台驱动器 |
| `FINER_PIPELINE_DRIVE_INTERVAL` | `300` | pass 间隔（秒） |
| `FINER_PIPELINE_DRIVE_LIMIT` | 全部 | 每 pass 最多处理的 content_id 数 |
| `FINER_PIPELINE_DRIVE_SETTLE` | `true` | 每 pass 是否跑 F8 settle（apply） |
| `FINER_PIPELINE_DRIVE_INITIAL_DELAY` | `5` | 首个 pass 前的延迟（秒） |

## 验证结果（Verification）

命令与输出（`.venv/bin/python`，2026-07-13）：

```
# 单测 + 回归（driver/settle/contract-drift 无回归）
$ .venv/bin/python -m pytest tests/test_pipeline_autodrive.py \
      tests/test_pipeline_driver.py tests/test_settle.py tests/test_contract_drift.py -q
41 passed, 7 warnings in 4.80s

# 真实 uvicorn 启动 · 默认 env（disabled 路径）
$ curl /api/health         → {"status":"ok","service":"finer-canonic-api"}
$ curl /api/system/autodrive → {"enabled":false,"running":false,"interval_seconds":300,
                                "runs":0,"last_report":null,...}

# 真实 uvicorn 启动 · FINER_PIPELINE_AUTODRIVE=1 LIMIT=0 SETTLE=false（enabled 路径，隔离无 F-data 变更）
$ curl /api/system/autodrive → {"enabled":true,"running":true,"runs":1,
                                "last_report":{"run_id":"drive_20260713-194641_c6ae6304",
                                "scanned":0,"f5_ran":0,"settle":null,"dry_run":false,...}}
```

- disabled：端点能返回 driver 状态即证明 lifespan 已初始化 `app.state.autodriver` 且 `start()` 为 no-op（未起后台任务）。
- enabled：`running:true / runs:1 / last_report` 为真实 `drive_once` 产出（真 run_id、dry_run:false），证明服务器托管循环真调了 drive_once 并更新状态；`limit=0 + no-settle` 保证零 F-data 变更（仅 1 行 pipeline_runs 日志）。
- 验证后已 `pkill` 清理，`lsof` 确认 8098/8099 无遗留监听。

## 未解决项（Open Issues）

- **真实语料端到端未跑**（属方向②，故意不在①内触发）：本次 enabled 冒烟用 `limit=0` 隔离，未让真实 drive_once 处理真语料/发 LLM。开启 `FINER_PIPELINE_AUTODRIVE=1`（不带 limit=0）跑真实一轮 + 修 `content_id f8f70a…` F0 写原子性缺陷，是方向②的内容。
- **生产化**：当前是单进程 in-server 循环；多副本部署需加分布式锁（避免多实例并发 drive 同一 envelope），本次未做（单机足够）。
- 变更在 `feat/pipeline-autodrive` 分支，未提交（待用户确认）。
