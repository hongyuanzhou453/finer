# MiMo 图片/PDF → F1 标准化：F0 建档 + 小样本验证

## 1. 概述

用 MiMo-V2.5 把 `data/raw` 下的历史图片/PDF 接入 F1 canonical 标准化。本轮完成三段：F0 批量建档（197 条 `ContentRecord`）+ F1 小样本验证（35 项）+ **③ 全量回填（191 项 → F1 canonical `ContentEnvelope`，0 fallback）**。结论：图片 OCR 生产级（财务表格逐字零误差），PDF 智能分流有效，canonical 校验全过。**全量首跑因并发 4 触发 MiMo 429，致 71 张图静默降级为 fallback 占位块（仍显示 ok/canonical=True）；经「adapter 加 429 退避重试 + 降并发到 2 + runner 识别 fallback 强制重做」根治，最终 191/191 真 OCR、2618 blocks、31.3 万字。二次体检又发现两类此前未拦的静默失败——content-safety **refusal**（拒绝消息当 OCR，1 张）与图表**幻觉**占位 URL（2 张）——已内置 OCR 质量门控（`ocr_quality.py`）源头拦截 + 重处理，191/191 machine-clean。**注意：门控只挡"显性"失败；clean 内容的隐性字符/数字准确率仍需 human gold set 背书，本轮未做。**

## 2. 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/ingestion/local_raw_intake.py` | 新增 | F0 本地 raw 建档器：扫描→推断元数据→content_hash 去重→构造 `ContentRecord` |
| `scripts/intake_local_raw.py` | 新增 | 建档 CLI（默认 dry-run，`--write` 落盘） |
| `scripts/validate_f1_sample.py` | 新增 | F1 小样本验证 runner：分层抽样→router→MiMo→envelope→报告 |
| `data/F0_intake/local/**/*.json` | 新增数据 | 197 条 `ContentRecord`（仅 JSON，未碰 SQLite） |
| `data/F1_validation_runs/{smoke,sample}_*` | 新增数据 | 验证产物 envelope + `_summary.json` |
| `scripts/backfill_f1_standardize.py` | 新增 | ③ 全量回填批处理器：并发 + 断点续跑 + fallback 重做 + 真调 MiMo 守卫 |
| `src/finer/parsing/image_ocr_standardizer.py` | 修改 | `_extract_via_vision_api` 加 429 退避重试（2/4/8/16s ×5），防单次限流静默降级 |
| `data/F1_standardized/{content_id}/content_envelope.json` | 新增数据 | 191 条 canonical envelope（content_id 命名，不覆盖旧 stem 目录孤儿产物） |

**仅** 对 `image_ocr_standardizer.py` 加 429 退避重试（健壮性增强，不改成功路径行为）；schema / router / 契约未动，其余完全复用现有 F1 管线。

## 3. 架构影响

- **F0（ingestion/）**：新增 local backfill 路径，输出 canonical `ContentRecord`，符合「F0 只输出 ContentRecord」约束。一次性脚本，不递归扫描启动、不写 SQLite 热索引。
- **F1（parsing/）**：完全复用 `StandardizationRouter` → `ImageOCRLayoutStandardizer`（图片，MiMo vision fallback）/ `PDFStandardizer`（PDF，pdfplumber 文本层 + 扫描页 vision fallback），零修改。
- **数据流**：`data/raw/{creator}/...` → `data/F0_intake/local/{creator}/{content_id}.json` → `router.route()` → `ContentEnvelope`。打通历史图片/PDF 的 F0→F1 路径。
- **契约**：`ContentRecord` / `ContentEnvelope` 字段无变更。

## 4. 关键决策

- **content_hash 作 content_id 基底**（`local_{sha256[:24]}`）：字节相同副本天然塌缩成一条 record（307 扫描 → 110 重复 → 197 唯一）。
- **只认 `data/raw` 为 canonical 建档源**；`L0_ingest` 仅借 3 个代表性 PDF 用于验证，不建档（避免与 raw 重复源烧两遍）。
- **`source_platform="local"`**：区别于飞书实时同步 record（无 chat_id/message_id），`metadata.origin_hint` 记录 `feishu_export`（从 `img_v3` 文件名推断）保留溯源。
- **`published_at` 从文件名 `YYYYMMDD_HHMM` 解析**（97%，191/197）→ 文件 mtime 回退（6 条）。
- **显式 None 守卫**：vision LLMClient 为空（如缺 `MIMO_API_KEY`）立即 `SystemExit`，杜绝图片静默走 fallback 占位块却显示 `canon=True` 的伪成功（smoke 首跑就踩了此坑——脚本漏 `load_dotenv()`）。

## 5. 验证结果

**命令**：
```bash
python scripts/intake_local_raw.py --write          # ① 建档
python scripts/validate_f1_sample.py --smoke        # ② smoke 6 图
python scripts/validate_f1_sample.py --img-per-creator 9 --pdfs   # ② 完整 29 项
```

**① 建档**：Scanned 307 / New 197 / Duplicates 110 / 写入 197；197 条 round-trip `ContentRecord` 全过（bad 0）。分布：maodaren 109 / 9you 81 / bilibili 5；image 194 / pdf 3；published_at 解析 filename 191 + mtime 6。

**② 验证**（smoke 6 + full 29 = 35 项，canonical_ok 35/35）：

| 路径 | 样本 | 质量 | 耗时 |
|------|------|------|------|
| 图片 OCR（MiMo） | 24 投研截图 | 财务表格逐字零误差（Read 原图核对 9 行数字全中）；长文/对话术语准确；block 语义分类准（表格→`table_region` 转 markdown、对话→`quote`、长文→`image_text` 按段落） | avg ~10–20s/张 |
| PDF 文本层（pdfplumber） | 文稿型 3 个 | 内容可读，**智能分流生效**：0.2–0.7s，不烧 MiMo | <1s |
| PDF vision（MiMo） | 研报截图型 1 个 | 走 vision OCR | 33.5s |

**硬证据**：maodaren 财务表格（[20260327_2141...png](data/raw/maodaren/unclassified/20260327_2141_img_v3_02106_76b60a52-3214-42a5-ba28-d362ea64cdcg.png)）OCR 输出与原图逐字一致——收入 114,583/99,322/+15.4%、归母净利润 2,495/1,759/+41.8%、每股股息 49.80/31.80 港仙，含单位「港仙」「个百分点」，零幻觉。

**③ 全量回填**（`scripts/backfill_f1_standardize.py --concurrency`）：191 项（189 图 + 2 PDF）→ `F1_standardized/{content_id}/content_envelope.json`。
- 首跑 concurrency=4：183/183「ok」但日志现多次 `429`，复查 **71 张 maodaren 图实为 fallback 占位**（占 37%）——静默降级伪成功。
- 修复后 concurrency=2 重做 71 张：71/71 真 OCR、**0 fallback**、零 429（重试未触发，降并发已足够）。
- 终态复查：191/191 真 OCR，2618 blocks（avg 13.7），31.3 万字，block 分类 `image_text` 1699 / `section_title` 501 / `table_region` 144 / `chart_region` 30 / `quote` 82 …，`ocr_unreadable` 仅 1。

**OCR 质量门控体检**（`src/finer/parsing/ocr_quality.py` + `scripts/audit_f1_ocr_quality.py`）：
- 体检 191 张发现两类此前"伪成功"的静默失败：**refusal**（MiMo 内容审核拒绝消息被当 OCR 入库，1 张）、**hallucination**（图表无法识别时编造 `via.placeholder.com` 占位 URL，2 张）。二者均通过 canonical 校验、无 fallback 标记——靠肉眼抽查必漏（我手检只找到 1/2 张幻觉，门控扫全）。
- 门控内置 adapter 源头：refusal/空 → 返回 None 走**标记 fallback**（不再伪成功）；placeholder → 清洗行保留真文字。`ocr_quality.py` 为单一真相源，adapter / runner / audit 共用，含「真实研报含风险·无法 不误判」守卫。
- 3 张重处理：refusal 张**重试即救回**（81 blocks 真 OCR → MiMo 审核为偶发非稳定误杀）；2 张幻觉清洗假 URL 后保留正文。**终态 191/191 machine-clean，hard-failure 清单为空**。
- 测试：7 项门控单测 + adapter/router 回归，全套 **104 tests 通过**。

**OCR 数字准确率评测**（`scripts/eval_ocr_accuracy.py` + `data/F1_gold_sets/ocr_accuracy/`，模仿 OmniDocBench 指标）：人工逐字转写 4 张清晰投研截图（TCL 业务收入表 + 3 张行情）的 ground-truth，共 126 个核心数字，对比 MiMo 输出——
- **数字 recall 97.3%**（215/219，7 张 gold）；**5 张财务表格 100%**（TCL/小米/小鹏/车企/布伦特，含会计括号负数 `(1,177,201)`/`(31.2%)` 全对）；4 个 missed 全是图表 Y 轴刻度/分时量边角小字。
- **零幻觉数字**：MiMo「多余」数字经核查全是原图真实内容（滚动成交明细价、年份 2024/2025、时间戳、成交笔数），非编造——表面 precision 0.71 仅因 gold 未标成交明细噪声列。
- 唯一漏项：图表 Y 轴刻度（±6.94%、94.14）、分时量边角小字——与「图表数据提取弱」的已知结论一致。
- 局限：样本 7 张/219 数字（标注员只能可靠核对清晰单表/行情图，超长拼接图核不了），已是稳定小 benchmark，可继续扩。eval 含会计括号负数标准化（`(1,234)`→-1234）。

## 6. 未解决项

1. ~~PDF pdfplumber 字体瑕疵 + 文稿误分类~~ **【已解决 2026-06-14】**：`pdf_standardizer._is_radical_garbled` 检测 CJK 部首占比 >5% → `page.to_image()` 渲染 + MiMo OCR（复用现有 `_extract_page_via_vision`，零新依赖，PDF vision 也过 `gate_vision_output`）。课代表整理.pdf 验证：异体字 223→7（96.9% 消除），渲染 OCR 同时修复误分类。MinerU 评估后弃用（Mac CPU 重慢、起 fast_api 服务、848M 模型 0.2% CPU 不推理；MiMo 渲染复用已验证 97.3% 能力更对口）。
3. **bilibili/covers 视频封面**（5 张）无文字，OCR 走 fallback（chars 39–149）→ ③ 全量应排除。
4. **MiMo 429 限流阈值**：concurrency=4 在 maodaren 大批（109 张）持续压力下触发 429；concurrency=2 则零 429。已加 adapter 退避重试兜底，但安全并发上限（2–3）仍是经验值，未做精确压测。
5. **旧 F1_standardized stem 目录**：195 个早期旁路产物（无 F0 record，stem 命名）与本轮 191 个 content_id 命名产物并存；同一图可能两份。清理需用户确认（删除操作）。
6. **教程 PDF 重复建档**：`data/raw/local/从0开始...Claude_Code教程.pdf` 已有旧 `api_upload` record（UUID）+ 本轮新建 `local_{hash}` record，两条并存（内容无关投研，无害未清理）。建档器去重未跨「已有其他建档路径登记」检查。
