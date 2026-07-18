# 外资研报接入 Finer OS —— 可行性设计与实测基线

> 日期：2026-07-15
> 状态：设计完成，待决策后实施
> 探查方式：6-agent 并行探查（733k token / 25min），关键断言已人工复核

## 1. 概述

把 `/Volumes/NAMEZY/外资研报`（28,565 份投行研报 PDF，73GB，2025-09 ~ 2026-06）接入 Finer OS，
以 **broker-as-creator** 架构走完整 F0-F8，产出可回测的机构 TradeAction 与券商晨星体检。

目标是解决项目主轴问题：**链路已编码+测试但从未跑真实活水**（1 KOL / 42 陈旧 action / 驱动器吞吐 0）。
研报是现成活水，且在 F0/F2/F7/F8 上**严格比 KOL 内容更容易**（显式 ticker、显式时间戳、声明式 direction）。

## 2. 决定性实测数据（约束一切）

| 事实 | 数值 | 口径 |
|---|---|---|
| 磁盘真实 PDF（剔除 `._*`） | **28,565** | `._*` 占 find 结果约 50%（109,267 → 28,565） |
| DB/metadata 可见 | **26,069**（2025: 20,249 / 2026: 5,820） | 2,496 份 2026 文件对流水线不可见，天花板 91.3% |
| **image-PDF 率** | **11.7%（≈3,339 份）**；text 88.3% | n=800, seed=42, poppler+pypdf 交叉校验（54,923 vs 55,479 chars，无库归因） |
| 按年拆分 | **2025 = 1.9% image / 2026 = 35.5% image** | 由**年份**（sourcing 工具变更）驱动，非 broker 属性 |
| 总页数 | ~562,000（median 14, p90 38） | 需 OCR 页数 ≈ **56,000** |
| 分布形态 | **双峰无中间带**（p5=3 chars/page, p25=2,527） | 阈值不是承重结构 |
| MiMo 端点实测 | concurrency **64 零 429**，**28 req/s**，p50 1.7s | token-plan-cn 从未推回 |
| 当前正文覆盖 | **267 / 26,069 = 1.02%**，冻结于 06-17 | 是 **bug→hang→放弃**，非语料限制 |
| 单票研报天花板 | 现 6,635（25.5%）+ 免费可救 3,254 = **~9,890（38%）** | 其余 16,179（62.1%）**天然无单一 ticker**（宏观 6,321 / 行业策略） |
| rating 覆盖 | filename 8.6%；单票子集 19.7% → 读 P1 可达 **~90%** | 已开 PDF 验证 P1 载有 Rating + Price Target + Bull/Bear |
| 正文含评级/目标价 | **267/267 = 100%** | 本会话实测；82% 可纯正则抽出数字目标价 |

**推论：OCR 不是瓶颈。** 56,000 页 @5s/call、concurrency 16 ≈ **4.9 小时**。9 天窗口过剩十倍以上。
**瓶颈是 schema 语义与人的确认。**

### ticker 身份分裂（必须在 F2 归一）

6,635 份单票研报混用 5 套代码体系：无后缀 1,499 / `.US` 1,229 / `.HK` 730 / 路透 RIC（`.N` 334, `.OQ` 253, `.SS` 132）/
本地所（`.T` 361, `.TW` 182, `.KS` 86, `.L` 160, `.AX` 83, `.NS` 103）/ 自造 `.NYSE` 103。

同一标的被拆成多个身份：`NVDA.US`(29) + `NVDA`(21)；`BABA.US`(19) + `BABA`(7)；`300750`(16) 无 `.SZ`。
另有 `PRC` / `China` 等非 ticker 脏值。**不归一则回测把一只票当成三只算。**

日期可信：2025-12 的 9,435 份物理上确实在 12 月目录，目录与解析日期 99.9% 一致，非解析 bug。

## 3. 计划变更清单（尚未实施）

### A0 —— 零 token / 零 schema 改动 ✅ **已实施（2026-07-15）**

用户批准路径：先 dry-run → 备份 db → 全量跑；保留研报仓 21 个未提交改动，本次改动叠加其上。

| 文件 | 变更 | 状态 |
|---|---|---|
| `外资研报/rag_system/database.py:177` | **新增** `mark_report_extraction_failed()` → `text_length=-1` 哨兵 | ✅ |
| `外资研报/rag_system/database.py` | **新增** `get_failed_reports()` / `reset_failed_reports()`（`-1` 必须可逆，供修好提取器后重试） | ✅ |
| `外资研报/rag_system/pipeline.py:105-112` | `else` 与 `except` 两分支调用失败标记 | ✅ |
| `外资研报/build_rag_text_coverage.py` | `extraction_failed_bool` + `coverage_status` 三态 + `GROUP_FIELDS` 登记 | ✅ |
| 运行 `--year 2025` | 当前默认 2026 | ✅ 解锁 19,459 份（96.1%），790 份标 `-1` |
| 运行 `--year 2026`（stall detector 重写后） | 队列无前进判据 + pdfplumber 兜底 | 🔄 穿透 image 密集段中（ok 2,300+） |
| `classify_reports.py:parse_filename` 分支 3/4 | `classify_industry` 已找到实体却丢弃 | ⏸ 未做 |

**备份**：`rag_data/reports_before_a0_20260715.db`（72M，`integrity_check` ok，26,069 行）。

#### 死循环根因（已确认并修复）

```python
# database.py:211 —— 取任务
WHERE year = ? AND text_length = 0  ORDER BY date DESC
# pipeline.py:92-112 —— 只有成功才写回
if full_text:  update_report_text(..., text_length=len(full_text))
else:          failed += 1     # ← 失败什么都不写，text_length 永远是 0
except:        failed += 1     # ← 同上
```
失败文件永远留在 `text_length=0`，`ORDER BY date DESC` 每次把它们排回队首。

**未提交改动里已有人发现此 bug**，但加的是 `Step2Outcome.stalled_batch` **检测**（整批失败即 `SystemExit(1)`），
不是根因修复。它解释了为何冻结于 06-17：跑 `--year 2026` 时队首 43.3% 是 image PDF，几乎必然整批失败即退出。

#### ⚠️ stall detector 判据在根因修复后已过时（未处理）

根因修复后失败记录会出队，「整批失败」不再意味着死循环，只意味着**这批恰好都是 image PDF**——
而 2026 队首恰恰如此。**结果：2026 现在会在第一批立刻 `SystemExit(1)`，永远穿不透 image PDF 层。**
正确判据应是「队列无前进」，而 `-1` 保证队列总会前进。**2026 的 ~3,582 份需先修此处。**
不影响 2025（97% 成功率，每批必有成功）。

#### `-1` 哨兵安全性（逐处核实）

- 用 `text_length > 0` 判「已完成」的全部安全：`database.py:353/354/362`、`build_dashboard.py:177/191`、
  `validate_library.py:990`、`sync_metadata.py:249/543/594`、`lib/rag_planning.py:52`、`run_summaries.py:36`。
- 用 `text_length = 0` 判「待处理」的会正确出队：`database.py:211`、`lib/rag_planning.py:93`、`build_rag_extract_preflight.py:7`。
- `build_rag_text_coverage.py:91` 用 `not has_text_bool` 筛 missing → **`-1` 仍在报告内，不会消失**，
  但会与「从未尝试」混淆 → 已加 `coverage_status` 三态区分。

#### 🐛 顺带发现：coverage 工具在 pipeline 运行时必报 malformed

`build_rag_text_coverage.py:153` 用 `connect_readonly_db(db_path, immutable=True)`。
`immutable=1` 令 SQLite 忽略 WAL 与锁直接读页；文件正被并发写入时是**未定义行为** → `database disk image is malformed`。
**非数据损坏**（同期 sqlite3 CLI 全表扫描返回 26,069 正常，备份 integrity ok）。
该工具隐含假设「运行时 pipeline 已停」，此假设未见于任何文档。

### A1 —— F0 channel（1 天）

| 文件 | 变更 |
|---|---|
| `src/finer/schemas/import_receipt.py:37-44` | `SourceChannel` Literal 加 `"broker"`（硬门：不加则 `ImportReceipt(...)` 抛） |
| `src/finer/ingestion/broker_research_intake.py` | **新建**，仿 `local_raw_intake.py:258-282` |
| — | `source_type="research_report"`（`content.py:36` **已合法，零 schema 改动**） |
| — | `content_id = f"broker_{sha256(bytes)[:24]}"`（内容哈希 → 免费去重） |
| — | 归档 `data/raw/broker/`，**绝不能 `data/raw/local/`**（见风险 R1） |
| — | `published_at` 用研报仓 `extract_date_from_filename`（6 级 regex）+ `extract_date_from_path`；**不得用 `local_raw_intake.infer_published_at`**（`:192-193` fallback file mtime = 伪造发布日） |

### A2 —— F3/F4 schema 补齐 ✅ **已实施并验收（2026-07-17，两波：主体 + horizon 接线 fixup）**

实际交付（全量 3,427 passed / 0 failed，+86 新测试）：
- `schemas/investment_intent.py`：`actionability` 加 `"recommendation"`；`IntentTargetPrice{value,currency,prior_value}`；
  `prior_direction` + `rating_action`；`conviction_source`（`derived_lookup` 明禁进 credibility）；
  `HORIZON_EXIT_TIERS{short:30, medium:90, long:180}` + `resolve_horizon_tier`（单一真相源，F4/F8 皆 import）。
  long=180 而非 365 是语料深度（~10 个月）妥协，须随数据积累上调。存量 JSON 零破坏（测试钉住）。
- `policy/global_base.py`：`_RECOMMENDATION_RULES` 独立规则表；**卖出评级黑洞已开**（bearish×7 delta 全部可执行，
  穷举测试钉死不进 review_required）；exit 按档位（long: -20%/+40%/180d）；honesty note 写明「跟随机构建议」。
- `policy/policy_mapper.py`（fixup 波）：`time_horizon_hint`/`actionability` 贯通 canonical 路径；
  `"unknown"` 在 mapper 归一为 None 保存量 flat 语义 bit-for-bit 不变。
- `backtest/per_action.py`：评估窗口按 tier 分档，`[window=Nd truncated]` 后缀标记（结构化字段是已认账的 schema gap）。
- `contracts.ts` + `check_contract_drift.py` REGISTRY 登记 4 条；顺手修了 TS enum 解析器的行内注释盲区。
- **所有权备案**：`src/finer_dashboard/src/components/audit/intent-card.tsx` 1 行（`recommendation` 补入
  exhaustive Record）系编译强制连带，验收判定保留。
- **附带影响**：存量 42 条 F5 action 在新窗口下结算结果会变（本就带 R7 旧偏置，放量前一并清理重跑）。

原计划表（留档）：

| 文件 | 变更 | 理由 |
|---|---|---|
| `src/finer/schemas/investment_intent.py:13-16` | `actionability` 加 `"recommendation"` | 见风险 R2 |
| 同上 | 加 `target_price` 槽位 | 见风险 R3 |
| 同上 | 加 `prior_direction` + `rating_action` | 研报自带前态，现被丢弃后事后反推 |
| 同上 | `conviction` 标注 `derived` | 查表值不得进 credibility |
| `src/finer/policy/global_base.py:64,70` | 为 `recommendation` 开分支 | 卖出评级黑洞（见 R4） |
| `src/finer/policy/global_base.py:342-344` | horizon-aware exit | **一号验收门**（见 R5） |
| `src/finer/backtest/per_action.py` | 按 `time_horizon_hint` 分档 | 同上 |

**F1 / F5 零改动。** F1 `standardization_router.py:95-99` 已路由 `.pdf` → `pdf_standardizer.py`（光栅化 `:604` + 429 backoff）。
F5 `action_composer.compose_trade_action` 签名不动。

### E2E 冒烟实录（2026-07-17，100 份 2025-09 研报，零源码修改）

漏斗：100 → F0 **100**（symlink/receipt/meta 日期全对）→ F1 **98**（2 份源 PDF 截断，优雅降级；
p50=20s，长尾=扫描件 OCR 37s/页 + CLSA 晨报合集 40-95 万字符单份 4-10 分钟）→ F1.5 装配 **35**（锚点驱动，无锚回退整文）
→ F2 **100** 跑完但 EntityAnchor 仅 **52%** → EvidenceSpan **62%**。**F5 硬门下可产 action 上限 ≈ 52%。**

三个放量前必修项（spec §8 未知数 #2/#3 就此关闭，替换为具体工单）：
1. **注册表覆盖**：`entity_registry` 仅 212 别名/95 ticker（KOL 策展），48% 研报无锚可用。
   解药：导入研报仓 `config/entities.yaml` 负规则 + 从其 metadata 挖 26k 条 company↔ticker 对。
2. **数字假阳性 ~10%**：UBS 电话 `+61-2-9324 2498` 被锚成 `2498.HK`。纯数字 alias 需上下文门。
3. **F1.5 依赖锚点**：注册表修好后自动改善；40-95 万字符合集整文进 F3 是 token 炸弹，需容量护栏。

另录：`pipeline-drive` 无渠道过滤参数且一跑就带 F5+settle——全量驱动前需加过滤或接受语义（工单）。
F2 单份 p50=0.77s 几乎免费，重跑全量無成本。

- **F0 边界**：`ingestion/orchestrator.py:44-49` 的 `F1_HANDOFF_SEAM` 由测试硬拦
  （`tests/test_bk1_feishu_nlm_f0.py:203-224`、`tests/test_feishu_f0_contract.py:139-158`）。
  **只搬研报仓的 filename parser（不开 PDF），不搬 extractor。**
- **不要移植 `rag_system` 提取器** —— 它是 F1 的劣质平行实现（无光栅化、无并发、
  `_is_image_pdf` **53.7% 假阳**、`_filter_garbled` 静默吃掉均值 3.1% 的纯数字表格行——正是金融数据）。
- **F2 纯收益**：显式 ticker 绕开实体锚定瓶颈（LLM 提议命中率仅 17.7%→18.6%）与 `sector_proxy` 伪 ticker hack。
  导入研报仓 `config/entities.yaml`（1,582 行，含 `NON_COMPANY_TICKERS` / `AMBIGUOUS_TEXT_TICKERS`(BP/GM/GE) 等**负规则**）。
- **F1.5 会被强制触发**：30 页 PDF 必过长内容路径（≥8 blocks 或 ≥2400 chars）。规则版 TopicRule 靠 F2 锚点驱动，
  研报有显式 ticker 理论上表现更好，**未验证**。
- **F7/F8 零社交耦合**：`KOLTimeline{kol_id: str}`、`build_timeline(kol_id)`，broker 原样嵌入。
- **前端**：`schemas/contract.py:8` + `contracts.ts:495` 必须同改（`check_contract_drift.py:41` 已注册 `SourceType`）。

## 4.9 首批机构 TradeAction 驱动实录（2026-07-17，Fix→Gate→Drive→Audit）

**F2 毒词修复**：歧义裸别名分层上下文门（判定/生成/加载/扫描四层，`entity_stoplist.is_ambiguous_broker_alias`
+ `requires_context` 标记 + 5 种显式 ticker 上下文放行）。8 毒词 212 锚点→**0**，锚定 97/121 文件、923 锚点，
独立门控抽检假阳性 5%（唯一残余：裸 `EW` 撞 MSCI OW/EW/UW 评级术语，已记工单）。3,548 测试零失败。

**驱动漏斗**：28 bri intent → grounding 桥命中 20（8 条诚实 skip：`.PA/.FP/.B/NSDQ` 后缀不在归一表或
envelope 确无该票锚点，不伪造）→ F4 映射 open 11 / reduce 5 / watch 4 → **F5 canonical 19 / partial 0 / rejected 1**
（pseudo_ticker）。落盘 `data/F5_executed/bri_broker_*_actions.json`（`bri_` 前缀隔离 regen 覆盖），
SQLite index 19 条对账一致，幂等重跑验证通过。`build_timeline('伯恩斯坦')` 冒烟 3 entries。
驱动脚本 `scripts/drive_broker_recommendations.py`，F3-F5 全程零 LLM。

**清点（9 券商 × 双向）**：bullish 10 / bearish 5 / neutral 4——卖出评级不进黑洞的实证（高盛 reduce 三七互娱、
瑞银 reduce Intel）。19/19 `canonical_trace_status="canonical"`、每条 21-40 个 evidence span 可回查原文、
时钟单调、`time_horizon=long_term` 15/19 + `max_holding_days=180`。

**审计留下的工单**：
1. 🟠 **honesty note 未落盘**：F4 risk_notes 生成了「Follows institutional recommendation」但 composer
   `build_action_metadata` 不搬运 risk_notes → F5 JSON 0 命中，诚实性只能靠 intent join 间接恢复。需 composer 补搬运。
2. 🟡 `time_horizon` 枚举漂移：4 条 watch 的 `TradeAction.time_horizon="review_required"`（holding_period
   词表经 `canonical_runner.py:950` 泄进 free-form 字段）。
3. 🟡 `intent_effective_at` 19/19 为 null（schema 合法；F2 无 `effective_trade_at` 时间锚可解析）。
4. 🟡 汇丰/BMO 有 action 但无 creator YAML（A3 已知 6 缺口之二）；裸 2 字母歧义别名（EW/ES/MA/SW）纳入 context gate。
5. ⏸ 放量前提：T3 覆盖 4,286 份中 4,255 份 no_f0——F0 只导入过 124 份，放量=F0 批量导入 + F1 全量驱动（实测 15.6s/份串行）。

## 4.95 首张券商记分卡（2026-07-18，F8 settle，独立审计 PASS）

19 条 bri action 定向结算（范围纪律：包装 `load_all_actions` 过滤，非 bri 的 168 条 PENDING 零波及，跑前后状态逐位比对）。
价格源 Yahoo chart（免 key，`data/cache/yahoo_prices/`），窗口 180d、止损 -20%/止盈 +40%（F4 hint）、0.3% 双边摩擦。

**结果：scanned 19 = verified 4 / failed 8 / 窗口未走完 2（END_OF_PERIOD 正确保持 PENDING）/ neutral 非方向 4 / no_data 1（LAZRQ 退市）。**

| 券商 | settled | W-L | 均值 | 亮点 |
|---|---|---|---|---|
| 瑞银 | 5 | 1-4 | −1.98% | 002475.SZ 除外全败，3 条止损出局 |
| 伯恩斯坦 | 2 | 1-1 | +12.54% | 002475.SZ +45.76%（27 天到目标价） |
| 汇丰 | 1 | 1-0 | +24.74% | **IBM bearish 空头赢**（297→223） |
| BMO | 1 | 1-0 | +20.77% | AEP time_exit |
| 花旗/高盛/杰富瑞 | 各 1 | 0-1 | ~−21% | 全部止损出局 |
| **合计** | **12** | **4-8（33%）** | **−0.27%** | |

审计铁证：4 条独立拉价重算 return bit-for-bit 一致；bearish 语义双向验证（IBM 空头跌=WIN ✓，INTC 空头涨触止损=FAIL ✓）；
无一条 30d 误窗；两条浮盈 bearish（000858.SZ +20.84%）未提前翻牌。
**统计学警示：n=12 是机器验证，不是券商结论**——样本来自「恰好有 F2 锚点」的切片，且 8 败中 5 条是 -20% 止损截断
（policy 参数效应，非纯观点错误）。放量后 n 数百才有发言权。

## 5. 关键决策

1. **采信 11.7% 而非 29%** —— 两个探针冲突（n=800 分层双库 vs n=55）。n=55 的 CI 覆盖不了这个差，
   且其样本偏 2026（该年确实 35.5%）。此裁决直接决定 token 预算。
2. **选 broker-as-creator（A）而非 reports-as-evidence（B）** —— B 是在瓶颈之外优化：
   它不产出任何 F5 TradeAction，F8 不动、晨星不动、吞吐仍是 0，却要先重建中文 FTS
   （研报仓 `database.py:85` 无 `tokenize=` → `MATCH '半导体'` **0 hits**，中文检索完全是死的）
   并在 F2 里新建一个 RAG 子系统（超出 `CLAUDE.md` 给 F2 的可调用清单）。
   **A 做完后 B 的一大半是免费的**（broker 立场本身就是最好的 evidence，且已在 F5 里）。
3. **F3 用声明式解析器（rating 关键词表 → direction），不走 LLM 推断** ——
   研报的 direction 是被**声明**的。顺带规避 `0e40f029` 刚修的 bearish 过提取（80%→2%）。
4. **token 先换成不可再生的中间产物**（OCR 全文 + P1 结构化 JSONL），schema 工作慢慢做。
   **token 7/24 过期，抽取结果不过期。** 这是本次唯一有时间压力的决策。

## 6. MiMo Burn Plan（7/24 到期）

| 优先级 | 任务 | 量 | token | 墙钟 |
|---|---|---|---|---|
| **1** | A0 正文抽取（text PDF） | 25,226 份 / ~506k 页 | **0**（pypdf） | 3–5 h |
| **2** | **T3 P1 结构化抽取**（rating/目标价/ticker） | ~9,890 份 × 1 页 | ~30M | **~1.7 h** |
| 3 | T2 image-PDF OCR | 3,339 份 / ~56k 页 | vision | ~4.9 h |
| 4 | T4 多实体抽取（宏观/行业） | 16,179 份 | ~8k tok/份 | ~3.4 h |
| ❌ | T5 全语料摘要 | ~900M tok | — | **不做**：摘要不是 TradeAction，无下游消费者 |

### T3 执行实录（2026-07-17）

- **reasoning 模型陷阱**：mimo-v2.5 隐藏思考 token 计入 `completion_tokens`，`max_tokens=1600` 被吃光致
  content 为空串（不报错，`tokens_out` 精确钉在 2×1600）。改 6000 后 json_ok 40%→100%。此坑适用于所有 MiMo 批量作业。
- **校准（30 份 seed=42，两轮）**：rating 93.3% / target_price 93.3% / 单份均值 4,159 tok / 延迟中位 24s。
- **evidence 空白过敏**：逐字匹配对 PDF 换行敏感，分层匹配（exact → `\s+` 折叠含全角）后 20%→76.7%。
- **第一轮大烧**（`--year all` 并发 32，与 2026 抽取并发）：**4,286/5,171 份成功**，json_ok 100%、
  rating 92.3%、target_price 85.9%、evidence_ok 81.4%（exact 629/normalized 2,860）、ticker_match 83.2%。
  实耗 **18,097,877 token**（单份 4,223，vs 校准预测偏差 1.5%），墙钟 102 分钟。
  产物：`rag_data/t3_structured/burn_all.jsonl`（4,286 行，零坏行）。
- **锁竞争**：写方大事务造成读方跳过 ~885 份（取正文阶段、零 token 损耗），待 2026 pipeline 退出后重跑同命令补扫。
- **基建**：`rag_system/structured_extract.py`（t3-v0.2）断点续传默认开、QuotaGuard 熔断（exit 3）、
  校准文件写保护；必须 `/opt/anaconda3/bin/python3`（默认 python3 缺 requests）+ 注入 `MIMO_API_KEY`。

**T3 是唯一被验证有明确增量的用法。** 已开真实 PDF 确认 P1 携带结构化字段：

```
大摩-微博（WB.US）    → p1: "Price Target US$7.50→US$6.60 / Bull US$11.10 / Bear US$6.10" + Overweight
伯恩斯坦-优步（UBER.US）→ p1: "Rating Outperform  Price Target UBER 110.00 USD"
大摩-哔哩哔哩（BILI.US）→ p1: "Stock Rating Overweight  Price target US$31.00  Up/downside 79"
```

### 出发前必修的 4 个 blocker

1. `/Volumes/NAMEZY/外资研报/rag_system/config.py:12` `MIMO_MODEL_CHEAP = "mimo-v2-omni"` → 实测 **400 Unsupported model**。摘要批次 dead on arrival。改 `mimo-v2.5`。
2. **vision registry 中毒**（`model_config.py:85`）：`mark_failed()` 在只有一个模型的 module-level 单例上是**永久性**的，`reset_failures()` **全仓零调用者**。第一个 429 后每个新 `LLMClient.from_registry()` 返回 `None` → `AttributeError` → 整个进程静默走 `ocr_failed` fallback。**批量跑必炸且不报错。**
3. `MIMO_VISION_BASE_URL` 未设 → 默认 `api.xiaomimimo.com`（`model_config.py:112`），而 `MIMO_API_KEY` 是 `tp-` 前缀 → **401**。现在能跑纯因 `.env` 设了 `MIMO_BASE_URL`。
4. **`usage` 无计量**：`LLMClient.chat()`（`client.py:205-213`）直接丢弃 `usage`，只有 `DeepSeekClient`（`deepseek_client.py:159`）抓且无人持久化。**无法计量则无法 pace。** 先落 JSONL、跑 100 份校准再外推。

## 7. 风险（按"会不会静默出错"排序）

| ID | 风险 | 级别 |
|---|---|---|
| **R5** | **30 天止损 vs 12 个月目标价**：`global_base.py:342-344` 硬编码 `-10%/+20%/30d`，`opinions.py:428` 拿 `return_pct > 0` 算赢。券商可信度分数 = 用 30 天噪声衡量 12 个月判断，**构造上的抛硬币渲染成自信数字，全程不报错**。 | 🔴 **一号验收门** |
| **R2** | `actionability` 中心断裂：`opinion` → 永远 `WATCH`（永不可回测）；`explicit_action`+`open` → **伪造分析师从未做过的开仓**。无第三条路。 | 🔴 |
| **R3** | `target_price` 无槽位：`intent_prompt.py:138` 禁止 F3 提，但 F4 也不产价格（`global_base.py:14-15` 纯定性），`ActionStep.target_price_low/high` 在 canonical 路径**从不被写**。 | 🔴 |
| **R1** | **静默蒸发**：`driver.py:282` `if file_type=="pdf" and "/raw/local/" in rp: return True` → `driver.py:450` `skipped_excluded += 1`，**无错误、无日志、报告"成功"**。归档到 `data/raw/local/` 则 28,565 份 100% 蒸发。 | 🔴 |
| **R6** | **分析师 vs 机构身份未解**：`creator_id` 是扁平字符串。`goldman_sachs` 把不同 desk 的矛盾判断合并成一个"KOL"并**凭空制造翻转**（正是 `stance_key_of` 为 sector proxy 防的病，KOL 粒度无等价护栏）；`goldman_zhang_wei` 又让样本量塌陷（`_CRED_PRIOR_K=4` / `_CRED_LOW_SAMPLE_N=5` 收缩把所有人钉在 ~68 先验）。**分析师还会跳槽。真实建模分叉，现无解。** | 🔴 |
| R7 | **F3 bearish 偏置**：live F5 仍持有旧的 80%-bearish 数据（guardrails 修到 2% 但数据没重跑）。接入 28k 研报前**必须先清那 42 条**，否则放大五个数量级。 | 🟠 |
| R8 | **外置盘依赖**：73GB 在 `/Volumes/NAMEZY`。`driver.py:225-230` 要求 `raw_path` 相对 `data_root` → 只能 symlink。**盘一拔 F1 全挂，且 F0 raw archive 不可变性保证作废**（哈希在，字节不在）。**必须显式决策。** | 🔴 |
| R9 | `kol_profile.py:229` `extra="ignore"` → 分析师姓名/研究所/sell-side flag 加进 YAML 会被**无警告丢弃**。 | 🟠 |
| R10 | `is_industry_report` **是反的**（`classify_reports.py:426` + `:518`），且只在关键词分支计算（分支 1-4 的 6,678 行硬编码 `False`），**已污染 `reports.db`**。实证：`摩根士丹利-中国股票策略`→`False`，`RBC-Raise PT to $26`→`True`。**删掉，不要用它做 triage。** | 🟠 |

## 7.5 验证结果（A0）

| 验证项 | 命令/方法 | 结果 |
|---|---|---|
| 队列现状 | `select count(*) from reports where year='2025' and text_length=0` | **20,249 全部待处理，已完成 0** —— 确认 `--year 2025` 从未跑过 |
| 抽取成功率（dry-run，只读） | n=200 随机样本，seed=42，pypdf | **97.0% 可抽取** / 1.5% image / 1.5% 异常 / 0 缺失 |
| 文本密度 | 同上 | 平均 **3,774 chars/page**，3,353 页 |
| 按券商 | 同上 | 瑞银 median 6,887 (image=0)、摩根大通 4,135 (0)、高盛 3,566 (1)、花旗 4,705 (0) —— 2025 全线 clean |
| 成功路径 | `pipeline.py --year 2025 --step 2 --max-files 5` | **5/5 成功，299 chunks**，2025 已提取 0 → 5 |
| 失败标记 | `--year 2026 --max-files 10`（队首全 image） | `-1` 计数 **0 → 10** ✅ |
| **死循环打破** | 再跑一次 `--year 2026 --max-files 10` | `-1` 计数 **10 → 20** ✅ **取到全新批次，非同一批** |
| 失败可见性 | `select ... where text_length=-1` | 可查到具体文件（全为高盛 2026-06-09，印证该年 47.1% image） |
| **全量完成（终态）** | `--year 2025 --step 2` 跑完，正常退出非中断 | **19,459 ok / 790 failed / 0 pending** |
| **队列清空** | `select count(*) where year='2025' and text_length=0` | **0** —— 死循环修复的终极证明 |
| 全量成功率 | 19,459 / 20,249 | **96.1%**（dry-run 预测 19,641，误差 0.9%） |
| 实测吞吐 | 全量 20,249 份 | ~57 份/分钟，总耗时约 **5.5h**（外置盘 IO 为瓶颈，非 CPU；MiMo 并发能力无关） |

### A0 终态收益

| 年份 | 总数 | 有正文 | 失败(-1) | 覆盖率 |
|---|---|---|---|---|
| 2025 | 20,249 | **19,459** | 790 | **96.1%** |
| 2026 | 5,820 | 267 | 20 | 4.6%（stall detector 阻塞） |
| **全库** | 26,069 | **19,726** | 810 | **75.7%**（原 1.02%） |

**零 token 消耗。** 全库正文覆盖率 **1.02% → 75.7%**；`chunks` **13,183 → 948,318**（72×，FTS 已可检索）；
`pragma integrity_check` = **ok**。为 T3 结构化抽取备好燃料。

#### 790 份 2025 失败的构成（日志分析）

| 类型 | 数量 | 判定 |
|---|---|---|
| pypdf 解析异常 | 174 | 其中 **157 份是 pypdf 自身 bug**（`unsupported operand for +: 'float' and 'IndirectObject'` — 未 resolve 间接对象），**非文件损坏** |
| 空文本 | 616 | 真 image PDF（占 2025 语料 3.0%），需 OCR |

**实测验证**：随机取 5 份 IndirectObject 失败文件用 **pdfplumber** 重试 → **5/5 成功**，各抽出 18k–36k chars。
失败集中于 Cantor Fitzgerald（某生产工具的 PDF 结构专门触发 pypdf 缺陷）。

**结论**：**157 份可零 token 救回**，只需换库。这独立印证了「不要移植 `rag_system` 提取器」——
它用 pypdf，而 finer `pdf_standardizer.py` 用 **pdfplumber**，在本语料上严格更强。
2026 待处理的 5,553 份大概率含同类假失败。

#### 🐛 本次引入的缺陷（待修）

`mark_report_extraction_failed(report_id, reason)` 接收 `reason` 参数但**从未持久化**；
`pipeline.py` 已传入（`"empty_text"` / 异常详情）却被丢弃 → 790 份失败无法从 DB 得知原因
（本次靠日志反推）。修法二选一：加 `extraction_error TEXT` 列（**schema 变更，需用户确认**），
或删除该参数以免伪装成已记录。

## 8. 未解决项

1. **MiMo 配额余额** —— 无计量 → 无法 pace。（blocker #4）
2. **F1 `pdf_standardizer` 在 26k 规模的吞吐/失败率** —— 最接近的 harness `scripts/backfill_f1_standardize.py` 并发默认 4，只跑过 **267** 条。**没有任何东西驱动过 10k+。**
3. **`evidence_span_ids` 能否在 OCR 版面上稳定产出** —— F5 硬门（`EmptyEvidenceSpanIdsError`），未验证。
4. **`conviction` 查表对 F8 结果的敏感度** —— sizing 由它决定，而它是编的。
5. **2,496 份 2026 文件对流水线不可见**（磁盘 8,316 / metadata 5,820），且这批最差（42.6% image）。完美运行也只到 91.3%。
6. **研报仓有 16 modified + 5 untracked、+1,446 insertions 未提交**（07-10/07-11，晚于 HANDOFF）：
   新 `lib/generation.py`、`lib/redline_watch.py`、3 个 validator，HANDOFF 一个都没提
   （自称在 Phase 3F，实际 `fb8343a Phase 3J`）。**有人做到一半走了，动之前必须先 reconcile。**
   其 P1 动作 `RAG_STEP2_2026_100` 状态 `blocked`（guard_fail=6），P2/P3 待确认已挂 11 天。

### 文档幽灵（会误导设计，应修正）

- **`ViewpointState` 在 Python 里不存在。** `AGENTS.md` 列它为 F7 core schema；`grep` 只命中 `errors/codes.py:310` 的错误串。
  真实 F7 状态是 `timeline/stance_snapshot.py` → `data/F7_timeline/stance_snapshots/{YYYY-MM-DD}.json`。
- **`F0IndexSchema.CONTENT_RECORDS_TABLE`（`f0_index.py:16-35`）无任何代码写入。** `F0IndexWriter` 写的是另一条链
  （`content_identities → source_groups → … → artifacts`）。**忽略 `CONTENT_RECORDS_COLUMNS`。**
- **memory 领先于本分支**：`next-optimization-directions.md:27` 称 `F0IndexWriter` 有 record_path 原子性门 ——
  `chore/quality-collar` 上不存在，在未合的 PR #8。`docs/specs/2026-07-13-*.md` **不存在**（全仓零命中）。

## 9. 结语

> **这件事变成陷阱的方式，不是它跑不起来，而是它跑起来了。**

一个工作的晨星看板、几千条 TradeAction、漂亮的可信度分数——全部建立在一个编出来的 `conviction`、
一个被迫说谎的 `actionability`、和一个拿 30 天秒表给 12 个月判断计时的退出规则上。**流水线不会报任何错。**

**先修 exit horizon 和 actionability，再放量。**
