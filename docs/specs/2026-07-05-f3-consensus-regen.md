# F3 共识提取器 + 全量重提取验收 — 方案 (b) 落地

## 概述

用户裁决方案 (b)：N-run 多数投票共识。本轮实现 `ConsensusIntentExtractor`（3-run 投票 + 确定性否决规则），完成 14 个 F2 envelope 的全量重提取与回填链，并借助新落盘的共识票据审计出两个 F4→F5 漏斗缺陷（bearish 观点整层被滤、mixed 方向被捏造成 bullish）。终态 **42 条 canonical action 替换 54 条规则版基线**：同日反向对 4→0、幻觉标的归零、conviction 3 档→6 档、多空分布回归内容真实（bearish 20 / bullish 16 / neutral 6）、每个 envelope 的提取决策（validator 拒绝、共识票数、降级记录）全部可审计。

## 变更清单

| 文件 | 类型 | 内容 |
|---|---|---|
| `src/finer/extraction/intent_extractor.py` | 修改 | 新增 `ConsensusIntentExtractor`：N-run 多数投票（按不同 run 计票，防单 run compound 对双票）、失败 run 重试补票基（最多 +2）、票基 <2 抛异常交 rule-based 兜底、contested 方向（bullish×bearish 跨 run 同时得票）需全票否则双杀、代表条目取最高 (confidence, conviction) 支持者原样保留（证据链自洽） |
| `src/finer/pipeline/canonical_runner.py` | 修改 | ① `_resolve_intent_extractor`：`FINER_F3_EXTRACTOR=llm` 默认包共识（`FINER_F3_CONSENSUS_RUNS` 默认 3,=1 退单跑,垃圾值防御回落 3）；② `_persist_canonical_artifacts` 新增 `{envelope_id}.notes.json` 落盘 result 级 F3 溯源；③ `OPINION_TIER_HINTS`/`ACTION_HINT_TO_ACTION_TYPE` 补 `avoid_or_watch_risk`（bearish 观点入 opinion tier）；④ `_resolve_direction` 兜底 BULLISH→NEUTRAL（mixed/unknown 不再捏造成看多） |
| `scripts/regen_f5_llm.py` | 修改 | docstring 与 wrapper `model` 标记同步为共识路径 |
| `tests/test_consensus_extractor.py` | 新增 | 15 个用例：多数保留/单票裁、方向分裂全裁、contested 2:1 双杀、全票豁免（叙述性反转）、compound 单 run 单票、重试补票基、票基坍缩抛异常、诚实空 run 计票、resolver 接线、垃圾 env 值 |
| `tests/test_opinion_tier.py` | 修改 | +bearish 观点物化为 WATCH（方向保真）、+mixed→neutral 单测 |
| 数据 | 批量重建 | `data/F5_executed` 42 action / 12 wrapper；F3/F4/F2-evidence sidecar 全量重写 + 13→12 个 `.notes.json`；备份 `data/regen-backup-20260705-{164236,171947,175849}`、`data/F5_executed.bak-20260705-{171520,175407,182927}` |

## 架构影响

- **F3 提取契约**：llm 模式的产出定义为「3 次独立提取中 ≥2 次达成一致的 (target, direction) 立场」；对立方向跨 run 同时得票的 target 要求全票，否则整体否决。单次提取的 validator（逐字证据/方向词典/锚点接地）与同 envelope 方向 collapse 在投票前逐 run 生效。
- **F3 溯源落盘**：`data/F3_intents/{envelope_id}.notes.json` 记录 extractor_version + 全部 processing_notes（validator 拒绝计数、每条 kept/vetoed 票据、fallback 记录）。审计台后续可直接消费。
- **F5 opinion tier 扩容**：`avoid_or_watch_risk` 与两个 watch hint 同级物化为 WATCH action（tier=opinion），方向取 intent 原方向。**多空对称**是本次最重要的产品级修复——此前时间线只放行看多观点。
- 无 schema 字段变更；`contracts.ts` 无需同步（tier/hint 走既有 metadata 通道）。

## 关键决策

1. **按 run 计票而非按 intent**：F3 第一遍 dedupe 允许同方向 compound 对（hold+add）共存，若按 intent 计票,单 run 可自投两票凑满阈值——对抗式 review 提出、主循环核实为真 bug 后修复。
2. **contested 方向全票制**：冒烟实测 GOOGL 在两轮共识间 bearish 2/3 ↔ bullish 2/3 翻面——内容真矛盾时 2:1 多数是掷硬币。全票制让结局确定（要么全票一边,要么双杀）,把「方向翻面」这种最坏形态的不确定性变成「宁缺」。
3. **失败 run 重试补票基**：一个 run 死掉会让 3-run 多数静默退化成 2-run 全一致（冒烟实测产出减半）,重试最多 2 次补足。
4. **共识 veto 后允许 rule-based 兜底**（沿用既有 runner 契约）:空产出交确定性基线裁决,防真实 call 整 envelope 丢失;兜底 envelope 由 notes 标记 `rule_based_v1`（本轮 2 个）,其 action 带规则版 conviction 指纹（0.55/0.65/0.75）可识别。
5. **mixed→NEUTRAL 而非 BULLISH**：方向枚举无 mixed 成员时,诚实降级为中性;旧兜底会凭空造多头立场（live 实测:共识 mixed 的 000001.SH 变 bullish action）。
6. **三轮 regen 而非一轮**：第 1 轮暴露溯源不落盘,第 2 轮的落盘票据对照 F5 产物暴露 bearish 漏斗与 mixed 失真——每轮都是靠上一轮补的审计能力发现下一个缺陷。LLM 成本（~130 次 MiMo 调用）换来的是漏斗级缺陷清零。

## 验证结果

- `python -m pytest tests/ -q` → **3120 passed, 15 skipped**（本任务线净增 24 个测试）。
- 终态数据面（42 action）vs 基线（54,规则版）:

| 验收项 | 基线 | 共识版终态 | 判定 |
|---|---|---|---|
| conviction 分布 | 3 档 {0.55×31, 0.65×22, 0.75×1} | 6 档 {0.5×3, 0.55×9, 0.6×6, 0.65×4, 0.7×14, 0.8×6} | PASS（0.55/0.65 部分来自 2 个 rule-fallback envelope） |
| 同日反向对 | 4 组 | **0** | PASS |
| 幻觉标的 (CL/NI225/XAUUSD) | — | **0**（`target_not_anchored` 每 run 拒 1-14 条） | PASS |
| 多空分布 | 未分层 | bearish 20 / bullish 16 / neutral 6（漏斗修复后） | PASS |
| 观点分层 | 无 | opinion 34 / trade 8 | PASS |
| creator 归属 | — | trader_ji 37 / sandbox 5 | PASS |
| F8 回测 | — | 32/42 落库（12 止损/19 到期/1 止盈）,9/32 胜 | PASS |
| 溯源可审计 | 无 | 12/12 envelope `.notes.json`（票据+拒绝计数+降级） | PASS |
| API 端到端 | — | /timeline、/changes、reindex 42/0 全通 | PASS |

- 共识稳定性（同 envelope 两轮全量共识对比,live 冒烟）:核心条目（0700.HK bullish 0.7、MU bullish 0.8、PDD mixed 0.5）方向与 conviction 完全一致;尾部 1-2 票条目在轮间出现/消失（可接受的失败形态:少展示,不错展示）。

## 未解决项

1. **MiMo 端点 temp-0 采样非确定是尾部波动的根源**（不可客户端修复）:边缘提及（茅台在 3 轮里 2 轮无人提出）会随轮次出现/消失。换支持 seed 的端点或加大 N 可收敛,是成本/稳定性权衡。
2. **`/api/opinions/timeline` 默认只回 20 条**——42 条时代需要确认前端分页/limit 语义（读层参数,非本轮 ownership）。
3. **2 个 rule-fallback envelope**（ccf079 本轮 0 产出、fdff74 持续 0 产出）:内容可能真无信号,也可能是 validator 对其文体过严,值得单独审阅 notes。
4. KOLScorer 公式后移、F2 锚定质量根因修复仍为既有 backlog（见 2026-07-02/03 系列文档）。
