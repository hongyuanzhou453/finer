# KOL Fixtures — 测试夹具目录

本目录存储 KOL 内容分析的测试夹具，用于各 F-stage 的回归测试。

## 目录结构

```
tests/fixtures/kol/
├── README.md                                          ← 本文件
├── cat_lord_strategy_2026_03_12.md                    ← 猫大人 3/12 策略原始内容
├── cat_lord_strategy_2026_03_12.expected_v0.json      ← V0 envelope（F1 输出）
├── cat_lord_strategy_2026_03_12.expected_v1.json      ← V1 intents（F3 输出）
├── cat_lord_image_strategy_2026_04_26.md              ← 猫大人 4/26 图片策略原始内容
├── cat_lord_image_strategy_2026_04_26.expected_v0.json ← V0 envelope（图片 F1 输出）
├── cat_lord_image_strategy_2026_04_26.expected_v1.json ← V1 intents（图片 F3 输出）
├── cat_lord_topic_assembly_input.json                  ← F1.5 输入：22-block 长聊天 ContentEnvelope
└── cat_lord_topic_assembly_expected.json               ← F1.5 输出：5 TopicBlocks + unassigned
```

## Fixture 说明

### cat_lord_strategy_2026_03_12（F1/F3 测试）

- **来源**: 飞书文档会话记录
- **内容**: 理想汽车、宝丰能源、算电协同/绿电、阿特斯/CSIQ、腾讯音乐 五段分析
- **用途**: F1 ContentEnvelope 构建 + F3 Intent 提取的 golden fixture

### cat_lord_image_strategy_2026_04_26（图片 F1/F3 测试）

- **来源**: 飞书图片 OCR
- **内容**: 市场环境判断、板块分析、个股分析、风险提示
- **用途**: 图片内容的 F1 标准化 + F3 Intent 提取

### cat_lord_topic_assembly（F1.5 Topic Assembly 测试）

- **来源**: 飞书直播聊天室长对话
- **内容**: 22 条消息，覆盖 5 个主题（泡泡玛特、新能源、巴菲特股东信、老铺黄金、卫星化学）+ 7 条未分配噪声
- **用途**: F1.5 TopicAssembly golden fixture
- **详见**: `docs/specs/2026-04-29-cat-lord-topic-fixture-report.md`

## 命名约定

```
{kol_id}_{content_type}_{date}.{variant}.json
```

| 段 | 说明 | 示例 |
|---|---|---|
| kol_id | KOL 标识 | `cat_lord` |
| content_type | 内容类型 | `strategy`, `image_strategy`, `topic_assembly` |
| date | 内容日期 | `2026_03_12` |
| variant | 文件角色 | `input`, `expected_v0`, `expected_v1`, `expected` |

## 验证命令

```bash
# 验证所有 JSON 文件格式
python -m json.tool tests/fixtures/kol/cat_lord_topic_assembly_input.json >/dev/null
python -m json.tool tests/fixtures/kol/cat_lord_topic_assembly_expected.json >/dev/null
```
