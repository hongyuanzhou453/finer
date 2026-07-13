import type { Metadata } from "next";
import { KOLTickerCrossSection } from "@/components/kol-ticker";
import { KOL_RADAR_FIXTURE } from "@/lib/fixtures/kol-radar";
import { deriveTickerCrossSection } from "@/lib/fixtures/kol-ticker";

export const metadata: Metadata = {
  title: "标的横截面 · Finer OS",
  description:
    "某标的的众 KOL 视角——共识裁决、谁对了、立场时间线（设计标杆，fixture 数据）。",
};

export default async function TickerCrossSectionPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const data = deriveTickerCrossSection(KOL_RADAR_FIXTURE, decodeURIComponent(ticker));

  return (
    <main className="h-full w-full overflow-y-auto bg-[var(--background)]">
      {data ? (
        <KOLTickerCrossSection data={data} />
      ) : (
        <div className="mx-auto max-w-[680px] px-6 py-16 text-center">
          <p className="text-lg text-[var(--foreground)]">未找到标的 {ticker}</p>
          <p className="mt-2 text-sm text-[var(--ink-soft)]">
            该标的不在示例数据内。{" "}
            <a className="text-[var(--accent-teal)] hover:underline" href="/demo/kol-radar">
              返回观点雷达
            </a>
          </p>
        </div>
      )}
    </main>
  );
}
