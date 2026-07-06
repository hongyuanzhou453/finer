# F1 假表格误分类修复 — pdfplumber 散文表拒绝启发式

## 概述

修复 F1 PDF 标准化的表格误分类：pdfplumber 把口播文稿类 PDF 的整页散文包成窄伪表格（生产实证：trader_ji 直播文稿 27/27 block 全部 `table_region`，散文被 `| --- |` 管道框包裹），污染 block 语义与下游 F2 bbox provenance。`_extract_tables` 增加"散文表"拒绝启发式，误判表降级为纯文本 block（去管道框、保 bbox、metadata 记 `demoted_from`）。**端到端铁证：对同一份真实 PDF 重跑，27/27 table_region → 27/27 paragraph（全部 demoted）**。全量 3031 passed 零回归。

## 根因与启发式

- pdfplumber `extract_tables()` 会把版式规整的文稿页识别为 1-2 列"表格"，一个 cell 装数百字多行散文（实测 block：`'| 20260315内部直播音频.mp3\n关键词\n…647 字'`，row_count=2）。原 `_extract_tables` 对 ≥2 行的检出全盘接受。
- 判据（打在 `_table_to_text` 之前的原始 `table_data` 上）：**列数 ≤2** 且（最长 cell ≥120 字 或 平均 cell >80 字 或 （含多行 cell 且最长 ≥60 字））→ 散文。真表格是 3+ 列短标签/数字 cell（本 tier 实测 avg 5-18 字），不会命中。
- 阈值故意保守（宁可漏判个别边缘窄表，不误伤真表格）；2 列长 note 表被降级属可接受权衡——内容以 paragraph 完整保留，只丢表格语义。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/parsing/pdf_standardizer.py` | 修改 | `_extract_tables` 加散文分支（降级 block_type 走 `_classify_text`、无管道框、metadata `demoted_from`/`row_count`）；bbox 提前注册保证 page-text 通道不重复抽取；新增 `_is_prose_table`（4 个类常量阈值）+ `_table_cells_to_prose` |
| `tests/test_pdf_prose_table.py` | 新增 | 8 用例：真实文稿形状检出 / 真表格（4 列）保留 / 2 列 KV 短表保留 / 长 cell 降级 / 多行 cell 降级 / 空 cell 不误判 / 拍平无管道 / 空 cell 跳过 |

## 验证结果

- 单测 8/8（期间修了两处**测试数据自身的字数算术错**，非启发式错）；既有 `test_pdf_document_standardizer.py` 54 条全过。
- **真实 PDF 端到端**：`data/L0_ingest/trader_ji/.../20260315内部直播文稿.pdf`（生产产出 27/27 假表格的那份）重跑 `_extract_tables` → `{'paragraph': 27}`，demoted=27。
- 全量 `pytest tests/` **3031 passed**（基线 3023+8）零回归。

## 存量处置（明确不重跑）

磁盘上 401 个 F1 envelope 里的既有假表格 block **保持原样**：重跑 F1→F5 会重掷全部 uuid、丢 backtest_result 与审计引用；且下游危害已在前几轮消解——evidence 句窗 builder 对管道框有剥除逻辑，F5 evidence 已修复。本修复的价值在**新导入**从此干净。若将来批量重标准化（如 Phase 2 LLM extractor 上线一并重跑），假表格自然消失。

## 未解决项

1. 阈值基于本 tier 语料校准（中文口播文稿）；英文长句表格 cell 的边界行为未专门验证。
2. `_classify_text` 对降级散文可能给出 `section_title`（短首行）——观察项，当前真实案例全部落 paragraph。
3. 1 行"表格"本就被 `len<2` 跳过、由 page-text 通道兜底——该既有行为未动。
