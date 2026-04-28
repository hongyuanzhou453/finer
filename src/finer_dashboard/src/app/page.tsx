"use client";

import { Sidebar } from "@/components/layout/sidebar";
import { MainBoard } from "@/components/layout/main-board";
import { InspectorPanel } from "@/components/layout/inspector-panel";
import { AnnotationWorkbench } from "@/components/studio/annotation-workbench";
import { IntegrationsHub } from "@/components/layout/integrations-hub";
import { DataSourceConfig } from "@/components/data-source-config";
import { SourceFilter } from "@/components/layout/source-filter";
import { FileAudio, FileImage, FileText, ChevronRight, ChevronDown, Loader2, Database, FolderKanban } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AssetFile, SourceGroup, SourceType } from "@/lib/contracts";
import { useState, useEffect, useCallback } from "react";

type EnrichmentContent = {
  id: string;
  name: string;
  type: string;
  creatorName: string;
  contentType: string;
  sourcePath: string;
  manifestPath: string;
};

type WorkflowView = {
  id: string;
  tier: string;
  title: string;
  subtitle: string;
  emptyTitle: string;
  emptyHint: string;
  importLabel: string;
  panelLabel: string;
};

const WORKFLOW_VIEWS: WorkflowView[] = [
  {
    id: "intake",
    tier: "F0",
    title: "接入台 / INTAKE",
    subtitle: "多源内容接入与原始文件归档，建立来源锚点。",
    emptyTitle: "接入队列为空",
    emptyHint: "导入新文件，或继续从飞书同步新的原始素材。",
    importLabel: "Import Asset",
    panelLabel: "F0 INTAKE",
  },
  {
    id: "standardize",
    tier: "F1",
    title: "标准化台 / STANDARDIZE",
    subtitle: "将原始内容统一转为 ContentEnvelope + ContentBlock，保留证据链。",
    emptyTitle: "标准化队列为空",
    emptyHint: "先完成接入，再在此层进行内容标准化与 Block 拆分。",
    importLabel: "Add Research File",
    panelLabel: "F1 STANDARDIZE",
  },
  {
    id: "anchor",
    tier: "F2",
    title: "锚定台 / ANCHOR",
    subtitle: "质量评估、实体解析、时间锚定，构建可追溯的证据图谱。",
    emptyTitle: "锚定队列为空",
    emptyHint: "标准化完成后，在此层进行质量门控与实体/时间锚定。",
    importLabel: "Enrich Content",
    panelLabel: "F2 ANCHOR",
  },
  {
    id: "execute",
    tier: "F5",
    title: "执行台 / EXECUTE",
    subtitle: "Intent 提取 → Policy 映射 → TradeAction 生成，完整执行链路。",
    emptyTitle: "候选事件队列为空",
    emptyHint: "当前还没有新的事件候选，先完成锚定或运行抽取模块。",
    importLabel: "Queue Extraction",
    panelLabel: "F5 EXECUTE",
  },
  {
    id: "review",
    tier: "F6",
    title: "复核台 / REVIEW",
    subtitle: "在证据、意图链和字段纠正之间做最终的人类判断。",
    emptyTitle: "复核队列为空",
    emptyHint: "当候选事件进入人工校准阶段，这里会成为主工作面。",
    importLabel: "Attach Review Input",
    panelLabel: "F6 REVIEW",
  },
  {
    id: "backtest",
    tier: "F8",
    title: "回测台 / BACKTEST",
    subtitle: "将语言观点映射到市场结果，用可执行规则验证事件质量。",
    emptyTitle: "还没有可展示的回测结果",
    emptyHint: "当事件完成标注并进入评测后，这里会出现结果面板。",
    importLabel: "Attach Benchmark Input",
    panelLabel: "F8 BACKTEST",
  },
];

export default function Home() {
  const [files, setFiles] = useState<AssetFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [tier, setTier] = useState("F1");
  const [showStudio, setShowStudio] = useState(false);
  const [selectedAsset, setSelectedAsset] = useState<AssetFile | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [showInspector, setShowInspector] = useState(true);

  // Source filter state
  const [sourceType, setSourceType] = useState<SourceType | "all">("all");
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [sourceGroups, setSourceGroups] = useState<SourceGroup[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // F2 Anchor enrichment expansion state
  const [expandedEntities, setExpandedEntities] = useState<Set<string>>(new Set());
  const [entityContents, setEntityContents] = useState<Map<string, EnrichmentContent[]>>(new Map());
  const [loadingEntities, setLoadingEntities] = useState<Set<string>>(new Set());

  // Double-click detection state
  const [lastClickTime, setLastClickTime] = useState<number>(0);
  const [lastClickedId, setLastClickedId] = useState<string | null>(null);
  const DOUBLE_CLICK_DELAY = 300; // ms

  const activeView =
    WORKFLOW_VIEWS.find((view) => view.tier === tier) ?? WORKFLOW_VIEWS[1];

  const fetchFiles = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("tier", tier);
      if (sourceType !== "all") {
        params.set("source_type", sourceType);
      }
      if (selectedGroupId) {
        params.set("source_group_id", selectedGroupId);
      }

      const res = await fetch(`/api/files?${params.toString()}`);
      const data = await res.json();
      setFiles(data.files || []);
      if (data.sourceGroups && JSON.stringify(data.sourceGroups) !== JSON.stringify(sourceGroups)) {
        setSourceGroups(data.sourceGroups);
      }
      if (data.files && data.files.length > 0) {
        setSelectedAsset(data.files[0]);
      } else {
        setSelectedAsset(null);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [tier, sourceType, selectedGroupId, sourceGroups]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles, refreshKey]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const urlTier = params.get("tier");
      if (urlTier && WORKFLOW_VIEWS.some(v => v.tier === urlTier)) {
        setTier(urlTier);
      }
    }
  }, []);

  const handleRefreshSource = async () => {
    if (sourceType === "all" || sourceType === "local") return;

    setIsRefreshing(true);
    try {
      const res = await fetch("/api/sources/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_type: sourceType,
          group_id: selectedGroupId,
        }),
      });
      const data = await res.json();
      console.log("Refresh result:", data);
      // Refresh the file list after sync
      setRefreshKey((prev) => prev + 1);
    } catch (err) {
      console.error("Refresh failed:", err);
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleTierChange = (newTier: string) => {
    setTier(newTier);
    setExpandedEntities(new Set()); // Clear expanded entities when changing tier
    if (typeof window !== "undefined") {
      window.history.pushState(null, '', `?tier=${newTier}`);
    }
  };

  // Fetch enrichment entity contents
  const fetchEntityContents = async (entityId: string) => {
    const entityName = entityId.replace("enrichment:", "");
    setLoadingEntities(prev => new Set(prev).add(entityId));

    try {
      const res = await fetch(`/api/files/enrichment/${encodeURIComponent(entityName)}`);
      const data = await res.json();
      setEntityContents(prev => {
        const newMap = new Map(prev);
        newMap.set(entityId, data.contents || []);
        return newMap;
      });
    } catch (err) {
      console.error("Failed to fetch entity contents:", err);
    } finally {
      setLoadingEntities(prev => {
        const newSet = new Set(prev);
        newSet.delete(entityId);
        return newSet;
      });
    }
  };

  const toggleEntityExpansion = (entityId: string) => {
    setExpandedEntities(prev => {
      const newSet = new Set(prev);
      if (newSet.has(entityId)) {
        newSet.delete(entityId);
      } else {
        newSet.add(entityId);
        if (!entityContents.has(entityId)) {
          fetchEntityContents(entityId);
        }
      }
      return newSet;
    });
  };

  // Extract time from fileTimestamp for display on icon
  const getTimeFromTimestamp = (timestamp: string | undefined): string => {
    if (!timestamp) return "";
    // Format: 2026-04-20T20:47:44 -> 04-20 20:47
    const match = timestamp.match(/(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (match) {
      return `${match[1]}-${match[2]} ${match[3]}:${match[4]}`;
    }
    return "";
  };

  const getFileIcon = (type: string) => {
    if (type === "mp3" || type === "wav") return <FileAudio className="w-5 h-5" strokeWidth={1.5} />;
    if (type === "pdf") return <FileText className="w-5 h-5" strokeWidth={1.5} />;
    if (type === "png" || type === "jpg") return <FileImage className="w-5 h-5" strokeWidth={1.5} />;
    if (type === "folder") return <FolderKanban className="w-5 h-5" strokeWidth={1.5} />;
    return <FileText className="w-5 h-5" strokeWidth={1.5} />;
  };

  const getFileColorClass = (type: string) => {
    if (type === "mp3" || type === "wav") return "bg-stone-100 text-stone-600 border border-stone-200";
    if (type === "pdf") return "bg-morningstar-red/5 text-morningstar-red border border-morningstar-red/10";
    if (type === "png" || type === "jpg") return "bg-amber-500/10 text-amber-500 border border-amber-500/20";
    if (type === "folder") return "bg-blue-50 text-blue-600 border border-blue-100";
    return "bg-stone-100 text-stone-600 border border-stone-200";
  };

  // Handle file card click with double-click detection
  const handleFileClick = (file: AssetFile) => {
    const now = Date.now();
    const isSameFile = lastClickedId === file.id;
    const isDoubleClick = isSameFile && (now - lastClickTime) < DOUBLE_CLICK_DELAY;

    // Update click tracking
    setLastClickTime(now);
    setLastClickedId(file.id);

    if (isDoubleClick) {
      // Double click: Open Review Workbench for any file
      setSelectedAsset(file);
      setShowStudio(true);
    } else {
      // Single click: Select asset and show in Inspector
      setSelectedAsset(file);
      // For F5/F6, open studio after delay (allows double-click detection)
      if (tier === "F5" || tier === "F6") {
        const clickId = file.id;
        const clickTime = now;
        setTimeout(() => {
          // Only open studio if no subsequent click occurred on same file
          if (lastClickedId === clickId && Date.now() - clickTime >= DOUBLE_CLICK_DELAY) {
            setShowStudio(true);
          }
        }, DOUBLE_CLICK_DELAY + 50);
      }
    }
  };

  // Handle folder click (F2 Anchor enrichment folders)
  const handleFolderClick = (file: AssetFile) => {
    if (tier === "F2") {
      toggleEntityExpansion(file.id);
    } else {
      handleFileClick(file);
    }
  };

  return (
    <>
      <Sidebar activeTier={tier} onTierChange={handleTierChange} />

      {tier === "Integrations" ? (
        <IntegrationsHub />
      ) : tier === "DataSource" ? (
        <DataSourceConfig />
      ) : (
        <>
          <MainBoard
            title={activeView.title}
            subtitle={activeView.subtitle}
            tier={tier}
            stageLabel={activeView.panelLabel}
            importLabel={activeView.importLabel}
            searchPlaceholder="搜索资产、证据、事件或创作者..."
            onRefresh={() => setRefreshKey(prev => prev + 1)}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            isInspectorOpen={showInspector}
            onToggleInspector={() => setShowInspector(!showInspector)}
            filterComponent={
              <SourceFilter
                sourceType={sourceType}
                groups={sourceGroups}
                selectedGroupId={selectedGroupId}
                onSourceTypeChange={(type) => {
                  setSourceType(type);
                  setSelectedGroupId(null);
                }}
                onGroupChange={setSelectedGroupId}
                onRefresh={handleRefreshSource}
                isRefreshing={isRefreshing}
              />
            }
          >
        {loading ? (
          <div className="h-64 flex flex-col items-center justify-center gap-6 text-foreground/10">
            <Loader2 className="w-10 h-10 animate-spin" strokeWidth={1} />
            <span className="text-[10px] font-bold uppercase tracking-[0.2em]">FETCHING GLOBAL ASSETS...</span>
          </div>
        ) : files.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center gap-4 text-foreground/20 italic">
            <Database className="w-16 h-16 opacity-5 mb-2" strokeWidth={1} />
            <span className="text-xs font-medium uppercase tracking-widest text-center">
              {activeView.emptyTitle}<br/>
              <span className="opacity-50 text-[10px] not-italic mt-2 block">{activeView.emptyHint}</span>
            </span>
          </div>
        ) : viewMode === "grid" ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
            {files.map((file) => {
               const isSelected = selectedAsset?.id === file.id;
               const isExpanded = expandedEntities.has(file.id);
               const isFolder = file.type === "folder";
               const fileTime = getTimeFromTimestamp(file.fileTimestamp);
               const contents = entityContents.get(file.id) || [];
               const isLoading = loadingEntities.has(file.id);

               return (
                 <div key={file.id}>
                   <div
                     onClick={() => {
                       if (isFolder) {
                         handleFolderClick(file);
                       } else {
                         handleFileClick(file);
                       }
                     }}
                     className={cn(
                       "editorial-card group p-6 border cursor-pointer relative",
                       isSelected ? "border-morningstar-red/30 shadow-md ring-1 ring-morningstar-red/10" : "border-stone-200"
                     )}
                   >
                     <div className="flex items-start justify-between mb-8">
                       <div className="relative">
                         <div className={cn("p-3.5 rounded-sm shadow-sm", getFileColorClass(file.type))}>
                           {getFileIcon(file.type)}
                         </div>
                         {fileTime && (
                           <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 text-[8px] font-bold text-foreground/50 bg-white px-1 rounded shadow-sm whitespace-nowrap">
                             {fileTime}
                           </span>
                         )}
                       </div>
                       <div className="flex items-center gap-2">
                         {isFolder && tier === "F2" && (
                           <div className="p-1 rounded hover:bg-stone-100 transition-colors">
                             {isExpanded ? (
                               <ChevronDown className="w-4 h-4 text-foreground/50" />
                             ) : (
                               <ChevronRight className="w-4 h-4 text-foreground/50" />
                             )}
                           </div>
                         )}
                         <div className={cn(
                           "px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest border shadow-sm",
                           tier === "F5" || tier === "F6" ? "border-morningstar-red/20 text-morningstar-red bg-morningstar-red/5" :
                           "border-stone-200 text-foreground/50 bg-white"
                         )}>
                           {file.status}
                         </div>
                       </div>
                     </div>

                     <div className="space-y-3">
                       <h3 className="text-[15px] font-bold leading-tight group-hover:text-morningstar-red transition-colors line-clamp-2">
                         {file.semanticTitle || file.name}
                       </h3>
                       <div className="flex items-center gap-3 text-xs text-foreground/40 font-bold tabular-nums uppercase">
                         {file.fileType && (
                           <>
                             <span className="text-foreground/60">{file.fileType}</span>
                             <span className="w-1 h-1 rounded-full bg-stone-300" />
                           </>
                         )}
                         {file.sourceName && (
                           <>
                             <span className="truncate max-w-[120px]">{file.sourceName}</span>
                             <span className="w-1 h-1 rounded-full bg-stone-300" />
                           </>
                         )}
                         <span>{file.date}</span>
                         <span className="w-1 h-1 rounded-full bg-stone-300" />
                         <span>{file.size}</span>
                       </div>
                     </div>

                     <div className="absolute right-6 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity translate-x-2 group-hover:translate-x-0 duration-300">
                       <div className="w-8 h-8 rounded-full bg-white shadow-md border border-stone-100 flex items-center justify-center">
                         <ChevronRight className="w-4 h-4 text-morningstar-red" strokeWidth={2} />
                       </div>
                     </div>
                   </div>

                   {/* Expanded contents for F2 folders */}
                   {isFolder && isExpanded && tier === "F2" && (
                     <div className="mt-2 ml-4 border-l-2 border-blue-200 pl-4 space-y-2">
                       {isLoading ? (
                         <div className="text-xs text-foreground/40 py-2">加载中...</div>
                       ) : contents.length === 0 ? (
                         <div className="text-xs text-foreground/40 py-2">无关联内容</div>
                       ) : (
                         contents.map((content) => (
                           <div
                             key={content.id}
                             onClick={(e) => {
                               e.stopPropagation();
                               setSelectedAsset({
                                 ...file,
                                 id: content.id,
                                 name: content.name,
                                 type: content.type,
                                 creatorName: content.creatorName,
                                 contentType: content.contentType,
                                 sourcePath: content.sourcePath,
                                 manifestPath: content.manifestPath,
                               });
                             }}
                             className="flex items-center gap-3 p-3 bg-white/80 border border-stone-200 rounded cursor-pointer hover:bg-white hover:border-morningstar-red/20 transition-all"
                           >
                             <div className={cn("p-2 rounded-sm", getFileColorClass(content.type))}>
                               {getFileIcon(content.type)}
                             </div>
                             <div className="flex-1 min-w-0">
                               <div className="text-sm font-medium truncate">{content.name}</div>
                               <div className="text-[10px] text-foreground/40">{content.creatorName}</div>
                             </div>
                           </div>
                         ))
                       )}
                     </div>
                   )}
                 </div>
               );
             })}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {files.map((file) => {
              const isSelected = selectedAsset?.id === file.id;
              const isExpanded = expandedEntities.has(file.id);
              const isFolder = file.type === "folder";
              const fileTime = getTimeFromTimestamp(file.fileTimestamp);
              const contents = entityContents.get(file.id) || [];
              const isLoading = loadingEntities.has(file.id);

              return (
                <div key={file.id}>
                  <div
                    onClick={() => {
                      if (isFolder) {
                        handleFolderClick(file);
                      } else {
                        handleFileClick(file);
                      }
                    }}
                    className={cn(
                      "flex items-center p-4 border rounded-sm cursor-pointer transition-all group",
                      isSelected ? "border-morningstar-red/30 shadow-md ring-1 ring-morningstar-red/10 bg-white" : "border-stone-200 bg-white/60 hover:bg-white"
                    )}
                  >
                    <div className="relative">
                      <div className={cn("p-2 rounded-sm shadow-sm mr-4", getFileColorClass(file.type))}>
                        {getFileIcon(file.type)}
                      </div>
                      {fileTime && (
                        <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 text-[8px] font-bold text-foreground/50 bg-white px-1 rounded shadow-sm whitespace-nowrap">
                          {fileTime}
                        </span>
                      )}
                    </div>
                    <div className="flex-1 flex flex-col justify-center min-w-0">
                      <h3 className="text-[14px] font-bold leading-tight group-hover:text-morningstar-red transition-colors truncate">
                        {file.semanticTitle || file.name}
                      </h3>
                      <span className="text-[11px] text-foreground/40 font-bold tabular-nums uppercase mt-1.5 flex items-center gap-2">
                        {file.fileType && <>{file.fileType} <span className="w-1 h-1 rounded-full bg-stone-300" /></>}
                        {file.sourceName && <><span className="truncate max-w-[100px]">{file.sourceName}</span> <span className="w-1 h-1 rounded-full bg-stone-300" /></>}
                        {file.date} <span className="w-1 h-1 rounded-full bg-stone-300" /> {file.size}
                      </span>
                    </div>

                    <div className="px-4 flex items-center justify-end w-32 border-l border-stone-100 mr-4">
                      {isFolder && tier === "F2" && (
                        <div className="mr-2 p-1 rounded hover:bg-stone-100 transition-colors">
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-foreground/50" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-foreground/50" />
                          )}
                        </div>
                      )}
                      <span className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest border shadow-sm border-stone-200 text-foreground/50 bg-stone-50">
                        {file.status}
                      </span>
                    </div>

                    <div className="w-8 flex justify-center opacity-0 group-hover:opacity-100 transition-opacity translate-x-2 group-hover:translate-x-0 duration-300">
                      <ChevronRight className="w-4 h-4 text-morningstar-red" strokeWidth={2} />
                    </div>
                  </div>

                  {/* Expanded contents for F2 folders */}
                  {isFolder && isExpanded && tier === "F2" && (
                    <div className="mt-1 ml-6 border-l-2 border-blue-200 pl-4 space-y-1">
                      {isLoading ? (
                        <div className="text-xs text-foreground/40 py-2 px-3">加载中...</div>
                      ) : contents.length === 0 ? (
                        <div className="text-xs text-foreground/40 py-2 px-3">无关联内容</div>
                      ) : (
                        contents.map((content) => (
                          <div
                            key={content.id}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedAsset({
                                ...file,
                                id: content.id,
                                name: content.name,
                                type: content.type,
                                creatorName: content.creatorName,
                                contentType: content.contentType,
                                sourcePath: content.sourcePath,
                                manifestPath: content.manifestPath,
                              });
                            }}
                            className="flex items-center gap-3 p-2 bg-white/80 border border-stone-200 rounded cursor-pointer hover:bg-white hover:border-morningstar-red/20 transition-all"
                          >
                            <div className={cn("p-1.5 rounded-sm", getFileColorClass(content.type))}>
                              {getFileIcon(content.type)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-xs font-medium truncate">{content.name}</div>
                              <div className="text-[9px] text-foreground/40">{content.creatorName}</div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </MainBoard>

      {showInspector && (
        <InspectorPanel 
          tier={tier}
          selectedAsset={selectedAsset}
          onOpenStudio={() => setShowStudio(true)} 
          onClose={() => setShowInspector(false)}
        />
      )}

      {showStudio && (
        <AnnotationWorkbench
          asset={selectedAsset}
          onClose={() => setShowStudio(false)}
          onSaved={() => setRefreshKey(prev => prev + 1)}
        />
      )}
      </>
      )}
    </>
  );
}
