import type { Metadata } from "next";
import { SiteFooter, SiteHeader } from "@/components/landing/site-chrome";
import { KolCheckReport } from "@/components/kol-check/KolCheckReport";

export const metadata: Metadata = {
  title: "KOL 晨星 · 真实战绩体检",
  description:
    "Finer OS 对一位真实 KOL 的喊单做晨星式体检：信誉分、结算命中率、言行不一（自述 vs 实盘）、每条观点可展开 F3→F4→F5→F8 证据链。数据为真实 canonical 结果的匿名化快照，非投资建议。",
};

const NAV_LINKS = [
  { href: "/demo", label: "完整演示" },
  { href: "/training", label: "训练闭环" },
];

export default function KolCheckPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader links={NAV_LINKS} />
      <KolCheckReport />
      <SiteFooter />
    </div>
  );
}
