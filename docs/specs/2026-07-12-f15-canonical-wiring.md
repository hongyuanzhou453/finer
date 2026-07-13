# F1.5 Topic Assembly 接入 canonical pipeline（2026-07-12）

## 概述（Overview）

Roadmap P1 #6（`docs/specs/2026-07-11-architecture-priorities.md`）落地：F1.5 从「已实现但游离」变为 canonical runner 的在线子阶段——长内容（≥8 块或 ≥2400 字）在质量门之后、F3 之前装配 TopicBlock，F3 按 topic 身份逐组提取，短内容与单话题内容保持原整文路径。真实 18 块聊天 envelope 离线回放：规则版提取 intent 集合与整文路径完全一致（无召回损失），全部 intent 的 `block_ids` 收窄到 topic 范围。全量测试 3237 条通过。

## 变更清单（Changes）

| 文件 | 类型 | 内容 |
|---|---|---|
| `src/finer/parsing/topic_routing.py` | 新增 | F1.5 路由与提取粒度层（见下） |
| `src/finer/pipeline/canonical_runner.py` | 修改 | `run_canonical_from_envelope` 质量门后接 `assemble_topics_for_extraction`；新增 `_extract_intents_per_topic`（逐子 envelope 提取 → intent 打 `f15_*` 溯源 → 跨 topic `_dedupe_intents` → 合并 evidence spans/notes）；`persist_dir` 时落 `F1_5_topics/{assembly_id}.json` |
| `tests/test_topic_routing.py` | 新增 | 16 条：锚点规则生成 / 路由开关与阈值 / 子 envelope 过滤与兜底 / 身份聚合 / runner 集成 |

### topic_routing.py 设计

1. **路由**（env 可覆盖）：`FINER_F15_MODE=auto|off|force`（auto 默认：非空块 ≥8 或总字数 ≥2400 才启用，`FINER_F15_MIN_BLOCKS`/`FINER_F15_MIN_CHARS` 可调）；装配结果 <2 topics 返回 None 走整文路径（单话题按 topic 切分无增益）。
2. **锚点驱动动态 TopicRule**：规则版 `TOPIC_RULES` 是 Cat Lord golden fixture 词表，真实语料几乎不命中。`build_anchor_topic_rules()` 把 envelope 的 F2 entity_anchors（aliases + 出现位置）转成 TopicRule——真实语料的 topic 种子就是 F2 锚定结果，零 LLM 成本、可复现。置信度分级（stock/etf/crypto 0.95 > index 0.8 > sector 0.72）保证具体标的压过板块泛称赢得块归属。
3. **LLM 装配为主方向、规则版为 fallback**：`FINER_F15_ASSEMBLER=llm` 走 constrained proposal adapter（已有 `llm_topic_assembly_adapter`），异常自动回退规则版；默认 rule（确定性、离线可测）。
4. **提取粒度 = topic 身份，不是位置**：assembler 的连续块合并在聊天体裁下把同一实体拆成多个位置性 TopicBlock（实测 18 块聊天 → 14 位置 topics / 9 个实体）。`topic_subenvelopes()` 按 `primary_entity_ids[0]`（缺省 topic_title）聚合成身份组——一个实体一次聚焦提取，LLM 提取调用量不随位置碎片放大。
5. **子 envelope 构造不变量**：`envelope_id` 保持原值（intent provenance 指向真实 envelope）；entity_anchors 按 `metadata.occurrences[].block_id` 过滤（无出现信息的锚保守保留在所有组）；temporal_anchors 按 `metadata.block_id` 过滤、envelope 级锚（published_at）全保留；`unassigned_block_ids` 兜底成「未分组」组——**F1.5 契约不丢块**，整文路径能看到的内容按 topic 路径也必须看到。

## 架构影响（Architecture Impact）

- **分层**：路由与切分逻辑归 `parsing/`（F1.5 ownership）；`pipeline/canonical_runner.py`（cross-stage）只做编排调用。F1.5 仍不产 direction/actionability/TradeAction、不解析 F1 格式细节。
- **F3 输入契约不变**：提取器仍收 `ContentEnvelope`，无 API 改动（LLM/rule 提取器零感知）；per-topic 路径复用 `_extract_with_fallback`，单个 topic 的 LLM 失败只影响该 topic（degrade to rule）。
- **F5 grounding 不变**：F2 证据索引仍建在**完整 envelope** 上；intent 的 `block_ids` 收窄让 block 级 fallback grounding 更精确（此前 LLM 提取器给每个 intent 挂全部块 id）。
- **数据目录**：`persist_dir/F1_5_topics/{assembly_id}.json` 新增审计产物（与 F3_intents/F4_policy_mapped 同级 sidecar）。
- **下游自动受益**：`pipeline/driver.py` 增量驱动器经 `run_canonical_from_envelope`，新语料自动走该路由——#2 增量流水线放量前的质量前置件就位。
- **intent metadata 新增可选键**：`f15_assembly_id` / `f15_topic_title` / `f15_topic_index`（自由 metadata，无 schema 变更，前端无契约同步需求）。

## 关键决策（Key Decisions）

1. **接线在 runner 而不是改提取器**：F3 提取器对 F1.5 零感知，子 envelope 是唯一交互界面——LLM/规则两个提取器、未来新提取器全部自动兼容。
2. **锚点驱动规则作为 rule fast-path 主力**：真实语料的 topic 结构已经被 F2 锚定捕获（出现位置即块归属证据），不需要为每个 KOL 手维词表；LLM constrained proposal 保持主方向（env 切换），规则版永远是可复现 baseline。
3. **身份聚合而非位置切分**：位置性 TopicBlock 忠实记录语篇结构（F1.5 装配语义，持久化保留），但 F3 提取按实体身份聚合——同一实体散布 3 处仍是一个观点上下文，也控制 LLM 调用量（识别为 N 个实体组 + 1 个未分组，而非 14 个位置片段）。
4. **<2 topics 回退整文**：单话题长文按 topic 切分只会丢上下文；F1.5 的价值仅在多话题混排场景。
5. **「未分组」兜底组单独提取**：不把未分组块并进任一 topic（污染上下文），也不丢弃（违反 F1.5 契约）；作为独立组过 F3，规则提取器天然逐块处理。

## 验证结果（Verification）

```bash
pytest tests/test_topic_routing.py -q   # 16 passed
pytest tests/ -q                        # 3237 passed, 15 skipped
```

真实数据离线回放（只读，rule-based 提取器）：

```
local_8463…（18 块 / 24.3k 字 / 21 锚）: 14 位置 topics → 10 身份组（腾讯/亚马逊/EWY/上证指数/泡泡玛特/理想/美光/紫金矿业/巴菲特/未分组）
  整文: 10 intents == 按 topic: 10 intents（集合完全一致，无召回损失）
  block_ids 收窄: 10/10
local_15c7…（~16 块 / 10 位置 topics → 8 身份组）
  整文: 8 intents == 按 topic: 8 intents（一致）
  block_ids 收窄: 8/8
```

规则版提取的「无损失 + 收窄」是安全性证据；LLM 提取器的方向稳定性收益（聚焦上下文 vs 24k 字整文）需线上语料验证，属 #2 增量驱动器放量后的观测项。

## 审查结论与修复（多视角审查工作流，13 agents，7 条确认全部处置）

| 级别 | 发现 | 处置 |
|---|---|---|
| high | per-topic 复用 `_extract_with_fallback` 把「空 LLM 输出=配额故障」启发式搬到 topic 粒度：LLM 正确判定无立场的 topic（事实复述/未分组噪声组）被规则提取器重跑，复活 LLM/validator 刻意压掉的假阳性并绕过共识投票门（审查 agent 实机复现：泡泡玛特复述块被回退产出 2 条 bullish action）。llm 共识是现役生产模式，而我的离线「整文=按 topic」验证恰好用的规则提取器——此缺陷在该配置下不可见 | **已修**：新增 `_extract_topic_with_fallback`，回退仅限异常 / None / 空结果带显式 `_LLM_FAILURE_MARKERS`（consensus 基座塌陷本身 raise 走异常路径）；空结果+无标记=真实无立场，如实接受。测试钉住 |
| high | 每 envelope F3 调用量 = 身份组数 × 共识投票数，无上限（实体极多的长聊天不可控） | **已修**：`FINER_F15_MAX_TOPICS`（默认 12）硬顶，按块数保大组，溢出组并入「未分组」兜底提取（不丢块），capped 时 warn 日志（无静默截断） |
| medium ×2 | 合并结果取首个 topic 的 extractor_version：单 topic 回退时全部 action/审计 sidecar 打错版本章（顺序依赖），并经 `PipelineSnapshot.extractor_version` 污染 RLHF/DPO 锚 | **已修**：每条 intent metadata 记录 `f15_extractor_version`（本 topic 实际版本）；合并版本单一来源→如实、混合来源→显式 `mixed(a+b)` 章。测试钉住 |
| low | 跨 topic dedupe 幸存者保留首见 f15_topic_title 但 union 了他组 block_ids，溯源部分指错 | **已修**：合并后 block_ids 跨组的 intent 追加 `f15_merged_topics` 标注。测试钉住 |
| low | `F1_5_topics` sidecar 被 `result.trade_actions` 门控：F1.5 启用但下游全拒的 run 无装配记录 | **已修**：装配即落盘（F1.5 产物归 F1.5 阶段），不受 F5 产出影响。测试钉住 |

被驳回的发现（3 条）：F2→F1.5「阶段倒置」（runner 流程中 envelope 本就是 F2-anchored，锚点作 topic 种子是既有事实的复用）；私有 `_dedupe_intents` 跨模块导入（pipeline 编排层复用单真相优于复制逻辑）；增量语料「混合粒度」（F5 fill-only 语义既有，不由本次引入）。

修复后全量测试 3243 passed（22 条 F1.5 测试）。

## 未解决项（Open Issues）

1. **LLM 提取器的按 topic 收益未量化**：需在 FINER_F3_EXTRACTOR=llm 的线上跑批中对比方向翻转率/共识稳定性（挂在 roadmap #2 增量驱动器的观测里）；离线「整文=按 topic」parity 证据仅覆盖规则提取器。
2. **LLM 装配路径（FINER_F15_ASSEMBLER=llm）未在 runner 集成测试覆盖**：adapter 有自己的单测；runner 侧只测了 rule 路径与异常回退逻辑。
3. **topic 溯源未上审计前端**：`f15_*` metadata（含 `f15_extractor_version` / `f15_merged_topics`）已入 F3 intents sidecar，audit trace 面板展示 topic 维度留给前端排期。
4. **mixed 版本章的下游消费语义**：`mixed(a+b)` 保证不误锚，但 RLHF/DPO 若需按版本切片，混合 envelope 应按 intent 级 `f15_extractor_version` 过滤——待 F6 数据量起来后在 rlhf_assembler 落地。
