# Phase 2 LLM extractor 三关验收 — 判定：数据回滚，代码保留

## 概述

按授权走完三关：LLM 冒烟 → 12(实际 14) envelope 全量重提取 → 对比验收。**验收判定不合格：LLM 版产出未达替换标准，数据已从备份完整回滚（54 条复原）；过程中落地的全部代码修复保留**（key 误路由、超时可配、max_tokens 截断、温度确定性、prompt 修锚）。这是分阶段验收设计的正确出口——学到的比换掉的多。

## 过程与发现（按关）

### 关 0：key 误路由修复（memory ⚠️ 证实并修复）
`DeepSeekClient` 的 base_url/model 会被 `FINER_LLM_BASE_URL/MODEL` 通用覆盖劫持（现值=MiMo 端点），但 api_key 硬编码读 `DEEPSEEK_API_KEY`——DeepSeek key 发往 MiMo → 401，与 memory 记录完全一致。修复：generic-override 模式下 key 跟随 `FINER_LLM_API_KEY_ENV`（`llm/deepseek_client.py`）。注：`ModelRouter`→registry 路径本就三件套连贯读取，不受此 bug 影响。

### 关 1：冒烟（判定 PASS）
排障链：裸进程不加载 `.env`（脚本需显式 `load_dotenv`，仓库惯例）→ 响应在 27.5k 字符被 `max_tokens=8192` 截断致 JSON 断裂（修：extractor 显式 `max_tokens=16384` + prompt 限 evidence_text ≤40 字）→ mimo 60s 超时由降级链救回（修：`FINER_LLM_TIMEOUT` 运行时覆盖，不动 .env）。修后单 envelope 输出质量好：**conviction 7 个不同值**（vs 规则版 2 档）、flags 带推理（`conflicting_direction: …dominant stance is bearish`）、`mixed` 方向正确使用。

### 关 2：全量重提取（54 → 18）
`scripts/regen_f5_llm.py`（全量备份 `data/regen-backup-20260705-094553` + 清旧 sidecar + LLM 主/规则兜底 + 重建索引）。14 个 F2 envelope → 9 wrapper / 18 action，5 个 envelope 0 产出。

### 关 3：对比验收（判定 FAIL，三条硬证据）

| 验收项 | 基线(规则版) | LLM 版 | 判定 |
|---|---|---|---|
| conviction 连续性 | 3 档 {0.55×31, 0.65×22, 0.75×1} | 4 值 {0.5, 0.6×5, 0.7×6, 0.8×6} | 部分改善（仍 0.1 步长聚集） |
| 同日反向对消失 | 4 组 | **更糟**：GOOGL 一个标的 3 天反向对，03-16 组**证据完全相同**（"Google：右走弱了，有点不对劲"）却一 bullish 一 bearish | ❌ FAIL |
| 量与内容 | 54 条（含 11 中性等已知杂质） | 18 条；**茅台等真实 call 丢失**；混入 CL/NI225/XAUUSD 虚假挂靠（evidence 为 F1 关键词行/会议议程——spurious F2 grounding） | ❌ FAIL |
| 确定性 | 确定性 | 同一 envelope 两次跑 0 vs 3 条（temperature 0.3） | ❌ FAIL |

**根因剖析（比失败本身更有价值）**：
1. **F5 opinion 漏斗**：LLM 诚实地把口播多数表述判为 `actionability=opinion` → F4 映射 `watch_only` → F5 以 `non_executable_action_hint` 全拒（实测单 envelope 11 intents → 8 拒）。**架构级矛盾：观点雷达吃的就是 opinion，管线却在 F5 把 opinion 全部滤掉**——规则版"更宽松地误判为 explicit_action"反而喂饱了产品。
2. **spurious grounding**：F2-grounding gate 按 symbol 匹配任意提及 span——LLM 提的标的只要注册表里有别名提及就"接地"，但 intent 主张与该提及无语义关联（CL 挂关键词行）。gate 挡得住幻觉 symbol，挡不住错误归因。
3. **方向稳定性 prompt 指令（§1b）不足以约束**：同证据反向对照出。需要确定性 validator（方向 vs 证据情感一致性校验），不是更多 prompt 措辞。

## 处置

- **数据**：从 `regen-backup-20260705-094553` 完整回滚 F5_executed + F3_intents + F4_policy_mapped + F2_evidence；重建索引 54/0 fail；API total=54 复原。
- **代码全部保留**（回归 3089 passed）：key 路由修复、`FINER_LLM_TIMEOUT`、`max_tokens=16384`、prompt evidence≤40字 + §1b、`LLMIntentExtractor` 默认 `temperature=0.0`（0.3 实测不可复现）、regen 脚本（下轮复用）。
- `FINER_F3_EXTRACTOR` 保持默认 rule-based；LLM 仍为 opt-in。

## 下一轮迭代设计（换方案再来，不是放弃）

1. **constrained proposal + deterministic validator**（仓库 F1.5 已验证的主方向平移到 F3）：LLM 只提议 (target, direction, conviction, evidence_quote)，确定性 validator 校验——evidence_quote 必须是 block 文本子串、方向与证据情感一致（词典级校验）、target 必须命中该 envelope 的 F2 锚点（按 raw_text/name 匹配而非仅 symbol）。不过校验的提议丢弃并记录。
2. **opinion 层物化决策**（产品级）：F5 增加 opinion-tier 输出（不可执行但上时间线）或雷达直接消费 F3 intents——否则诚实的 LLM 永远喂不饱观点产品。
3. 温度 0 + 同 envelope 双跑一致性纳入验收门。
