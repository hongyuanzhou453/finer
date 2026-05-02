# F1 Standardization Fixtures

F1 工程验收 fixture：5 个真实 F0 样本，用于验证 F1 adapter 输出是否满足 canonical contract。

## 样本清单

| Fixture ID | 类型 | 来源 | 日期 | 描述 |
|---|---|---|---|---|
| `chat_maodaren_0312` | feishu_chat | maodaren | 03-12 ~ 04-20 | 1079 条飞书群消息，含 Q&A、合并转发、图片引用 |
| `img_9you_0416` | image | 9you | 04-16 | PNG 截图，OCR 未提取（API key 缺失） |
| `pdf_maodaren_0415` | pdf | maodaren | 04-15 | 14MB 第三方研报 PDF |
| `img_9you_0409` | image | 9you | 04-09 | PNG 截图，OCR 未提取 |
| `img_maodaren_0319` | image | maodaren | 03-19 | PNG 截图，含吉利汽车财报分析上下文 |

## 文件结构

```
f1_standardization/
  README.md
  chat_maodaren_0312.json     # fixture manifest
  img_9you_0416.json
  pdf_maodaren_0415.json
  img_9you_0409.json
  img_maodaren_0319.json
```

## Manifest 字段

- `fixture_id`: 唯一标识
- `source_type`: canonical F1 source type
- `raw_path`: 相对于项目根目录的原始文件路径
- `source_record_id`: F0 ContentRecord content_id
- `expected_adapter`: 应处理此样本的 adapter 类名
- `expected_profile`: standardization_profile 值
- `assertions`: 结构化验收断言定义
- `engineering_risks`: 每个样本的已知工程风险

## 原始文件位置

原始文件在 `data/raw/` 下，不在 fixtures 目录内。Manifest 中的 `raw_path` 使用项目根目录相对路径。

## 测试

```bash
python -m pytest tests/test_f1_standardization_fixtures.py -q
```

## 设计原则

- **不做 golden text 全量比对**：adapter 实现变化不应导致 fixture 失败
- **结构断言**：验证 blocks 非空、order 连续、quality/provenance 存在、canonical validator 通过
- **类型断言**：验证必须出现的 block_type（如 chat 必须有 chat_message）
- **不依赖绝对路径**：manifest 使用相对路径，测试中动态解析
