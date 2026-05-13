"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2, LineChart } from "lucide-react";
import { useAsyncData } from "@/lib/hooks/useAsyncData";
import { listBacktestResults } from "@/lib/api-client";

/**
 * Redirect page: fetches backtest results for this KOL and
 * redirects to the first one. Shows empty state if none exist.
 */
export default function KOLBacktestIndexPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const { data: results, loading } = useAsyncData(
    () => listBacktestResults({ kol_id: params.id, limit: 1 }),
    [params.id],
  );

  useEffect(() => {
    if (results && results.length > 0) {
      router.replace(`/kol/${params.id}/backtest/${results[0].backtest_id}`);
    }
  }, [results, params.id, router]);

  return (
    <main className="min-h-screen bg-[#f3efe7]">
      <div className="container py-8">
        <Link
          href={`/kol/${params.id}`}
          className="mb-6 inline-flex items-center gap-2 text-sm text-foreground/60 hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          返回 KOL 详情
        </Link>

        {loading ? (
          <div className="h-64 flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-foreground/30" />
          </div>
        ) : !results || results.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-foreground/40">
            <div className="text-center">
              <LineChart className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium mb-2">暂无回测结果</p>
              <p className="text-sm">该 KOL 尚未运行过回测。</p>
            </div>
          </div>
        ) : null}
      </div>
    </main>
  );
}
