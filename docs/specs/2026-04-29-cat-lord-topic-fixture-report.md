# 猫大人长聊天 F1.5 Topic Assembly Fixture 报告

## 概述

为 F1.5 Topic Assembly 子阶段创建 golden fixture，基于猫大人（Cat Lord FIRE）2026年4月29日飞书直播聊天室的 22 条长对话消息，验证 topic assembler 能正确拆分出 5 个独立主题并识别 7 条未分配噪声。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `tests/fixtures/kol/cat_lord_topic_assembly_input.json` | 新增 | F1.5 输入：22-block ContentEnvelope |
| `tests/fixtures/kol/cat_lord_topic_assembly_expected.json` | 新增 | F1.5 输出：5 TopicBlocks + unassigned |
| `tests/fixtures/kol/README.md` | 新增 | 夹具目录说明文档 |
| `docs/specs/2026-04-29-cat-lord-topic-fixture-report.md` | 新增 | 本报告 |

## 主题组装详情

### Topic 1: 泡泡玛特估值与海外增长分析

| 属性 | 值 |
|------|---|
| topic_type | `single_stock` |
| source_block_ids | `cl_ta_002`, `cl_ta_003`, `cl_ta_004` |
| block_index 范围 | [1, 3] |
| primary_entity | 泡泡玛特 (9992.HK) |
| confidence | 0.92 |

**组装逻辑**: 三条连续消息围绕同一标的展开。Block 002 提出核心观点（IP 运营能力是护城河），Block 003 是估值 Q&A（PE 35→25，营收 130亿+），Block 004 延伸到海外增长（东南亚+欧美 30% 指引）。语义高度连贯，无歧义。

### Topic 2: 新能源汽车行业趋势与个股观点

| 属性 | 值 |
|------|---|
| topic_type | `industry` |
| source_block_ids | `cl_ta_005`, `cl_ta_006`, `cl_ta_007` |
| block_index 范围 | [4, 6] |
| primary_entity | 新能源汽车（行业） |
| secondary_entity | 比亚迪 (002594.SZ), 特斯拉 (TSLA) |
| confidence | 0.88 |

**组装逻辑**: 三条消息从行业宏观（政策退坡分化）→个股精选（比亚迪/小米）→个案分析（特斯拉竞争力下降）。主题类型标注为 `industry` 而非 `single_stock`，因为涉及多个标的且以行业趋势为主线。`ambiguity_flags` 包含 `mixed_single_stock_and_industry`，反映行业讨论中夹杂个股观点的混合特征。

### Topic 3: 巴菲特股东信读书笔记

| 属性 | 值 |
|------|---|
| topic_type | `investment_philosophy` |
| source_block_ids | `cl_ta_008`, `cl_ta_009`, `cl_ta_010` |
| block_index 范围 | [7, 9] |
| primary_entity | 巴菲特 |
| confidence | 0.95 |

**组装逻辑**: 三条消息是连贯的读书笔记分享，从核心理念（买公司而非股票）→能力圈原则（不投看不懂的）→复利思维（长期持有）。这是整个聊天中 confidence 最高的 topic，因为主题明确、语义边界清晰、无歧义。

### Topic 4: 老铺黄金

| 属性 | 值 |
|------|---|
| topic_type | `single_stock` |
| source_block_ids | `cl_ta_012`, `cl_ta_013`, `cl_ta_014` |
| block_index 范围 | [11, 13] |
| primary_entity | 老铺黄金 (HK) |
| confidence | 0.93 |

**组装逻辑**: 三条消息构成完整的单标的分析。Block 012 切入赛道（古法黄金、毛利率 40%+），Block 013 Q&A 回答一季报（营收增 65%、门店扩张），Block 014 给出估值判断（PE 40 倍偏贵，480 以下建仓）。注意与 Topic 1 之间被 `cl_ta_011`（链接）隔开，assembler 需能识别内容边界跨越噪声块。

### Topic 5: 卫星化学

| 属性 | 值 |
|------|---|
| topic_type | `single_stock` |
| source_block_ids | `cl_ta_016`, `cl_ta_017`, `cl_ta_019` |
| block_index 范围 | [15, 18] |
| primary_entity | 卫星化学 (002648.SZ) |
| confidence | 0.90 |

**组装逻辑**: 这是最具挑战性的 case——三条消息**不连续**，`cl_ta_016`/`cl_ta_017` 和 `cl_ta_019` 之间被 `cl_ta_018`（结束语）隔开。assembler 需要基于语义相似度而非位置邻近性来关联。Block 019 是对 016/017 的补充（风险点分析），与前两条在主题上完全一致。`ambiguity_flags` 包含 `non_contiguous_blocks`，提示这是非连续块合并场景。

## 未分配块分析

| block_id | 内容摘要 | 未分配原因 |
|----------|---------|-----------|
| `cl_ta_001` | "大家早上好，今天行情不错..." | **greeting** — 问候语，无实质性金融内容 |
| `cl_ta_011` | 转发研报链接 | **external_link** — 外部链接，无分析内容 |
| `cl_ta_015` | "不会公开持仓的..." | **meta_discussion** — 关于 KOL 行为的元讨论，不构成投资分析 |
| `cl_ta_018` | "今天先聊这些..." | **farewell** — 结束语，无实质内容 |
| `cl_ta_020` | 回顾之前分析标的的列表 | **reference_list** — 汇总回顾，不构成独立新主题 |
| `cl_ta_021` | "茅台没深入研究过..." | **capability_circle_decline** — 明确拒绝分析，无投资内容 |
| `cl_ta_022` | 系统点赞通知 | **system_noise** — 平台 UI 噪声，非用户内容 |

未分配块覆盖了真实聊天场景中的典型噪声类型：问候/告别、链接转发、元讨论、回顾性引用、能力圈拒绝、系统消息。

## 验证结果

```
$ python -m json.tool tests/fixtures/kol/cat_lord_topic_assembly_input.json >/dev/null
# OK

$ python -m json.tool tests/fixtures/kol/cat_lord_topic_assembly_expected.json >/dev/null
# OK
```

额外验证项（Python 脚本）：
- [x] 所有 5 个 TopicBlock 的 `raw_text` 均可由 `source_block_ids` 对应 block 的 text 用 `\n\n` 拼接得到
- [x] 22 个 block 全部被覆盖（15 assigned + 7 unassigned = 22）
- [x] assigned 与 unassigned 无交集
- [x] `start_block_index` / `end_block_index` 与 source block 的 order 一致

## 关键设计决策

1. **Topic 2 标为 `industry` 而非 `single_stock`**: 虽然提到了比亚迪、特斯拉等个股，但讨论主线是新能源行业趋势，个股是作为行业观点的例证出现的。如果 assembler 有歧义，这个 case 可以用来测试 topic_type 的判断边界。

2. **Topic 5 允许非连续块合并**: `cl_ta_019` 被 `cl_ta_018`（结束语）与前两条隔开，但语义上完全属于同一主题。这是真实聊天场景的常见模式——用户聊完一个话题后说了句"今天先这些"，又想起来补充了一条。assembler 应基于语义而非纯位置来做合并。

3. **confidence 分布**: 0.88-0.95，反映不同 topic 的清晰度差异。巴菲特读书笔记最高（0.95），因为主题边界最清晰；新能源板块最低（0.88），因为混杂了行业与个股观点。

4. **Topic 4 与 Topic 5 之间有 2 个 unassigned block**: `cl_ta_011`（链接）和 `cl_ta_015`（持仓讨论），测试 assembler 在噪声干扰下能否正确识别内容边界。

## Fixture 局限性

1. **无时间戳**: 原始 fixture 的 `start_time` / `end_time` 均为 null（聊天消息无音频时间戳）。如有时间信息的 fixture，应额外测试时间维度的主题切割。

2. **仅 5 个主题**: 真实长聊天可能有 10+ 个主题，当前 fixture 覆盖了基本场景但未测试大规模 topic 拆分的性能。

3. **无跨 envelope 测试**: 每个 fixture 对应单个 envelope。跨多个 envelope 的主题关联（如同一标的在不同日期的讨论）不在本次 fixture 覆盖范围内。

4. **entity_anchors 预置**: 输入 fixture 中已包含 F2 阶段的 entity_anchors，实际 F1.5 可能在 F2 之前执行。如需测试纯 F1 输入，应移除 entity_anchors 并调整 expected 输出。

5. **单一 KOL**: 仅覆盖猫大人一人的聊天风格。多 KOL 群聊场景（多人讨论同一话题）未测试。
