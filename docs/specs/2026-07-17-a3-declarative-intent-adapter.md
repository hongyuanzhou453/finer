# A3 —— T3 JSONL → F3 声明式 Intent 适配器（broker recommendation）

> 状态：已实施并验收（2026-07-17）。上游 spec：`docs/specs/2026-07-15-broker-research-source-integration.md`（§5 关键决策 3、§7 R2/R3/R6/R10）。
> 执行会话：worktree musing-bell-c975d7（Workflow `a3-declarative-intent-adapter`，5 agents）+ 主仓化升级波。

## 1. 概述

把研报仓 T3 结构化抽取产物（`rag_data/t3_structured/burn_all.jsonl`，t3-v0.2，4,286 行）与 finer 内部血统（F0 ContentRecord → F1 envelope_id → F2 evidence span）合流，产出 canonical `NormalizedInvestmentIntent`。**纯关键词表解析，零 LLM**——研报评级是被声明的，不做推断（规避 `0e40f029` 修掉的 bearish 过提取一类问题）。同波交付 8 家券商 creator 档案，broker creator_id 可 join KOL 注册表。

## 2. 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/extraction/broker_recommendation_adapter.py` | 新增 | F3 声明式适配器：纯函数 `adapt_t3_line` + 幂等 CLI |
| `tests/test_broker_recommendation_adapter.py` | 新增 | 84 tests，纯 dict fixture + tmp_path，不碰真盘、不 mock schema |
| `configs/creators/{瑞银,摩根士丹利,摩根大通,高盛,杰富瑞,RBC,伯恩斯坦,花旗}.yaml` | 新增 | 8 家券商 creator 档案（T3 语料覆盖 88%），creator_id=中文名对齐 F0 join key |
| `data/F3_intents/bri_*.json` | 数据 | 28 条 recommendation intent（切片 20 + E2E 批次 T3 覆盖 8） |

无任何既有文件修改。与同期进行中的 F2 注册表增强波（enrichment/**）文件面零重叠。

## 3. 架构影响

- **F3 层新增第二条 intent 生产路径**：声明式适配器与 LLM `intent_extractor.py` 并列。适配器只处理 `source_platform=broker` 的 T3 覆盖内容；未接入 pipeline driver 自动路由（见未解决项 1）。
- **A2 schema 槽位全量启用**：`actionability="recommendation"`、`target_price`（schema `IntentTargetPrice`）、`prior_direction`、`rating_action`、`conviction_source="derived_lookup"` 全部使用真槽位（首个生产消费者）。`recommendation`+`position_delta_hint="none"` 组合经核验不触发任何 ambiguity validator。
- **血统诚实**：`envelope_id` 必须来自真实 F1 envelope（join 不到即 skip）；`evidence_span_ids` 只引用 F2 已有 span，引用不到留空——F5 硬门 `EmptyEvidenceSpanIdsError` 会如实拦截，不伪造证据。
- **join 键**：T3 `filepath` ↔ F0 `metadata.source_filepath`（免哈希重算）；`intent_id = "bri_" + sha1(content_id|symbol|rating|date)[:24]` 内容派生稳定 id，重跑幂等且保留原 `created_at`（字节稳定）。

## 4. 关键决策

1. **direction 只来自词表**（模块级 frozenset，覆盖实测 18 种写法含中文）：bullish←buy/overweight/ow/outperform/add/positive/accumulate/买入/增持/surperformance；neutral←neutral/hold/equal weight/ew/market perform/sector perform/in line/持有/中性；bearish←sell/underweight/underperform/reduce/卖出/减持。归一化：casefold + 连字符/下划线→空格 + 空白折叠。未识别→skip(unmapped_rating) 并记录原词长尾（实测唯一长尾：`Buy/High Risk` ×1）。
2. **conviction 查表 + R6 防线**：strong(0.7)/tilt(0.6)/neutral(0.4)，`conviction_source="derived_lookup"` 恒定——明禁进 credibility 计算（当前 `_credibility_score` 不消费 conviction，天然无违反面，但无代码级 guard，见上游 spec）。
3. **horizon_months→time_horizon_hint**：null→long_term（卖方 12M 惯例，对齐 `resolve_horizon_tier` 未知默认 long/180d）；≤2→short；≤6→medium；>6→long。
4. **currency 启发式**：报告未声明 currency 时按 ticker 后缀推断（.HK→HKD、.SZ/.SS/6位→CNY、否则 USD），`metadata.target_price_currency_inferred=true` 标记——schema 槽位只装声明事实，推断痕迹进 metadata。
5. **不用 `is_industry_report`**（R10：字段是反的）；**不 import enrichment.***（ticker 深度归一属 F2 波 ownership，适配器只做 upper+strip）。
6. **worktree→主仓迁移**：A3 workflow 的 agent 在 worktree 执行（缺主仓未提交的 A2 schema），初版被迫 `opinion`+metadata 双写；主仓化时升级为 A2 真槽位并同步 84 个测试断言。worktree 中留有初版副本（untracked，未清理）。

## 5. 验证结果

| 验证项 | 命令/方法 | 结果 |
|---|---|---|
| 适配器单元测试 | `pytest tests/test_broker_recommendation_adapter.py -q`（主仓） | **84 passed**（0.54s） |
| 全量回归 | `pytest tests/ -q`（主仓） | 3,501 passed / 22 skipped / **1 failed——归因 F2 增强波 WIP**（`test_entity_registry_broker.py`，该波 impl agent 当时正在写盘），与 A3 无关；A3 文件面内零失败 |
| 全量执行 | `python -m finer.extraction.broker_recommendation_adapter --t3-jsonl burn_all.jsonl --data-root data --execute` | 4,286 行 → adapted 28 / no_f0 4,255 / not_rated 2 / unmapped_rating 1 |
| 产物语义 | 程序化核验 28 个 bri_*.json | 28/28 `actionability="recommendation"`、28/28 `conviction_source="derived_lookup"`、25/28 有 target_price（含修订对 59←47 CNY）、28/28 rating_action、4/28 prior_direction、2/28 evidence_span_ids 非空 |
| 幂等 | 重跑 --execute 两次 | 文件数不翻倍、intent_id 稳定、`created_at` 保留（字节稳定） |
| registry join | `KOLRegistry` 只读加载 | 11 profiles（8 新增），与 F0 broker creator_id 精确 join |
| workflow 验收 | 只读验收 agent（worktree 初版） | 所有权 PASS / 语义 9 项 8 PASS 1 PARTIAL（PARTIAL 即 opinion 降级，主仓化已消除） |

## 6. 未解决项

1. **driver 未接线**：适配器是独立 CLI，pipeline driver 尚不会对 broker 内容自动路由声明式路径（动共享 driver 需单独 ownership，建议 F2 波收口后做）。
2. **evidence_span_ids 覆盖率低（2/28）**：F2 实体锚定对外资研报英文实体命中不足（registry 为 KOL 语料策展）——正是进行中的 F2 注册表增强波要修的；该波收口后重跑 F2 + 本适配器（幂等），evidence 覆盖会显著提升。F5 硬门当前会拦截 26/28。
3. **T3 覆盖缺口**：4,255 行 no_f0——T3 烧了 4,286 份但 F0 只导入过 124 份。放量导入是激活主轴的下一步（注意 R8 外置盘依赖未决策）。
4. **registry 覆盖缺口**：F0 存量含 6 个无档案 creator_id（里昂/巴克莱/BMO/汇丰/Cantor Fitzgerald/None×2——None 需排查 F0 intake 的 broker 字段缺失路径）。
5. **worktree 副本清理**：musing-bell-c975d7 worktree 中的初版 adapter/tests/YAML 未删除（等用户确认后清理）。
