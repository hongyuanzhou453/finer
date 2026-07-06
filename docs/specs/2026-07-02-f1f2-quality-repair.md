# F1/F2 质量修复 — 退化 evidence / 伪 ticker / 平置信度

## 概述

照妖镜清单三病灶的根治：溯源（3 视角并行，逐层打开 F0→F1→F2→F5 真实数据）→ 管线向前修 → 存量 in-place 修复（已授权）。结果：**退化 evidence 49/58 → 0/58**（"亚马逊|亚马逊|亚马逊"→真实上下文句子），**sector 伪 ticker 双层拦截**（F5 gate + 前端概念降级），**conviction 与 confidence 分字段**（58/58 回填真实三档信念，浮点残差修复）。全量 3018 passed 零回归。

## 根因（三张溯源卡的结论）

1. **退化 evidence 不在 F0/F1/F2，在 F5 组装**：F2 evidence span 按设计是 mention 级锚点（text=别名本身 2-4 字），`canonical_runner._build_evidence_text` 把全部提及 span 用 " | " 直拼——block 原文一直完好（直播口播散文）。F1 把散文包进假表格管道符是**独立问题**（pdfplumber 误分类，27/27 block 全 table_region），与本病灶无关，另立后续。
2. **伪 ticker 不是 F2 的错**：entity_registry 的 sector 占位条目（"光模块"→OPTICAL_MODULE）+ F2 正确标注 entity_type=sector；是 F3 无条件塞 target_symbol、F5 gate 只查"有无 symbol"不查"是不是 sector"。**DXY 不是缺陷**（有意的指数代理，回测正常）。降级信号（instrument_type=unspecified）在磁盘上一直存在，是 API 边界把它丢了。
3. **平置信度是 F3 规则阶梯**（有 symbol=0.85，每 flag −0.05→浮点残差 0.7999…），F5 纯透传；**F3 conviction（keyword 计数三档 0.55/0.65/0.75）本来就有区分度但从未进 F5**；F4 mapping_confidence 也被 runner 忽略（builder 早有 `min()` 先例）。LLM 从未在环里。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/pipeline/canonical_runner.py` | 修改 | `_build_evidence_text` 句窗重写（`_sentence_window`+`_block_texts`，去重+top-3+剥管道框）；programmatic/llm 双路径 sector gate（`sector_target_not_tradable`）+ 裸 target_name gate（`unresolved_target_symbol`）；`conviction=intent.conviction` + `confidence=min(intent, mapping)`（对齐 builder 语义）；rationale 只取首条 snippet |
| `src/finer/schemas/trade_action.py` | 修改 | `TradeAction.conviction: Optional[float]`（信念强度，区别于管线置信度） |
| `src/finer/extraction/intent_extractor.py` | 修改 | confidence `round(,3)` 消浮点残差 |
| `src/finer/extraction/canonical_action_builder.py` | 修改 | conviction 透传（与 runner 一致） |
| `src/finer/api/routes/opinions.py` | 修改 | `TimelineOpinion` 增 `conviction`/`instrumentType` |
| `src/finer_dashboard/.../OpinionTimeline.tsx` | 修改 | 接口同步 |
| `src/finer_dashboard/src/lib/live/opinions-adapter.ts` | 修改 | 信念取 `conviction ?? confidence`；概念类 market 槽显示"概念·不可交易" |
| `tests/test_canonical_evidence_quality.py` | 新增 | 5 用例（句窗/去重/兜底/上限/剥管道框） |
| `scripts/repair_f5_quality.py` | 新增 | 存量修复（dry-run 默认；只改 evidence_text/rationale/conviction 三键；F2 span 重解析 + F3 intent_id join） |
| `data/F5_executed/*` | 数据修复 | 🔴 红线已授权；备份 `F5_executed.bak-20260702-223850`；12 文件原子写 + 索引重建 |

## 关键决策

1. **修在 F5 组装层，不动 F1/F2 锚定语义**——mention 锚点本身是对的（审计定位用），错在把锚点当可读文本；`evidence_span_ids` 保持全量不裁。
2. **sector 走"F5 拒绝 + RejectedIntent 审计"而非静默丢弃**；存量 4 条 OPTICAL_MODULE 不重跑（重跑会换 uuid 丢 backtest），走 API 透出 instrumentType + 前端降级标注。
3. **conviction/confidence 分字段而非加权混合**——溯源卡实测加权后仍只有 3 档（同源规则高度相关），混合只会搅浑语义；三档是规则提取的诚实上限，LLM 打分（Phase 2）才给连续分布。
4. **存量 in-place 修复而非全量重跑**：F2 span+block 全文完好、F3 join 58/58 命中，保 uuid/保 backtest/保 RLHF 引用。

## 验证结果

- 溯源 workflow：3 卡全部带逐层数据证据 + file:line。
- 单测：evidence 质量 5/5；全量 **3018 passed**（+5）双轮（管线修后 / 存量修后）零回归。
- 存量修复：dry-run 报表（49→0 退化、58 evidence、58 conviction）→ 授权 → apply 12 文件 + reindex 58/0 fail。
- API 实测：conviction=0.55、instrumentType=stock、evidence 为真实原话（"那紫金矿业里面都是铜"）。
- `/radar/kol/trader_ji` 浏览器实测：时间线全部为 KOL 原话证据 + 55% 真实信念显示；无 console error。

## 未解决项（后续任务线）

1. **F1 假表格误分类**（pdfplumber 把口播文稿整页判成 table_region）——独立 F1 任务，需散文表拒绝启发式；影响 block_type 分布与 F2 bbox provenance。
2. **F3 同 envelope 重复 intent**（3×光模块、2×腾讯等重复卡上屏可见）——F3 需 per-envelope 同标的去重。
3. **Phase 2 LLM conviction 打分**（连续区分度）：canonical_runner 的 extractor 改可注入 + 修 prompt 里 0.85 锚定示例。
4. 句窗 120 字上限会截断长句（"…换成估值更优但方向相同的标的（如谷"）——可调参或按标点回退。
5. sector 观点的"降级保留"产品路线（instrument_type=sector_concept 上屏但禁回测）未启用——当前新数据一律 Rejected，若产品要板块观点上时间线再开。
