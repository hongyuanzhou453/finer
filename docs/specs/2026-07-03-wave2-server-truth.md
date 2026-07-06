# Wave 2 — 服务端真值化：信誉分后移 + 快照-diff 服务 + F3 可注入 LLM + summary 优化

## 概述

四件套一次落地：② 信誉分公式后移后端成为唯一真相源；③ F7 立场快照按日落盘 + `/api/opinions/changes` 端点（真快照-diff）；① F3 extractor 可注入（LLM opt-in + 确定性回退）+ prompt 修锚（方向稳定性/反聚类/去 0.85 示例锚定）；④ 适配器 summary 兜底修复。全量 **3046 passed**（+15 新测试）零回归；`/radar` 端到端实测：异动 20 条来自服务端、可信度榜 71/70 为服务端真值。

## 变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/finer/api/routes/opinions.py` | 修改 | `_credibility_score`/`_CRED_*` 常量（样本收缩公式唯一实现）；stats `topKols` 增 `settledCount/hitRate/credibility/lowSample`；`_attributed_actions`/`_kol_credibility_map`/`_history_change_events`；新端点 `GET /changes`（历史派生 + 快照 diff 合并、按 id 去重、当日快照幂等落盘） |
| `src/finer/timeline/stance_snapshot.py` | 新增 | F7 快照模块：`build_snapshot`（latest-by-(kol,ticker) 按 canonical 时钟，tie 按 id 确定性）/ `persist_snapshot`（原子写 `data/F7_timeline/stance_snapshots/{date}.json`）/ `load_latest_snapshot_before`（严格早于语义）/ `diff_snapshots`（flip/new_call/score_change；全新 KOL 不刷屏 new_call）/ `signal_clock_of` |
| `src/finer/pipeline/canonical_runner.py` | 修改 | `_resolve_intent_extractor`（显式注入 > `FINER_F3_EXTRACTOR=llm` > rule-based；LLM 构造失败降级带注记）+ `_extract_with_fallback`（异常或非规则空产出→规则兜底，note 记录）；`run_canonical_from_envelope` 增 `intent_extractor` 参数；F5 LLM prompt 去 `"confidence": 0.85` 示例锚定 |
| `src/finer/prompts/f3_intent_extraction/system.j2` | 修改 | 新增 §1b Direction Stability（同标的全文判一次方向；双向表述出单条 dominant/mixed + `conflicting_direction` flag；仅显式叙述转向才允许两条 + `stance_change` flag）+ conviction 反聚类指令 |
| `src/finer_dashboard/src/lib/fixtures/kol-radar.ts` | 修改 | `CredibilityOverride` 类型 + `KOLRadarData.credibilityOverrides`；`deriveCredibilityBoard` 有 override 时以服务端为准（trend/立场/主推仍由 viewpoints 派生） |
| `src/finer_dashboard/src/lib/live/opinions-adapter.ts` | 修改 | `fetchCredibilityOverrides`（/stats?timeRange=ALL）+ `fetchServerChanges`（/changes）并行拉取，失败容错回退客户端派生；summary 兜底改"方向+标的"短语（④，消除与引文块同源重复） |
| `src/finer_dashboard/src/app/radar/page.tsx` | 修改 | banner："异动：每日快照对比 + 历史派生 · 信誉分为服务端真值" |
| `tests/test_stance_snapshot.py` | 新增 | 8 用例（latest 语义/未归属排除/flip/new_call/score_change/无变化/新 KOL 不刷屏/持久化往返+strictly-before） |
| `tests/test_f3_extractor_injection.py` | 新增 | 7 用例（显式注入优先/默认规则/LLM 构造失败降级/主 extractor 异常回退/非规则空产出回退/规则空即空/成功主产出原样使用） |

## 关键决策

1. **信誉分单一真相源在后端**：前端保留同公式派生仅作 fixture 展示与离线兜底；live 一律 override。验证：服务端 trader_ji 70=(19+2)/(35+4) 公式核对，榜面逐位一致。
2. **/changes 双源合并**：历史派生（翻向/止损，冷启动即有内容）+ 快照 diff（新增覆盖/隔日翻向/信誉变动，随历史积累出现），按事件 id 去重防同日双计。快照当日幂等覆盖；`prevSnapshotDate` 显式返回冷启动状态。
3. **LLM extractor 是 opt-in 不是默认**：`FINER_F3_EXTRACTOR=llm` 才启用，且构造失败/运行异常/空产出三层都降级到确定性 rule-based 并留痕——在真实语料验证前不拿生产管线冒险。
4. **同日反向对治本在 prompt**：规则版方向检测按 section 不稳（既存 0700.HK bearish+bullish@02-16），LLM prompt 现在明确"同标的全文判一次"；规则版不动（它是回退基线）。

## 验证结果

- pytest 全量 **3046 passed**（3031+15）零回归；py_compile 全过；tsc/eslint clean。
- `/api/opinions/changes` 冷启动实测：20 事件（17 翻向+3 止损）、`snapshotDate=2026-07-03`、`prevSnapshotDate=null`、快照文件落盘。
- `/api/opinions/stats/summary?timeRange=ALL`：topKols 带 credibility 70/71、hitRate、lowSample=false（35/5 笔）。
- `/radar` 浏览器端到端：banner 新文案、近期异动 20 条（服务端事件带公司名）、可信度榜 71/70 服务端真值、无 console error。

## 未解决项

1. **① 的下半场未做（刻意）**：真实 LLM 冒烟 + 12 envelope 全量重提取——重提取会重掷全部 uuid（丢 backtest_result/RLHF/审计引用，需再跑回填链）且产生 LLM 成本；另有已知 `from_env` key 误路由隐患（memory ⚠️）。需要单独决策：验证 LLM 输出质量 → 定重提取窗口 → 重跑回填。
2. 快照-diff 的隔日事件明日起才会出现（今日冷启动）；score_change 依赖快照内 credibility（已存）。
3. `/changes` 每次调用全量文件扫描 + 写快照——量级无虑，上千条后应挪 cron/缓存。
4. 历史翻向含同日反向对产生的"翻向"事件（数据既存缺陷的下游回声），LLM 重提取后自然消失。
