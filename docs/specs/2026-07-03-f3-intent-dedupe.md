# F3 同 envelope 意图去重 — 管线修复 + 存量清理

## 概述

修复"同一内容产出多条相同观点"的 F3 缺陷：`RuleBasedIntentExtractor` 按 section 独立产 intent（外加 `entity_anchors[0]` 盲取 fallback 把无实体 section 归到同一标的），同一标的同一立场跨 section 就重复——下游放大为重复 TradeAction（存量：3×000001.SH、2×OPTICAL_MODULE、2×0700.HK，屏上可见重复卡）。管线加 per-envelope 合并去重；存量删 4 条完全重复（58→54，已授权）。全量 **3023 passed** 零回归。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/extraction/intent_extractor.py` | 修改 | 新增 `_dedupe_intents`：key=(target_symbol\|target_name, direction, position_delta_hint)，合并保留全部 block_ids/evidence_span_ids/ambiguity_flags（去重保序）、conviction/confidence 取 max、time_horizon 取已知值，processing_notes 记录合并数；接入 rule-based 与 LLM 两条 parse 路径 |
| `tests/test_intent_dedupe.py` | 新增 | 5 用例：同标的同立场合并（证据聚合+最强信念）、反向立场保留（真实翻向不合并）、不同标的保留、time_horizon 择优、端到端两 section 同实体→1 intent |
| `scripts/dedupe_f5_actions.py` | 新增 | 存量清理（dry-run 默认；严格 key=ticker+direction+action_type+执行日+evidence_text；保留首条） |
| `data/F5_executed/*` | 数据清理 | 🔴 红线已授权；备份 `F5_executed.bak-20260703-091756`；删 4 条 / 2 文件；重建索引 54/0 fail |

## 关键决策

1. **合并而非丢弃**：重复 intent 的证据引用全部并入保留项（audit 完整性），信念取最强表达。
2. **反向立场绝不合并**：同标的 bullish+bearish 是真实翻向信号（近期异动的素材），只合并同 (标的, 方向, 仓位提示)。
3. **存量用严格 key**（含 evidence_text 全文）宁可漏删不误删：58 条里只判定 4 条为完全重复，同标的同日反向对（0700.HK bearish/bullish@02-16）合法保留。
4. **保留首条**：其 uuid 在 F8 provenance 中已被引用；重复项回测结果与保留项相同，删除无信息损失。

## 验证结果

- 单测 5/5；全量 **3023 passed**（+5）零回归——无既有测试依赖重复产出行为。
- 存量：dry-run 精确命中溯源预告的 3 组/4 条 → apply 后磁盘复查**精确重复 0 组**；API `total=54`；trader_ji 页 52→48。
- 伪重复排查：页面同句出现 2 次实为同一卡的 summary（sourceText 前 40 字兜底）与引文块同源，非重复卡。

## 未解决项

1. **同日反向对**（0700.HK bearish+bullish@02-16 同证据）：不是重复而是 F3 方向检测在相邻 section 上不稳定的产物，属"方向检测质量"问题（Phase 2 LLM extractor 的范围），本轮不自动合并（自动裁决方向有风险）。
2. 适配器 summary 兜底用 sourceText 前 40 字，与引文块视觉重复——小的前端展示优化，可让 summary 在无 trigger 时显示"—"或方向短语。
3. LLM 路径的去重已接线但只有 rule-based 的端到端测试覆盖（LLM extractor 无生产调用方，mock 测试留 Phase 2）。
