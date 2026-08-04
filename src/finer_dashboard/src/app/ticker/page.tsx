"use client";

/** /ticker — 个股共识入口：输入代码，跳转到 /ticker/[symbol]。 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";

const EXAMPLES = ["NVDA", "0700.HK", "AZN.L", "600519.SS"];

export default function TickerIndexPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const go = (symbol: string) => {
    const s = symbol.trim();
    if (s) router.push(`/ticker/${encodeURIComponent(s)}`);
  };

  return (
    <div className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">个股共识记录</h1>
      <p className="mt-2 text-sm text-zinc-500">
        查一只标的：谁说过什么、什么时候说的、每一条可下钻到原文。
        本页不预测谁更准。
      </p>

      <form
        className="mt-6 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          go(query);
        }}
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入代码，如 NVDA / 0700.HK / AZN.L"
          className="flex-1 rounded border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-zinc-500"
        />
        <button
          type="submit"
          className="inline-flex items-center gap-1 rounded bg-zinc-900 px-4 py-2 text-sm text-white hover:bg-zinc-700"
        >
          <Search className="h-4 w-4" /> 查询
        </button>
      </form>

      <div className="mt-4 flex gap-2 text-xs text-zinc-500">
        试试：
        {EXAMPLES.map((s) => (
          <button
            key={s}
            onClick={() => go(s)}
            className="rounded border border-zinc-200 px-2 py-0.5 font-mono hover:bg-zinc-50"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
