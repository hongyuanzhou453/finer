# C9 follow-up · international ticker upside (F5 tradability gate + F2 anchor loader)

> 版本：v1.0 | 日期：2026-07-21 | 执行：Opus 4.8
> 上游：`docs/specs/2026-07-21-c9-additive-persist-dir-followup.md` §6（两处国际解锁 follow-up）

## 1. 概述（Overview）

上一 follow-up 断言国际解锁需两处扩展：**(2) F5 tradability 门认国际 shape** 和 **(1) envelope 侧锚点检测**。本轮实测把它精确化：

- **#2 已完成并落地**：F5 门改为「normalize 的 fixed-point」单一真相源 → 立即放行 **226 条** TW/JP action（0 拒），三向审计保持硬 100%（2141/2141）。
- **#1 根因被证伪并重定位、且已完整执行**：不是「锚定不检测」，而是**运行时 loader 的 `_VALID_MARKETS` 硬编码 `{US,CN,HK,TW,JP}`，在加载期静默丢弃 builder 已写入、ticker_normalization 已认可的所有国际市场条目（UK/FR/KR/…）**。用户拍板 **surgical append**（保留现 registry、只追加国际条目）→ loader 修复 + append +821 alias/329 ticker（0 冲突）+ ASX/SK 精度门控 + 重锚 1,819 envelope + 重驱动 → **新增 463 条国际 canonical action（0 拒）**，三向审计 **2604/2604 全 100%**（evidence span 85706/85706），FP 抽检 6/6 全真。

- **#1b Bloomberg 方言尾（二轮，已执行）**：`ticker_normalization` 加 24 行方言表（按发行人名核对交易所——`.SA`=巴西 B3、`.BR`=布鲁塞尔、`.S`/`.SS`/`.CN`/`.SE`/`.F` 因撞 Swiss/Shanghai/China/Saudi/衍生品脏码故意不加）+ 重建源 registry（pairs_code_rejected 430→237）+ append +291 alias/113 ticker + 重锚 1,356 + 重驱动 → **新增 136 条 canonical action（0 拒）**，审计 **2740/2740 全 100%**（span 89647/89647），FP 抽检 10/10 交易所全真。

broker action 累计 1,773 → **2,614**（bri 文件；总 F5 action 2,740）：#2 +16 US +226 TW/JP、#1 +463 国际、#1b +136 Bloomberg 尾。

## 2. 变更清单（Changes，已落地）

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/entity_registry.py` | 修改 | `matches_tradable_format` 改为 **fixed-point**：`symbol` 可交易 iff `normalize_broker_ticker(symbol).symbol == symbol`（已是 canonical 形）。删除硬编码 `_TRADABLE_SYMBOL_RE` 与死 `import re`。保留 `is_plausible_tradable_symbol` 的 registry-membership 分支（`BRK.B` 这类非归一 fixed-point 的注册符号仍放行）。 |
| `src/finer/enrichment/broker_entity_registry.py` | 修改 | `_VALID_MARKETS` 从 `ticker_normalization` 两张表的 market 并集**派生**（20 个市场），替代硬编码 5 个。loader 不再丢弃 builder 合法写入的国际条目。lazy/顶层 import 无环（ticker_normalization 无 finer 依赖）。 |
| `tests/test_sector_proxy.py` | 修改 | `TestPlausibleTradableSymbol` 加国际 accept 例（TW/T/L/PA/KS）+ 非归一 reject 例（`AAPL.JP`/`7203.SA`/`RY.TSX`/`600519.L`）。 |
| `tests/test_entity_registry_broker.py` | 修改 | `TestLoaderValidMarkets`：国际市场条目（SJP.L/UK、000660.KS/KR）加载成功、未知 market（XX）仍拒；`_VALID_MARKETS` 无漂移（等于两表并集）。`test_committed_registry_parses_clean` market 断言改用 `breg._VALID_MARKETS`（不再硬编码 5 市场）。 |
| `src/finer/enrichment/entity_stoplist.py` | 修改 | `AMBIGUOUS_BARE_UPPER_TOKENS` 加 `ASX`/`SK`（append 引入的裸歧义 alias：ASX=交易所/「ASX 200」指数、SK=SK 集团前缀/常见双字母，在 UK/IN 报告误锚）——context-gate，`.AX`/`.KS` 后缀孪生仍锚。 |
| `scripts/append_international_registry_entries.py` | 新增 | surgical append 工具：只追加国际市场条目（market ∉ 内地 5 集）、不改现有条目、保留 AUTO-GENERATED 头、dry-run 默认 + 执行前备份 target。 |
| `configs/entity_registry_broker.yaml` | 修改（committed config） | 两轮 append：#1 +821 国际 alias（4457→5278），#1b Bloomberg 尾 +291 alias（5278→5569）。0 冲突、现有条目全保留。备份 `.bak-…-3507f85c` / `.bak-…-ae3b966b`（移出 configs）。 |
| `src/finer/enrichment/ticker_normalization.py` | 修改（#1b） | `SUFFIX_NORMALIZATION_TABLE` 加 `TT`→TW、`JP`→T；`INTERNATIONAL_SUFFIX_TABLE` 加 22 行 Bloomberg 方言（TSX/NA/GR/GY/SM/IM/AU/IN 并入既有 canonical；SA/MX/TWO/BR/BB/OL/NO/CO/DC/JK/WA/BK/LS/NZ 新交易所）。交易所按发行人名核对，不按后缀字母猜。 |
| `tests/test_c9_ticker_stoplist.py` | 修改（#1b） | 24 例 Bloomberg 尾映射 + 6 例故意不加的 collision/脏码（.SS/.CN/.SE/.F/.S/.B）仍返回 None。 |

## 3. 架构影响（Architecture Impact）

- **两处 gate 现共享 ticker_normalization 单一真相源**：F5 tradability shape（entity_registry）与 F2 loader market allowlist（broker_entity_registry）都从归一表派生 → 加一行交易所自动放宽两处，无第二份后缀/市场清单可漂移（符合 CLAUDE.md「唯一真相源」）。
- **F5 门 blast radius（3 call sites，全 benign）**：`canonical_runner` 程序化门 + LLM 门（放行国际正是目的）、`sector_proxy` 配置校验（15 个现役 proxy fixed-point 全过，无回归）。
- **loader 改动当前 inert**：committed `entity_registry_broker.yaml` 只含 US/CN/HK/TW/JP，无国际条目，故 `_VALID_MARKETS` 扩展在重生 registry 前不改变任何锚定；full suite 3671 passed 佐证。

## 4. 关键决策（Key Decisions）

1. **fixed-point 而非扩正则**：把「可交易 shape」定义为归一函数的不动点，避免在 entity_registry 复制一份国际后缀正则（会与 ticker_normalization 漂移）。副带更正：`00051.SZ`（5 位畸形 SZ 码）旧正则 `\d{4,6}` 误放行、新门正确拒（真码是 `000051.SZ`）；`BUY/SELL/EPS` 等裸大写词旧门本就放行（shape 检查非语义，上游 registry/F3 负责语义）——非本次引入。
2. **`_VALID_MARKETS` 派生自表**：根因是 loader 与 builder/表三者市场集合不一致（builder 用表归一出 UK/FR/…，loader 只认 5 个 → 丢弃）。派生消除漂移。
3. **#1 只落 code、data op 留授权**：realize 需重生 committed registry（影响全部 F2 锚定）+ 重锚语料 + 重驱动，且重生有回归面（§6），属 CLAUDE.md「批量重建 + 改 committed 配置」红线 → 先出证明与计划，授权后执行。

## 5. 验证结果（Verification）

```
# #2 门改：全宇宙对拍（3125 符号 = 全 F3 target ∪ 全 F5 ticker ∪ registry）
新放行/旧拒（国际解锁）: 546（T/L/TW/PA/KS/NS/AX/…）
旧放行/新拒（回归）: 1（00051.SZ，畸形码，更正非回归）
对抗垃圾语料被新门放行: 0（BUY/SELL/EPS 旧门本就放行）
15 个 sector-proxy 配置符号: fixed-point 全过

# #2 落地：drive --execute（备份 F5.bak-…-c9-intl-gate-c61e61f1 先行）
grounding bridge matched 226 → F5 produced 226（canonical），rejected 0
三向审计 audit_trace_integrity: 2141/2141 fully intact，intent/policy/evidence 全 100%，span 73404/73404

# #1 完整执行（surgical append + 重锚 + 重驱动，备份先行）
append dry-run: +821 国际 alias / 329 ticker / 0 冲突（现有条目全保留）
loader 校验: SJP.L/UK、000660.KS/KR、BBVA.MC/ES 现加载；markets 20 个（KR/UK/FR/IN/AU/…）
ASX/SK 门控后再锚 3 envelope: 目标仍锚、spurious ASX.AX 消失
c9_reanchor_no_anchor_envelopes --execute: 1,819 processed / 0 failed / 463 would-bridge
drive --execute: grounding matched 463 → F5 produced 463（canonical）/ rejected 0
audit_trace_integrity: 2604/2604 fully intact, intent/policy/evidence 全 100%, span 85706/85706
FP 抽检 6 条: LVMH.PA/SASY.PA(Sanofi)/MAXI.BO/HIK.L/CNFH.NS/SMWH.L —— evidence 全对上公司名，0 假阳
备份: F2_anchored+F5_executed .bak-…-c9-additive-f779c4d9；registry .bak-…-intl-append-3507f85c

# 回归
pytest -q tests/  → 3671 passed, 72 skipped, 0 failed（loader/append 改动前）
targeted 后续: test_entity_registry_broker + entity_anchoring + stoplist + sector_proxy = 182 passed
```

## 6. #1 data operation（已执行 · surgical append）

用户拍板 **surgical append**（非整体重生）→ 已完整执行：

1. **loader 修复**：`_VALID_MARKETS` 从 ticker_normalization 两表派生（20 市场，含国际）。
2. **surgical append**：`scripts/build_broker_entity_registry.py --out <temp>`（读外置盘 reports.db，14s）→ `scripts/append_international_registry_entries.py --execute` 只把国际市场条目（market ∉ 内地 5 集）**追加**进 committed registry（+821 alias/329 ticker，0 冲突，现有条目全保留 → **不 drop 那 19 条 ADR 名**）。
3. **精度门控**：`ASX`/`SK` 加 stoplist（context-gate）——消除 append 引入的裸歧义 alias 误锚。
4. **重锚**：`c9_reanchor_no_anchor_envelopes.py --execute`（备份先行、ProcessPool 8、1,819 processed / 0 failed）。
5. **重驱动**：`drive_broker_recommendations.py --execute` → 463 国际 action（0 拒）+ evidence sidecar。
6. **审计**：`audit_trace_integrity.py` → 2604/2604 全 100%。FP 抽检 6/6 真。

**为何选 surgical append 而非整体重生**：整体重生会 drop 19 条现有 alias（ASML/Diageo/ADP/Aegon/Bunzl/Carnival/Ferrovial/Ipsen/Reckitt…，欧股美 ADR 名）——append-only 零回归。代价=committed registry 变「原始 + append」混合而非 builder 干净输出（AUTO-GENERATED 头保留，加一行 append 溯源注释）。

## 7. 未解决项 / 更远 follow-up

- **⚠️ 国际 action 的 market 字段 = intent 的 'US'（非交易所），828/828 条**：`bridge_target_symbol` 只把 `normalize_broker_ticker().symbol` 写回 intent，丢弃了 `.market`。ticker（工具身份）正确（EQNR.OL），但 `TargetInfo.market='US'` → `build_execution_timing` 的 `timezone_map` 只认 CN/HK/US，未知市场 fallback Asia/Shanghai → 现用 **US 日历代理**做国际股的 execution timing。**修复是耦合的**：需 (a) bridge 写回 normalized.market + (b) `timing_builder` 扩国际市场日历（Oslo/B3/…）——盲目只改 (a) 会 fallback 上海反而更糟。backtest 按 ticker 取价不受影响，仅 timing 日历是代理。**pre-existing，跨全部三轮国际 action**。
- **仍 no_anchor 的 1,220 条**：剩余 Bloomberg/exotic 方言（.S Swiss/.SS Sweden-Shanghai 撞/.CN Canada-China 撞/.SE Saudi 脏/.F 衍生品码/南非 .J·.JSE·.SJ 三形/单条冷门交易所）+ 报告正文未提 target 的 envelope + registry 未覆盖的 ticker。撞车的需先消歧（intent 市场标签 + 上下文）才能安全加。
- **append 引入的裸国际 alias 精度**：gate 了 ASX/SK；两轮其余裸短码（BBVA/GSK/LVMH/…/DSV/EDP/UCB）为独特公司码、低误锚，未逐条审计——可做一轮 ambiguous-international-bare-alias 精度扫。
- **ADR vs 本地上市身份**：部分公司同时有美股 ADR 与本地上市（ASML/ASML.AS）——抽检未见问题，但身份对齐是系统性隐患。
- **committed registry 状态**：现为 append 混合态（两轮追加）；日后整体重生需保留会被 drop 的 19 条 ADR 名（或先入 curated KOL registry）。
