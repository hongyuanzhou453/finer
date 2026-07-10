/**
 * 雷达页下钻链接的路由上下文。demo（fixture 标杆）与 live（真实数据）路由前缀
 * 不同：问责页 /demo/kol/[id] vs /radar/kol/[id]；证据审计 /demo/audit/[id] vs
 * /audit?kol=；标的横截面暂无 live 页。组件同构，链接由数据源页面注入——
 * 缺省为 demo，缺失的 optional 链接渲染为非链接内容（诚实降级，不把 live
 * 用户悄悄导回 fixture 页）。
 *
 * 注意：该对象会跨 Server→Client Component 边界传递，必须保持可序列化
 * （纯数据，无函数）；href 拼装用下方的模块级 helper。
 */
export interface RadarLinks {
  /** 问责页前缀：`${kolBase}/${kolId}` */
  kolBase: string;
  /** 标的横截面前缀；undefined = 该数据源无对应页面，渲染纯文本 */
  tickerBase?: string;
  /**
   * 证据审计入口；undefined = 不渲染下钻入口。
   * viewpoint 模式按单条观点深链（demo），kol-query 模式按 KOL 过滤深链（live）。
   */
  audit?:
    | { kind: "viewpoint"; base: string }
    | { kind: "kol-query"; base: string };
}

export const DEMO_RADAR_LINKS: RadarLinks = {
  kolBase: "/demo/kol",
  tickerBase: "/demo/ticker",
  audit: { kind: "viewpoint", base: "/demo/audit" },
};

export const LIVE_RADAR_LINKS: RadarLinks = {
  kolBase: "/radar/kol",
  // live 标的横截面页尚未存在 → 卡片渲染为纯文本
  // live 审计台支持 ?kol= 深链（按 KOL 过滤后自动选中该 KOL 的 action）
  audit: { kind: "kol-query", base: "/audit" },
};

export function kolHref(links: RadarLinks, kolId: string): string {
  return `${links.kolBase}/${encodeURIComponent(kolId)}`;
}

export function tickerHref(links: RadarLinks, ticker: string): string | null {
  return links.tickerBase
    ? `${links.tickerBase}/${encodeURIComponent(ticker)}`
    : null;
}

export function auditHref(
  links: RadarLinks,
  viewpointId: string,
  kolId: string,
): string | null {
  if (!links.audit) return null;
  return links.audit.kind === "viewpoint"
    ? `${links.audit.base}/${encodeURIComponent(viewpointId)}`
    : `${links.audit.base}?kol=${encodeURIComponent(kolId)}`;
}
