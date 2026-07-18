# ①②⑧ 续:自动驱动器/F0/策略面 硬化（2026-07-14）

## 概述（Overview）

对 2026-07-13 三条已完成方向各推进一个无外部依赖的收口增量,并在过程中定位并根治了 f8f70a 孤儿的**真实成因**（一个测试污染线上库，而非生产写原子性缺口）。全套件 3216 passed / 0 回归；真实 dry-run `scanned=369 reconciled=0 failures=0`（孤儿彻底离开 ready 集且不再被重建）。

## 变更清单（Changes）

| 文件 | 变更 | 方向 | 说明 |
|------|------|------|------|
| `src/finer/pipeline/driver.py` | 修改 | ① | `_acquire_drive_lock`/`_release_drive_lock` 非阻塞 fcntl 单飞锁；`drive_once` 包装为「取锁→`_drive_once_unlocked`→释放」，被占则 `skipped_locked=True` 即返；`DriveReport` 加 `skipped_locked` |
| `src/finer/policy/policy_config.py` | 修改 | ⑧ | `PolicyTuning` 加 `small_at/medium_at` + `conviction_bands()`；loader 读 `position_sizing_bands`（默认==0.35/0.70，越界/逆序降级默认） |
| `src/finer/policy/global_base.py` | 修改 | ⑧ | `compute_position_sizing_hint` 改读 `self.tuning.conviction_bands()`；删除模块级 `_CONVICTION_BANDS` |
| `src/finer/ingestion/f0_index_writer.py` | 修改 | ② | `record_imported` 顶部写原子性门：`receipt.record_path` 有但文件缺 → 拒绝注册（防新孤儿），前置于所有 insert，不留半写 |
| `configs/skills/f3f4-policy.yaml` | 修改 | ⑧ | `position_sizing_bands` 标「已 wire」 |
| `tests/test_wechat_channels_f0.py` | 修改 | ②(根因) | `test_wechat_channels_import_route` 补 `patch(_register_f0_index)`，堵住写线上 PM 库的隔离泄漏 |
| `tests/test_f0_index_writer.py` | 修改 | ② | autouse fixture 造 record 文件 + `TestWriteAtomicityGuard`（缺文件 raise / 零残留行 / 无 record_path 放行） |
| `tests/test_policy_config.py` | 修改 | ⑧ | +5 band 测试（默认==硬编码/shipped 回归/覆盖/逆序降级/越界降级） |
| `tests/test_pipeline_driver.py` | 修改 | ① | `test_concurrent_drive_is_skipped` + `skipped_locked` roundtrip |

## 架构影响（Architecture Impact）

- **①单飞锁**：锁文件 `.pipeline_drive.lock` 落在 `db_path.parent`（测试各自 tmp 隔离）或 `DATA_ROOT`（生产）。使 server autodrive 与 CLI `pipeline-drive --watch` 并发安全——不会两个 driver 争同一 envelope 造成 F1 uuid churn。POSIX only；非 POSIX/不可写目录降级为不加锁（best-effort）。
- **⑧position bands**：延续 F4 可调面「迁一个验证一个」纪律，`position_sizing_bands` 值镜像旧硬编码 → 行为不变（回归测试钉住）。GlobalBase 仍 Layer0 风格无关。
- **②写原子性门 + 测试隔离**：`F0IndexWriter` 现拒绝为「record_path 指向的文件不存在」的记录标 F0=ready → 防止生产侧产生 ready-无-record 孤儿。**f8f70a 真实成因确认**：`test_wechat_channels_import_route` 把 `REPO_ROOT` patch 到 tmp（record 文件落 tmp）但未隔离 `_register_f0_index`（`F0IndexWriter()` 绑定线上 `PROJECT_MEMORY_DB`）——注册瞬间 record 文件存在（门通过），tmp 拆除后文件消失 → 线上库留下孤儿，每次跑测试重建。堵住隔离即根治。

## 关键决策（Key Decisions）

1. **①锁用 GC/finally 双保险的 wrapper 而非重排 130 行**：把原 `drive_once` 改名 `_drive_once_unlocked`，新 `drive_once` 只做取锁/委托/释放（`try/finally`），零风险改动核心循环体。
2. **②写原子性门只在 `record_path` 显式给出且文件缺时 raise**；`record_path=None` 放行（Optional 契约不变）。真实 adapter 都是先写文件后注册，门恒通过；只在不变量被破坏时触发。
3. **②根因归因到测试而非生产**：f8f70a 不是生产写序问题，是测试写线上库。修 driver 侧 reconciliation（已有，自愈）+ writer 侧门（防新）+ **堵测试泄漏**（断源）三管齐下，比单纯反复 reconcile 干净。orphan 用「标 failed」自愈，不硬删多表行（删除红线）。
4. **⑧ `none_below` 固定 0.0 不可调**：GlobalBase 恒有 none 桶是不变量，只暴露 `small_at/medium_at`。

## 验证结果（Verification）

```
# 全套件（0 回归；较昨日 +9 测试：5 band + 1 lock + 3 F0 guard）
$ pytest tests/ -q → 3216 passed, 22 skipped in 70s

# 定向
$ pytest tests/test_policy_config.py tests/test_policy_mapper.py tests/test_policy_style_overlay.py → 78 passed
$ pytest tests/test_f0_index_writer.py → 13 passed（含 3 guard）
$ pytest 全部 F0 import 路径（bk1/writer/upload/wechat/bilibili/channels/pm）→ 102 passed
$ pytest tests/test_pipeline_driver.py tests/test_pipeline_autodrive.py tests/test_settle.py → 37 passed

# 真实路径冒烟
① 持锁时 drive_once → skipped_locked=True scanned=0；释放后 → scanned=370 正常
⑧ position sizing：conviction 0.34→none / 0.35→small / 0.69→small / 0.70→medium（与旧一致）
② 修 wechat 测试后跑该测试 → f8f70a 仍 failed（未被写回 ready）→ 泄漏封闭
最终真实 dry-run：scanned=369 reconciled=0 failures=0（孤儿彻底离开 ready 集）
```

## 未解决项（Open Issues）

- **f8f70a 残留热索引行**（contents/asset_index/source_* 仍在，stage_status F0=failed）：Import Console 可能仍显示；彻底删除需多表 DELETE（删除红线，需用户确认）。当前 failed 状态已让它离开 driver ready 集且（asset_index 重建时）逐步收敛。
- **②新内容 F1→F8 E2E 仍未演示**：需一次真实新导入（待用户给内容源）。
- **⑧真实差异化参数未配**：`by_style`/band 覆盖需回测数据支撑选值（依赖③/④活水）。
- **其他 import 路由测试的隔离**：已抽查 bilibili（有隔离）、files/wechat 契约（无 import POST）；未做全量 import-route 测试隔离审计，建议后续一轮 sweep（凡 TestClient POST import 且不 patch `_register_f0_index`/`get_connection` 者都会写线上库）。
- 变更在 `feat/pipeline-autodrive` 分支，未提交。
