# Audit Evidence 面板 — EvidenceSpan 落盘

> 2026-06-25 · F2 evidence / Audit · branch `feat/audit-evidence-spans`

## 概述 (Overview)

审计台 trace bundle 的 `evidence_spans` 一直是硬编码 `[]`（最后一块没点亮的面板）。
EvidenceSpan 本就在 canonical pipeline 里（`evidence_map`，F3 intent 提取产出），只是没落盘。
本次把动作引用的 EvidenceSpan 写成 `F2_evidence/{evidence_span_id}.json` sidecar，assembler
按 `action.evidence_span_ids` 解析，**Evidence 面板点亮**。实测真实 14 个 F2 → 227 span sidecar，
59/59 action 的证据面板非空。

## 变更清单 (Changes)

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/pipeline/canonical_runner.py` | 修改 | `_persist_canonical_artifacts` 增加 `evidence_spans` 参数，写 `F2_evidence/{id}.json`；调用点收集动作引用的 span（`used_evidence_ids`）后传入 |
| `src/finer/services/audit_assembler.py` | 修改 | import `EvidenceSpan`；新增 `_load_evidence_spans_for_action`（按 `evidence_span_ids` 读 `F2_evidence` sidecar）；bundle 的 `evidence_spans` 由 `[]` 改为该解析 |
| `tests/test_canonical_from_envelope.py` | 修改 | 持久化测试扩展为 F3/F4/**evidence** 三件；no-persist 测试加 F2_evidence 不写断言 |
| `tests/test_audit_api.py` | 修改 | +2：sidecar 解析点亮面板、缺失 sidecar 优雅跳过 |
| `docs/specs/2026-06-25-audit-evidence-spans-persist.md` | 新增 | 本文档 |

## 架构影响 (Architecture Impact)

- **审计台链路全亮**：trace bundle 的 5 个面板（trade_action / intent / policy /
  **evidence_spans** / envelope）现已全部由真实数据驱动。evidence 面板此前是唯一 stub。
- **存储位置 `data/F2_evidence/`**：EvidenceSpan 是 F2-tier schema，sidecar 与 `F2_anchored`
  平级；由 F3→F5 route 的 persist 步骤写出（与 F3_intents/F4_policy_mapped 同一步）。
- **只持久化被引用的 span**：调用点用 `{eid for action in actions for eid in
  action.evidence_span_ids}` 收集，避免写出未被任何 action 引用的孤儿 span。
- **前端零改动**：assembler 返回的 EvidenceSpan dict（`model_dump(mode="json")`）与
  `contracts.ts` 的 `EvidenceSpan` 完全对齐；`evidence-source.tsx` 用 char_start/char_end/text
  做高亮，offset 不匹配时优雅回退。
- **向后兼容**：未写 F2_evidence 时 `_load_evidence_spans_for_action` 返回 `[]`，既有
  `test_trace_bundle_canonical`（断言 `evidence_spans == []`）仍通过。

## 关键决策 (Key Decisions)

1. **per-id sidecar，与 F3/F4 同构。** assembler 已有 `_safe_load_model` 读路径模式，
   evidence 沿用最自然、零新机制。
2. **只落被引用的 span，不落全部 evidence_map。** 一个 envelope 的 evidence_map 可能含
   未成 action 的 span；只写动作引用的，保持审计数据精简、无孤儿。
3. **缺失 sidecar 跳过而非报错。** 部分 span 缺失时证据面板仍渲染已有部分，不让整个
   bundle 失败。
4. **ID 是 uuid4 → 重生成会产生孤儿 sidecar。** intent_id/policy_id/evidence_span_id 均
   uuid4，重跑 route 产生全新 id，上一轮的 F3/F4 sidecar 成为无人引用的孤儿（assembler 只读
   当前 F5 引用的 id，功能无影响，仅磁盘冗余）。清理孤儿属删除操作，按规矩单独确认。

## 验证结果 (Verification)

执行环境：worktree `/Users/zhouhongyuan/Desktop/finer-evidence`
（`feat/audit-evidence-spans`，基于 `docs/f0-review-fixes` HEAD `8eb96c8a`），
临时重生成至 `/tmp/regen_evidence`（未动真实数据）。

**真实 14 个 F2 → evidence sidecar + 面板**
```
F2_evidence sidecars written: 227
bundles with non-empty Evidence panel: 59/59 | total spans served: 227
sample span: text='抄底' block_id=block_b6c0349cb59c offsets=(1083,1085) conf=0.8
```

**测试**
```
pytest tests/test_audit_api.py tests/test_canonical_from_envelope.py -q -> 23 passed, 1 skipped
全量 pytest tests/ -q -> 2795 passed, 70 skipped, 3 failed
```
3 个失败为预存 `mimo_vision_config` / `live_mimo_multimodal` flake（多次确认无关）。
新增 2 个测试全过，无新增回归。

## 未解决项 (Open Issues)

- **需重生成真实数据**（批量重建，需用户确认）：现仅临时重生成至 `/tmp/regen_evidence`。
  重生成真实 `data/` 后真实审计台 evidence 面板才点亮（旧 F5 action 引用的 span 未持久化，
  无法回填，必须整体重生成）。
- **重生成的孤儿 sidecar**：因 uuid4，重跑会让上一轮 F3/F4 sidecar 成孤儿；清理需单独确认。
- **char offset 对齐质量**：evidence-source.tsx 高亮依赖 char_start/char_end 与 envelope
  源文匹配；当前 offset 来自 F3 关键词匹配，少数可能不精确（组件会回退为不高亮，非 bug）。
