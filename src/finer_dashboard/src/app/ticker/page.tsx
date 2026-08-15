"use client";

/**
 * /ticker — 个股共识入口：输入代码，跳转到 /ticker/[symbol]。
 *
 * 版式（2026-08-13）：与 /ticker/[symbol] 共用报头横规与墨色 token，
 * 避免入口页与详情页看起来像两个产品。
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { Disclosure, Masthead } from "@/components/crd/primitives";

const EXAMPLES = ["NVDA", "0700.HK", "AZN.L", "600519.SS"];

export default function TickerIndexPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const go = (symbol: string) => {
    const s = symbol.trim();
    if (s) router.push(`/ticker/${encodeURIComponent(s)}`);
  };

  return (
    <div className="finer-scrollbar h-full w-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-14">
        <Masthead
          eyebrow="FINER OS · 个股共识记录"
          title="个股共识记录"
          suffix="按代码查记录"
          lede="查一只标的：谁说过什么、什么时候说的、每一条可下钻到原文。本页不预测谁更准。"
        />

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
            className="flex-1 rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] px-3 py-2 font-mono text-[13px] outline-none transition-colors focus:border-[var(--foreground)]"
          />
          <button
            type="submit"
            className="inline-flex items-center gap-1.5 rounded-sm bg-[var(--foreground)] px-4 py-2 text-[13px] text-[var(--surface-strong)] transition-colors hover:bg-[var(--morningstar-red)]"
          >
            <Search className="h-3.5 w-3.5" /> 查询
          </button>
        </form>

        <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-[var(--ink-soft)]">
          试试：
          {EXAMPLES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => go(s)}
              className="rounded-sm border border-[var(--table-border)] px-2 py-0.5 font-mono tabular-nums transition-colors hover:border-[var(--foreground)] hover:text-[var(--foreground)]"
            >
              {s}
            </button>
          ))}
        </div>

        <div className="mt-7">
          {/* 整段写成单个字符串字面量：JSX 会把源码换行折成空格，中文里那是可见的破洞。 */}
          <Disclosure title="覆盖边界">
            {
              "语料是静态档案而非活水：多数标的的最新报告已有数月，详情页会在页头标出该标的的陈旧度。未被已接入信源覆盖的代码会返回空记录，这不代表「没有观点」，只代表「本库没有」。"
            }
          </Disclosure>
        </div>
      </div>
    </div>
  );
}
