# F0 写原子性 reconciliation + 首次真实驱动一轮（roadmap ②）（2026-07-13）

## 概述（Overview）

执行 `docs/specs/2026-07-13-next-optimization-directions.md` 方向②：修 F0 写原子性缺口（`stage_status F0=ready` 但磁盘无 ContentRecord 的孤儿），并借①的 autodrive 机制跑通首次真实一轮。**结果**：孤儿 reconciliation 已实现并在真实 DB 上生效自愈（ready 集 370→369、每轮 failures=0）；autodrive 首次真实驱动一轮成功（真实 drive_once + settle 执行、无报错）。**诚实缺口**：本轮 `f1/f2/f5_ran=0`——当前 ready 集内没有任何新内容（12 个真实 envelope 已处理完且不在 stage_status，唯一的真实 ready 项就是那个孤儿），所以「新内容 F1→F8 上榜」这一 E2E 尚未演示，需一次真实新导入才能闭合。

## 变更清单（Changes）

| 文件 | 变更 | 说明 |
|------|------|------|
| `src/finer/pipeline/driver.py` | 修改 | `DriveReport` 加 `reconciled` bucket；新增 `_reconcile_orphan()`；`rec is None` 分支从「每轮报 failure」改为「标 F0=failed 自愈」；日志加 reconciled 计数 |
| `src/finer/pipeline/autodrive.py` | 修改 | run_pass 日志加 reconciled 计数 |
| `tests/test_pipeline_driver.py` | 修改 | 旧 `test_missing_content_record_is_failure` 重写为 reconcile 语义 + 新增 3 测（不再被 rediscover / 再导入恢复 / dry-run 不写盘） |
| `tests/test_pipeline_autodrive.py` | 修改 | `_FakeReport` 加 `reconciled` 属性 |
| 真实 PM DB `stage_status` | 数据 | 孤儿 `f8f70a…` 的 F0 行 `ready`→`failed`（driver 正常 reconciliation，非手工 SQL；自愈） |

## 架构影响（Architecture Impact）

- **F0 Project Memory 契约**：SQLite 是热索引、ContentRecord 文件是 F0 真值。`ready` 但无 record = 索引与真值不一致。driver 现把这类行收敛为 `failed`（离开 ready 集），符合「索引向真值对齐」纪律，不做多表硬删除（保留审计）。
- **自愈语义**：`_upsert_stage_status` 的 ON CONFLICT 让真实再导入把 F0 翻回 `ready`（`F0IndexWriter` 写 ready 时）→ reconciliation 可逆、无需人工干预。
- **settle owner（P0#3）**：本轮真实 settle 证明其正确性——42 action 中 32 terminal 跳过、6 non-directional（neutral，永久不可结算）、4 no_data（000905.SH/SOX 无价格）、0 误翻。10 条 pending 各有正当归因，非 bug。
- **契约/schema**：无 Pydantic/contracts.ts 改动；`DriveReport.reconciled` 是内部报表字段，不入前端契约。

## 关键决策（Key Decisions）

1. **只做 driver 侧 reconciliation，不做 writer 侧硬门**。原计划让 `F0IndexWriter` 在标 `ready` 前验证 record 落盘，但现有 `test_f0_index_writer.py` 把 `receipt.record_path` 当元数据传（指向不存在的文件），加硬门会误伤 11 个测试并触碰 F0 导入热路径。driver 侧 reconciliation 已完全达成「真实一轮干净 + 孤儿自愈」，writer 侧「标 ready 前验证 record 持久化」列为显式 follow-up（需连带改导入契约与测试）。
2. **reconcile 用「标 failed」而非「删多表行」**。标 failed 是单行、可逆、自愈、保留审计的最小修复；删 contents/asset_index/source_* 多表行是删除红线且更具破坏性，留作独立 Import Console 清理（需用户确认）。
3. **reconciled 独立于 failures**。只有孤儿的一轮 = 干净完成（`pipeline_runs.status=completed`，failures=0），不再把「已处理的历史脏数据」误报为运行失败。
4. **真实 settle 前先备份 F5**（`data/F5_executed.bak-<ts>`，镜像 CLI `settle --apply`）。本轮 settle 零翻牌，diff 确认与备份逐字节一致（数据 no-op），备份冗余可删。

## 验证结果（Verification）

命令与输出（`.venv/bin/python`，2026-07-13）：

```
# 单测 + 回归（driver 新增 4 测 / autodrive / f0_writer / settle / drift 无回归）
$ pytest tests/test_pipeline_driver.py tests/test_pipeline_autodrive.py \
         tests/test_f0_index_writer.py tests/test_settle.py tests/test_contract_drift.py -q
54 passed

# 真实一轮（server autodrive, FINER_PIPELINE_AUTODRIVE=1, 无 limit, settle on）
autodrive status: enabled=True running=True runs=1 last_error=None
last_report: run_id=drive_20260713-214037_3e17e168
  scanned=370 f1=0 f2=0 f5=0 skipped_legacy=368 excluded=1 reconciled=1 failures=0
  RECONCILED: f8f70a474225400c240af9013c29dbe7 -> marked_failed
settle: scanned=42 verified=0 failed=0 skipped_non_directional=6 skipped_no_data=4
        skipped_terminal=32 errors=[] dry_run=false

# 自愈证据
孤儿 F0 状态: ready → failed (error_code=ContentRecordMissing)
二次真实 dry-run: scanned=369 (↓1, 孤儿离开 ready 集) reconciled=0 failures=0
F5 validation_status: 23 failed / 10 pending / 9 verified (settle 零误改)
diff F5_executed vs 备份: 逐字节一致
剩余 uvicorn 进程: none
```

- **孤儿修复闭环**：真实一轮把 f8f70a 标 failed → 二次 dry-run scanned 370→369、0 failures → 未来每轮干净，且真实再导入会翻回 ready（自愈）。
- **① 机制真实验证**：autodrive `enabled/running/runs=1` + 真实 `run_id` + settle 执行，证明服务器托管循环在真实 DB 上跑通一轮。
- **settle owner 正确**：0 误翻，10 pending 归因清晰（6 无方向 + 4 无价格）。

## 未解决项（Open Issues）

- **新内容 F1→F8 E2E 未演示（②的另一半）**：本轮 `f1/f2/f5_ran=0`，因 ready 集内无新内容。真正闭合需一次**真实新导入**（飞书/B站/本地上传一条新内容），确认 drive_once 带它走 F1→F1.5→F2→F5→F8→settle 并在 `/api/opinions/timeline` 出现 verificationStatus。需用户提供内容源。
- **writer 侧原子性硬化（follow-up）**：`F0IndexWriter` 标 `ready` 前验证 ContentRecord 落盘（+ 连带把 `test_f0_index_writer.py`/`test_import_receipt.py` 的 `record_path` 从元数据升级为落盘契约）。当前 adapter 都是先写文件再 record_imported，暴露面小，故降为 follow-up。
- **4 条 no_data pending（000905.SH 中证500 / SOX 费半）**：价格数据层缺这两个指数，settle 永久跳过。属方向③「价格数据层 owner」范畴。
- **6 条 non-directional pending**：neutral/watch 无方向，本就不可结算——考虑给它们一个 terminal-neutral 态以出 pending 池（避免长期挂 pending 造成「未结算」错觉）。
- Import Console 仍会显示 f8f70a（asset_index/contents 行未删）；彻底清理需多表删除，属删除红线，留待确认。
- 变更在 `feat/pipeline-autodrive` 分支，未提交。
- 冗余备份 `data/F5_executed.bak-20260713-214009`（与现状一致）可删。
