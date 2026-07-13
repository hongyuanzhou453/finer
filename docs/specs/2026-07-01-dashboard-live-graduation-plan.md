# 操作台 fixture → live 化计划（后端任务卡 + 依赖排序）

## 概述

KOL 决策操作台的四层前端（观点雷达 L1 / KOL 问责页 L2 / 标的横截面 L3 / 证据审计 L4）已作为 fixture 标杆全部验证成立。本文把"切真实数据"所需的后端工作拆成 grounded 任务卡（每条现状/改动带 file:line 证据，源自 2026-07-01 4-agent 后端深挖 workflow），并给出依赖排序。

## 两个地基发现（决定一切排序）

深挖后最重要的结论不是四张卡本身，而是**所有 per-KOL / 兑现相关功能都压在两块地基上，而这两块今天都是空的**：

1. **地基 A — creator_id 归属**：真实数据 162 条 F5 action 的 `creator_id` = `unknown`(58) / 飞书 open_id `ou_4b89…`(26) / `kol_cat_lord_fire`(7)，distinct=3。归属链**在 F1 断裂**——几乎所有 canonical F1 standardizer 只透传 `creator_name` 漏了 `creator_id`。不修这块，`deriveCredibilityBoard`/`deriveMarketSentiment` 的"按 KOL 分组"在真实数据上塌成单一 unknown 桶（前端 `kol-radar.ts:16` 注释已自认此风险）。

2. **地基 B — F8 回测落库（settled 数据）**：真实 162 条 F5 action 的 `backtest_result` **全部为 null**、`validation_status` 全是 pending。除 `data/review/` 下 2 个手工 F8 artifact 外，**没有任何 KOL 有可算命中率的 settled 记录**。信誉分、观点象限、拥挤打脸、谁对了、止损异动——全部依赖 return_pct，即依赖 F8 回测批量跑通并落库（还隐含依赖 `data/market/tushare` 行情覆盖）。

**含义**：唯一能独立、立刻落地的是 opinions 五向放开（纯 API 层，S）。其余三块都排在地基 A、B 之后。

## 依赖排序路线图

```
Wave 0（独立·立即）    opinions 五向放开 (S)  ── 解除前端 fidelity 天花板
Wave 1（地基）         creator_id 归属 P0 (M) + F8 回测批量落库 (L/XL)
Wave 2（榜单）         信誉分聚合端点 (L)          ← 依赖 Wave 1 (A+B)
Wave 3（异动）         近期异动 snapshot-diff (L)  ← 依赖 Wave 1+2 + 快照存储
```

---

## 卡 1 · opinions 五向方向放开  ·  effort S  ·  Wave 0（无依赖）

**现状**：`TradeDirection` 真值本就 5 向（`schemas/trade_action.py:31-37`），存储层 5 向直通（`services/storage.py:200`）。收窄只发生在 **F7 DTO 层**：`api/routes/opinions.py:118-124` `_DIRECTION_MAP` 把 `watchlist→neutral`、`risk_warning→bearish`；`opinions.py:48` `TimelineOpinion.direction` Literal 只声明 3 值；`/stats/summary` 的 `byDirection` 只初始化 3 键（`opinions.py:411,419-427`）。过滤 `directions=watchlist` 其实已端到端命中（纯等值 `opinions.py:281-283`），只是响应被压平。

**改动**：
- `opinions.py:48` Literal 扩为 5 值；`opinions.py:118-124` `_DIRECTION_MAP` 改恒等直通（仅留未知兜底）；`opinions.py:411,419-427` `byDirection` 扩 5 键、删两个折叠 elif。
- **前端同步（否则 tsc 断）**：旧活数据视图 `components/opinion-timeline/` 的 `OpinionDirection` 从 3→5，并补穷举 `Record`：`TimelineNode.tsx:33`、`OpinionDetailModal.tsx:55`、`TimelineFilter.tsx:48-50`。新 kol-snapshot/kol-radar 已是 5 向，无需改。

**契约影响**：API 契约"放宽"非破坏（3 值是 5 值子集）。同步点：`opinions.py` 的 direction Literal 必须与 `opinion-timeline` 的 `OpinionDirection` 字面量集逐字一致。

**依赖**：无硬前置。⚠️ 但上游要真产出 watchlist/risk_warning action，本卡才有真数据展示，否则只是"解除天花板"。

**验收**：新增测试证明 `directions=watchlist`/`risk_warning` 的 action 经 `/timeline` 原样透出、`/stats/summary.byDirection` 出现非零 5 键；`npm run build` + `tsc --noEmit` 通过。

---

## 卡 2 · creator_id KOL 身份归属  ·  effort M  ·  Wave 1（地基 A）

> **进度（2026-07-01）**：**P0-1/P0-2/P0-3 已完成并验证**（`parsing/` 6 处：standardization_router / manual_text / pdf / placeholder 补 `creator_id=f0_record.creator_id`；image_ocr 改从 f0_record 顶层取；feishu 改 F0-first + sender 兜底）。不改 schema、不回填、不碰 legacy/content_id。验证：新增 `tests/test_creator_id_propagation.py`（3 例）+ 真实数据端到端（F0 trader_ji → F1 creator_id='trader_ji'，原 None）+ 全量 `pytest tests/` **3003 passed**。
> **P0-6 回填已执行（2026-07-01，已授权）**：`data/F5_executed/` 12 文件 58 action 的 `source.creator_id` 从全 `unknown` 回填为 **trader_ji×52 / sandbox×6**（filename→F0 content_id→creator_id join，0 unresolved）。备份 `data/F5_executed.bak-20260701-182019`；仅填空值不覆盖；cache DB 重建后 `SELECT creator_id` = {trader_ji:52, sandbox:6}。脚本 `scratchpad/backfill_creator_id.py`（dry-run 默认 + --apply）。
>
> 🚨 **回填时发现一个独立的前置阻断（非 creator_id 问题、非本次改动引入）——"F5_executed → opinions 读路径"断裂**：`data/F5_executed/*_actions.json` 是数组包裹 `{actions:[...]}`，而 `opinions._load_all_actions`/`repo._load_from_file` 期望每个 JSON 是单条 `*.action.json`；且 `TradeAction` 子模型 `ConfigDict(strict=True)`，存盘的字符串枚举/时间需 `model_validate(strict=False)` 才能反序列化。二者叠加导致 **`opinions._load_all_actions()` 返回 0**、DB 索引一直为空——即**现存真实 F5 数据在修好读路径前，dashboard 一条都读不出来，与 creator_id 无关**。kol.py 读错路径(L5/L6)是同一类"F5_executed 未接读层"问题。→ **应新增一张卡：F5_executed → 读层接线**（决定：改 `_load_from_file` 支持数组包裹 + `strict=False`，或让 opinions 直接读 DB 列不重建全 action，或统一 F5 落盘为单条 `.action.json`）。这是"graduate to live"被低估的前置。
>
> **仍待办**：上述 F5→读层接线（新，🔴 涉及 TradeAction strict / loader 决策）；P0-4（legacy 弃用）、P0-5（content_id）、P1（KOLProfileManager + 规范化）；地基 B（F8 回测落库）才有兑现数据。

**现状**：F0 正确设置 `ContentRecord.creator_id`（`content.py:43`；磁盘实证 `data/F0_intake/local/trader_ji/*.json` creator_id='trader_ji'）。**F1 系统性丢弃**：`standardization_router.py:252`(主分派)、`manual_text_standardizer.py:245`、`pdf_standardizer.py:937`、`placeholder_adapters.py:86` 都只写 `creator_name` 漏 `creator_id`；`image_ocr_standardizer.py:752` 从 metadata 取（错源）；`feishu_chat_standardizer.py:463` 用 per-message sender 覆盖。F2/F3/F5 忠实透传 None。legacy F5 `trade_action_extractor.py:352` 根本不传。**已存在但零接线**：`services/kol_profile.py` 的 `KOLProfileManager`（get_or_create/find_by_platform 全套 + 持久化 `data/kol_profiles/`），F0/F1/F3 全链 0 调用。**关键无损点**：所有中间产物都保留了 `source_record_id`（F1/F2 磁盘实证），F0↔下游 join 可靠。

**改动**：
- **P0-1**（覆盖 ~80% 真实数据）：4 个 canonical F1 standardizer 构造 ContentEnvelope 时补 `creator_id=f0_record.creator_id`（与既有 creator_name 对称）。
- **P0-2** 修 `image_ocr_standardizer.py:752` 取源；**P0-3** 停 `feishu_chat_standardizer.py:463` 的 sender 覆盖；**P0-4** legacy F5 补 creator_id 或按 AGENTS.md 弃用 legacy；**P0-5** `canonical_action_builder.py:330` content_id 改用 F0 `source_record_id`（需 Intent 透传该字段）。
- **P0-6 回填**（🔴 红线：批量重建须先确认）：用 `source_record_id` join F0 反查 creator_id，批量回填已落盘 F2/F3/F5（无损）。不回填，旧数据仍是 unknown。
- **P1**（增量）：F0/F1 接 `get_kol_profile_manager().get_or_create(platform, handle)` → 稳定 `kol_id`；清洗 `notebooklm`/`_inbox` 等非 KOL 值；跨平台合并同一 KOL。

**契约影响**：P0 不改 schema（ContentEnvelope.creator_id 已存在，只改填充）。P1 若引 `kol_id` 稳定键，需给 ContentRecord/Envelope/Intent/SourceInfo 各加 Optional `kol_id`（🔴 SQLite `storage.py:70` 增列须确认）。前端 fixtures 用 handle 风格 kolId（trader_ji…），与 F0 handle 同构 → **P0 贯通后前端无需改**。

**依赖**：P0-1~P0-3 无前置（地基）。P0-6 依赖 P0-1 + 用户确认。P1 依赖 P0。

**验收**：本地 F0 记录走 F0→F5 后 `action.source.creator_id=='trader_ji'`（今为 unknown）；`/meta` 的 kols 不再单一 unknown；`deriveCredibilityBoard` 真实数据返回 ≥2 行；`pytest tests/ -v` 全绿、333 F1 tests 不回退。

**开放问题**：飞书 chat 是否恒单 KOL？legacy F5 是否硬禁用？分组键选 handle 还是 canonical `kol_{uuid}`（建议 P0 handle、P1 升级）？

---

## 卡 3 · 信誉分聚合  ·  effort L  ·  Wave 2（依赖 A+B）

**现状**：两条评分路径都不可用。① `api/routes/kol.py`（已接线 `/api/kol/*`）的 `_calculate_kol_rating` **读错路径** `data/L5_candidate`/`L6_annotated`（0 文件），真实 action 在 `F5_executed/` → rating 主路径永远走空回落。② `ml/kol_scorer.py` `KOLScorerV2`（1-5 多维）是**死代码**，全仓 0 调用，且吃的字段（annualized_return/is_correct/lead_days）真实数据基本缺。③ `/stats/summary` `topKols[].avgRating` 硬编码 `0.0`（`opinions.py:473`）。④ F8 `BacktestEngine.run_backtest` 已产 `kol_metrics.win_rate`（`backtest/engine.py:803`），但磁盘仅 2 个手工 artifact 且 trades 被 storage 剥空。

**最短路径**：**不碰 KOLScorerV2**（1-5 维与 fixture 的 0-99 命中率不同源）。① 修 `kol.py` 读真实 `F5_executed/F6_reviewed`（或复用 opinions 的 `TradeActionRepository`）。② 新增 `GET /api/kol/credibility-board`，逐 KOL 取 F8 `win_rate`+`total_trades`，套 **fixture 同款收缩公式**（`adjRate=(wins+2)/(settled+4)`, `credibility=clamp(40+55*adjRate,0,99)`, `lowSample=settled<5`——与 `kol-radar.ts:684-693` 逐字对齐）。③ `opinions.py:473` avgRating 接同一聚合。

**契约影响**：新增 `CredibilityRow` response model + `contracts.ts` 同步；后端公式必须逐字复制前端收缩口径否则前后端不一致。🔴 **明确废弃/隔离 KOLScorerV2**，避免三套评分（1-5维 / kol.py 1-5 / fixture 0-99）并存打架。

**依赖**：🔴 硬依赖 **地基 A（creator_id）**（否则只有 unknown 一桶）+ **地基 B（F8 落库）**（否则无 return_pct 可算命中率，今天全 null）。步骤②③依赖步骤①先修路径。

**验收**：`/api/kol/credibility-board` 对 trader_ji 返回 credibility≈71（手算可复核）、带 lowSample；后端输出与 `deriveCredibilityBoard` 对同一输入一致（单测）；`topKols[].avgRating` 不再恒 0.0。

---

## 卡 4 · 近期异动 snapshot-diff  ·  effort L  ·  Wave 3（依赖 A+B+信誉分 + 快照存储）

> ⚠️ 此卡的 workflow agent 完成了调研但未产出结构化输出（StructuredOutput 重试超限），以下为主循环基于前端事件模型 + 依赖链综合。

**现状**：后端只读当前 F5/F6 全量，**无"相对上一快照"的变化检测服务**；F7 `timeline/engine.py` 是按 KOL 聚合当前观点，无每日快照持久化。前端"近期异动"六类（flip 翻向 / new_high_conviction / new_call / stop_loss / score_change / consensus_alert）全是 fixture 手写。

**缺口/改动**：需要 ①一个**每日快照存储**（落每日 per-(KOL,ticker) latest direction + credibility 快照）；②一个 **diff 计算**（翻向=latest direction 变化；stop_loss=F8 exit_reason=stop_loss；score_change=credibility delta；new_call=首次出现的 action；consensus_alert=某标的 bull/bear 计数跨阈值）。放 F7 timeline 引擎扩展或独立 job。

**依赖**：翻向/new_call 依赖 **地基 A**（按 KOL/标的分组）；stop_loss 依赖 **地基 B**（F8 exit）；score_change 依赖 **卡 3（信誉分）**；全部依赖**每日快照持久化**（今天不存在）。→ 排在最后。

**验收**：连续两日快照能 diff 出翻向/止损/信誉变动事件；`deriveChangeFeed` 的 live 源可产出与 fixture 同形的事件流。

---

## 前端解锁映射

| 后端 Wave 完成 | 前端解锁 |
|---|---|
| 卡1 五向 | DirectionTag 5 色 / 广度条 / 异动翻向保真（opinion-timeline 立即；kol-snapshot 待适配器） |
| 地基 A creator_id | 可信度榜、市场情绪按 KOL 分组不塌桶；L2 问责页可按真实 KOL 出页 |
| 地基 B F8 落库 | 观点象限、标的兑现榜、谁对了、拥挤打脸、命中率——所有 return_pct 相关 |
| 卡3 信誉分 | 可信度榜脊柱、可跟 call 排序、L2 信誉分 |
| 卡4 异动 diff | 雷达"近期异动"流 |

## 🔴 红线清单（须用户显式确认后才动）

1. **批量重建/回填**（卡2 P0-6：回填 F2/F3/F5 creator_id；地基 B：批量跑 F8 落库）——CLAUDE.md 红线。
2. **SQLite schema 变更**（卡2 P1：storage 增 kol_id 列 + 索引）——CLAUDE.md 红线。
3. **弃用 legacy `TradeActionExtractor.extract_from_text`**（卡2 P0-4）——影响主链路，需拍板。

## 建议下一步

- **想要一个能立刻看见效果的小胜**：做**卡1（opinions 五向，S）**——无依赖、无红线、当天可完成并让 opinion-timeline 活数据保真 5 向。
- **想真正推动 live**：先攻**地基 A（creator_id 归属 P0，M）**——它是一切 per-KOL 功能的前提，P0 部分不改 schema、不碰红线（回填才碰）。
- **地基 B（F8 落库）** 是隐藏的最大工作量（需行情数据 + 批量回测编排），建议单列评估。

## Open Issues

- 卡4（异动 diff）缺结构化任务卡，需补一次单块深挖或直接进入设计。
- 分组键最终选型（handle vs canonical kol_id）需产品拍板，影响卡2/卡3 的 contract。
- KOLScorerV2 去留（删除 vs 降级为详情页 1-5 维度雷达）。
