import type { Metadata } from "next";
import { KOLSnapshot } from "@/components/kol-snapshot";
import { KOL_SNAPSHOT_FIXTURE } from "@/lib/fixtures/kol-snapshot";

export const metadata: Metadata = {
  title: "KOL 观点潮汐快照 · Finer OS",
  description:
    "单个 KOL 的 F7 观点时间线快照——立场研判、观点象限、证据时间线（设计标杆，fixture 数据）。",
};

export default function KOLSnapshotDemoPage() {
  return (
    <main className="h-full w-full overflow-y-auto bg-[var(--background)]">
      <KOLSnapshot data={KOL_SNAPSHOT_FIXTURE} />
    </main>
  );
}
