/**
 * CRD-2 效力门的**类型级**执行点。
 *
 * 事故背景（2026-08-15 盘点发现）：此前门只写成组件内部的控制流——
 * `CardRatioBlock` 里 `if (count_only) return <只报计数>`。但 JSX 的兄弟节点
 * 不受这个 return 约束：`RecordCardWall` 的 `<dl>` 与 `CreatorRecordView` 的
 * 页头都在门**外面**无条件渲染了「均值收益（历史）」。后果是 34 张 count_only
 * 卡中 24 张对外印着比率，KeyBanc settled=1 印 +58.0%——而那张卡自己的
 * notes 就写着「样本不足，只报计数」。
 *
 * 修法不是再加一个 if：控制流的门只要有人在旁边加个节点就会被绕过，
 * 这已经是同一形状的第四次。这里把门下沉到**数据与类型**：
 * `gateCard()` 在数据入口处把 count_only 卡的比率字段整个摘掉，
 * `DisplayCard` 让这些字段在该分支上**不存在**（不是 null，是不存在）。
 * 于是任何试图渲染被门挡下的比率的代码都会被 tsc 拒绝编译。
 *
 * finer_site 没有测试运行器，编译器就是这条红线的回归测试。
 */
import type { RecordCard, Sufficiency } from "@/demo/records/types";

/** 卡面上的比率字段——count_only 时必须不可用。 */
type CardRatioFields = "mean_return" | "median_return" | "expected_win_rate";

/** sufficiency 里的比率字段。后端对 count_only 卡**照样**计算这些值
 *  （实测 settled_n=1 的卡 point_estimate=1.0），所以它们同样要摘掉——
 *  否则门外的代码换个字段名就能继续泄漏。 */
type SufficiencyRatioFields =
  | "point_estimate"
  | "wilson_low"
  | "wilson_high"
  | "ci_width";

/** 计数与判定字段：任何情况下都可渲染，它们不是比率。 */
export type GatedSufficiency = Omit<Sufficiency, SufficiencyRatioFields>;

/**
 * 唯一允许进入渲染层的记录卡类型。
 *
 * - `ratiosPermitted: true` —— 与原始 `RecordCard` 完全同形，比率可渲染；
 * - `ratiosPermitted: false` —— 比率字段在类型上不存在，访问即编译错误。
 *
 * 判别式必须先窄化才能取比率字段，这正是我们要的：门变成了必经之路。
 */
export type DisplayCard =
  | ({ ratiosPermitted: true } & RecordCard)
  | ({ ratiosPermitted: false } & Omit<
      RecordCard,
      CardRatioFields | "sufficiency"
    > & { sufficiency: GatedSufficiency });

/**
 * 把原始快照卡转成过门后的展示卡。在数据入口调用一次即可，
 * 下游（卡墙、下钻页、以及将来任何新增节点）拿到的就已经是安全值。
 */
export function gateCard(card: RecordCard): DisplayCard {
  if (card.sufficiency.display_policy !== "count_only") {
    return { ratiosPermitted: true, ...card };
  }
  const s = card.sufficiency;
  // 白名单而非黑名单：这里逐个列出「允许穿过门」的字段，而不是排除已知的比率。
  // 将来快照新增字段时，默认结果是被挡住而不是被放行——门的失效方向必须是
  // 保守的（记忆「门在缺信息时放行」记的就是反过来做的四次事故）。
  return {
    ratiosPermitted: false,
    creator_id: card.creator_id,
    signal_class: card.signal_class,
    n_total: card.n_total,
    n_settled: card.n_settled,
    wins: card.wins,
    market_mix: card.market_mix,
    first_action_at: card.first_action_at,
    last_action_at: card.last_action_at,
    rows_file: card.rows_file,
    sufficiency: {
      settled_n: s.settled_n,
      total_n: s.total_n,
      successes: s.successes,
      confidence: s.confidence,
      // coverage_ratio 是数据完整度（已结算/总数），描述的是语料本身而非信源
      // 表现，与 n_settled/n_total 同类，不属 CRD-2 要挡的绩效比率。
      coverage_ratio: s.coverage_ratio,
      coverage_penalised: s.coverage_penalised,
      tier: s.tier,
      display_policy: s.display_policy,
      predictive_claim: s.predictive_claim,
      notes: s.notes,
    },
  };
}
