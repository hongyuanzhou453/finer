# F3 constrained validator 迭代 — LLM 关进确定性笼子后的再验收

## 概述

按上一轮验收文档（`docs/specs/2026-07-05-llm-extractor-acceptance.md`）的迭代设计第 1 条，为 F3 LLM extractor 落地 **constrained proposal + deterministic validator**：LLM 只负责提议，确定性 validator 负责否决。再验收结果：**上轮三条结构性 FAIL 全部关闭（伪引文、错误归因、反向对），但 MiMo 端点在 temperature=0 下仍非确定——同一 envelope 两次跑产出集合不同，且同 target 的冲突条目胜者方向可翻面**。全量重提取 go/no-go 交用户裁决。

## 变更清单

| 文件 | 类型 | 内容 |
|---|---|---|
| `src/finer/extraction/intent_extractor.py` | 修改 | 新增 `_validate_llm_intents()`（三重确定性校验，接入 `_parse_llm_output`）；`_dedupe_intents()` 第二遍从「严格 bullish×bearish 对」放宽为「同 target 多方向组一律 collapse 到 dominant」（§1b：一个 envelope 一个 target 一个方向；`stance_change` 叙述性反转豁免；同方向 hold+add compound 不动） |
| `src/finer/prompts/f3_intent_extraction/system.j2` | 修改 | evidence_text 逐字要求 + validator 警告；§1b Direction Stability；conviction 反聚集 |
| `tests/test_llm_intent_validator.py` | 新增 | 8 个用例，逐一映射上轮验收的失败模式 |
| `tests/test_intent_dedupe.py` | 修改 | + 反向对 collapse、bearish×neutral collapse、compound 不误伤、narrated reversal 保留 |
| `tests/test_intent_extractor_canonical.py` | 修改 | 契约改写：非逐字/空 evidence 不再 block-level fallback，改为拒绝 + `evidence_not_verbatim` note |
| `tests/test_intent_extractor.py` | 修改 | 3 个 mock 的 evidence_text 改为 envelope 逐字子串（旧 mock 编码了旧宽松契约） |
| `tests/test_golden_path.py` | 修改 | `_make_envelope` 增加 blk_002，使多 intent mock 的证据可逐字命中 |

## 架构影响

- **F3 契约收紧**：LLM 提议的 intent 必须同时通过 (1) evidence 逐字门（`span_type=="intent_keyword"`，block_level fallback 即拒绝）、(2) 方向-证据词典一致性（反向词典严格占优才拒，无关键词放行）、(3) F2 锚点接地（symbol 或 name 双向包含匹配；name 命中时 **归一化 target_symbol 到锚点 resolved_symbol**，杀幻觉 symbol；无锚点的 raw-text 路径跳过）。被拒条目计数写入 `processing_notes`（`validator rejected: {...}`），宁缺毋假。
- **F3 去重不变式升级**：同 envelope 同 target 只允许一个方向（此前只处理 bullish×bearish）。下游 F5/时间线因此获得「每 envelope 每 target 至多一行」的保证。
- 无 schema 字段变更，无 API 契约变更，`contracts.ts` 不需要同步。

## 关键决策

1. **非逐字证据 = 拒绝，而不是降级到 block-level span**。上轮 live 数据证明 fallback 会让伪引文混进 F5；两个旧测试编码的就是这个旧契约，已按新契约改写而非放宽 validator。
2. **方向一致性只在反向词典严格占优时拒**（`bear > bull and bear > 0`）。无情感关键词的证据放行——词典是否决器不是分类器，避免误杀中性表述。
3. **collapse 范围放宽到任意多方向组**：双冒烟实测 GOOGL 在同一 run 内出现 bearish + neutral×2 三行（neutral 不构成 bullish×bearish 对，hint 不同又躲过第一遍合并），只有「一 target 一方向」不变式能关住。
4. **temperature=0 保留 + 不再加 prompt 措辞**：端点侧采样噪声已证实不是 prompt 问题。

## 验证结果

- `python -m pytest tests/ -q` → **3103 passed, 15 skipped**（修复前 6 failed / 3095 passed）。
- temp-0 双冒烟（`local_fe9e43483fa14b4ce3ffed66`，两次独立 LLM 调用）：
  - Run A：4 intents（0700.HK bullish 0.7 / AMZN neutral 0.5 / GOOGL 单行带 `conflicting_direction_in_envelope` / PDD mixed 0.5）；validator 拒 10；collapse 4。
  - Run B：7 intents（+000001.SH、1810.HK、MU）；validator 拒 17；collapse 6。
  - **META 反向对：两次 run 均消失**（上轮 FAIL 证据之一）。
  - 幻觉目标（上轮 CL/NI225/XAUUSD 类）：`target_not_anchored` 拒 5-14 条/run，产出中为零。
  - 伪引文：`evidence_not_verbatim` 拒 2-4 条/run，产出中为零。

## 未解决项

1. **MiMo 端点 temp-0 非确定（不可客户端修复）**：两次 run 产出 4 vs 7 条；交集稳定（0700.HK/AMZN/GOOGL/PDD），尾部（000001.SH/1810.HK/MU）是采样噪声。
2. **冲突条目方向可翻面**：GOOGL 在 Run A 收敛为 bullish 0.6、Run B 收敛为 bearish 0.6（conviction 平局时胜者取决于该 run 哪些提议活过 validator）。带 flag 可审计，但对「散户决策辅助」这是最坏形态的不确定性。
3. **全量重提取 go/no-go 未执行**：属用户裁决（红线：批量数据重建）。备选路径：(a) 接受带 provenance 的非确定性重提取；(b) N-run 多数投票共识（确定性换 N 倍成本）；(c) 维持 rule-based 默认，LLM 继续 opt-in 精炼。
