# C6 · OPS-6 外置盘护栏（D1 决议的落地）

> 版本：v1.0 | 日期：2026-07-18（跨零点收尾 07-19）| 执行：Opus 4.8
> 上游任务卡：`docs/specs/2026-07-18-phase0-activation-task-cards.md` §C6 · 决策 D1
> 依赖：C5（AlertEvent / send_alert）已合入 main；driver 线最后一卡

## 1. 概述（Overview）

落地 D1「外置盘保留 + 护栏」：①**挂载健康检查**——broker raw PDF 所在外置卷（默认 `/Volumes/NAMEZY`，env 可覆盖）未挂载时，driver 跳过 broker F1、broker intake 跳过整轮，各发一条 warning `AlertEvent`，**绝不报错中断其他渠道**；②成文「关键中间产物全在内置盘」清单——盘拔最坏损失 = 不能重跑 F1 原文，已产出的 envelope/anchor/action 不受影响；③`.bak` 保留策略 + `scripts/prune_backups.py`（保留最近 N 份 + 保护命名安全快照 + wal/shm 同删；**dry-run 默认，实删需人过目**）。

## 2. 变更清单（Changes）

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/ops/mount_health.py` | 新增 | `broker_source_volume()`(env `FINER_BROKER_SOURCE_VOLUME`，默认 `/Volumes/NAMEZY`)/`is_volume_mounted`/`broker_volume_available`/`broker_mount_alert`(warning) |
| `src/finer/schemas/ops.py` | 修改 | AlertType 加 `volume_unmounted` |
| `src/finer/pipeline/driver.py` | 修改（C6 挂载检查） | DriveReport 加 `skipped_unmounted`；每轮开头查一次 broker 卷(仅当 channel 含 broker)；broker 项缺 F1 envelope 且卷未挂载→跳过计数，不走 f1_run（**不改 stage 执行逻辑，只加前置 guard**）；已有 envelope 的 broker 项照走 F2/F5 |
| `src/finer/cli.py` | 修改 | `_ledger_and_alert_drive`：`skipped_unmounted>0` 时发 `broker_mount_alert`（复用 C5 send_alert） |
| `src/finer/ops/ledger.py` | 修改 | drive ledger stats 加 `skipped_unmounted` |
| `src/finer/ingestion/broker_research_intake.py` | 修改 | CLI `main()` guard：**meta 不可达 且 卷未挂载**时→发 alert + skip + `return 0`（真「外置盘拔出」场景）；meta 可达（卷在/本地 meta）照常，meta 缺失但卷在仍是硬错（typo）。C7 精化：不再无条件查卷（避免 tmp meta + 盘掉线时误跳）。**只改 CLI，`run_intake` 库函数不变** |
| `scripts/prune_backups.py` | 新增 | 两族备份(`F5_executed.bak-*` 目录 / `finer.project.sqlite3.bak-*` 文件)；保留最近 `--keep`(默认3)个时间戳备份、**保护命名安全快照**(非 `YYYYMMDD-HHMMSS` 后缀，如 `-prebroker`/`-pre-*-cleanup`)、wal/shm 随基文件同删；dry-run 默认 |
| `tests/test_c6_disk_guardrail.py` | 新增 | 11 例：mount_health、prune plan/delete/scan/CLI(dry+execute)、intake guard、CLI mount alert |
| `tests/test_pipeline_driver.py` | 修改 | +3 例：卷未挂载 broker F1 skip、已有 envelope 照走 F2、卷可用照跑 |

## 3. 关键中间产物耐久性清单（盘拔安全边界）

| 产物 | 位置 | 盘拔影响 |
|------|------|---------|
| F0 ContentRecord + receipt | `data/F0_intake/broker/`（内置盘） | ✅ 不受影响 |
| F0 stage_status / asset_index | `data/project_memory/finer.project.sqlite3`（内置盘） | ✅ 不受影响 |
| **raw PDF 原文** | `/Volumes/NAMEZY/外资研报/...`（**外置盘**）；`data/raw/broker/*.pdf` 是 symlink | ⚠️ 盘拔后 symlink 悬空——**唯一损失 = 不能重跑 F1 原文** |
| F1 ContentEnvelope | `data/F1_standardized/`（内置盘） | ✅ 不受影响（已抽干 4298 份全在内置盘） |
| F2 anchor / F5 action / F8 result | `data/F2_anchored`、`data/F5_executed`、`data/F8_*`（内置盘） | ✅ 不受影响 |
| T3 结构化抽取 JSONL | 内置盘（rag_system 产物已落地） | ✅ 不受影响 |

**结论**：外置盘只承载 raw PDF 原文。盘拔最坏 = 已抽干的 broker F1 无法「从原文重烧」（但 envelope 已全在内置盘，无需重烧）；F2 起全链不依赖外置盘。故 D1「保留外置盘 + 护栏」成立——护栏保证盘拔时优雅降级而非崩溃。

## 4. 关键决策（Key Decisions）

1. **卷路径 env 可覆盖**：`FINER_BROKER_SOURCE_VOLUME`（默认 `/Volumes/NAMEZY`）。既让测试用 tmp 路径模拟「未挂载」(`os.path.ismount(tmp)` 恒 False)，也让换机可配。
2. **只跳 broker F1，不跳整条 broker 链**：外置盘只承载 raw PDF——只有「缺 F1 envelope 的 broker 项」需要它。已有 envelope 的 broker 项 F2/F5 读内置盘，照走。故 guard 精确落在「broker item + 缺 envelope + 卷未挂载」，不误伤已标准化内容。
3. **挂载检查加在 driver 但不改 stage 逻辑**：C6 owning 明确含「driver 挂载检查」；guard 是循环前的一次布尔 + 每项一个前置判断，F1/F2/F5 执行体一字未动（满足「禁改 raw 归档路径语义」与 stage 逻辑）。告警发射留在 CLI（与 C4/C5 同拓扑，driver 不耦合 alerts）。
4. **intake guard 只加 CLI `main()`，不加 `run_intake`**：库函数 `run_intake` 被大量单测直调（CI 无 `/Volumes/NAMEZY`）——若 guard 进 run_intake 会全体误跳。故只在 CLI 前置，且排在 meta-exists 硬错之前，让「meta 也在盘上」的情形优雅降级。
5. **prune 保护命名安全快照**：`.bak-<纯时间戳>` = 例行备份（settle 前快照），超 keep 剔除；`.bak-<命名>`(如 `-prebroker`/`-pre-f8f70a-cleanup`) = 刻意的迁移前安全快照，**永不自动删**。DB 的 wal/shm 随基文件同删。
6. **删除是红线——dry-run 默认，实删人过目**：D4 授权了 F5/DB 重建备份，但**未覆盖 .bak 清理**。故 `prune_backups.py` 默认 dry-run 只打印清单；`--execute` 才删，且工作流是「跑 dry-run → 人审清单 → 再 --execute」。**本卡未执行任何删除**——只交付脚本 + 展示 dry-run 清单（见 §5）。

## 5. 验证结果（Verification）

- 新增/改动测试：`pytest tests/test_c6_disk_guardrail.py tests/test_pipeline_driver.py` → **41 passed**（C6 11 + driver 30）。
- 全量：`pytest -q` → **3681 passed, 22 skipped**（基线 3667 + 新增 14，零回归）。
- **prune dry-run 实证**（真数据，只读，零删除）：`scripts/prune_backups.py` → F5_executed 保留最近 3、标记 10 个旧时间戳待删(~1.1MB)；DB 两个命名快照(`-prebroker`/`-pre-f8f70a-cleanup`)均 PROTECT；`dry-run: nothing deleted`。
- **挂载 guard 实证**（测试用 env→tmp 模拟未挂载）：driver 对 broker F1 项计 `skipped_unmounted`、local 项照跑；broker 有 envelope 项照走 F2；intake `main()` 未挂载→`return 0` 优雅跳过非报错。

## 6. 未解决项（Open Issues）

- **实删未做（有意）**：10 个旧 F5 备份的实际清删属删除红线，留给用户跑 `scripts/prune_backups.py --execute`（审清单后）。
- **卷判定基于 `os.path.ismount`**：外置盘挂在 `/Volumes/NAMEZY` 的常规场景成立；若挂载点异常（如挂成子目录）可能误判——当前部署不涉及。
- **告警去重**：driver 每轮若持续未挂载会每轮发一条 volume_unmounted 告警；Phase 0 可接受，未来随告警静默窗口一并处理（同 C5 失败率告警）。
- **prune 只覆盖两族已知备份**：新出现的备份命名族需在 `families` 列表登记。
