# C9 follow-up · persist_dir root-cause fix + additive broker drive

> 版本：v1.0 | 日期：2026-07-21 | 执行：Opus 4.8
> 上游：`docs/specs/2026-07-18-c9-f2-reanchor-redrive.md` §6（deferred follow-up）
> 依赖：C9 core（evidence 6.6%→100%）已完成并推 main（`7cc01801`）

## 1. 概述（Overview）

根治 broker evidence 断链的**根因**（driver 从不写 F2 evidence sidecar），并把「新可匹配 action」落地。根因修复后，一次普通 `drive --execute` 就产出 **16 条全新 canonical action** 且三向审计**保持硬 100%**。原任务假设的 ~238 additive 经实测证伪：其中 226 条是国际 ticker（`.T`/`.TW`），在 F5 tradability 门被正确拒（`pseudo_ticker_symbol`）；真正可落地的只有 16 条美股裸 ticker。**重锚 no_anchor envelope 被实测证明是 0 增益**（详见 §4 决策 2），故未执行。

## 2. 变更清单（Changes）

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/pipeline/canonical_runner.py` | 修改 | `run_canonical_from_artifacts` 新增 `persist_dir` 参数；新增 `_persist_evidence_sidecars` helper。set 时把**每条 emitted action 引用的 F2 evidence span**写成 `persist_dir/F2_evidence/{span_id}.json` sidecar。只写 grounded 子集（来自 action 已 grounded 的 `evidence_span_ids`，非整包 envelope span），不写 F3/F4（上游输入，caller 拥有）。 |
| `scripts/drive_broker_recommendations.py` | 修改 | ① 传 `persist_dir=DATA_ROOT` 给 F5 runner（根因修复：所有未来 broker drive 自动写 sidecar）；② 新增 `--data-root`（worktree 下 `data/` 被 gitignore/缺席，指向 canonical data root）；③ `TradeActionRepository(db_path/action_dir)` 绑定到选定 data root。 |
| `scripts/c9_reanchor_no_anchor_envelopes.py` | 新增 | no_anchor broker envelope 的 additive 重锚工具（dry-run 默认，`--execute` 先备份 F2+F5，`ProcessPoolExecutor` 真并行）。**本轮未执行**（0 增益）；交付给未来「国际锚点检测」follow-up 使用。 |
| `tests/test_canonical_artifacts_persist.py` | 新增 | 2 例：persist_dir 只写 grounded 子集（目标 symbol 的 span 写、无关 symbol 的 span 不写）；无 persist_dir 时 runner 只读。 |

**数据变更（main repo `data/`，gitignore，不进 commit）**：+16 `bri_*_actions.json`（1773→1789）、+849 F2_evidence sidecar（64105→64954）、+242 F4（2127→2369，driver 对每条 mapped intent 写 F4，含被拒的 226）。备份 tag `20260721-033106-c9-additive-drive-bde261d3`（F5_executed + F2_anchored 命名快照）。

## 3. 架构影响（Architecture Impact）

- **F5 canonical contract 强化**：`run_canonical_from_artifacts` 现与 `run_canonical_from_envelope` 对齐——都能在 `persist_dir` 下产出可被三向审计 resolve 的 evidence sidecar。契约差异（有意为之）：artifacts 路径只写 evidence（F3/F4 是 caller 已在盘上的上游产物），envelope 路径写全三层（它自己 generate F3/F4）。
- **审计不变量**：`scripts/audit_trace_integrity.py` 的 `EVIDENCE_MIN=1.0`（硬门，`tests/test_audit_trace_integrity.py`）现由 driver 侧自动满足——任何新 broker action 落盘即带 sidecar，不再需要事后补写 pass。
- **数据流**：`extraction/action_composer.py:compose_trade_action`（唯一构造点）不变；本次只在 runner 出口补 sidecar 持久化，未碰 F5 构造/grounding 逻辑。
- **无跨层违规**：driver 仍走 F3(bri)→F4(policy_mapper)→F5(canonical_runner) canonical 链。

## 4. 关键决策（Key Decisions）

1. **persist_dir 只写 evidence sidecar（不写 F3/F4）**：根因（spec §6）明确是「driver 不写 sidecar」。F3 bri intent 由 A3 adapter 预先落盘（100% resolve），F4 由 driver 自身写。故最外科的修复=补 evidence sidecar。避免了改写 caller 上游 F3（driver 的 `bridge_target_symbol` 会 mutate `target_symbol`，若 persist 改写 F3 会把 normalized 值写回盘）。
2. **重锚 no_anchor envelope 被证伪、跳过**：三重实测——(a) driver dry-run 显示 **242 条已 bridge**（未重锚，靠 phase-1 intent 侧 `normalize_broker_ticker` 对**现存**锚点匹配）；(b) 同一 160 样本 old-anchor match == new-anchor(重锚后) match == **16**，重锚增益 = 0；(c) 剩 1819 未匹配是 US/CN/HK（实为国际 `.PA`/`.L`），重锚不产生新锚点（spec §6 打脸：envelope 侧不检测国际 ticker）。→ 重锚是「40 分钟覆写 2061 个 F2、换 0 action」，不做。脚本仍交付，因为国际锚点检测 follow-up 落地后需要它。
3. **`--data-root` 贯通**：worktree 的 `data/` 被 gitignore 故缺席；main repo 与本 worktree branch 同 commit 且持有 canonical `data/`。用 `main-venv python + worktree scripts（sys.path 前插 worktree/src）+ --data-root main/data` 跑，实现「worktree 代码 + venv 依赖 + canonical 数据」，代码隔离不破。
4. **~238 估计的证伪根因 = F5 tradability 门**：spec 的 ~238 是 **bridged intent 数**，未计 F5 `is_plausible_tradable_symbol` 门。242 bridged 里 76 `.TW` + 150 `.T`（东京）= 226 条国际 shape 被 `pseudo_ticker_symbol` 正确拒，只有 16 条裸美股 ticker 落地。**国际解锁需两个 follow-up**（锚点检测 + tradability 门扩展），非一个。

## 5. 验证结果（Verification）

```
# 单测（新增 + 相关回归）
pytest tests/test_canonical_artifacts_persist.py tests/test_canonical_from_envelope.py \
       tests/test_sector_proxy.py tests/test_canonical_runner_mapping.py \
       tests/test_canonical_runner_quality_gate.py tests/test_canonical_f3_f4_f5_contract.py \
       tests/test_audit_trace_integrity.py tests/test_c9_ticker_stoplist.py
→ 115 passed, 1 skipped

# 全量
pytest -q tests/  → 3668 passed, 72 skipped, 0 failed（28.5s）

# additive drive（canonical data，备份先行）
drive_broker_recommendations.py --data-root <main>/data --execute
→ grounding bridge matched: 242
  F5 trade_actions produced: 16 （canonical_trace_status: {canonical: 16}）
  F5 rejected: 226 （全部 pseudo_ticker_symbol = .T/.TW 国际 shape）
  files written: 16, indexed: 16, F4 persisted: 242

# 三向审计（硬门 EVIDENCE_MIN=1.0）
audit_trace_integrity.py --data-root <main>/data
→ total 1915  fully intact 1915
  intent 1915/1915 (100%) · policy 1915/1915 (100%) · evidence 1915/1915 (100%)  span 64954/64954 (100%)
```

`build_f2_deterministic_envelope` 确认**确定性**（同输入 → 完全相同 span id）且**无网络 I/O**（纯 CPU regex+registry）；重锚脚本据此用 ProcessPool（GIL 下 thread 无效）。

## 6. 未解决项 / follow-up（Open Issues）

- **国际解锁（~226 条 .T/.TW + ~1000 条 .PA/.L 上行）需两处扩展**，非一处：
  1. **envelope 侧锚点检测**：`enrichment/entity_anchoring` 需**检测** PDF 正文的国际 ticker 提及并产出国际锚点（现只 intent 侧 bridge）。交付的 `scripts/c9_reanchor_no_anchor_envelopes.py` 是这一步落地后的重锚工具。
  2. **F5 tradability 门扩展**：`entity_registry.is_plausible_tradable_symbol` 需承认 `.T`/`.TW`/`.PA`/`.L` 等国际 shape，否则即使锚上、bridge 上，仍在 F5 被 `pseudo_ticker_symbol` 拒（本轮 226 条即此）。
- **226 条 TW/JP intent 仍未 action**：当前行为正确（tradability 门拦截），待上面两处 follow-up 后可落地。
- **`c9_reanchor_no_anchor_envelopes.py` 已交付但未运行**：本轮 0 增益。国际锚点检测 follow-up 落地后运行它重锚，才有增量。
- **额外备份磁盘占用**：F5_executed + F2_anchored 命名快照（~6100 文件，data/ gitignore）。确认无误后可清理旧 `.bak-*`。
