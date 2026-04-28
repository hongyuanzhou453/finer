"use client";

import React, { useEffect, useState } from "react";
import { Download, UploadCloud, RefreshCw, Layers, CheckCircle2, AlertCircle, MessageSquare, Database } from "lucide-react";
import { cn } from "@/lib/utils";

type FeishuChat = {
  chat_id: string;
  name: string;
};

type NLMNotebook = {
  id: string;
  title: string;
  source_count: number;
};

type PoolFile = {
  name: string;
  type: string;
  origin: string;
  date: string;
  size_bytes: number;
  previewable: boolean;
  download_path: string;
};

export function IntegrationsHub() {
  const [chats, setChats] = useState<FeishuChat[]>([]);
  const [notebooks, setNotebooks] = useState<NLMNotebook[]>([]);
  const [poolFiles, setPoolFiles] = useState<PoolFile[]>([]);
  
  const [selectedChats, setSelectedChats] = useState<Set<string>>(new Set());
  const [selectedNotebooks, setSelectedNotebooks] = useState<Set<string>>(new Set());
  const [selectedPoolFiles, setSelectedPoolFiles] = useState<Set<string>>(new Set());
  
  const [fetching, setFetching] = useState(false);
  const [fetchingNlm, setFetchingNlm] = useState(false);
  const [importing, setImporting] = useState(false);
  
  useEffect(() => {
    loadChats();
    loadNotebooks();
    loadPool();
  }, []);

  const loadChats = async () => {
    try {
      const res = await fetch("/api/integrations/feishu/chats");
      const data = await res.json();
      setChats(data.chats || []);
    } catch(e) { console.error(e); }
  };

  const loadNotebooks = async () => {
    try {
      const res = await fetch("/api/integrations/nlm/notebooks");
      const data = await res.json();
      setNotebooks(data.notebooks || []);
    } catch(e) { console.error(e); }
  };

  const loadPool = async () => {
    try {
      const res = await fetch("/api/integrations/pool");
      const data = await res.json();
      setPoolFiles(data.files || []);
    } catch(e) { console.error(e); }
  };

  const handleFetch = async () => {
    if (selectedChats.size === 0) return;
    setFetching(true);
    try {
      for (const chatId of selectedChats) {
        await fetch("/api/integrations/feishu/fetch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: chatId })
        });
      }
      setSelectedChats(new Set());
      await loadPool();
    } catch (e) {
      console.error(e);
    } finally {
      setFetching(false);
    }
  };

  const handleFetchNlm = async () => {
    if (selectedNotebooks.size === 0) return;
    setFetchingNlm(true);
    try {
      for (const notebookId of selectedNotebooks) {
        await fetch("/api/integrations/nlm/fetch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ notebook_id: notebookId })
        });
      }
      setSelectedNotebooks(new Set());
      await loadPool();
    } catch (e) {
      console.error(e);
    } finally {
      setFetchingNlm(false);
    }
  };

  const handleImport = async () => {
    if (selectedPoolFiles.size === 0) return;
    setImporting(true);
    
    // Process feishu and nlm separately based on their origin
    try {
      const poolFeishu = Array.from(selectedPoolFiles).filter(name => poolFiles.find(f => f.name === name)?.origin === "feishu");
      const poolNlm = Array.from(selectedPoolFiles).filter(name => poolFiles.find(f => f.name === name)?.origin === "nlm");
      
      if (poolFeishu.length > 0) {
        await fetch("/api/integrations/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filenames: poolFeishu, pool_type: "feishu" })
        });
      }
      if (poolNlm.length > 0) {
        await fetch("/api/integrations/import", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filenames: poolNlm, pool_type: "nlm" })
        });
      }
      
      setSelectedPoolFiles(new Set());
      await loadPool();
    } catch (e) {
      console.error(e);
    } finally {
      setImporting(false);
    }
  };
  
  const toggleChat = (id: string) => {
    const next = new Set(selectedChats);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedChats(next);
  };
  
  const toggleNotebook = (id: string) => {
    const next = new Set(selectedNotebooks);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedNotebooks(next);
  };
  
  const togglePoolFile = (name: string) => {
    const next = new Set(selectedPoolFiles);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setSelectedPoolFiles(next);
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col bg-stone-50/50">
      <div className="p-8 border-b bg-white">
        <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-3">
          <Layers className="text-morningstar-red w-6 h-6" />
          Sync & Integrations Hub
        </h1>
        <p className="mt-2 text-sm text-[var(--ink-soft)]">
          两段式同步架构：从飞书和 NotebookLM 拉取原始资产到暂存盘，再按需清洗入库。
        </p>
      </div>
      
      <div className="flex-1 flex overflow-hidden">
        {/* Left Column: Fetch from External */}
        <div className="w-1/2 border-r p-8 overflow-y-auto finer-scrollbar">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-sm font-bold uppercase tracking-widest text-[var(--ink-soft)] flex items-center gap-2">
              <Download className="w-4 h-4" />
               1. Fetch Available Sources
            </h2>
            <button 
              onClick={handleFetch}
              disabled={selectedChats.size === 0 || fetching}
              className={cn(
                "px-4 py-1.5 text-xs font-bold uppercase tracking-widest text-white rounded-sm transition-all",
                (selectedChats.size === 0 || fetching) ? "bg-stone-300" : "bg-morningstar-red hover:bg-morningstar-red/90"
              )}
            >
              {fetching ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Fetch Selected"}
            </button>
          </div>
          
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase text-stone-500">Feishu Watched Chats</h3>
            {chats.map(chat => (
              <div 
                key={chat.chat_id}
                onClick={() => toggleChat(chat.chat_id)}
                className={cn(
                  "flex items-center gap-4 p-4 border rounded-sm cursor-pointer transition-all",
                  selectedChats.has(chat.chat_id) ? "border-morningstar-red/30 bg-morningstar-red/5 ring-1 ring-morningstar-red/10" : "bg-white border-stone-200 hover:border-morningstar-red/20"
                )}
              >
                <div className="w-8 h-8 rounded-full bg-stone-100 flex items-center justify-center">
                  <MessageSquare className="w-4 h-4 text-stone-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold truncate">{chat.name}</p>
                  <p className="text-[10px] text-stone-400 font-mono mt-0.5">{chat.chat_id}</p>
                </div>
                {selectedChats.has(chat.chat_id) && <CheckCircle2 className="w-5 h-5 text-morningstar-red" />}
              </div>
            ))}
            {chats.length === 0 && <div className="p-4 text-xs text-stone-500 border border-dashed rounded-sm">No watched chats found in configs/feishu.yaml</div>}
          </div>

          <div className="mt-8 flex items-center justify-between mb-6">
            <h2 className="text-sm font-bold uppercase tracking-widest text-[var(--ink-soft)] flex items-center gap-2">
              <Download className="w-4 h-4" />
               Fetch from NotebookLM
            </h2>
            <button 
              onClick={handleFetchNlm}
              disabled={selectedNotebooks.size === 0 || fetchingNlm}
              className={cn(
                "px-4 py-1.5 text-xs font-bold uppercase tracking-widest text-white rounded-sm transition-all",
                (selectedNotebooks.size === 0 || fetchingNlm) ? "bg-stone-300" : "bg-morningstar-red hover:bg-morningstar-red/90"
              )}
            >
              {fetchingNlm ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Fetch NLM"}
            </button>
          </div>
          
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase text-stone-500">Accessible Notebooks</h3>
            {notebooks.map(nb => (
              <div 
                key={nb.id}
                onClick={() => toggleNotebook(nb.id)}
                className={cn(
                  "flex items-center gap-4 p-4 border rounded-sm cursor-pointer transition-all",
                  selectedNotebooks.has(nb.id) ? "border-morningstar-red/30 bg-morningstar-red/5 ring-1 ring-morningstar-red/10" : "bg-white border-stone-200 hover:border-morningstar-red/20"
                )}
              >
                <div className="w-8 h-8 rounded-full bg-stone-100 flex items-center justify-center">
                  <Database className="w-4 h-4 text-stone-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold truncate">{nb.title}</p>
                  <p className="text-[10px] text-stone-400 font-mono mt-0.5">{nb.source_count} sources • {nb.id.split("-")[0]}</p>
                </div>
                {selectedNotebooks.has(nb.id) && <CheckCircle2 className="w-5 h-5 text-morningstar-red" />}
              </div>
            ))}
            {notebooks.length === 0 && <div className="p-4 text-xs text-stone-500 border border-dashed rounded-sm">No NotebookLM notebooks found or CLI not configured.</div>}
          </div>
        </div>

        {/* Right Column: Pool to Intake */}
        <div className="w-1/2 p-8 overflow-y-auto finer-scrollbar bg-stone-50 flex flex-col">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-sm font-bold uppercase tracking-widest text-[var(--ink-soft)] flex items-center gap-2">
              <UploadCloud className="w-4 h-4" />
               2. Sync Pool & Import
            </h2>
            <button 
              onClick={handleImport}
              disabled={selectedPoolFiles.size === 0 || importing}
              className={cn(
                "px-4 py-1.5 text-xs font-bold uppercase tracking-widest text-white rounded-sm transition-all",
                (selectedPoolFiles.size === 0 || importing) ? "bg-stone-300" : "bg-[var(--accent-teal)] hover:opacity-90"
              )}
            >
              {importing ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Import to F0"}
            </button>
          </div>
          
          <div className="flex-1 space-y-2">
            {poolFiles.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-stone-400 gap-3">
                <AlertCircle className="w-8 h-8 opacity-20" />
                <p className="text-xs font-medium tracking-widest uppercase">暂存盘目前为空</p>
              </div>
            ) : (
              poolFiles.map(file => (
                <div 
                  key={file.name}
                  onClick={() => togglePoolFile(file.name)}
                  className={cn(
                    "flex items-center p-3 text-sm border rounded-sm cursor-pointer transition-all",
                    selectedPoolFiles.has(file.name) ? "border-[var(--accent-teal)] bg-[var(--accent-teal)]/5" : "bg-white border-stone-200 hover:border-stone-300"
                  )}
                >
                  <div className="flex-1 min-w-0 pr-4">
                    <p className="text-[13px] font-bold truncate">{file.name}</p>
                    <div className="flex gap-2 items-center mt-1 text-[10px] uppercase font-bold text-stone-400 tabular-nums">
                      <span className="bg-stone-100 px-1.5 py-0.5 rounded-sm">{file.origin}</span>
                      <span>{(file.size_bytes / 1024).toFixed(0)} KB</span>
                    </div>
                  </div>
                  {selectedPoolFiles.has(file.name) && <CheckCircle2 className="w-4 h-4 text-[var(--accent-teal)]" />}
                </div>
              ))
            )}
          </div>
          
        </div>
      </div>
    </div>
  );
}
