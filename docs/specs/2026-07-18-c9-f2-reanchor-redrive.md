# C9 · AUD-4 F2 收口 + 全量重锚 + 重驱动（混合方案）

> 版本：v1.0 | 日期：2026-07-18（跨零点 07-19 起）| 执行：Opus 4.8
> 上游任务卡：`docs/specs/2026-07-18-phase0-activation-task-cards.md` §C9 · 决策 D4-①
> 依赖：C7（1,773 bri action + F4）/ C8（三向审计量化出 evidence 6.6% 缺口）

## 0. 混合方案的由来（决策 + 实测）

任务卡假设 19 条 bri，live 实为 **1,773 条**（scorecard 放量），其中 **1,099 条已结算**。C9 的重驱动会撞上这批，核心是 id 语义：**就地更新(保 id) vs 强制重生(换 id→孤立 1,099 结算)**。实测把方向锁死：

- **(a) 就地的软肋 = 7 条**：现有 1,773 条里只有 7 条 target 会被 C9 修复改动（5×EW + 2×MP，MSCI 评级词误匹配）；后缀新增只影响之前没匹配上的输入，不动已解析 target。
- **纯新增上行 = 550~1,400 条**：1,835 条 no_anchor_match 里，550 条命中 C9 明确后缀集，~1,400 条带任意交易所后缀 → 修好后出**全新** action（新 id，无孤立）。

结论：**混合方案** —— 现有 1,773 走 (a) 就地（保 1,099 结算）、无锚 1,835 走纯新增、7 条评级误匹配列 review。强制重生 (b) 是「为修 7 条而孤立 1,099」，错。

## 1. 三阶段计划

| 阶段 | 内容 | 安全边界 |
|------|------|---------|
| **① ticker/stoplist 修复** | `ticker_normalization` 补 NSDQ + 国际交易所后缀；`entity_stoplist` 把 MSCI OW/EW/UW/MP context-gate | **代码 + 单测，零数据变更**（✅ 已完成 `e727407c`） |
| **② 重锚 dry-run** | 用①的代码对 broker envelope 重锚 dry-run，测真实 delta | ✅ 已完成（打脸修正：见 §6） |
| **③ 执行（收 A+C+D，B 转 follow-up）** | 备份 → 重锚 1,773 existing-action envelope + **grounded** evidence 就地更新(保 id) → 7 条评级词核对 → C8 复审+门槛收紧 | ✅ 已完成（数据变更，备份先行、小样本验证过） |

**② dry-run 的打脸修正（重要）**：intent 侧估计新增 1,341 条，但真实重锚后**只 13% 匹配 → ~238 条，且全是 TW/JP**。根因：**entity 锚定不「检测」PDF 正文的国际 ticker 提及**——①的 `normalize_broker_ticker` 只帮 intent 侧 bridge，envelope 侧不产出国际锚点。故国际解锁 ≈0（要 realize 得单独扩锚定检测）。**用户拍板 C9 收在 evidence（A+C+D），additive(~238 TW/JP)+ 国际解锁列独立 follow-up。**

**关键：C9 全程不需要外置盘。** 重锚读 F1 envelope（内置盘）+ broker registry（内置盘），不碰 raw PDF（那是 F1，已完成）。stoplist 在 `broker_entity_registry.py` 加载期以 `is_ambiguous_broker_alias` 并集应用（防御式，defense-in-depth）→ 改 stoplist **无需重生 yaml**（重生 yaml 才需盘上的 reports.db）。

## 2. 变更清单（Phase ①，已完成）

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/enrichment/ticker_normalization.py` | 修改 | `SUFFIX_NORMALIZATION_TABLE` 加 `NSDQ→US`；新增 `INTERNATIONAL_SUFFIX_TABLE`（16 交易所：London/Paris/Amsterdam/XETRA/Swiss/Milan/Madrid/Stockholm/Helsinki/ASX/Toronto=alpha，KOSPI/KOSDAQ/SGX/Bursa/India=alnum）；`base_kind` 守护（欧洲 alpha、亚洲 alnum → `600519.L` 这类错配码仍拒）；Bloomberg 变体并入 Reuters canonical（.FP→.PA、.LN→.L） |
| `src/finer/enrichment/entity_stoplist.py` | 修改 | `AMBIGUOUS_BARE_UPPER_TOKENS` 加 OW/EW/UW/MP（context-gate，非删除——MP Materials / EW Edwards 是真票，有 ticker 上下文才锚） |
| `tests/test_c9_ticker_stoplist.py` | 新增 | 22 例：NSDQ、国际 alpha/alnum 交易所、Bloomberg 变体合并、base_kind 拒错配、评级词 context-gate、真票不 gate |
| `tests/test_entity_registry_broker.py` | 修改 | `test_rejects_unmappable` 参数：`005930.KS` 现合法映射（移除）→ 换 `600519.SW`（Swiss alpha-only 拒数字基） |

## 3. 关键决策（Phase ①）

1. **国际后缀 base_kind 守护**：欧洲交易所用 alpha ticker、亚洲用 numeric/alphanumeric 码。`600519.L`（上海码+伦敦后缀）这类错配必须仍拒 → alpha 交易所拒数字基。既扩覆盖又不引假阳性。
2. **Bloomberg 变体并入 Reuters canonical**：`.FP`(Bloomberg 法国) 与 `.PA`(Reuters) 同一股票 → 都 canonical 成 `.PA`，让 intent target 与 anchor 合并（driver bridge 要的就是一致）。
3. **评级词 context-gate 不删除**：OW/EW/UW/MP 与真票（MP Materials、EW Edwards）碰撞，故 gate（需 ticker 上下文才锚）而非从注册表删，兼顾「不漏真票」与「不锚裸评级词」。
4. **stoplist 运行期生效、无需重生 yaml**：`broker_entity_registry.py` 加载期并集应用 `is_ambiguous_broker_alias`（防御式），故改词表即生效 → 避开重生 yaml 的外置盘依赖。

## 4. 验证（Phase ①）

- 新增/改动测试：`pytest tests/test_c9_ticker_stoplist.py tests/test_entity_registry_broker.py tests/test_entity_anchoring.py` → **159 passed**。
- 全量：`pytest -q` → **3716 passed, 22 skipped**。
- 手验：`MC.FP`/`MC.PA`→`MC.PA`(FR)、`BP.L`(UK)、`005930.KS`(KR)、`AAPL.NSDQ`(US)、`600519.L`→None；`is_ambiguous('EW'/'OW'/'UW'/'MP')`=True、`('AAPL')`=False。

## 5. Phase ③ 执行结果（A+C+D）

新增工具 `scripts/c9_evidence_reanchor.py`（dry-run 默认，--execute 先备份 F2_anchored + F5_executed；ThreadPool 并发重锚；per-envelope 文件写不重叠）：

- **A · 就地 evidence 修复**：重锚 1,773 existing-action envelope（`build_f2_deterministic_envelope`，用①的修复）→ 每条 action 的 evidence_span_ids **换成 grounded 子集**（只留提到 target 的 span，替代原「整包 envelope span」的过宽做法，修 C8 质量注记）→ 写 sidecar。**1,773 更新、0 失败、0 空 evidence、63,600 grounded sidecar（35.9/env）**；trade_action_id/policy_id **全保留** → 1,099 结算不孤立。备份 `F5_executed.bak-20260720-131259-c9-reanchor-c19b1971`（C9 前干净 F5 = 更早的 `-d73b25ff` 小样本备份）。
- **C · 7 条评级词核对**：MP/EW **都是真票**（MP Materials / Edwards Lifesciences）。重锚后 7 条**全部仍锚**（有 ticker 上下文，EW 组共锚 ABT/BSX = 心脏/医疗器械同业 = 真 Edwards）→ **均合法，无需隔离**。stoplist 的价值是防**未来**裸 EW/MP 误匹配 + gate 无上下文者。
- **D · C8 复审 + 门槛收紧**：`audit_trace_integrity` → **evidence 6.6%→100%**（fully-intact 136→**1,899/1,899**，span-level 64,105/64,105）；假阳性抽检：1,773 条里 25 条(1.41%)target 撞停用词，但 NOW/HE/SE/KEY/IQ/COO/EW/MP 皆真票，实际 FP «5%。C8 测试门槛 `EVIDENCE_MIN` 0.05→**1.0**（硬回归门）。

**C9 验收全达成**：evidence 覆盖 100%（≥80%）/ C8 bri 完整率 100% / 假阳性 ≤5% / pytest 绿。

## 6. 未解决项 / follow-up

- **additive（~238 TW/JP）转独立 follow-up**：需先补 `drive_broker_recommendations` 的 `persist_dir`（现不写 sidecar = 当初 evidence 全断的根因）+ 重锚 no_anchor envelope，否则新 action 无 sidecar 会破 C8 100%。这本身值一张小卡（根治 sidecar 根因 + 出 238 新 action）。
- **国际解锁 follow-up**：需扩 entity 锚定去**检测** PDF 正文的国际 ticker 提及（我的①后缀正确但 envelope 侧不产出国际锚点）。~1,000 条上行在此。
- **entity_registry_broker.yaml 未重生**：stoplist/ticker 已运行期生效，不阻塞；固化进 yaml 待外置盘挂载后单独做。
- **63,600 sidecar 文件量**：grounded 已比整包（~192k）少 3×；仍是大量小文件（data/ gitignore）。
