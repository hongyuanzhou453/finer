# MiMo Token 过期前收尾烧录编排（2026-07-21）

## 概述

MiMo token 将于 **2026-07-24 23:59 过期**。本任务盘点了外资研报仓（local_rrepo 镜像）三条烧录线的实时进度，并部署了一条**自动接棒编排链**（`mimo_burn_finale.sh`），在现役 key1/key2 双链烧完 T2 OCR 后自动补齐 T3/T4 结构化抽取、pending 解锁与残余 OCR，预计 **7/22 深夜全部完成**，比截止线提前约 2 天。

## 现状盘点（2026-07-21 20:40 实测）

| 线 | 池子定义 | 池子大小 | 已完成 | 剩余 | 已烧 token |
|---|---|---|---|---|---|
| T2 OCR (image PDF) | `text_length=-1` | 动态 | 2,409 份（ok 2,361 / raster_failed 104） | 2026≈258 + 2025≈334 | **1.72 亿** |
| T3 单票结构化 | `text>0 AND stock_code!=''` | 6,369 | 5,357 (json_ok 100%) | ~1,012（随 T2 解锁增长） | 2,266 万 |
| T4 宏观/行业结构化 | `text>0 AND stock_code=''` | 18,293 | 17,032 (json_ok 100%) | ~1,261（随 T2 解锁增长） | **1.145 亿** |
| pending（从未尝试正文抽取） | `text_length=0/null` | — | — | 2026:1,054 + 2025:7（零 token 解锁） | 0 |

合计已烧约 **3.1 亿 token**（不含 finer 侧 F1 scaleup）。剩余计划烧约 **5,000–7,000 万**。

现役进程（另一会话 3400c72c 启动，OS 级驻留）：
- key1 链：`STAGE SWEEP401`（已完成，429 熔断退出、剩 381 当时）→ `STAGE T2_2026` 循环（batch 150 / 并发 16，b011 时 pool_left≈258，预计 7/21 23:30 前烧完）
- key2 链：`t2_stager --year 2025`（batch 100 / 并发 3，pool_left≈334，约 4h/批，预计 7/22 上午烧完）

关键判断：T3 sweep5 的「配额耗尽（429×15）」是 **T2 并发 16 抢占同 key 触发的限流，不是 quota 真死**——同 key 的 T2 批次在其后持续成功（b008–b011 全 ok）。

## 变更清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `<scratchpad-609a>/mimo_burn_finale.sh` | 新增 | 收尾编排链（详下），nohup 脱离会话驻留，pid 48751 |
| `<scratchpad-609a>/burn_finale.log` | 新增 | 编排链主日志（各 stage 起止、rc、最终统计） |
| `<scratchpad-609a>/finale_{t3,t4}_{r1,final}.log` 等 | 新增 | 各阶段子日志 |
| `docs/specs/2026-07-21-mimo-token-burn-finale.md` | 新增 | 本文档 |

`<scratchpad-609a>` = `/private/tmp/claude-501/-Users-zhouhongyuan-Desktop-finer/609aa862-00f9-4c98-a8fc-0570aa223579/scratchpad`
`local_rrepo` = `/private/tmp/claude-501/-Users-zhouhongyuan-Desktop-finer/3400c72c-120b-4132-8541-a5584d9f33cd/scratchpad/local_rrepo`（外资研报仓本地镜像，规避外置盘 IO 与 SQLite 锁）

**未改任何 finer 源码 / 未动 NAMEZY 保护文件 / 未动 .env。**

## 编排链设计（mimo_burn_finale.sh）

```
Stage0 等 key1 T2_2026 链退出（pgrep 三模式轮询，120s）
Stage1 T3 补烧   structured_extract --year all --n 0 --budget 6000 --concurrency 16（断点续传）
Stage2 T4 补烧   t4_multi_entity_extract --limit 0 --budget 20000 --concurrency 16
Stage3 等 key2 T2_2025 trickle 退出（避免与 pipeline 写写冲突）
Stage4 pipeline --step 2 解锁 pending（零 token，2026 全量 + 2025 全量，独占 DB 写方）
Stage5 残余 T2 OCR（pipeline 新标 -1 的 image PDF，t2_stager 循环至 rc=0，2026→2025）
Stage6 最终 T3/T4 补烧（吃掉 Stage4/5 新解锁正文；budget 4000/8000）
收尾   JSONL ok 计数 + DB 三态统计写入日志，touch burn_finale.DONE
```

保护机制：断点续传幂等（`json_ok=true` 跳过）；`exit 3`（QuotaGuard 熔断）即停后续 LLM 阶段但仍跑零 token 阶段；**2026-07-24 22:30 硬截止**（每个 stage 与每轮等待都检查）；t2 循环重试上限 30；lockdir 防双开；key 只从 env 读绝不打印。

## 时间规划

| 时间 | 事件 |
|---|---|
| 7/21 ~23:30 | key1 T2_2026 烧完（剩 ~258/批 150）→ Stage1/2 自动接棒 |
| 7/22 凌晨 ~02:00 | T3 补烧（~1h）+ T4 补烧（~1.5h）完成 |
| 7/22 上午 ~10:00 | key2 T2_2025 trickle 烧完 → Stage4 pipeline 解锁 1,061 pending（~25min，零 token） |
| 7/22 下午 | Stage5 残余 OCR（估 350–450 份 image PDF，并发 16，~3–4h） |
| 7/22 深夜 | Stage6 最终 T3/T4 补烧完成 → `burn_finale.DONE` |
| 7/23–7/24 | **富余窗口**（约 2 天）：可选 T5 摘要大烧（见未解决项） |
| 7/24 22:30 | 编排链硬截止（token 23:59 过期） |

监控：`tail -f <scratchpad-609a>/burn_finale.log`；完成标志 `burn_finale.DONE`。

## 关键决策

1. **接棒而非重建**：现役双链（另一会话构建）只烧到 T2 结束即停，无人接棒 T3/T4 补烧与 pending 解锁——本链只补空档，不动现役进程，不重复烧（断点续传保证幂等）。
2. **pipeline 等 key2 drain 再跑**：pipeline step2 与 t2_stager 都是 DB 写方，SQLite 单写者，写写并存会锁风暴——宁可 key1 空闲数小时也串行。
3. **429 判读**：无并发争抢时 429×15 = quota 真死（实测并发 64 零 429），此时熔断止损是正确行为；有 T2 并发争抢时的 429 不代表 quota 死。
4. **run_summaries.py 不纳入主计划**：串行老工具（batch 10 + delay），24s/篇 reasoning 延迟下全量需 160h+，赶不上截止；如要烧需先改造并发版（见未解决项）。
5. **`local rc=$?` 陷阱规避、`--max-tokens ≥6000` reasoning 陷阱**等纪律沿用 T3 大烧基建结论。

## 验证结果

- 编排链启动实测：pid 48751 存活，日志正确进入 `Stage-wait[key1-T2-2026]` 等待态。
- 现役链健康：b011 批 `ocr_ok=150 ocr_fail=0`（19:20），pdftoppm 渲染进程活跃（b012 进行中）。
- 数字核验：T3/T4 JSONL 逐行解析计数 + DB `busy_timeout=15000` 只读查询，均与 stager 日志 `cum_ok/pool_left` 交叉一致。
- 附带发现并处理：`.env` line 37 `BBDOWN_COOKIE` 未加引号导致 `source .env` 中途 syntax error（MIMO_API_KEY 在其前不受影响）；报错曾把 cookie 打进 launcher 日志，**已清除**。

## T5 全库摘要大烧（2026-07-21 22:24 追加，用户已拍板）

**新工具 `local_rrepo/rag_system/t5_summarize.py`（t5-v0.1）**——`run_summaries.py` 的并发替代品。旧工具在 mimo-v2.5 上有三处致命问题：`SUMMARY_MAX_TOKENS=800` 必被 reasoning 思考 token 吃光产出空摘要（不报错）、串行 24s/篇全量需 160h+、每篇塞 15 万字符全文（池子正文中位数 50,002 字符，成本失控）。

设计：池子 = `text_length>0 AND has_summary=0`（25,011 份）；头 10k + 尾 2k 切片（T3 已实证评级/目标价在正文头部）；复用 T3 的 LLMCaller（max_tokens 6000）/QuotaGuard/断点续传 + T4 的 patient db_query；只读 DB、输出 JSONL 不写库；**全量按 date DESC 烧**（quota 中途死也优先保住最新研报）；摘要校验 = 非空 + 含 `## 核心观点` + finish_reason=stop，不合格严令重试 1 次。

**校准实测（30 份 seed=42）**：summary_ok **30/30**、零重试、finish_stop 100%；单篇均值 **5,253 token**、延迟 13.8s；两篇人工抽读（高盛阳光电源个股篇 + TD Cowen 行业篇）结构/评级/目标价/数字全对，行业篇正确写「未提及」不硬编。**全池外推 ≈1.31 亿 token，并发 24 约 4.2h 墙钟**。

排程（`t5_burn_launcher.sh`，nohup pid 51867）：
- **R1 主烧**：等 finale 链进入「等 key2」空闲窗口（预计 7/22 ~01:00，key1 无 LLM 负载）开烧全池，conc 20，与 key2 的 conc-3 OCR 写方共存；兜底 7/22 06:00 强制开跑。
- **R2 补烧**：等 `burn_finale.DONE`（残余 OCR 解锁的增量正文），conc 24；兜底 7/23 18:00。
- 保护：7/24 23:30 后不再启动；exit 3 后 JSONL 零增长连续 2 次判 quota 真死停手；完成标志 `t5_burn.DONE`。

## 第二轮价值烧录 T6/T7/T9（2026-07-22 17:31 追加，第一轮收官后 token 仍剩约一半）

**第一轮收官实绩（7/22 09:30）**：T3 6,636 / T4 19,428 / T5 25,752（130M token）全部完成；正文覆盖 26,019、失败仅 50（0.2%）、pending 清零。

第二轮三个新烧点（共享 runner `rag_system/t_burn_runner.py`，从 T5 主循环抽取），按价值优先级串行（quota 中途死也先保高价值资产），链 `t6t7t9_burn_chain.sh`（pid 84644）：

| 工具 | 池子 | 抽什么（与 T3/T4 零重复） | 校准实测 | 外推 |
|---|---|---|---|---|
| `t6_deep_equity_extract.py` (t6-v0.1) | 单票 6,632 | **盈利预测数字**（指标×期间×上调/下调幅度）+ 估值方法参数 + 催化剂时间窗 + 风险 + beat/miss —— 券商预测 vs 实际 = 信源可信度终端核心可回测资产 | json_ok 96.7%→修 max_tokens 10000（6000 截断根因）；86% 篇有 estimates、引文命中 92.6%；瑞银特斯拉篇人工核对全对 | ~76M token / conc24 约 5h |
| `t7_consensus_verify.py` (t7-v0.1) | T3 json_ok 6,631 | T3 评级/目标价 **2 次独立重抽（中英双 prompt+温差）+ 三票多数投票**，rating 归一五档、目标价 0.5% 容差 —— CRD 审计线置信度原料 | verify_ok 100%；**rating 三票全一致 100%、T3 在多数派 100%**、target 全一致 95% | ~48M / 约 1.6h |
| `t9_sector_deep_extract.py` (t9-v0.1) | 宏观/行业 19,387 | 产业链**传导逻辑**（driver→affected）+ 受益/受损标的（conviction 分档，ticker 仅原文出现才填）+ 景气方向 + 主题时间窗 + 政策依赖 —— sector proxy / F7 timeline 原料 | json_ok 100%、chains 100%、**ticker grounding 100%（零幻觉）**、引文命中 76.7% | ~132M / 约 8h |

合计计划 ≈2.56 亿 token；预计 **7/23 早 ~07:30 收官**。保护同前：断点续传幂等、exit 3+零增长×2 判 quota 真死全链停、7/24 23:30 硬截止。完成标志 `t6t7t9_burn.DONE`，日志 `t6t7t9_burn.log` + `burn_t{6,7,9}.log`。

## 第三轮价值烧录（2026-07-22 20:26 追加，用户拍板三项）

链 `round3_burn_chain.sh`（pid 14981）等 `t6t7t9_burn.DONE` 自动接棒（兜底 7/23 14:00 强制开跑）。顺序按**资产完整性优先**（quota 中途死也先修已交付资产）：

| 序 | 阶段 | 内容 | 校准/验证 | 预估 |
|---|---|---|---|---|
| S1 | **t6-r2 存疑重烧**（③） | T6 r1 中 json 失败/证据未命中/零 estimates 的篇，切片 10k+4k → **16k+6k**，独立落盘 `burn_t6_r2.jsonl` | smoke 2 份通过；存疑池筛选逻辑实测（r1 中途快照已识别 1,934 份） | 估 ~2-2.5k 份 / ~30M / ~1.5h |
| S2 | **t7x 五票升级**（②） | T7 三票 + 2 次新重抽（run C 中文变体 temp0.6 / run D 数据核对 temp0.2），**三票存疑篇排最前**；rating/target 置信度分档 unanimous(5/5)/strong(4/5)/majority(3/5)/disputed | 校准 10/10：rating 五票全一致 10/10、target 9 全一致+1 strong | 6.6k 份 / ~48M / ~1.7h |
| S3 | **t9-r2 存疑重烧**（③） | T9 r1 中 json 失败/证据未命中/零受益标的 的篇，切片 10k → **16k**，独立落盘 `burn_t9_r2.jsonl` | 复用 t6-r2 同款机制 | 估 ~5-8k 份 / ~50-80M / ~3h |
| S4 | **t8 深度长摘要**（①） | 2026 年全池（5,820 份）1500-2500 字深摘要：投资逻辑链/共识差异/关键数据明细(8-15个数字)/时间线催化剂/结论倾向；切片 16k+4k、max_tokens 12000；独立于 T5 不覆盖 | 校准 **15/15 全对**、零重试、中位 2,581 字、8.65k token/篇 | ~50M / ~2.9h |

新增工具：`t8_deep_summary.py` (t8-v0.1)、`t7x_five_votes.py` (t7x-v0.1)；`t6/t9` 增 `--head-chars/--tail-chars/--slice-chars/--suspect-from` 参数（默认值不变，r1 行为零影响）。合计 ≈1.8-2.1 亿 token，预计 **7/23 下午 ~17:00 收官**。踩坑记录：`global` 声明必须放函数首行（argparse default 先引用了模块常量），t6/t9 首版编辑 SyntaxError 已修（运行中的 r1 进程不受影响——Python 导入时已整体加载）。完成标志 `round3_burn.DONE`，日志 `round3_burn.log` + `burn_{t6r2,t7x,t9r2,t8}.log`。

## 429 限流补丁 + key1 耗尽 + key3 单车道终局链（2026-07-23 追加）

**429 补丁（7/22 22:06）**：T7 短调用（~20s×2）请求率比 T6（60s 思考重）高 3-4 倍，撞 RPM 突发限流：每 attempt 只 +43 条即熔断×6 轮。给 `structured_extract.LLMCaller.call` 加 429 退避重试（2/4/8/16/30s×5，401/402 真配额不重试直接进 QuotaGuard）——attempt 7 立即 +2,235 条（50 倍）。T5 昨夜反复 rc=3 同根因。

**key1 耗尽（7/23 07:56）**：round2 收官实绩 T6 6,556（61.1M）/ T7 6,507/6,633（48.2M）/ T9 18,603/19,387（122.6M），T9 连续 2 attempt 零进度判 quota 真死——**非限流，是 plan 用尽**（背书：backoff 在场仍 +0）。round3 链 08:06 醒来即判死跳过全部（t6r2/t7x/t9r2/t8 全 SKIP），且进程未落 `round3_burn.DONE` 即退出（收尾统计后崩，无碍——数据都在）。catchup 链因此永等，已于 7/23 20:36 kill（连同 key3 v1 链），运行中的 t6r2 python 保留。

**key3 单车道终局链（7/23 20:37，用户提供新 plan key，要求用完）**：key 落 `mimo_key3.env`（600 权限，不进 ps/日志）。`key3_burn_chain_v2.sh`（pid 87882）价值序 + 最大烧点垫底当排水阀：S0 等/续 t6r2（存疑池实测 **2,772** 份）→ S1 T7 尾巴(~130) → S2 T9 尾巴(~780) → S3 t7x 五票(6.6k) → S4 t9r2 存疑重烧 → S5 t8-2026(5.8k) → S6 **t8-2025(~19.9k, ~170M, 排水阀)**。

## key3 极限并行冲刺（7/23 20:42，用户告知 key 仅剩 ~3h，要求并行尽快用完）

**串行改并行**：3h 窗口下串行链自杀，拆 5 车道并行（不同输出文件零冲突，API 限流由 429 退避自动调度成服务端上限）。`parallel_burn_3h.sh`（deadline 23:50）：A t6r2 / B T7尾→t7x / C T9尾→t9r2 / D t8-2026 / E t8-2025。每车道循环重试，quota-strikes 提 30 防重并发下 429 竞争误判。**关键教训**：run_burn 里单条 http_error 只记不阻断→全 future 处理完 rc=0 会漏掉被 429 打穿的记录（T7 6,518 vs 池 6,631 差 113）；补 `gap_sweeper.sh`（每 12min 扫 rc=0 阶段的缺口 resume）。

**key 死亡（7/24 00:28）**：四车道 44 秒内同步熔断——非错峰限流，是 plan 配额触顶。deadline 后 `afterburner.sh` 延长烧录（**v1 因 macOS bash3.2 不支持 `declare -A` + set -u 启动即死，已改 `afterburner2.sh` 用 `eval` 动态变量**）。AB2 两轮探针每阶段零进度→7 阶段全判 dead→00:11 收官。

**3h 并行冲刺战果（AB2-FINAL 全文件总账）**：本轮 key3 实烧 **≈9,100 万 token（~24M/h，单车道历史吞吐 1.6 倍）**，七文件累计存量 **2.62 亿 token**：
| 文件 | 记录 | 累计 token |
|---|---|---|
| burn_t6_r2 (盈利预测存疑重烧) | 1,783 | 19.65M |
| burn_t7 (共识复核) | 6,650 ✅完整 | 49.21M |
| burn_t9 (行业深抽) | 18,763 | 123.68M |
| burn_t7_5votes (五票) | 1,122 | 8.79M |
| burn_t9_r2 (传导链存疑重烧) | 1,820 | 15.20M |
| burn_t8 (2026深摘要) | 2,597 | 23.29M |
| burn_t8_2025 (2025深摘要) | 2,529 | 22.32M |

**死因确诊 + 复活监视器（7/24 01:14）**：单请求 concurrency1+10s 间隔仍 **429 `type:limitation`**（非 401）→ 排除「高并发打穿限流」。初判 plan 配额触顶。`revival_monitor.sh` 每 8min 单请求探针。

**⚠️ 重大更正：429 不是永久死亡，是滚动窗口配额（约 70min 周期）。** 01:38 探针即恢复 200（距 00:28 触顶 ~70min）→ 证明「00:28 四车道同步熔断=key 死」的结论**错误**，实际是**当期滚动窗口配额用尽、下期自动恢复**。key 到 **04:24 仍返回 200 "Hello!"**，远超用户 20:42 说的「~3h 到期」（那是模糊估计）。**处置策略因此反转：MiMo 持续 429 `type:limitation` 应「等下一个窗口」而非「放弃」；只有单请求跨越 >100min（超一个窗口周期）持续非 200 才是真死。**

复活监视器演进：v1(conc3,大池优先) → **v2(conc4,小缺口优先**——先补完 t6r2/t7x/t9r2 让审计资产 100%，t8 大池垫底排水) → **v3(`revival_monitor3.sh` pid 5828，烧到真死**：HARD_END 推到 20:00 兜底 + 连续 13 次(≈104min>窗口周期)非 200 才判永久死亡收官)。**每个滚动窗口开就按小缺口优先烧一轮，窗口关等 8min 重探。**

**已补完**：t6r2 存疑重烧 **2,774 全量 100%**（04:23，+991）。截至 04:25 七文件累计 **2.73 亿 token**（REVIVE-FINAL）。v3 继续吃 t7x/t9r2/t8-2026/t8-2025 缺口直到 key 真死。监控 `revival.log`。

## ⚠️ /tmp 清理事故与产物抢救（2026-07-25）

**事故**：烧录全程在 `/private/tmp/claude-501/.../scratchpad/local_rrepo`（外资研报仓临时镜像）中进行。2026-07-24 13:33 起 macOS /tmp 清理 + 磁盘 95% 满，**删除了镜像里的 `rag_data/reports.db`（4GB）及 `rag_system/` 多个模块**（config.py / database.py / pipeline.py / t4_multi_entity_extract.py / mimo_client.py）。此后所有烧录阶段抛 `sqlite3.OperationalError: unable to open database file`，在监视器日志里表现为 **rc=1 空转刷屏**——`rc=1 ≠ 限流，是进程崩溃`，v4 监视器缺少「rc=1 连续无进展即停」的判据，空转到 20:00 兜底才退出。**真正的烧录终止时间是 7/24 13:34，不是 key 耗尽。**

**抢救（7/25 14:58）**：JSONL 产物与新建工具幸存，全量复制到 `/Volumes/NAMEZY/外资研报/rag_data/burn_rescue_20260725/`（**零覆盖**，新建目录 + README.md 说明恢复路径）。校验：12 个产物文件逐行 JSON 解析，**坏行 0**，行数与终账逐一吻合。`tools/` 里的 t5–t9 系列 + `t_burn_runner.py` + 打了 429 补丁的 `structured_extract.py` **此前是唯一副本**。

**最终成果（抢救副本重算）：8.89 亿 token / 103,832 条记录 / 12 类资产**

| 资产 | 记录 | token | 完成度 |
|---|---|---|---|
| T2 OCR | 3,017 | 2.18 亿 | image PDF 池 |
| T3 评级/目标价 | 6,636 | 2,818 万 | ✅ 100% |
| T4 宏观/行业多实体 | 19,428 | 1.31 亿 | ✅ 100% |
| T5 短摘要 | 25,753 | 1.30 亿 | ✅ 全量 |
| T6 盈利预测深抽 | 6,556 | 6,113 万 | ✅ 99% |
| T6r2 存疑重烧 | 2,774 | 3,083 万 | ✅ 100% |
| T7 三票共识 | 6,650 | 4,921 万 | ✅ 100% |
| T7x 五票升级 | 6,635 | 5,035 万 | ✅ 100% |
| T9 行业深抽 | 18,763 | 1.24 亿 | 97% |
| T9r2 存疑重烧 | 2,488 | 2,080 万 | 尾巴待补 |
| T8 深摘要 2026 | 2,597 | 2,329 万 | 45%（剩 3,208） |
| T8 深摘要 2025 | 2,535 | 2,237 万 | 13%（剩 17,664） |

**2026-07-25 用户告知 key 有效期还有 1 个月（~8/24），烧录不再赶时间。** 恢复烧录步骤见抢救目录 README：重建工作镜像（**DB 不要放 /tmp**）→ 补齐 rag_system 模块 → 产物放回即断点续传。

**教训（已入记忆）**：长时烧录的产物与唯一副本工具绝不能只存在 /tmp；监视器必须区分 rc=1（崩溃）与 rc=3（限流/配额），前者应立即停并报错而非重试。

## 未解决项
1. ~~T5 全库摘要需拍板~~ → 已拍板并部署（见上节）。T5 摘要的 DB 回灌（summary 列 + `has_summary` + SUMMARY_DIR md 文件）是烧后零 token 步骤，随 NAMEZY 回灌一并做。
2. **烧录成果回灌 NAMEZY**：local_rrepo 的 `reports.db`、`burn_all.jsonl`、`burn_t4.jsonl`、`burn_t5.jsonl`、`rag_system/t5_summarize.py` 需同步回 `/Volumes/NAMEZY/外资研报`（保护文件边界，需用户确认走守卫流程）。**零 token，不受 7/24 截止约束**，可 7/25 后做。
3. **`.env` 值未加引号**（BBDOWN_COOKIE 等）：任何 `source .env` 的消费者（含 C4 launchd wrapper）都会在 line 37 中断，其后变量不加载。改 .env 属红线，已另立任务卡待用户确认。
4. **raster_failed 104 份**：pdftoppm 渲染失败的 image PDF，OCR 管线救不了，属corpus 天然损耗（0.4%），未深究。
5. finer 侧 C10 金丝雀（已授权 1000 份）与本烧录线独立，未在本任务执行——它主要不烧 MiMo（text PDF 走 pdfplumber，F3/F5 用 GLM/Qwen），不抢过期 token 窗口。
