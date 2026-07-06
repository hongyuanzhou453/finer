import type { Metadata } from "next";
import { KOLRadar } from "@/components/kol-radar";

export const metadata: Metadata = {
  title: "观点雷达 · Finer OS",
  description:
    "全 KOL 观点聚合操作台——市场情绪、今日异动、可信度榜、此刻可跟、标的共识（设计标杆，fixture 数据）。",
};

export default function KOLRadarDemoPage() {
  return (
    <main className="h-full w-full overflow-y-auto bg-[var(--background)]">
      <KOLRadar />
    </main>
  );
}
