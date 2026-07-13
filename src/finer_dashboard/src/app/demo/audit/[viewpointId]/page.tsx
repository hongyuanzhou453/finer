import type { Metadata } from "next";
import Link from "next/link";
import { ViewpointAudit } from "@/components/kol-audit";
import { findViewpointById } from "@/lib/fixtures/kol-audit";

export const metadata: Metadata = {
  title: "证据审计 · Finer OS",
  description:
    "单条观点的证据链——F2 证据 / F5 动作 / F8 回测（设计标杆，fixture 数据）。",
};

export default async function ViewpointAuditPage({
  params,
}: {
  params: Promise<{ viewpointId: string }>;
}) {
  const { viewpointId } = await params;
  const data = findViewpointById(decodeURIComponent(viewpointId));

  return (
    <main className="h-full w-full overflow-y-auto bg-[var(--background)]">
      {data ? (
        <ViewpointAudit data={data} />
      ) : (
        <div className="mx-auto max-w-[680px] px-6 py-16 text-center">
          <p className="text-lg text-[var(--foreground)]">未找到观点 {viewpointId}</p>
          <p className="mt-2 text-sm text-[var(--ink-soft)]">
            该观点不在示例数据内。{" "}
            <Link className="text-[var(--accent-teal)] hover:underline" href="/demo/kol-radar">
              返回观点雷达
            </Link>
          </p>
        </div>
      )}
    </main>
  );
}
