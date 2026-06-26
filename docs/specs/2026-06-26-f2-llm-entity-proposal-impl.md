# F2 中文实体候选 — constrained-LLM 提议 + 确定性 validator（Phase 1+2 实现）

> 日期: 2026-06-26
> F-stage: F2 (enrichment / entity anchoring)
> 分支: docs/f0-review-fixes
> 任务卡: [2026-06-26-f2-llm-entity-proposal-task.md](2026-06-26-f2-llm-entity-proposal-task.md)
> 上轮结论: [2026-06-26-f2-anchor-hit-rate.md](2026-06-26-f2-anchor-hit-rate.md)（规则方案为何失败）

## 1. 概述

给 F2 gap-候选生成新增一条 **constrained-LLM 提议路径**（mirror F1.5 `llm_topic_assembly_adapter.py`）：DeepSeek 约束 JSON 提议「实体名 + ticker/market」，再用**确定性 validator** 逐条硬校验（evidence 子串 / registry 去重 / stoplist / 板块拒绝 / ticker 格式），产出与规则路径同格式的候选喂现有 review→apply 闭环。**Phase 1/2/3 全部完成**（均经用户在红线前确认）：Phase 1 提议器+validator+20 mock 测试；Phase 2 backfill opt-in 接入 + eval 脚本 + 两轮真跑（precision 63%，**conf≥0.8 达 100%**，对比规则 ~6%）；Phase 3 validator 打磨（板块精确拒绝 + 大小写去重）+ 插 2 高频核验实体（地平线 9660.HK / 吉利 0175.HK）→ all-local 命中率 **17.7%→18.6%**。全量 2983 passed。LLM 路径成功识别规则完全无能为力的纯中文实体，**任务卡目标达成**。

## 2. 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/enrichment/entity_stoplist.py` | 新增 | F2 候选降噪共享真相源：`NOISY_UPPER_TOKENS`(frozenset) + `CN_GENERIC_CANDIDATE_TERMS`(tuple)，从 backfill 迁出 |
| `src/finer/enrichment/llm_entity_proposal.py` | 新增 | `LLMEntityProposal` / `LLMEntityProposalPayload` / `LLMEntityProposalAdapter` + 确定性 validator |
| `scripts/backfill_f2_anchor.py` | 修改 | ① 改 import 共享 stoplist（删 ~190 行原地字面量）② `_gap_candidates_for_block` 加 `include_llm` 路径 + 模块级 adapter 单例/缓存/cap ③ CLI `--llm-proposals` / `--llm-max-blocks` |
| `scripts/eval_f2_llm_proposals.py` | 新增 | precision eval 工具：`propose`（红线，双闸保护，`--base-url`/`--model` 运行时覆盖、`--per-doc-cap` 分散采样）+ `score`（离线算分，对比 ≥0.60 达标线） |
| `tests/test_llm_entity_proposal.py` | 新增 | 20 mock 测试：validator 四道门 + ticker/market 归一 + DeepSeek JSON 模式 + 板块拒绝/大小写去重/精确匹配存活 |
| `tests/test_backfill_f2_llm_path.py` | 新增 | 8 mock 测试：opt-in 开关 / 缓存 / max-blocks cap / 未配置跳过 / 错误吞掉 / 去重 |
| `src/finer/entity_registry.py` | 修改 | **Phase 3**（授权后）：插 4 alias / 2 实体（地平线 `9660.HK`、地平线机器人、吉利 `0175.HK`；吉利汽车已在库补简称「吉利」） |
| `src/finer/enrichment/entity_stoplist.py` | 修改 | **Phase 3 打磨**：加 `CN_SECTOR_THEME_TERMS` 板块泛称精确拒绝集 |
| `src/finer/enrichment/llm_entity_proposal.py` | 修改 | **Phase 3 打磨**：validator 加板块精确拒绝 + registry 去重 `.upper()` 兜底 |
| `tests/test_entity_anchoring.py` | 修改 | +`test_f2_llm_proposal_additions_resolve_and_scan` 锁定地平线/吉利锚定 |

> Phase 1/2 全程未碰 `entity_registry.py`；Phase 3 经用户授权后才插入与打磨。

## 3. 架构影响

- **新增 F2 共享真相源 `entity_stoplist.py`**：`scripts/backfill_f2_anchor.py`（规则路径）与 `enrichment/llm_entity_proposal.py`（LLM validator）现共用一份 stoplist，消除双副本漂移。backfill 由原地字面量改为 `import ... as _NOISY_UPPER_TOKENS / _CN_GENERIC_CANDIDATE_TERMS`，等价重构。
- **契约零改动**：LLM 候选 dict 对齐 `GAP_CANDIDATE_REVIEW_FIELDS` 前 8 字段（candidate_type=`llm_entity_proposal`），LLM 的 ticker/market/confidence 作为**附加键**携带；`build_f2_gap_review_batch` 用白名单重建 row（[backfill:267-277]），附加键被安全忽略。`EntityAnchor` / `ContentEnvelope` / registry-gap 格式不变。
- **LLM 路径默认关闭**：opt-in via `--llm-proposals`；no-key / 未配置时 `adapter.is_configured()` 为 False 干净跳过（mirror 范例），命中率与基线逐字一致。
- **不触红线**：registry 写入、批量跑 LLM、批量重锚定均未执行。

## 4. 关键决策

1. **stoplist 抽到 `src/finer/enrichment/` 共享模块**（而非 LLM 模块从 `scripts` 反向 import）。`scripts/` 非 package 且有 `sys.path` hack，反向 import 脆弱；stoplist 本是 F2 enrichment 领域知识，归属 `src/finer/enrichment/`。backfill 改 import 由其 54 项测试套件守护（54 passed）。
2. **schema 用 `extra="forbid"` 但不加 `strict=True`**（偏离 mirror 范例）。范例用 strict 让类型不符即整批降级；F2 场景 validator 已逐条硬校验（substring/registry/stoplist/格式），strict 在 parse 层价值被覆盖。去 strict 换 `confidence:1`（int）等鲁棒容错，避免一条良性类型差异毁掉整批召回。`extra=forbid` 仍拦截幻觉结构字段。
3. **validator 硬门**（全过才成候选）：`evidence_quote ∈ text` ∧ `alias ∈ text` ∧ `alias ∈ evidence_quote`（自洽）∧ `resolve(alias) is None`（去重）∧ 非 stoplist ∧ ticker 格式合法。`alias` 长度门 2–20（牺牲单字母 ticker 换抗噪，对话语料里 `V`/`F` 误锚 > 收益）。
4. **非法/幻觉 ticker 清空而非丢候选**：alias 可能是真实体而 LLM 只是 ticker 编错，清空 ticker 保留 alias 供人工补，比丢整条更保召回。ticker 后缀（.HK/.SH/.SZ）权威定 market，压制 LLM 的 ticker/market 不一致。
5. **backfill 接入用 `include_llm` 参数 + 按-block 缓存 + max-blocks cap**：`build_gap_report` 被 `print_plan` + `main` 调两次，缓存（key=(content_id,block_id)）防重复烧 token；`_missed_block_diagnostic` 的调用保持 `include_llm=False` 让诊断 reason 纯规则、不被 LLM 候选改语义；`--llm-max-blocks` 是失控保险。
6. **eval propose 双闸**：`--confirm-spend` + `--limit`，缺一不真跑，防误触烧 token。`score` 模式按 cohort + confidence 分桶（mock 验证显示 ≥0.80 confidence 提议显著更可信），呼应任务卡「边界实体低 confidence 人工兜底」。

## 5. 验证结果

- **基线只读测量**（`backfill --scope all-local --dry-run`）：命中率 **17.7%**（hit 540/3051）、anchors 584、零锚文档 68；cohort 拖累主体 unclassified 对话截图 2653 块@12.8%，候选样本全是上轮已知噪声（MSCI/ICE/MA/BCRED…）—— 印证规则路径天花板。
- **F2 子集** `pytest tests/test_llm_entity_proposal.py tests/test_backfill_f2_llm_path.py tests/test_backfill_f2_anchor.py tests/test_entity_anchoring.py tests/test_apply_f2_gap_reviews.py tests/test_build_f2_gap_review_batch.py`：**79 passed**。
- **全量** `pytest tests/`：**2983 passed, 15 skipped**（Phase 1 后 2971 → +8 接入 → +3 validator 打磨 → +1 registry 锚定断言）。
- **带 `--llm-proposals` 无 key dry-run**：命中率/anchors/zero 与基线 **IDENTICAL**，stderr 打印「not configured; running rule paths only」，候选无 `llm_entity_proposal` 类型 —— opt-in + 零回归确认。
- **eval score 模式**（mock 评判数据）：precision 0.600 → PASS，cohort/confidence 分桶正确。
- **Phase 2 step 5 真跑**（用户授权 `--limit 30`，真 DeepSeek `deepseek-chat`/v4-flash）：30 gap block → 13 提议，agent 核对 **precision 1.000（13/13 correct）**，全 ≥0.80 confidence → 达标线 PASS。**质突破**：13 条全是「地平线」（`9660.HK`，Horizon Robotics 港股）—— 规则路径完全抓不到的纯中文名（无 cue/bracket），LLM 全抓对且 ticker 准确（对比上轮规则 precision ~6%）。**样本局限**：`--limit 30` 在首个 gap-heavy 文档（local_048…，猫大人 FIRE 地平线财报深度分析）内耗尽，13 提议去重后仅 1 个独特实体，代表性不足；已给 eval 加 `--per-doc-cap` 让样本分散，待扩样重测。
- **Phase 2 step 5 扩样重测**（`--limit 40 --per-doc-cap 3`，跨 **8 文档 / 17 独特实体**）：19 提议，**precision 0.632（12/19）> 60% PASS**。**confidence 分层决定性**：≥0.80 → precision **1.000**（11/11，召回 地平线/DRAM ETF/标普/Nvidia/纳指/VIX/吉利 `0175.HK`/黄金/tsla）；0.60–0.79 → 0.167；<0.60 → 0。拖累 precision 的 7 条 incorrect 全是**板块/概念泛称**（券商/保险/机器人/创新药/中概/标普消费/新消费）且 conf 全 <0.8。**结论：LLM 路径在真实多实体语料 precision 63%（规则 6%），加 conf≥0.8 过滤达 100%；Phase 3 应只采纳高 conf 提议。**
- **Phase 3 validator 打磨 + registry 插入 + 命中率 delta**（用户授权）：先做两个无红线打磨 —— ① `CN_SECTOR_THEME_TERMS` 板块泛称**精确**拒绝集（券商/保险/创新药… 精确匹配，新华保险≠保险不误杀）② registry 去重加 `.upper()` 兜底（Nvidia/tsla 命中 NVIDIA/TSLA），+3 单测。再插 4 alias / 2 实体（地平线 `9660.HK`、地平线机器人、吉利 `0175.HK`；吉利汽车已在库，补简称）→ all-local 命中率 **17.7% → 18.6%**（hit 540→568 +28，anchors 584→592，零锚文档 68→65）；unclassified 对话 cohort **12.8%→13.9%**。地平线高频（local_048 13+ 块）贡献主要 delta，**验证 LLM 候选→人工核验→registry→命中率闭环**。
- **配置诊断**（真跑前排清，**未改 .env**）：`DeepSeekClient.from_env()` 经 `FINER_LLM_BASE_URL` fallback 把 `DEEPSEEK_API_KEY` 错路由到 MiMo endpoint（`token-plan-cn.xiaomimimo.com` / `mimo-v2.5`）→ 401。探测确认 `DEEPSEEK_API_KEY` 是有效真 DeepSeek key（`api.deepseek.com` 认证成功）。eval 脚本加 `--base-url`/`--model` 运行时覆盖修复，不动 .env。**遗留**：F1.5 `llm_topic_assembly_adapter` 生产同样走 `from_env()`，若需真打 DeepSeek 也受此 fallback 影响，建议在 .env 设 `DEEPSEEK_BASE_URL` 或让 from_env 区分 DeepSeek/MiMo 配置（独立任务）。

## 6. 未解决项与后续

> Phase 1 / 2 / 3 均已完成（adapter+validator+接入 / 两轮真跑 / validator 打磨+registry 插入+命中率 delta）。以下为剩余红线与改进项。

1. **全量放量（红线，待确认）**：本轮仅插 2 个高频核验实体（地平线/吉利）验证闭环。规模化拉命中率需大批量跑 LLM（`eval propose` 去 `--per-doc-cap` 或大 `--limit`）→ 人工核验 → 批量插 registry。**批量 LLM + 大量 registry 写入双红线**，需另行授权。放量时建议只采纳 **conf≥0.8** 提议（实测 precision 100%）。
2. **配置遗留（独立任务）**：`DeepSeekClient.from_env()` 经 `FINER_LLM_BASE_URL` fallback 把 `DEEPSEEK_API_KEY` 路由到 MiMo endpoint → 401；F1.5 `llm_topic_assembly_adapter` 生产同样受影响。建议在 .env 设 `DEEPSEEK_BASE_URL=https://api.deepseek.com` 或让 from_env 区分 DeepSeek/MiMo（**改 .env 是红线，需用户做**）。
3. **finance-skills 交叉验证（P1）**：validator 已留 `finance_skills_validator` 注入缝（mock 测试覆盖），未接 `services/finance_skills_client.py` 真实 client 确认 ticker 存在。
4. **review row 不含 LLM ticker extras**：`build_f2_gap_review_batch` 白名单丢弃 LLM 的 suggested_ticker/market（任务卡数据流本就是人工 review 时填 ticker，可接受）；放量时若要 LLM 建议预填 review row 供 reviewer 参考，需评估扩列。
5. **registry 插入 fixture 耦合**：插实体前须 `rg <alias> tests/` 且 `resolve(alias)` 查重 —— 本轮实测发现新华保险（1336.HK）、吉利汽车（0175.HK）已在库。测试已全用虚构实体规避。
6. **✅ 已修（Phase 3 打磨）**：板块/概念泛称 → `CN_SECTOR_THEME_TERMS` 精确拒绝集；registry resolve 大小写敏感 → 去重加 `.upper()` 兜底。各 +单测覆盖。
