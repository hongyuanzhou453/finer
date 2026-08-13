"use client";

import { useState } from "react";
import { BookOpen, ChevronDown, ChevronRight, FileWarning } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DeepSummary } from "@/lib/contracts";
import { SectionLabel } from "./primitives";

/**
 * M3 研报深摘要面板。
 *
 * 三条硬约束（见 docs/specs/2026-07-25-burn-asset-consumption-design.md §5.4）：
 * 1. 必须标注「LLM 生成，非券商原文」+ 生成模型 —— disclaimer 常驻，不折叠。
 * 2. 未命中显示「未生成深摘要」，绝不用短摘要冒充。
 * 3. 数字以原文为准的提示随摘要一起出现（图表类数据是已知弱项）。
 */

/** 内联 `**粗体**` → <strong>。T8 输出大量 `**目标价**:` 式标注，不处理会满屏星号。 */
function renderInline(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") && p.length > 4 ? (
      <strong key={i} className="font-semibold text-foreground/90">
        {p.slice(2, -2)}
      </strong>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}

/** 极简 markdown 渲染：只认 T8 产出的 `## 小节` / `- 列表` / `N. 编号` / 段落。 */
function renderSummary(md: string) {
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = (key: string) => {
    if (!list.length) return;
    blocks.push(
      <ul key={`ul-${key}`} className="ml-4 list-disc space-y-1">
        {list.map((li, i) => (
          <li key={i} className="text-[12px] leading-6 text-foreground/80">
            {renderInline(li)}
          </li>
        ))}
      </ul>,
    );
    list = [];
  };
  md.split("\n").forEach((raw, idx) => {
    const line = raw.trim();
    if (!line) {
      flush(String(idx));
      return;
    }
    if (line.startsWith("## ")) {
      flush(String(idx));
      blocks.push(
        <div key={`h-${idx}`} className="mt-3 first:mt-0">
          <SectionLabel>{line.slice(3)}</SectionLabel>
        </div>,
      );
      return;
    }
    if (/^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
      list.push(line.replace(/^[-*]\s+/, "").replace(/^\d+\.\s+/, ""));
      return;
    }
    flush(String(idx));
    blocks.push(
      <p key={`p-${idx}`} className="text-[12px] leading-6 text-foreground/80">
        {renderInline(line)}
      </p>,
    );
  });
  flush("end");
  return blocks;
}

export function DeepSummaryPanel({ summary }: { summary: DeepSummary | null | undefined }) {
  const [open, setOpen] = useState(false);

  if (!summary) {
    // 覆盖诚实性：明确说没有，而不是安静地什么都不显示（后者会被读成"这份没内容"）
    return (
      <div className="rounded-sm border border-dashed border-[var(--table-border)] bg-[var(--surface-strong)] px-3 py-2.5">
        <div className="flex items-center gap-1.5 text-[11px] text-foreground/45">
          <FileWarning className="h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
          本报告未生成深摘要（深摘要覆盖为部分覆盖，不代表该报告内容缺失）
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-sm border border-[var(--table-border)] bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left transition-colors hover:bg-[var(--surface-strong)]"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-foreground/45" strokeWidth={2} />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-foreground/45" strokeWidth={2} />
        )}
        <BookOpen className="h-3.5 w-3.5 shrink-0 text-[var(--accent-gold)]" strokeWidth={1.8} />
        <span className="text-[12px] font-medium text-foreground/85">研报深摘要</span>
        <span className="text-[11px] text-foreground/40">
          {summary.broker ?? "—"}
          {summary.report_date ? ` · ${summary.report_date}` : ""} · {summary.n_chars} 字
        </span>
      </button>

      {/* 免责声明常驻（不随折叠隐藏）——它是展示这段内容的前提条件 */}
      <div
        className={cn(
          "border-t border-[var(--grid-line)] px-3.5 py-1.5 text-[10px] leading-4 text-foreground/45",
          open ? "" : "border-t-0 pt-0",
        )}
      >
        {summary.disclaimer}
        <span className="ml-1 text-foreground/35">（生成模型 {summary.generated_by}）</span>
      </div>

      {open && (
        <div className="max-h-[520px] overflow-y-auto border-t border-[var(--grid-line)] px-3.5 py-3">
          {renderSummary(summary.summary)}
        </div>
      )}
    </div>
  );
}
