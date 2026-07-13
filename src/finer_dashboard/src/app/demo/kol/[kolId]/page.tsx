import type { Metadata } from "next";
import Link from "next/link";
import { KOLSnapshot } from "@/components/kol-snapshot";
import { KOL_RADAR_FIXTURE } from "@/lib/fixtures/kol-radar";
import { deriveKolSnapshot } from "@/lib/fixtures/kol-l2";

export const metadata: Metadata = {
  title: "KOL 问责页 · Finer OS",
  description:
    "单个 KOL 的观点潮汐快照——立场研判、观点象限、证据时间线（设计标杆，fixture 数据）。",
};

export default async function KolAccountabilityPage({
  params,
}: {
  params: Promise<{ kolId: string }>;
}) {
  const { kolId } = await params;
  const data = deriveKolSnapshot(KOL_RADAR_FIXTURE, decodeURIComponent(kolId));

  return (
    <main className="h-full w-full overflow-y-auto bg-[var(--background)]">
      {data ? (
        <>
          <div className="mx-auto max-w-[1180px] px-6 pt-4">
            <Link
              href="/demo/kol-radar"
              className="text-[11px] uppercase tracking-[0.2em] text-[var(--accent-teal)] hover:underline"
            >
              ← 返回观点雷达
            </Link>
          </div>
          <KOLSnapshot data={data} />
        </>
      ) : (
        <div className="mx-auto max-w-[680px] px-6 py-16 text-center">
          <p className="text-lg text-[var(--foreground)]">未找到 KOL {kolId}</p>
          <p className="mt-2 text-sm text-[var(--ink-soft)]">
            该 KOL 不在示例数据内。{" "}
            <Link className="text-[var(--accent-teal)] hover:underline" href="/demo/kol-radar">
              返回观点雷达
            </Link>
          </p>
        </div>
      )}
    </main>
  );
}
