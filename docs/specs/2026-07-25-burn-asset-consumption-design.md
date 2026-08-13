# 烧录资产消费方案设计（8.89 亿 token → 产品）

> 基线：HEAD `1906d136`（定位转向对外收敛完成后）。
> 资产：`/Volumes/NAMEZY/外资研报/rag_data/burn_rescue_20260725/products/`，
> 12 类 / 103,832 条 / 8.89 亿 token（详见 `docs/specs/2026-07-21-mimo-token-burn-finale.md`）。

## 1. 概述

烧录产出的 12 类资产里，**只有 3 类在当前定位下有产品价值**。本设计诚实剔除其余，
并为这 3 类各给一条完整落地路径（数据契约 → 适配器 → schema → API → UI → 验证）。

核心判据是定位转向的那句话：**「不告诉你谁更准，让你查得清谁说过什么」**。
凡是需要「谁更准」才成立的用法，一律作废；凡是「谁说过什么」的记录与自洽性审计，全部保留。

---

## 2. 资产盘点与定位契合度

| 资产 | 记录数 | 定位契合 | 判定 |
|---|---|---|---|
| **T6 盈利预测**（estimates 含 raised/cut 方向） | 6,556 + r2 2,774 | ★★★ | **M1**：评级—预测口径背离检测（新审计能力） |
| **T7x 五票共识**（置信度分档） | 6,635 | ★★★ | **M2**：记录**抽取质量**标签（纯审计） |
| **T8 深度长摘要**（1500-2500 字结构化） | 2,597 + 2,535 | ★★★ | **M3**：/records 下钻的「他到底说了什么」 |
| T9 行业传导链 | 18,763 + r2 2,488 | ★★ | **M4 暂缓**（§7，非不做，是要先解决行业研报的信源归属） |
| T5 短摘要 | 25,753 | ★ | 已被 F1 正文覆盖，检索场景才需要，不单独立项 |
| T4 宏观多实体 | 19,428 | ★ | 同 T9，等 M4 一起处理 |
| T3 评级/目标价 | 6,636 | — | **已消费**（`broker_recommendation_adapter`，现役 5,852 条 bri intent） |
| T2 OCR | 3,017 | — | **已消费**（是 F1 正文的来源） |

### 2.1 被否的用法（写下来防止后续 agent 重新发明）

| 诱人但错误的用法 | 为什么错 |
|---|---|
| 用 T6 算「券商盈利预测准确率」→ 给券商排名 | 这就是被跨期检验否掉的前提（历史超额不预测未来超额）。预测准确率同理，未经检验不得作为能力指标 |
| 用 T7x 置信度做「信源可信度评分」 | T7x 衡量的是**我们的抽取有多确定**，不是**券商有多可信**。混淆二者是把管道质量伪装成信源质量 |
| 把 T6 的 estimate 冲突并入 CRD-4「言行不一」 | `credibility/divergence.py` 明写：券商只产零仓位承诺的 `recommendation`，**结构上不可能**言行不一。误并会把每家券商误告一遍 |
| 用 T8 深摘要生成「投资建议」 | 摘要是记录的呈现，不是二次推荐 |

---

## 3. M1：评级—预测口径背离检测（最高价值）

### 3.1 它是什么

同一份研报内部的**自洽性审计**：券商维持/上调评级，同时**下调**盈利预测（或反之）。

这不是「言行不一」（说 vs 做，CRD-4 的领域，券商结构上不适用），
而是**「口径背离」**（说 vs 说，同一份文档内两个声明互相拉扯）。它满足新定位的全部要求：

- 是**可被证据锚定的事实**：研报白纸黑字写着「维持买入」+「下调 2026E EPS 8%」
- **不需要任何预测性假设**：不问谁对谁错，只问这份文档自不自洽
- **用户能查证**：两侧都能下钻到 `evidence_quote` 原文

### 3.2 数据契约

输入：T6 JSONL（`t6-v0.1`）的 `extraction.estimates[]`

```json
{"metric":"eps","period":"12/26E","value":1.93,"action":"raised","change_pct":11}
```

`action` ∈ `raised|cut|unchanged|new|unknown`；**只有 `raised`/`cut` 参与判定**
（`unchanged`/`new`/`unknown` 一律不参与，同 CRD-4 第 3 条「只比明确方向」的保守纪律）。

与既有 bri intent 的 join：**`t6.filepath ↔ f0.metadata.source_filepath`**
（`broker_recommendation_adapter` 已验证的同一把 key），再经 `content_id → intent_id`。

**T6 与 T6r2 的合并**：r2 是 r1 中「json 失败 / 证据未命中 / 零 estimates」篇的大切片重抽，
**r2 优先、回退 r1**，按 `report_id` 去重。合并后有效篇数以实跑为准（勿凭估算写进代码注释）。

### 3.3 判定规则（保守优先，假阳性成本高）

一条 `RatingEstimateInconsistency` 成立需**同时**满足：

1. 该研报有 canonical bri intent，且 `direction` ∈ {`bullish`,`bearish`}（`neutral` 不参与）
2. 该研报 T6 抽取 `json_ok=true` 且 `evidence_ok=true`（证据未命中的不进）
3. 存在至少一条 `metric ∈ {eps, net_profit, revenue}` 且 `action ∈ {raised, cut}` 的 estimate
4. **方向冲突**：`direction=bullish` 且 estimate `action=cut`（或 `bearish` + `raised`）
5. 冲突的 estimate 有可下钻的 `evidence_quotes`（无证据不对外展示，同 CRD-4 §81 纪律）

**明确不判定的情形**（写死在代码里，附理由注释）：

- 目标价上调但盈利预测下调 → **不算背离**（估值倍数扩张是正当逻辑，不是矛盾）
- 评级 `maintain` + 预测微调（|change_pct| < 5） → 不算（噪声区间）
- 跨报告比较 → 不做。本模块**只看单份文档内部**，跨报告的立场变化是正常的改变主意

### 3.4 落地物

| 层 | 文件 | 内容 |
|---|---|---|
| Schema | `src/finer/schemas/broker_estimates.py`（新增） | `BrokerEstimate`（metric/period/value/action/change_pct/evidence_span_ids）、`RatingEstimateInconsistency`（双侧证据 + intent_id + report_id） |
| F3 适配 | `src/finer/extraction/broker_estimate_adapter.py`（新增） | T6 JSONL → `BrokerEstimate[]`，挂到既有 bri intent 的 sidecar（**不新建 intent**，不动 F5） |
| 审计 | `src/finer/credibility/rating_estimate_consistency.py`（新增） | 判定规则 §3.3；**独立于 `divergence.py`**，不共用 `DivergenceEvent` |
| API | `src/finer/api/routes/` 既有 broker 路由扩展 | `GET /api/broker/{id}/inconsistencies`；比率字段**必须带 `sufficiency`** |
| UI | `/records` 记录卡增设「口径背离」徽标 + 下钻 | 徽标只在证据双全时出现；文案禁止评价性措辞（「该报告内部口径不一致」，不是「该券商不靠谱」） |

### 3.5 红线检查

- [ ] 背离**计数**可直接展示；背离**率**必须走 `SampleSufficiency` + `display_policy`，`count_only` 时不渲染比率
- [ ] 不进任何排序键：不得出现「按背离率排名的券商榜」
- [ ] `signal_class` 保持 `broker_recommendation`，不与 `kol_statement` 混算
- [ ] 假阳性抽检：**上线前人工核对 30 条**，精度门 ≥95%（沿用 F2 定向验证的判据）

---

## 4. M2：记录抽取置信度标签

### 4.1 它是什么

T7x 对每条评级/目标价做了 5 票独立重抽投票，产出 `unanimous(5/5) / strong(4/5) / majority(3/5) / disputed(<3)`。

**语义边界（最重要的一条）**：这是「**我们把这条记录抽对的把握**」，
**不是**「这家券商有多可信」。它是**管道质量指标**，属于审计面，不属于信源评价面。

### 4.2 为什么值得做

/audit 目前能证明「这条 action 的证据链完整」，但不能回答
「这个『买入』真的是原文写的吗，还是抽取模型看花眼了」。T7x 正好补上这一格，
而且它对用户是**降低信任成本**的：明确标出 disputed 的少数条目，比假装全都精确更诚实。

### 4.3 落地物

| 层 | 内容 |
|---|---|
| Schema | `TradeAction` / intent metadata 增 `extraction_confidence`（`unanimous`/`strong`/`majority`/`disputed`）+ `extraction_votes`（`{rating: n, target: n}`）。**新增 Literal 需同步 `contracts.ts` 并过 `check_contract_drift.py`** |
| 回填 | `scripts/backfill_extraction_confidence.py`：join T7x JSONL → 现役 5,852 条 bri intent；**先备份**（沿用 C7/C9 的 `.bak-<ts>-<hash>` 约定） |
| API | 既有 audit / ticker 响应透传该字段 |
| UI | `/audit` 与 `/ticker` 逐行标签；`disputed` 醒目但**不删除**该记录（隐藏等于篡改记录） |

### 4.4 红线检查

- [ ] 字段命名必须含 `extraction_`，禁止叫 `confidence` / `reliability`（会被误读为信源可信度）
- [ ] 不得进任何信源级聚合或排序
- [ ] 文档与 UI tooltip 都要写明「这是抽取一致性，不是券商准确性」

---

## 5. M3：研报深摘要下钻

### 5.1 它是什么

T8 的 5,132 条 1500-2500 字结构化深摘要（核心观点 / 投资逻辑链 / 关键信息 / 与共识差异 /
关键数据明细 / 时间线与催化剂 / 风险提示 / 结论倾向），挂到 `/records` 的第三层下钻。

**这是「让你查得清谁说过什么」最直接的兑现**：用户现在查到一条记录只能看到
评级/目标价/标题，看不到「他凭什么这么说」。

### 5.2 覆盖诚实性（必须处理，否则是误导）

T8 只烧了 **2026 池 45% / 2025 池 13%**，绝大多数记录**没有**深摘要。

- 有摘要 → 展示
- 无摘要 → 明确显示「本报告未生成深摘要」，**不得**降级用 T5 短摘要冒充（两者结构与深度不同）
- 列表页**不得**按「有无深摘要」排序或筛选置顶——那会让覆盖偏差伪装成质量差异

### 5.3 落地物

| 层 | 内容 |
|---|---|
| 存储 | 深摘要按 `content_id` 落 `data/F1_standardized/{content_id}/deep_summary.json`（沿用 sidecar 惯例，不进 SQLite） |
| 适配 | `scripts/ingest_deep_summaries.py`：join `filepath ↔ source_filepath`，校验 8 个必需小节齐全（复用 T8 的 `validation.summary_ok`） |
| API | `GET /api/records/{content_id}/deep-summary`，未命中返回 Line F envelope（`fix_hint` 说明「该报告未在 T8 覆盖范围内」） |
| UI | `/records` 第三层下钻面板；顶部标注生成模型与日期（`mimo-v2.5` / 烧录日） |

### 5.4 红线检查

- [ ] 摘要页必须标注「由 LLM 从原文生成，非券商原文」+ 生成日期
- [ ] 数字类内容旁保留「以原文为准」提示（OCR/摘要的已知弱项是图表数据，见 `docs/mimo-integration-guide.md` §7）
- [ ] 覆盖率在页面上如实可见，不做隐藏

---

## 6. 实施顺序与工作量

| 序 | 模块 | 依赖 | 估算 | 产出可验证性 |
|---|---|---|---|---|
| 1 | **M2 置信度回填** | 无（纯 join + 字段） | 0.5 天 | `audit_trace_integrity.py` 仍 100%；drift 测试绿 |
| 2 | **M3 深摘要下钻** | 无 | 1 天 | 抽 10 条比对原文；覆盖率数字与 JSONL 一致 |
| 3 | **M1 口径背离** | M2（复用 join 管道） | 2-3 天 | 人工核对 30 条精度 ≥95%；背离计数可复现 |
| — | M4 行业资产 | 见 §7 | — | 暂缓 |

**先 M2/M3 后 M1** 的理由：前两个是纯增量展示（零判定逻辑、零假阳性风险），
能先把 join 管道跑通验证；M1 有判定规则和假阳性成本，放在管道已验证之后做。

每个模块的验证命令（沿用 CLAUDE.md §6）：

```bash
pytest tests/ -v && python scripts/audit_trace_integrity.py && python scripts/materialize_projections.py
```

前端改动另需：

```bash
cd src/finer_dashboard && npx tsc --noEmit && npm run build
```

---

## 7. M4 暂缓：行业/宏观资产（T9 + T4，21,251 + 19,428 条）

**不是没价值，是有一个前置问题没解**：行业研报**天然没有单一 ticker**（语料的 62% 属此类），
而当前消费面（`/ticker`、记录卡）全部以 ticker 为主键组织。

T9 的 `beneficiaries[]` 带 ticker，看起来能桥接——但那是**研报作者提到的受益标的**，
把它当成「该券商对该股的推荐」是**语义偷换**：提及 ≠ 评级。若直接接入，
会让一份行业研报凭空变出十几条个股观点，污染 `/ticker` 的共识计数。

**要先回答的设计问题**（下一轮）：行业观点在「记录终端」里是什么一等公民？
是 sector 级记录卡？还是个股页里单列的「行业研报提及」区（与个股评级严格分区）？
在这个问题有答案前，T9/T4 只做离线存档，不进消费面。

---

## 8. 不做什么

- **不新建 F5 TradeAction**：M1/M2/M3 全部是既有 intent/action 的 sidecar 增强，
  不碰 `action_composer` 单一构造点，不影响 2,604 条现役 action 与结算
- **不跑更多研报**：语料是静态档案，个股研报已吃掉 96-98%
  （见 `memory/broker-corpus-is-a-static-archive.md`）；剩余 T8 烧录只是提升**深摘要覆盖率**，
  与时效性无关，可用剩余 key 额度慢慢补
- **不做任何按新指标的信源排序**

---

## 9. 开放问题（需用户拍板）

1. **M1 的 UI 位置**：口径背离是 `/records` 的徽标（记录属性），还是 `/discover` 记录卡的一列（信源属性）？
   我的建议是**前者**——放信源卡会被读成对券商的评价，即使文案再中性。
2. **剩余 T8 烧录**（2025 池 17,664 / 2026 池 3,208）：是否用剩余 key 额度补齐？
   关掉 thinking 后成本约为原估算 1/5（`docs/mimo-integration-guide.md` §2），一个月窗口充裕。
   补齐能把深摘要覆盖率从 13%/45% 拉到接近全量，直接提升 M3 的价值。
3. **文档日期不一致**：本文件按系统日期记为 2026-07-25，但仓库 HEAD 与 `docs/specs/` 中
   最新文档均为 2026-08 月份。若以仓库时间线为准，请告知正确日期，我改文件名与标题。

---

# M2 实施记录（同日完成）

## 落地物

| 层 | 文件 | 说明 |
|---|---|---|
| 回填脚本 | `scripts/backfill_extraction_confidence.py`（新增） | dry-run 默认 / 自动备份 / 幂等 / 只 add 不改其他字节 |
| 数据 | `data/F3_intents/bri_*.json` 的 `metadata.extraction_confidence` | **5,849 条已写入**，备份 `data/F3_intents.bak-20260813T002618Z-m2-0647262e` |
| 前端契约 | `src/finer_dashboard/src/lib/contracts.ts` | `ExtractionConfidenceTier` / `ExtractionConfidence` / `readExtractionConfidence()` 类型守卫 |
| 漂移守卫 | `scripts/check_contract_drift.py` | `ExtractionConfidenceTier` 登记进 `UI_ONLY_TS_ENUMS` |
| UI | `src/finer_dashboard/src/components/audit/intent-card.tsx` | 非 unanimous 时渲染抽取一致性提示块 |

## 两处对原设计的修正（实施中发现，均已采纳）

1. **不新增 schema 字段，走 `intent.metadata`。**
   原设计写「`TradeAction`/intent 增一等公民字段 + contracts.ts + drift」。实际读码后确认
   `broker_recommendation_adapter` 的既有契约是「真实 intent 语义进槽位，sidecar 事实进 metadata」——
   抽取投票描述的是**我们的管道**，不是投资意图本身，属 sidecar。走 metadata 后
   **零 pydantic 变更、零 drift 风险**，且 `audit_assembler:114` 的 `intent.model_dump()`
   自动透传 → **API 层零改动**（已实测拿到 disputed 记录的完整字段）。

2. **UI 只标注非 unanimous（79 条 / 1.35%），unanimous 完全静默。**
   原设计写「逐行标签」。实测分布推翻了它：**unanimous 5,770 (98.65%) / strong 47 / majority 27 /
   disputed 5**。98.65% 的行显示「五票一致」是满屏噪音、零信息量；只在需要留意时出现才有价值。

## 验证结果（全部实测）

| 项 | 结果 |
|---|---|
| join 命中 | **5,849 / 5,852 = 99.9%**（3 条未命中，T7x 侧无对应记录） |
| 幂等性 | 重跑 → `already_current 5,849 / 待写入 0` |
| 三向引用审计 | **4,919 / 4,919 全 100%**（intent/policy/evidence 均无回归） |
| 全量测试 | **4,078 passed, 22 skipped** |
| 契约漂移 | ✓ 33 mapped enums in sync；`test_contract_drift.py` 8 passed |
| tsc / build | 均通过（build 23 页静态生成正常） |
| action 侧覆盖 | 前 800 条 trace 抽查：**bri 458/458 全部带标签**，非 broker action 0 条带（正确） |
| **UI 渲染目击** | 临时预览页喂三条真实 intent：disputed → 「抽取存疑」；strong → 「抽取 4/5 一致」；**unanimous → 完全不渲染**。验证后临时页已删除 |

## 现场发现（与 M2 无关，但值得记）

`/audit` 页的 `getAuditActions()` **不传 filter**，后端默认 `limit=100`，KOL 下拉与标的搜索
都是**客户端过滤已加载的这 100 条**。因此第 100 条之后的 action **无法经界面到达**
（本次为找一条非 unanimous 记录目击渲染时撞到）。这是既有产品限制，不在 M2 范围内，
建议后续独立处理（服务端过滤 + 分页，或加载量提升）。

## 回滚

```bash
rm -rf data/F3_intents && mv data/F3_intents.bak-20260813T002618Z-m2-0647262e data/F3_intents
```
（前端改动为纯增量渲染，无数据依赖；回滚数据后徽标自动消失。）

---

# M3 实施记录（同日完成）

## ⚠️ 落地面变更：从公开站 `/records` 改为 dashboard `/audit`

原设计写「挂到 `/records` 第三层下钻」+「`GET /api/records/{id}/deep-summary`」。实施时发现两处硬冲突：

1. **`/records` 在宣传站 `finer_site`，是静态导出 + 冻结快照**（`public/records-data/*.json`），**没有后端**，原 API 方案不成立。
2. **公开站已声明的边界**：`CreatorRecordView.RowDetail` 末尾写着「**公开快照只含结构化事实，不含研报原文**」。深摘要含大量原文数字与论点，放公开站等于对外发布第三方研报的实质内容，**触及版权与对外发布红线**。

因此 M3 落在 **dashboard `/audit`**（内部工作台，无对外发布风险），与 M2 同处一屏：查一条 action 时既看到证据链，也看到「这份研报当时说了什么」。**公开站的深摘要展示需要用户单独授权**（见开放问题）。

## 落地物

| 层 | 文件 | 说明 |
|---|---|---|
| 摄取 | `scripts/ingest_deep_summaries.py`（新增） | T8 JSONL → `data/deep_summaries/{report_id}.json` sidecar + `_index.json`；八小节质量门 |
| 数据 | `data/deep_summaries/` | **5,164 篇**（41MB，`data/` 已 gitignore）；2025:2,540 / 2026:2,624 |
| 后端 | `services/audit_assembler.py` `_load_deep_summary()` | 按 `intent.metadata.report_id` join（M2 同款，99.9% 命中）；未命中返回 None |
| 契约 | `contracts.ts` `DeepSummary` + `AuditTraceBundle.deep_summary` | 无新枚举，drift 无影响 |
| UI | `components/audit/deep-summary.tsx`（新增） | 折叠面板 + 极简 markdown 渲染（`##` 小节 / 列表 / `**粗体**`）；**免责声明常驻不折叠** |
| 测试 | `tests/test_audit_api.py` | 两处 bundle 键集断言加 `deep_summary` |

## 顺带修复：M3 曾整个不可达

`/audit` 的 `getAuditActions()` 不传 limit → 后端默认 `limit=100`，而左栏 KOL/标的筛选是**客户端过滤这 100 条**。broker 记录（唯一有深摘要的）**全部在第 100 条之后**，因此深摘要在界面上根本看不到。已改为显式请求 `limit=1000`（后端上限）。这也是 M2 记录时提到的同一个既有限制，现已解决；更彻底的服务端过滤+分页仍值得后续做。

## 补烧（用户授权使用 MiMo key）

`/records` 快照 4,587 条记录中仅 1,132 条（24.7%）有深摘要，故对**快照实际需要的 3,055 篇**做定向补烧（不是全池 2 万篇）：

- 工作副本建在**外置盘**而非 `/tmp`（吸取 7/24 清理事故），`worktools/` 零污染原仓
- `t8_deep_summary.py` 加 `--only-ids` 支持按需补烧
- **默认关闭 thinking**（`MIMO_KEEP_THINKING=1` 可恢复）
- 校准 10/10 通过，摘要中位 2,363 字，八小节齐全

**中断**：外置盘 NAMEZY 于验证阶段卸载，补烧在 round 1 中断（已入库 25 篇）。**本仓 `data/deep_summaries` 的 5,164 篇不受影响**；重新挂载后重跑 `worktools/m3_burn.sh` 即断点续传。

## 对 MiMo 指南的实测修正

关闭 thinking 的节省幅度**取决于真实输出长度，不是任务复杂度**：

| 任务 | out（思考开） | out（思考关） | 节省 |
|---|---|---|---|
| 简单分类 | 185 | 6 | -97% |
| 结构化抽取 | 1,310 | 140 | -89% |
| **长摘要（本轮 n=10）** | **2,462** | **1,503** | **仅 -39%** |

已回写 `docs/mimo-integration-guide.md` §2，避免后续 agent 按 89-97% 估算长输出作业。

## 验证结果（全部实测）

| 项 | 结果 |
|---|---|
| 摄取质量门 | 5,164 通过 / 3 failed_gate（缺必需小节） |
| 后端 join | 前 400 条 trace 抽查命中 12 条，payload 字段完整 |
| 全量测试 | **4,078 passed, 22 skipped**（修复 2 处键集断言后） |
| 三向引用审计 | **4,919 / 4,919 全 100%** |
| tsc / drift / build | 全部通过 |
| **UI 目击（有摘要）** | SK海力士（野村 2,812 字）：八小节渲染、粗体正常、目标价上调轨迹 KRW 1,250,000→1,560,000、逻辑链带具体数字；免责声明常驻 |
| **UI 目击（无摘要）** | 芯片ETF华夏：显示「本报告未生成深摘要（深摘要覆盖为部分覆盖，不代表该报告内容缺失）」 |

## 开放问题

1. **公开站是否展示深摘要**——涉及版权与对外发布红线，需明确授权；若做，还需决定是否只放脱敏后的结构化要点而非全文摘要。
2. **补烧续跑**——外置盘重新挂载后是否继续补齐那 3,030 篇（约 24M token，一两小时）。

---

# M1 实施记录（判定层完成；真实数据待外置盘）

## 状态：代码与纪律测试完成，**真实数据验证被阻塞**

外置盘 `/Volumes/NAMEZY` 在 M3 验证阶段卸载后未挂回，T6 产物（9,330 条盈利预测抽取）
不可达，`/tmp` 镜像也已被清理。因此本轮交付**不依赖数据的全部内容**，
盘挂回来后一条命令即可跑真实数据并做人工核对。

## 落地物

| 层 | 文件 | 说明 |
|---|---|---|
| 判定器 | `src/finer/credibility/rating_estimate_consistency.py`（新增） | 五道保守门 + 排除原因普查；**独立于 `divergence.py`**，不共用 `DivergenceEvent` |
| 测试 | `tests/test_rating_estimate_consistency.py`（新增） | **16 项，全绿**；重点测「每道排除门真的挡住了」而非只测正例 |
| 驱动 | `scripts/detect_rating_estimate_inconsistency.py`（新增） | r2 优先合并 → join → 判定 → 计数报告；dry-run 默认 |

## 判定纪律（与设计 §3.3 的差异已在代码注释中说明）

成立需**同时**满足：intent `direction` ∈ {bullish, bearish}；T6 `json_ok` 且
`evidence_ok`；至少一条 `metric ∈ {eps, net_profit, revenue}` 且 `action ∈ {raised, cut}`
且 **|change_pct| ≥ 5**；方向相悖（看多却下调 / 看空却上调）；有可下钻引文。

**对原设计的两处修正**：

1. **证据是报告级而非 estimate 级。** 原设计 §3.3 第 5 条写「冲突的 estimate 有可下钻的
   `evidence_quotes`」，但 T6 的 schema 里 `evidence_quotes` 是**顶层字段**
   （prompt 定义为「支持 estimates 或 valuation 结论的原文证据」），estimate 条目本身不带引文。
   实现改为：报告级引文 + `evidence_ok`（全部引文逐字命中）双重门。
2. **`change_pct` 缺失时不放行。** 原设计只说「微调不算」，未定义缺失情形。
   实现选择**宁可漏报**——幅度未知就无法证明超出噪声区间。

**明确不判定**（已写死并附理由）：目标价上调 + 盈利下调**不算背离**（估值倍数扩张是正当逻辑，
本模块根本不读 target_price）；跨报告不比（改变主意是正常的）。

## 红线执行情况

- ✅ 只出**计数**，不出比率——脚本不计算任何 rate，避免 `SampleSufficiency` 缺位下的越界
- ✅ 按信源分布打印时显式标注「计数，非比率，不构成排名」
- ✅ 不新建 F5 action，不碰 `action_composer`
- ⏳ **人工核对 30 条、精度门 ≥95%** —— 待数据可达后执行，**未过此门不得上 UI**

## 验证结果

| 项 | 结果 |
|---|---|
| 判定纪律测试 | **16 passed**（中性排除/非核心指标/未调整/微调/缺 change_pct/证据未锚/抽取失败/无引文/畸形条目/批量普查） |
| 全量测试 | **4,094 passed, 22 skipped** |
| 真实数据 | ⏳ 阻塞：外置盘未挂载 |

## 盘挂回来后的续跑

```bash
python scripts/detect_rating_estimate_inconsistency.py \
  --t6-dir /Volumes/NAMEZY/外资研报/rag_data/burn_rescue_20260725/products/t6_deep_equity
```

先看命中量与排除普查，人工核对 30 条（精度 ≥95%）后再 `--execute` 落盘、接 UI。
