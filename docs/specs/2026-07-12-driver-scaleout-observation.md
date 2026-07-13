# 增量驱动器放量前观测：F2 sector 代理取价 + F1.5 llm 方向稳定性（2026-07-12）

## 概述（Overview）

P1 #5/#6 落地后的两项线上指标观测。结论先行：**指标 #2（sector 代理 F8 取价）17/17 全通过**，12 个 researched 级 ETF 码实战校验完成；**驱动器当前无新语料可放量**（370 条扫描 368 条 legacy 身份，按设计跳过）；**指标 #1 经 llm 实测 A/B**：方向翻转率两模式均为 0，真正的收益是**长文召回 ~3 倍**（整文模式因 JSON 截断与证据退化严重有损），模式间 3 个方向冲突 target 列为人工判读观察项。测试期间发现 GLM-5.1 订阅失效（需人工处理），mimo/qwen 降级链在 `FINER_LLM_TIMEOUT=240` 下可用。

## 指标 #2：sector 代理 ETF 实战取价 — ✅ 17/17

`configs/sector_proxies.yaml` 全部 17 个 instrument（16 板块）经 `backtest/yahoo_prices.fetch_daily_closes`（range=3mo）实拉：

```
17/17 price-resolvable，各 62 个交易日，最新收盘 2026-07-10
含全部 12 个 researched 级码（518880 黄金 / 512880 证券 / 512660 军工 /
513180 恒生科技 / 562500 机器人 / 159819 人工智能 / 512690 酒 / 515790 光伏 /
159755 电池 / 159992 创新药 / 516160 新能源 + priority-2 的 515880）
```

`.SH→.SS` 映射与 `.SZ` 直通均验证。sector 代理 action 一旦产出，F8 取价通路无障碍；「researched 级码待复核」的风险降级为已消除（价格层可解析 + 代码↔名称此前已在 eastmoney 核验）。

## 驱动器放量盘点 — 无新语料，机制在位

`drive_once(dry_run=True)` 实测：

```
scanned: 370, skipped_legacy_identity: 368 (cnt_ 前缀、无 F0 ContentRecord),
skipped_excluded: 1, failures: 1 (f8f70a…: stage_status ready 但 F0_intake 无记录),
f1/f2/f5_ran: 0
```

- 驱动器只消化身份契约下的新导入内容；368 条 legacy 是刻意跳过（legacy 批量重建属需用户确认的红线，驱动器不越权）。**「导入一条新内容→自动 F1→F1.5→F2→F5→F8」的验证要等下一次真实导入**。
- 故障隔离正常：1 条坏账本行进 failures 不阻塞批次。
- 遗留数据不一致 ×1：`f8f70a474225400c240af9013c29dbe7` 的 stage_status 与 F0_intake 不符，待人工核对（不影响其他内容）。

## 指标 #1：F1.5 llm 模式方向稳定性 A/B

### LLM 通路现状（观测的前置发现）

- **GLM-5.1（SVIPS）订阅失效**：`500 SUBSCRIPTION_NOT_FOUND — No active subscription found for this group`。F3 llm 模式主模型不可用，需人工续订/换组。
- mimo-v2.5 / qwen-plus 在默认 60s 超时下对 10-24k 字 envelope 全部超时；`FINER_LLM_TIMEOUT=240` 后可用（单次共识 3-run ≈ 195s）。**建议**：llm 跑批时显式设置 `FINER_LLM_TIMEOUT`（默认 60s 对长文档不现实）。
- 冒烟（local_15c7 整文共识）：4 intents kept（GOOGL/INTC bullish、ENERGY_STORAGE bearish、PDD mixed，均 2/3 票），2 vetoed；`ENERGY_STORAGE:bearish` 正是落地后会代理映射 159566.SZ 的板块观点。

### A/B 设计

2 个真实长 envelope（local_15c7 ~16 块、local_8463 18 块/24.3k 字）× F15 {off, auto} × 2 独立重复，llm 共识提取（3-run 投票）。稳定性信号取自共识票据：kept 全票率（3/3 vs 2/3）、veto 数、contested（多空分裂）veto 数、重复间方向翻转与出现闪烁。

### 结果（2026-07-12，mimo/qwen 降级链，FINER_LLM_TIMEOUT=240）

| envelope | 模式 | kept stances（rep1/rep2） | 全票率 | veto（contested） | 重复间方向翻转 | JSON 解析失败 | 时延/次 |
|---|---|---|---|---|---|---|---|
| local_15c7（~16 块） | F15 off | **1 / 1** | 0%→100% | 2(0) / 3(0) | 0 | 2 次（截断） | 129-370s |
| local_15c7 | F15 on | **7 / 9** | 71% / 78% | 8(4) / 7(2) | 0 | 0 | ~9.5min |
| local_8463（18 块 24.3k 字） | F15 off | **5 / 7** | 100% / 57% | 1(0) / 0 | 0 | 0 | 148-168s |
| local_8463 | F15 on | **19 / 20** | 79% / 80% | 8(2) / 8(3) | 0 | 0 | ~9.3min |

**1. 方向翻转率：两模式均为 0**（重复间无任何同 target 方向反转）。共识投票本身已压制采样翻转，F1.5 不劣化方向稳定性；kept stance 的全票率（3/3）on 模式稳定在 71-80%。

**2. 真正的发现是召回：长文整文 llm 提取严重有损**。local_15c7 整文两次都只活下 **1 条** stance（GOOGL），而按 topic 提取出 7-9 条（含储能 bearish、9992.HK、美团等）；local_8463 从 5-7 → 19-20 条。根因可直接观察：整文模式两次 JSON 截断解析失败（24k 字文档要求单次输出全部 intent）+ validator `evidence_not_verbatim` 大量拒绝（整文引用退化）；按 topic 后单次输出小而聚焦，零解析失败。**F1.5 的按 topic 提取在长内容上约 3 倍召回，且新增 stance 均过了 per-topic 3-run 多数票。**

**3. 模式间方向冲突（3/8 共享 target）——观察项，需人工判读**：
- `GOOGL`：off 稳定 bullish，on rep1 被 contested veto、rep2 bearish。这是 2026-07-05 live smoke 就记录过的著名 contested target（内容本身两面表述），F1.5 不为真实歧义捏造稳定性。
- `000001.SH`：off 两次 bullish，on 两次 bearish——上证指数评述散布全文，孤立 topic 上下文与整文语境读出相反方向，是「上下文范围敏感」的典型案例（index/宏观类 topic 或需更宽上下文窗）。
- `601899.SH`：off bearish vs on rep1 bullish（rep2 缺席）。
- 板块观点跨 envelope 复现正确：储能在 15c7 读 bearish、在 8463 读 bullish，与既往 F3 落盘的多空对一致。

**4. 成本**：on 模式 ~9-10 分钟/envelope（约 30 次 LLM 调用 vs 整文 3 次）。身份组上限（FINER_F15_MAX_TOPICS=12）+ 长度阈值控制上界；放量跑批需预算此时延。

## 未解决项（Open Issues）

1. **GLM-5.1 订阅失效** → 人工处理；处理前 llm 模式靠 mimo/qwen 降级链（可用但慢）。
2. `FINER_LLM_TIMEOUT` 默认 60s 对长文档共识不现实——llm 跑批必须显式设置（本次 240s）；考虑调高默认或入驱动器启动配置。
3. **上下文范围敏感 target**（000001.SH 类指数/宏观评述）：孤立 topic 与整文语境可读出相反方向，3/8 共享 target 模式间冲突需人工判读；候选方案——index/宏观类 topic 组附带邻近上下文块，或此类 target 保持整文提取。
4. legacy 语料（368 条）是否迁移到新身份契约，等用户决策（红线）。
5. `f8f70a…` 账本/文件不一致待人工核对。
6. A/B 样本小（2 envelope × 2 rep）：结论方向明确（召回 3 倍、翻转 0），置信区间靠放量后的线上观测收窄。
