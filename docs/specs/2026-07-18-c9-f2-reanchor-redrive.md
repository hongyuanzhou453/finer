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
| **① ticker/stoplist 修复** | `ticker_normalization` 补 NSDQ + 国际交易所后缀；`entity_stoplist` 把 MSCI OW/EW/UW/MP context-gate | **代码 + 单测，零数据变更**（✅ 已完成） |
| **② 重锚 dry-run** | 用①的代码对 broker envelope 重锚 dry-run，测真实 delta（实际解锁多少无锚、实际几条现有 target 变、evidence 覆盖预测） | **只读**，出报告给用户过目 |
| **③ 执行** | 备份 F2_anchored(broker) → 重锚写 evidence sidecar → 现有 1,773 就地更新 evidence(保 id) + 无锚 1,835 纯新增驱动 → 7 条 review | **数据变更**，备份 + dry-run 过目后 |

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

## 5. 未解决项 / 下阶段

- **Phase ②③ 未执行**（数据变更，待 dry-run 过目 + 用户 go）。
- **entity_registry_broker.yaml 未重生**：卡列其为 owning（再生成），但重生需盘上 reports.db（现未挂载）；stoplist 已运行期生效，ticker 后缀亦运行期生效，故 Phase ②③ 不阻塞。若要把新后缀/词表固化进 yaml，待盘挂载后单独重生（非 C9 主线阻塞项）。
- **国际后缀集可扩**：当前 16 交易所覆盖测得的高频后缀；Phase ② dry-run 会暴露还差哪些，按需补行。
