# F1 OCR 像素级 bbox — Qwen-VL-OCR layout 引擎接入

> 日期: 2026-06-14
> F-stage: F1 (parsing)
> 状态: Phase 1（引擎验证）+ Phase 2（接线）已完成并验证；Phase 3（全量回填）待用户确认
> 关联: [自改进标注闭环 §10 任务 D](2026-06-13-self-improving-annotation-loop.md)、[MiMo 图片/PDF 接入 F1](2026-06-13-mimo-image-pdf-f1-intake.md)

## 1. 概述

给 MiMo chat-vision 产出的、`bbox=None` 的 OCR 块补**像素级 bbox**，使溯源链能从 TradeAction 一路点回原图具体区域。做法：引入 **Qwen-VL-OCR `advanced_recognition`**（阿里 DashScope，原生返回像素坐标）作为 F1 OCR 路径的主引擎，把行/单元格级 box 几何聚类成语义 region，喂给**早已存在但无生产方**的 `_build_blocks_from_regions` 消费口。MiMo 保留为 Qwen 失败时的纯文本兜底。零新 pip 依赖（复用 dashscope 凭据 + 原始 HTTP），零 schema 改动。

实测：图片端到端 bbox 100% 非空、数字零误差、audit machine-clean；PDF 渲染页 OCR bbox 100% 非空且正确换算到 PDF point 空间。

## 2. 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `scripts/eval_bbox_ocr.py` | 新增 | Phase 1 验证脚本：Qwen-VL-OCR vs MiMo，产 bbox overlay + 数字 recall 对照 |
| `src/finer/parsing/layout_ocr_client.py` | 新增 | Qwen-VL-OCR 客户端（原始 HTTP + 429 退避）+ 纯几何聚类（行→块、表格按列结构识别、像素→aabb） |
| `src/finer/parsing/image_ocr_standardizer.py` | 修改 | `standardize()` 加 Path 0 layout 路径（主），MiMo chat-vision 降为兜底；`_build_blocks_from_regions` 加 `model_name` + `line_boxes` 透传 |
| `src/finer/parsing/pdf_standardizer.py` | 修改 | `_ocr_fallback_page` 先走 `_ocr_page_via_layout`（新增）：渲染页→Qwen→像素 bbox ×72/dpi 换算到 point 空间 |
| `tests/test_layout_ocr_client.py` | 新增 | 19 项：几何聚类/坐标/响应解析/mock HTTP/standardizer 集成 |
| `data/F1_bbox_eval/*` | 新增数据 | Phase 1 overlay PNG + regions.txt + _summary.json |

## 3. 架构影响

- **F1 (parsing)**：OCR 文本源由 MiMo 变为 **Qwen-VL-OCR（Design 1 全替换，用户 2026-06-14 批准）**，MiMo 降为兜底。原 model_config「MiMo 唯一 vision provider」规则获显式例外：Qwen 作 OCR 引擎（文本+几何），MiMo 仍是兜底文本源。
- **消费链复用**：`ImageOCRLayoutStandardizer._build_blocks_from_regions` / `_extract_bbox` / `_map_region_type` / 噪声检测 / 质量打分零改逻辑，仅加 `model_name`+`line_boxes`。`standardize()` 的 `layout_regions`（来自外部 metadata）路径仍兼容。
- **坐标空间**：图片 = 原图像素空间；PDF 渲染页 OCR 块 = PDF point 空间（×72/150 换算，与 pdfplumber 文本层块同空间），`metadata.render_dpi` 记录。
- **契约**：`BoundingBox` / `ContentBlock` / `ContentEnvelope` 字段零变更。块粒度与 MiMo 同级（表格→1 个 table_region 块，非单元格爆炸）。
- **护栏保留**：`gate_vision_output`、异体字 `_is_radical_garbled`、429 退避全部保留；Qwen 失败/限流/无 key → 干净回退 MiMo。

## 4. 关键决策

- **引擎=Qwen-VL-OCR `advanced_recognition`**：MiMo 无 bbox 文档端点（已查证，仅 chat-vision）；MinerU 前轮因 Mac-CPU 慢弃用；PaddleOCR 属新重依赖。Qwen 经现有 DASHSCOPE_API_KEY + 原始 HTTP（mirror bilibili_adapter）→ 零新依赖、零本地算力、云端、中文原生、原生像素 bbox。
- **Design 1 全替换 而非 Design 2 混合**：Phase 1 实测 Qwen 数字 recall 0.992 ≥ MiMo 0.973，且 Design 1 每块=一个 Qwen region 天然 text↔box 1:1、零跨引擎对齐风险（Design 2 的模糊对齐本身会产生错框）。用户在数据呈现后拍板。
- **表格按列结构识别，不靠垂直间隙**：表格行间有真实空白，间隙分块会把一张表撕成 N 块。改为「连续 ≥2 个多单元格行 = 表格」，再按行渲染 markdown；纯文本才用垂直间隙分段。这是单引擎自身几何，无对齐风险。
- **像素→point 换算（PDF）**：渲染 OCR 的像素坐标 ×72/dpi 转 PDF point，使同页 OCR 块与文本层块共享坐标系。
- **line_boxes 保留**：region 内每个 cell 的 box 存入 block metadata，支持「点回具体行/单元格」的更细溯源。

## 5. 验证结果

**Phase 1 引擎验证**（`scripts/eval_bbox_ocr.py`，7 张 gold）：
- bbox 覆盖率 **7/7 张 100%**；overlay 人工核对：框精准落在表格单元格/行情逐笔/Y轴刻度上（表格+密集图表两种版式）。
- Qwen 数字 recall **0.992** > MiMo 基线 **0.973**；precision 0.748（偏低=gold 未标滚动逐笔等真实屏上数字，与 MiMo 同源、非幻觉，overlay 证实每个识别串都锚定真实像素区域）。

**Phase 2 接线**：
- 单测：`tests/test_layout_ocr_client.py` 19/19 通过。
- 回归：parsing 套件（image/pdf/ocr_quality/router/fixtures/content）281/281 通过。
- 图片端到端（真实 TCL 表 + live Qwen）：1 个 table_region 块、bbox 1/1 非空、model_name=qwen-vl-ocr-latest、84 line_boxes、关键数字全中、**audit=clean**。
- PDF 端到端（真实异体字 PDF 单页 + live Qwen）：13 块（标题/段落/表格）、bbox 13/13 非空、坐标在 point 空间内（max x1=562≤595, y1=800≤842）证明换算正确。

## 6. 未解决项

1. **Phase 3 全量回填未做**：104 渲染 OCR + 2534 图片 OCR 块需重跑补 bbox（mirror `backfill_f1_standardize.py`）。属批量重建（CLAUDE.md 红线），**待用户确认**。
2. **长文/对话版式 Qwen 文本质量未验证**：gold set 全是财务/行情图。放量(P3)前应补 prose/dialogue 小样本验证 Qwen 文本不回退（用户在 Design 1 选择时已要求）。
3. **EvidenceSpan 穿透（F2）不在本轮**：本任务只到 `ContentBlock.bbox`，与 F2 主线解耦（任务 D 的 F2 部分另立）。
4. **eval_bbox_ocr.py 与 layout_ocr_client 的 HTTP 调用有少量重复**：前者一次性验证脚本，后者生产真相源；可接受，未抽公共。
5. **qwen-vl-ocr-latest 未钉快照**：为审计可复现性，放量前可考虑钉 `qwen-vl-ocr-2025-11-20` 等快照（现经 `QWEN_OCR_MODEL` 环境变量可覆盖）。
