"use client";

import React from "react";
import Link from "next/link";
import {
  AudioLines,
  ArrowUpRight,
  BrainCircuit,
  ChevronRight,
  FileImage,
  FileText,
  FolderKanban,
  Info,
  ScanSearch,
  ShieldCheck,
  Tag,
  Eye,
  X,
  Loader2
} from "lucide-react";
import type { AssetFile } from "@/lib/contracts";
import { cn } from "@/lib/utils";

interface EnrichmentContent {
  id: string;
  name: string;
  type: string;
  creatorName: string;
  contentType: string;
  sourcePath: string;
  manifestPath: string;
}

interface InspectorPanelProps {
  onOpenStudio: () => void;
  onClose?: () => void;
  selectedAsset: AssetFile | null;
  tier: string;
}

function renderIconForType(type: string) {
  if (type === "mp3" || type === "wav") {
    return <AudioLines className="w-5 h-5 text-foreground/70" strokeWidth={1.6} />;
  }
  if (type === "png" || type === "jpg" || type === "jpeg" || type === "webp") {
    return <FileImage className="w-5 h-5 text-foreground/70" strokeWidth={1.6} />;
  }
  if (type === "folder") {
    return <FolderKanban className="w-5 h-5 text-foreground/70" strokeWidth={1.6} />;
  }
  return <FileText className="w-5 h-5 text-foreground/70" strokeWidth={1.6} />;
}

function getFileColorClass(type: string) {
  if (type === "mp3" || type === "wav") return "bg-stone-100 text-stone-600 border border-stone-200";
  if (type === "pdf") return "bg-morningstar-red/5 text-morningstar-red border border-morningstar-red/10";
  if (type === "png" || type === "jpg" || type === "jpeg") return "bg-amber-500/10 text-amber-500 border border-amber-500/20";
  if (type === "folder") return "bg-blue-50 text-blue-600 border border-blue-100";
  return "bg-stone-100 text-stone-600 border border-stone-200";
}

function buildEvidenceSummary(type: string, tier: string) {
  if (tier === "F1") {
    return "当前视图强调标准化证据，应优先核查 ContentBlock 拆分质量和原文保留是否可用于后续锚定。";
  }
  if (tier === "F5" || tier === "F6") {
    return "当前视图已进入事件候选或人工复核阶段，应核查字段完整性、action chain 结构和歧义来源。";
  }
  if (type === "mp3" || type === "wav") {
    return "该资产是音频类素材，最关键的 provenance 是 transcript 来源、段落切分和黑话实体映射。";
  }
  if (type === "png" || type === "jpg" || type === "jpeg" || type === "webp") {
    return "该资产是图像类素材，最关键的 provenance 是视觉描述、版面顺序与文字证据块的可追踪性。";
  }
  return "当前资产尚处于较早阶段，建议先确认来源、命名、归档位置和后续流转目标。";
}

export function InspectorPanel({
  onOpenStudio,
  onClose,
  selectedAsset,
  tier,
}: InspectorPanelProps) {
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [entityContents, setEntityContents] = React.useState<EnrichmentContent[]>([]);
  const [loadingContents, setLoadingContents] = React.useState(false);
  const hasAsset = Boolean(selectedAsset);
  const evidenceSummary = buildEvidenceSummary(selectedAsset?.type ?? "", tier);
  const isExecuted = tier === "F5" || tier === "F6";

  // Fetch F2 Anchor entity contents when folder is selected
  React.useEffect(() => {
    if (tier === "F2" && selectedAsset?.type === "folder" && selectedAsset.contentId?.startsWith("enrichment:")) {
      const entityName = selectedAsset.contentId.replace("enrichment:", "");
      setLoadingContents(true);
      fetch(`/api/files/enrichment/${encodeURIComponent(entityName)}`)
        .then(res => res.json())
        .then(data => {
          setEntityContents(data.contents || []);
        })
        .catch(err => {
          console.error("Failed to fetch entity contents:", err);
          setEntityContents([]);
        })
        .finally(() => setLoadingContents(false));
    } else {
      setEntityContents([]);
    }
  }, [tier, selectedAsset?.id, selectedAsset?.contentId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Compute best path to preview
  // For image assets, prefer sourcePath (actual image) over evidencePath (OCR .md text)
  const imageTypes = new Set(["png", "jpg", "jpeg", "webp", "gif"]);
  const isImageAsset = selectedAsset?.type ? imageTypes.has(selectedAsset.type) : false;
  let previewPath = isImageAsset
    ? (selectedAsset?.sourcePath || selectedAsset?.evidencePath)
    : (selectedAsset?.evidencePath || selectedAsset?.sourcePath);
  let previewType = previewPath ? previewPath.split('.').pop()?.toLowerCase() : null;

  // Enforce Word doc fallback to MD
  if (previewType === 'docx') {
    if (selectedAsset?.evidencePath?.endsWith('.md')) {
      previewPath = selectedAsset.evidencePath;
      previewType = 'md';
    }
  }

  // For F2 folders, find preview path from entity contents
  const firstEntityContent = entityContents[0];
  if (tier === "F2" && selectedAsset?.type === "folder" && firstEntityContent?.sourcePath) {
    previewPath = firstEntityContent.sourcePath;
    previewType = previewPath.split('.').pop()?.toLowerCase();
  }

  // To view, we need path relative to data dir if the backend resolves it
  const previewUrl = previewPath ? `/api/streams/download?path=${encodeURIComponent(previewPath)}` : null;

  if (!hasAsset) {
    return (
      <aside className="w-96 bg-[rgba(255,252,247,0.72)] border-l border-[rgba(95,67,40,0.12)] flex flex-col p-8 z-10 relative backdrop-blur-xl">
        <button 
          onClick={onClose}
          className="absolute top-6 right-6 p-2 text-stone-300 hover:text-morningstar-red transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
        <div className="flex-1 flex flex-col justify-center items-center">
          <Info className="w-10 h-10 text-stone-300 mb-4" strokeWidth={1} />
          <p className="text-xs font-bold text-foreground/40 text-center uppercase tracking-widest">
            选择一个资产后，这里会显示它的 provenance、证据摘要与流转历史
          </p>
        </div>
      </aside>
    );
  }

  return (
    <>
    <aside className="w-96 bg-[rgba(255,252,247,0.72)] border-l border-[rgba(95,67,40,0.12)] flex flex-col z-10 backdrop-blur-xl">
      <div className="h-20 border-b border-[rgba(95,67,40,0.12)] px-8 flex items-center justify-between text-foreground/50 text-[10px] font-bold uppercase tracking-[0.2em]">
        <div className="flex items-center gap-3">
          <Info className="w-4 h-4 text-morningstar-red" strokeWidth={1.5} />
          Provenance Rail
        </div>
        <div className="flex items-center gap-2">
          {previewUrl && (
            <button 
              onClick={() => setPreviewOpen(true)}
              className="flex items-center gap-2 hover:text-morningstar-red transition-colors cursor-pointer bg-white border px-2 py-1 rounded shadow-sm"
            >
              <Eye className="w-3 h-3" /> PREVIEW
            </button>
          )}
          <button 
            onClick={onClose}
            className="p-1.5 hover:text-morningstar-red transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto finer-scrollbar p-8 space-y-8">
        <section className="space-y-4">
          <div className="text-[10px] text-morningstar-red font-bold uppercase tracking-widest">
            Selected Asset
          </div>

          <div className="rounded-2xl border border-[rgba(95,67,40,0.12)] bg-white/80 p-5 shadow-sm">
            <div className="flex items-start gap-4">
              <div className="rounded-xl border border-[rgba(95,67,40,0.12)] bg-[rgba(99,76,55,0.04)] p-3">
                {renderIconForType(selectedAsset?.type ?? "file")}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold text-foreground truncate" title={selectedAsset?.name}>
                  {selectedAsset?.name}
                </div>
                <div className="mt-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] text-[var(--ink-soft)]">
                  <span>{selectedAsset?.type}</span>
                  <span className="h-1 w-1 rounded-full bg-stone-300" />
                  <span>{selectedAsset?.size}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <span className="rounded-full border border-[rgba(95,67,40,0.12)] bg-[rgba(99,76,55,0.04)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                    {selectedAsset?.creatorName || "unknown creator"}
                  </span>
                  <span className="rounded-full border border-[rgba(95,67,40,0.12)] bg-[rgba(99,76,55,0.04)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--ink-soft)]">
                    {selectedAsset?.contentType || "untyped"}
                  </span>
                </div>
                <div className="mt-3 inline-flex items-center rounded-full border border-[rgba(159,29,34,0.18)] bg-[rgba(159,29,34,0.07)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-morningstar-red">
                  Current stage {tier}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* F2 Anchor Entity Contents */}
        {tier === "F2" && selectedAsset?.type === "folder" && (
          <section className="space-y-4">
            <div className="flex items-center gap-2 text-[10px] text-foreground/40 font-bold uppercase tracking-widest">
              <FolderKanban className="w-3.5 h-3.5" strokeWidth={1.5} />
              关联内容 ({entityContents.length})
            </div>
            <div className="rounded-2xl border border-[rgba(95,67,40,0.12)] bg-white/70 p-4 max-h-64 overflow-y-auto finer-scrollbar">
              {loadingContents ? (
                <div className="flex items-center justify-center py-4 text-foreground/40">
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  <span className="text-xs">加载中...</span>
                </div>
              ) : entityContents.length === 0 ? (
                <div className="text-xs text-foreground/40 py-2">无关联内容</div>
              ) : (
                <div className="space-y-2">
                  {entityContents.map((content) => (
                    <div
                      key={content.id}
                      className="flex items-center gap-3 p-2 bg-white border border-stone-200 rounded-sm hover:border-morningstar-red/20 transition-all"
                    >
                      <div className={cn("p-1.5 rounded-sm", getFileColorClass(content.type))}>
                        {renderIconForType(content.type)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium truncate">{content.name}</div>
                        <div className="text-[9px] text-foreground/40">{content.creatorName}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        )}

        <section className="space-y-4">
          <div className="flex items-center gap-2 text-[10px] text-foreground/40 font-bold uppercase tracking-widest">
            <ShieldCheck className="w-3.5 h-3.5" strokeWidth={1.5} />
            证据链审计 · Audit Trace
          </div>

          <div className="rounded-2xl border border-[rgba(95,67,40,0.12)] bg-white/70 p-5">
            <p className="text-sm leading-relaxed text-foreground/80">
              {isExecuted
                ? "该资产已进入执行 / 复核阶段。在审计台可逐层核验其 TradeAction 的 F3 Intent → F4 Policy → F5 执行链，以及原文证据高亮与四时钟 ExecutionTiming。"
                : "完成 F3 Intent → F4 Policy → F5 执行后，可在审计台逐层核验证据链。当前阶段尚未生成 TradeAction。"}
            </p>
            <Link
              href="/audit"
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-sm bg-morningstar-red px-4 py-2.5 text-xs font-bold uppercase tracking-widest text-white shadow-md transition-all hover:bg-red-700 hover:shadow-lg"
            >
              <ShieldCheck className="h-4 w-4" strokeWidth={1.8} />
              打开证据链审计台
              <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={2} />
            </Link>
            <p className="mt-2 text-center text-[10px] text-foreground/40">
              展示 F3→F4→F5 canonical trace（当前为演示数据）
            </p>
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-2 text-[10px] text-foreground/40 font-bold uppercase tracking-widest">
            <ScanSearch className="w-3.5 h-3.5" strokeWidth={1.5} />
            Evidence Readiness
          </div>
          <div className="rounded-2xl border border-[rgba(95,67,40,0.12)] bg-white/70 p-5 text-sm leading-relaxed text-foreground/80">
            {evidenceSummary}
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-2 text-[10px] text-foreground/40 font-bold uppercase tracking-widest">
            <BrainCircuit className="w-3.5 h-3.5" strokeWidth={1.5} />
            Machine Notes
          </div>
          <div className="rounded-2xl border border-[rgba(95,67,40,0.12)] bg-white/70 p-5">
            <div className="text-sm leading-relaxed text-foreground/80">
              {selectedAsset?.summary || "当前版本建议把每个资产都绑定到来源、解析证据、候选事件和人工修改历史，避免出现“只有结果，没有证据”的漂浮事件。"}
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-2 text-[10px] text-foreground/40 font-bold uppercase tracking-widest">
            <Tag className="w-3.5 h-3.5" strokeWidth={1.5} />
            Semantic Anchors
          </div>
          <div className="flex flex-wrap gap-2">
            {["source", "manifest", "evidence", "action-chain"].map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-[rgba(95,67,40,0.12)] bg-white/80 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-foreground/70"
              >
                {tag}
              </span>
            ))}
            {selectedAsset?.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full border border-[rgba(159,29,34,0.12)] bg-[rgba(159,29,34,0.05)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-morningstar-red"
              >
                {tag}
              </span>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-2 text-[10px] text-foreground/40 font-bold uppercase tracking-widest mt-6">
            <FolderKanban className="w-3.5 h-3.5" strokeWidth={1.5} />
            Physical Paths
          </div>
          <div className="space-y-2">
            {[
              { label: "SOURCE", path: selectedAsset?.sourcePath },
              { label: "MANIFEST", path: selectedAsset?.manifestPath },
              { label: "EVIDENCE", path: selectedAsset?.evidencePath },
              { label: "CANDIDATE", path: selectedAsset?.candidateEventPath },
              { label: "APPROVED", path: selectedAsset?.approvedEventPath },
            ].map(({ label, path }) => path ? (
              <div key={label} className="flex flex-col gap-1 p-3 rounded-md bg-[rgba(99,76,55,0.04)] border border-[rgba(95,67,40,0.12)]">
                <span className="text-[9px] font-bold text-[var(--ink-soft)] uppercase tracking-widest">{label}</span>
                <span 
                  className="text-[11px] font-mono text-foreground/70 break-all select-all hover:text-morningstar-red cursor-text transition-colors"
                  title="Double click to select path"
                >
                  {path}
                </span>
              </div>
            ) : null)}
          </div>
        </section>
      </div>

      <div className="p-8 border-t border-[rgba(95,67,40,0.12)] bg-[rgba(255,252,247,0.54)]">
        <button
          onClick={onOpenStudio}
          className="w-full bg-morningstar-red hover:bg-red-700 text-white py-3.5 rounded-sm text-xs font-bold uppercase tracking-widest shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 group"
        >
          Open Review Workbench
          <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" strokeWidth={2} />
        </button>
      </div>
    </aside>

    {previewOpen && previewUrl && selectedAsset && (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-8 bg-black/40 backdrop-blur-sm">
        <div className="bg-[#fcfbf9] w-full max-w-5xl h-[85vh] rounded-md shadow-2xl flex flex-col overflow-hidden border border-stone-200">
          <div className="flex items-center justify-between p-4 border-b bg-white">
            <div className="flex items-center gap-3">
              {renderIconForType(previewType ?? "file")}
              <h2 className="text-sm font-bold truncate max-w-xl">{selectedAsset.name}</h2>
            </div>
            <button
              onClick={() => setPreviewOpen(false)}
              className="p-2 bg-stone-100 hover:bg-red-50 hover:text-red-500 rounded-sm transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-auto bg-stone-100/50 flex flex-col">
            {['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(previewType ?? '') ? (
              <div className="flex-1 flex items-center justify-center p-8">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={previewUrl} alt="Preview" className="max-w-full max-h-full object-contain shadow-sm border border-stone-200 bg-white" />
              </div>
            ) : previewType === 'pdf' ? (
              <iframe src={previewUrl} className="w-full h-full border-0" title="PDF Preview" />
            ) : ['md', 'txt'].includes(previewType ?? '') ? (
              <iframe src={previewUrl} className="w-full h-full border-0 bg-white" title="Text Preview" />
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-stone-400 gap-4">
                <Info className="w-12 h-12 opacity-20" />
                <p className="text-sm font-medium tracking-widest uppercase">No internal preview available for {previewType}.</p>
                <a href={previewUrl} download className="text-morningstar-red text-xs hover:underline mt-2">Download File</a>
              </div>
            )}
          </div>
        </div>
      </div>
    )}
    </>
  );
}
