# CRD-1 记录卡 + CRD-3 个股共识（2026-08-03）

## 概述

消费面路线第 ③ 步：把「审计谁说过什么」做成可被 API/投影消费的两个只读视图。
CRD-1 = 每信源一张历史记录卡（scorecard 聚合的序列化边界，效力门必填）；
CRD-3 = 每标的一张共识记录（等权、仅方向、每源只计最新一篇）。
CRD-3 是 25/28 已落盘 target_price 的**第一个真实消费者**。

## 变更清单

| 文件 | 类型 |
|---|---|
| `src/finer/schemas/credibility.py` | 新增：CreatorRecordCard / ConsensusSourceRow / TargetPriceSummary / TickerConsensusView + CONSENSUS_DIRECTION_LITERAL |
| `src/finer/credibility/record_card.py` | 新增：build_record_cards（复用 build_scorecard，不重算统计） |
| `src/finer/credibility/consensus.py` | 新增：build_ticker_consensus |
| `tests/test_credibility_views.py` | 新增：12 单测 |

## 关键决策

1. **记录卡不排序**。输出序 = 已结算样本量降序（UI-1 拍板的默认序），是稳定
   输出序不是排名；`sufficiency` 为 schema 必填——没有效力判定的比率不允许
   离开后端。
2. **共识每源只计最新一篇**。多篇是立场时间序列，每篇一票会让高频覆盖的券商
   霸占共识（重述膨胀教训）；历史篇数记 `n_reports`。
3. **目标价 `.L` 显式排除**。2026-08-03 审计实测镑/便士混存，聚合 100 倍错；
   排除并计数比错误的中位数诚实。多币种只聚合多数币种，其余计 mismatch。
4. **符号方言归一**（AZN.LN → AZN.L）后再聚合，跨券商写法不分裂视图。
5. 每行带 `intent_id` 下钻入口；`notes` 恒带「不构成对未来的预测」与等权口径。

## 验证

pytest 12/12；contract drift 29 枚举同步（credibility schema 暂无前端消费方，
UI 轮镜像时登记 CONSENSUS_DIRECTION_LITERAL）；真实语料冒烟：
NVDA 9 源全 bullish（目标价 USD 205/284/350）、0700.HK 10 源（HKD 650/745/800）、
AZN.L 正确拒绝聚合目标价并保留双方下钻。

## 未解决项

- ④ /ticker 页面与只读 API 未做（下一步）；contracts.ts 届时同步。
- `.L` 目标价的量级归一化器（按报告日价格推断镑/便士）留给 MKT/数据修复轮。

---

## 附：④ /ticker 页落地（同日）

- `api/routes/ticker.py`：`GET /api/ticker/{symbol}/consensus`（60s TTL intent
  缓存过渡，PROJ-1 落地时只换数据源；未命中走 Line F envelope）
- `dashboard /ticker` + `/ticker/[symbol]`：口径声明逐条展示、排除计数可见、
  逐行 intent_id 下钻、页首自述「不预测谁更准」
- contracts.ts 镜像 4 个类型，`CONSENSUS_DIRECTION_LITERAL` 进 drift REGISTRY
  （30 枚举同步）

浏览器实测：NVDA（9 源全多，205/284/350 USD）、AZN.L（分歧 + 单位排除声明 +
拒聚合）、NOSUCH999（fix_hint 友好提示）三条路径全通，控制台零报错；
`npm run build` 通过。消费面路线 ①-④ 全部完成。
