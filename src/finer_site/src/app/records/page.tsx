import type { Metadata } from "next";
import { SiteFooter, SiteHeader } from "@/components/landing/site-chrome";
import { RecordsExplorer } from "@/components/records/RecordsExplorer";

export const metadata: Metadata = {
  title: "信源记录",
  description:
    "外资券商研报的冻结快照（2026-08-10）：每家信源的历史记录可逐条点开——评级、目标价、方向与机器结算结果。个股评级与板块观点两种口径分开记账；样本不足只报计数。历史记录，不构成对未来的预测。",
};

const NAV_LINKS = [
  { href: "/#records", label: "记录与共识" },
  { href: "/demo", label: "在线演示" },
  { href: "/training", label: "训练闭环" },
];

export default function RecordsPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader links={NAV_LINKS} />
      <RecordsExplorer />
      <SiteFooter />
    </div>
  );
}
