# Audit Review Fixes — Envelope 解析 (P1) + 只落引用 (P2)

> 2026-06-25 · Audit / F3-F4 persist · branch `fix/audit-envelope-resolution`

## 概述 (Overview)

审计台线 review 的两个真问题：**P1** trace bundle 的 Envelope 面板是 2 字符空壳、证据无法高亮
（根因：assembler 按 `content_id` 找 F2 文件，但 `content_id` 是 `env_*` id，F2 文件名是
`local_*`，永远 miss）；**P2** 每次重生成写 160 个 F3/F4 sidecar 但只有 59 被引用，留 101+101
孤儿。P1 改为优先用已接好的 `source_file` 链接解析 envelope；P2 改为只落 action 引用的
intents/policies（与 evidence 一致）。验证：envelope source_text 2 → 5402~24353 字符，
证据 59/59 可高亮；F3/F4 持久化 160→59。

## 变更清单 (Changes)

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/services/audit_assembler.py` | 修改 | P1：`_load_envelope_for_action` 加 `source_file` 参数，优先 `data_root/F2_anchored/{basename}`（可移植）再 literal 绝对路径（分离布局兜底），最后才退回 content_id；`get_trace_bundle` 传 `indexed.source_file` |
| `src/finer/pipeline/canonical_runner.py` | 修改 | P2：persist 调用点先按 `used_intent_ids`/`used_policy_ids` 过滤，只落被 action 引用的 intents/policies/spans |
| `tests/test_audit_api.py` | 修改 | +1：content_id 与文件名不匹配时经 source_file 解析出富 envelope |
| `tests/test_canonical_from_envelope.py` | 修改 | 持久化测试加"无孤儿"不变式：persisted F3/F4 stem 集合 == action 引用集合 |
| `docs/specs/2026-06-25-audit-envelope-resolution-and-persist-filtering.md` | 新增 | 本文档 |

## 架构影响 (Architecture Impact)

- **P1 Envelope/Evidence 面板真正可用**：之前 envelope 永远 None → source_text 退化成
  `action.source.evidence_text`（实测 2 字符）→ 证据 span 偏移（如 1083）塞不进 → 无法高亮。
  现在经 `source_file`（指向真实 `local_*.json`）解析出完整 envelope（实测 5402~24353 字符），
  前端 `evidence-source.tsx` 的 `indexOf` 兜底即可高亮（59/59 span 文本可在源文检索到）。
- **可移植 + 兜底**：先 `data_root/F2_anchored/{basename}`（数据目录整体搬迁仍有效），
  再 literal `source_file` 绝对路径（F2/F5 分目录时兜底），最后 content_id（旧行为）。
- **P2 持久化精简**：只落被 action 引用的 F3/F4（160→59），减少孤儿；与 evidence 的
  `used_spans` 过滤现已一致。assembler 只按 action 的 intent_id/policy_id 读，未引用的本就读不到。
- **契约/前端零改动**：bundle 结构不变，envelope 仍含 envelope_id/source_text/creator_id/
  kol_id/source_file。

## 关键决策 (Key Decisions)

1. **P1 用 source_file 而非改写 content_id。** `source_file` 已在 bridge 阶段接好并存进
   `IndexedTradeAction`，指向真实 F2 文件；直接用它最小改动、最稳，不必回改 route 写出的
   content_id 语义。
2. **三级解析顺序：basename+data_root → literal path → content_id。** 兼顾可移植（搬迁数据目录）、
   分离布局（F2/F5 不同根，如临时重生成）、向后兼容（旧路径）。
3. **P2 与 evidence 对齐。** evidence 已只落 `used_spans`；intents/policies 同样只落引用的，
   消除 101+101 孤儿/批次的不一致。
4. **未在本次解决的 review 项**：P3 route 重跑仍累积孤儿（uuid4，需 route 清理或确定性 id）；
   P4 索引重建 O(N) 读盘；P5 前端"Sample data"徽章常显（批次 A 归属）。本次只收 P1+P2。

## 验证结果 (Verification)

worktree `/Users/zhouhongyuan/Desktop/finer-envelope-fix`（基于 `docs/f0-review-fixes` HEAD
`0d36dfe3`），临时重生成真实 14 个 F2 至 `/tmp/regen_envfix`。

**P1 Envelope/Evidence**
```
source_text len: min=5402 median=17261 max=24353  (was 2)
bundles with rich envelope (>200 chars): 59/59
bundles where all evidence spans findable in source: 59/59
sample: envelope_id=env_04530c84bf10 source_text_len=24353
```

**P2 只落引用**
```
actions: 59 | F3: 59 | F4: 59 | evidence: 227   (was F3/F4=160/160)
持久化不变式：persisted F3/F4 stem == action 引用集合（无孤儿）
```

**测试**
```
pytest tests/test_audit_api.py tests/test_canonical_from_envelope.py -q -> 24 passed, 1 skipped
全量 pytest tests/ -q -> 2796 passed, 70 skipped, 3 failed（预存 mimo flake，无关）
```

## 未解决项 (Open Issues)

- **需重生成真实数据**（清理重建，需用户确认）：临时已验证；真实 `data/` 需清空派生目录后
  重生成，才在真实审计台生效（F3/F4 降到 59、envelope 面板变富）。
- **P3/P4/P5 未动**：route 重跑孤儿累积、索引 O(N) 读盘、前端 demo 徽章——按优先级排后/转交。
- **evidence 偏移仍块相对**：高亮靠前端 `indexOf` 兜底（实测 59/59 可命中）；精确块级偏移
  对齐为可选打磨。
