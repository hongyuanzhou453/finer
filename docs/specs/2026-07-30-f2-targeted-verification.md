# F2 定向实体验证（闭集） — P1 实施记录（2026-07-30）

> 依据：`docs/specs/2026-07-30-next-actions-plan.md` P1（用户已确认设计）。
> 所有数字为实测，口径标注在各节。

## 1. 概述

给 F2 补上一条**闭集**证据通路：对每条搁浅的 bri intent，只在它自己的信封正文里
核实 T3 已声明的那 1–2 个标的，命中则产出与注册表扫描同构的 `EntityAnchor` +
`EvidenceSpan`，未命中就保持搁浅、绝不伪造。

结果：2,503 条搁浅 intent 中 **1,057 条（42.2%）** 取得可审计证据，四轮独立精度
审计（共 200 条样本）确认最终配置**零假阳性**。

## 2. 为什么是闭集，而不是扫正文里的 ticker

开放集裸 ticker 扫描在真实券商语料上**已实测不安全**，三类批量假阳性：

| 模式 | 实例 |
|---|---|
| 点分法律实体缩写 | `Morgan Stanley C.T.V.M. S.A.` → 伪命中 `C.T` |
| PDF 乱序抽取残片 | `…sacinhceT NE.T MBS CEOOC yelroW…` → 伪命中 `NE.T` |
| 单双字母码 | `L.L`（27 次）、`P`（18 次）出自普通英文散文 |

**假锚点比缺锚点危害大得多**：它让 F5 产出「有证据支撑」的错误 action，直接污染
可审计性——而可审计性是本项目的立身之本。

闭集把候选集压到 1–2 个：T3 说了什么，就只验证那一件事（A3 声明式原则用到证据层）。

## 3. 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `src/finer/enrichment/targeted_anchor.py` | 新增 | 闭集验证核心；四道确定性上下文门 |
| `tests/test_targeted_anchor.py` | 新增 | 22 个单测，反例全部取自实测失败模式 |
| `scripts/backfill_targeted_anchors.py` | 新增 | dry-run 默认 / 精度抽样 / 增量并入 |
| `scripts/diagnose_no_occurrence_bucket.py` | 新增 | P1.5：未命中桶三层文本对照诊断 |

未改动任何既有 F2/F3/F5 代码路径；新增锚点与 span 全部带
`metadata.layer = "targeted_verification"`、confidence 0.9（低于注册表精确命中的
1.0），可按标记整体审计或回滚。

## 4. 上下文门与它们的来历

每一道门都对应一个**实测**的失败样本，不是预防性设计。

| 门 | 拒绝什么 | 来历 |
|---|---|---|
| 词边界 + 缩写链 | `C.T` in `C.T.V.M.`；`4091.T` in `14091.TW` | 语料实测 |
| 乱序窗口 | ±60 字符内 ≥2 个反转 token（`sacinhceT`/`ruE`） | 语料实测 |
| 免责声明块 | `disclaimer` / `免责声明` / `distributed in` … | 语料实测 |
| **覆盖名单（span 局部）** | `(ANF), (GOLF), (AS),` 式枚举，±120 字符内 ≥2 条 | **审计轮 1 抓到的 4/50 假阳性** |
| **交易所限定（正向）** | 裸字母码**只**认 `TSX: FTS` / `CP-TSX` / `NAVI US` | **P1.5 诊断** |

### 4.1 交易所限定门：为什么是「加正向模式」而不是「放宽负向门」

P1.5 诊断发现 8 条搁浅 intent 的代码字面就在正文里，全部栽在通用
`bare_alias_context_ok` 上。但**不能**直接放宽——`EUV` 那条暴露了真问题：T3 把
技术名词「极紫外光」抽成了 ticker，放宽会产生一个自信的假锚点。

看实际上下文，7 条合法命中与 1 条误抽的**唯一稳定差别**是交易所限定语法：

```
TSX: FTS   NYSE: BLCO   LSE: HTG   CP-TSX   GEI-TSX   BNTX-NSDQ   FTS CN
—— vs ——
"China built an EUV prototype in early 2025"        （无限定符）
```

所以加一条高精度**正向**接受条件，并把通用负向门从裸字母路径上撤掉。
回收 776 → 1,064（+37%），且裸代码专项审计 50/50 = 100%。

### 4.2 覆盖名单门：为什么必须是 span 局部

审计轮 1 抓到 4/50 假阳性，全是同一模式：唯一命中落在摩根大通的
`Explanation of Equity Research Ratings … Coverage Universe` 名单里——那份名单
列几十家不相干公司，命中它只证明该券商覆盖这只票，不证明本篇对它有观点。

第一版修法是把 `coverage universe` / `important disclosures` 加进整块词表。
**这是错的**，两个独立审计各自实测出同一后果：

- 每篇研报封面都印着 “see page N for analyst certification and important
  disclosures”，而 F1 的券商块常达数千字符、封面与披露同处一块；
- 整块拒 → 毁掉全篇最权威的那一块（标题 + 评级 + 目标价），实测毁 10 条封面
  锚点、召回 −18%；
- **精度增益为零**——那 4 条名单命中早已被交易所限定门拒了。

改为 span 局部（±120 字符窗口内 ≥2 条 `(代码),` 枚举）后：召回从 878 回到
1,057，名单门只花掉 7 条。括号内允许点号，覆盖 `(PETR3.SA),` 这条残留路径。

## 5. 精度审计（四轮，共 200 条样本）

审计由独立 agent 执行，两个正交视角（identity / evidence 或 identity / 对抗性
skeptic）分别判定，分歧交由第三方裁决并要求复核原文。

| 轮次 | 样本 | 配置 | 结果 |
|---|---|---|---|
| 1 | 50（全类） | 交易所门前 | 46/50 = **92%**，4 条覆盖名单假阳性 |
| 2 | 50（裸代码分层） | 交易所门后 | 50/50 = **100%** |
| 3 | 50（全类） | 块级词表版 | 50/50 = 100%（但指出块级词表 −18% 召回） |
| 4 | 50（全类） | 发车配置 | 50/50 = **100%** |

**轮 1 的价值不可替代：我差点在 92% 精度下发车。** 两个视角的分歧点正是缺陷所在
（identity 说「确实是这家公司」，evidence 说「但这是披露名单，不是观点」）。

轮 4 还提供了反向的一课：两个视角**一致**判 `CRH.N` 为假阳性，裁决方读原文后
**推翻**了它们——这篇报告的 `stock_code` 就是 `CRH.N`，正文 95 次提及、有专属的
`The Long View: CRH` 与 `Financials: CRH` 章节。命中确实落在
「Other Companies Mentioned」条目里，但那份名单列的是本篇自己覆盖的一组标的。
判定是「**锚点正确、引文位置不佳**」，不是精度失败。

一致的两票也可能一起错——所以裁决方必须回原文，不能只做投票汇总。

## 6. P1.5 — 未命中桶诊断

对 `no_occurrence` 桶抽样，把三层文本对照：F1 信封正文 / `pdftotext` 直抽原始
PDF / T3 声明。n=40，随机种子 3：

| 判定 | 占比 | 含义 |
|---|---|---|
| `image_only` | **87.5%** | PDF 文本层仅 66–81 字符——纯图片型研报 |
| `verified_elsewhere` | 10.0% | 字面在正文里，被上下文门拒（门的取舍） |
| `t3_hallucination` | **2.5%** | PDF 里确实没有——T3 抽取幻觉 |

两个直接结论：

1. **T3 数据可信**。幻觉率 2.5–3.3%（两次抽样一致），不构成对 T3 产物的信任问题。
2. **OCR 决策的收益侧有了硬数字**。剩余 1,214 条未命中里约 1,062 条卡在
   F1 没有文本层。

### 6.1 关键发现：视觉的钱已经付过了

对这 21 份图片型 PDF 逐一核对 T3 产物：**21/21 全部有记录**，且带真实视觉抽取
内容（`key_thesis` + `evidence_quotes`）。MiMo 视觉模型当初读懂了这些图片页。

但 T2 OCR 产物对同一批文件**零覆盖**（`ocr_log.jsonl` 里大量 `raster_failed`），
所以「复用现成 OCR 文本」这条路不存在。

这把 OCR 决策的问题从「值不值得花 token」改写成了「**F1 要不要接受视觉抽取作为
文本层**」——完全不同的一道题，留给 P4 决策，本轮不动。

## 7. 验证结果

```
pytest tests/test_targeted_anchor.py -q  →  23 passed
pytest tests/ -q                          →  exit 0（全绿）
backfill_targeted_anchors.py --execute    →  信封写回 1,044，新增锚点 1,044
```

漏斗（发车配置）：

| 状态 | 条数 |
|---|---|
| verified（已写回） | **1,044** |
| no_occurrence | 1,227 |
| symbol_not_normalizable | 210 |
| symbol_too_ambiguous | 22 |

上下文门拒绝分布：`bare_context` 13,750 / `boilerplate_block` 3,709 /
`abbreviation_chain` 1,788 / `coverage_roster` 1,701 / `scrambled_window` 88 /
`numeric_context` 35。

写回是**增量并入**：只加不改既有锚点与 span，按稳定 span id 去重（重跑幂等），
原子写（tmp+fsync+replace），改动前全量备份至
`data/F2_anchored.bak-20260730-233456-targeted-anchor`，审计 JSON 在写入**前**
以 `planned` 落盘、成功后翻 `applied`。

### 7.1 F4→F5 转化与三向审计

```
drive_broker_recommendations.py --execute
  →  F4 PolicyMappingResults persisted: 1044
  →  indexed actions: 1044          （零损耗：每条锚上的 intent 都成了 action）

scripts/audit_trace_integrity.py
  total F5 actions: 4577   fully intact: 4577
    intent_id  -> F3           : 4577/4577  (100.0%)
    policy_id  -> F4           : 4577/4577  (100.0%)
    evidence   -> F2 (all spans): 4577/4577 (100.0%)
                 span-level      : 124,988/124,988 (100.0%)
```

全语料 canonical action 从 3,533 增至 **4,577（+29.5%）**，审计闭环未破。

## 8. 已知缺口（不在本轮修）

**裸代码被兜底盖成美股 → 结算可能取错公司：149 条（写回集的 14.3%）。这是
settle 的阻断项。**

`normalize_broker_ticker` 对**任何**裸代码一律返回 `market="US"`。写回集里 598 条
是裸码，其中 149 条的正文交易所限定符明确指向别的市场：
`AC/CG/PD/SU/TD/BMO/ATRL←CN`（Bloomberg 的 CN = **加拿大**不是中国）、
`WGX/XRO←ASX`、`COLOB←CSE`。

危害不止「日历错了」，而是**取错公司**——同一个裸码在美股属于另一家公司：

| 裸码 | 研报实际标的（RBC 覆盖） | 美股同名 |
|---|---|---|
| `AC` | 加拿大航空（TSX） | Associated Capital（NYSE） |
| `CG` | Centerra Gold（TSX） | 凯雷集团（NASDAQ） |
| `PD` | Precision Drilling（TSX） | PagerDuty（NYSE） |

T3 对这批只给了代码、没给公司名（`target_name == target_symbol`），所以唯一的
身份证据就是正文里的交易所限定符。

- 锚点本身**是对的**（公司确实被提到），错的是继承来的市场戳；
- 这是**既有缺陷**：已结算的 999 条裸码 action 里 17 条（1.7%）同样中招，
  不是 P1 引入的，但 P1 把暴露面显著放大了；
- 本轮的处置：把交易所 token 记进 `metadata.occurrences[].exchange_hint`
  **留痕但不改** `resolved_symbol`——改 canonical 身份是数据迁移，需用户授权；
- **settle 在此项决策前不执行**：按错误公司结算会产出貌似合理的错误回测，
  正是本项目上周刚做过全语料修复的同一类污染。

### 8.0 修复方案（已备好，dry-run 完成，待授权）

`scripts/repair_bare_symbol_market.py`（默认只读）用 `exchange_hint` 确定性升级
`resolved_symbol`：405 个带 hint 的裸码符号中 **120 个可确定性升级**（其余 285 个
因无映射/hint 冲突/回解失败被跳过，宁缺勿滥），影响 **150 条 action**。

关键是 **已结算的受影响 action = 0**——因为 settle 一直没 `--apply`。所以这是
纯前向修正：不作废任何既有回测、不需要重结算、三代记分卡口径不受影响。

抽样逐字核对原文（5/5 全对，且每条都是真会取错公司的）：

| 代码 | 研报标的（正文限定符） | 美股同名 | 升级为 |
|---|---|---|---|
| `AC` | 加拿大航空 `TSX: AC` | Associated Capital | `AC.TO` |
| `ADM` | Admiral Group `LSE: ADM` | Archer-Daniels-Midland | `ADM.L` |
| `AMC` | Amcor `ASX: AMC` | AMC Entertainment | `AMC.AX` |
| `BC` | Brunello Cucinelli `BC IM` | Brunswick | `BC.MI` |
| `CG` | Centerra Gold `TSX: CG` | 凯雷集团 | `CG.TO` |

写回时保留 `resolved_symbol_before_repair` / `ticker_before_repair` 与
`repair_source`，全量备份，可回滚。

**不在本方案内**：已结算的 999 条裸码 action 里那 17 条（1.7%）是注册表锚点、
没有 hint，属独立课题。

### 8.1 交易所 token 集里的两字母词形码

`_EXCHANGE_TOKENS` 含 `IN`/`NA`/`NO`/`SS`/`SW`/`AU` 等与英文词撞车的彭博码，
表格里的 `NVDA IN LINE` 会被误读成「印度上市」。实测影响：

- **对精度无实害**：100 条裸码样本两轮审计零假阳性；仅靠这类 token 被接受的
  锚点共 64 条，且其 `resolved_symbol` 已自带正确后缀（`.ST`/`.AX`/`.SW`/`.HE`/
  `.TO`），与 hint 相互印证。
- **对统计有实害**：用松散 token 集统计「非美暴露」会虚高——我第一次量出
  15.2%/16.0%，改用严格集后是 14.3%（写回集）与 1.7%（已结算）。凡是拿 hint
  做统计的，必须用严格集。

**名单门误伤：13 条（1.2%）。** 为堵住轮 4 发现的「括号内带行情」写法
（`(AWI: $196.57, HOLD)`），把 `_ROSTER_ENTRY` 从「括号紧闭」放宽后，代价是 13 条
从 1,057 降到 1,044。裁决方指出其中至少 `CRH.N` 是正确锚点被误伤：它的 91 处
合法提及全是无限定符的裸写法（`The Long View: CRH`、估值表行），唯一带限定符的
那处恰好在名单里。

方向是**精度安全**的（宁可漏不可假），因此本轮接受这个代价。可选的召回补丁是
「按公司分节标题接受」——`^(The Long View|Financials|Investment Thesis)[:：]\s*<base>$`
这类券商分节表头在散文与披露文本里不会出现。但它是一条**新的接受路径**，需要
自己的精度审计，归入下一轮。

其余：图片型 PDF 的 F1 文本层缺口（§6.1，归 P4）；`symbol_not_normalizable`
210 条未做二次诊断。

## 9. 方法论记录

本轮延续「可检验性优先于产量」的排序，并新增一条经验：

> **我自己写的门，精度不能由我自己判。** 四轮独立审计里，第一轮就抓到了我会
> 放行的一整类假阳性；第二、三轮各自独立地否定了我的第一版修法，并给出了正确
> 的 span 局部方案。两次都是「中期正面信号」被更多证据推翻——与 07-30 记录的
> 同日三次单一切口错误同源。
