"use client";

import { useMemo, useState, type ReactNode } from "react";
import {
  ArrowRight,
  Ban,
  Check,
  ClipboardCheck,
  FileText,
  GitCompare,
  Lock,
  Pencil,
  RotateCw,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  F6_CASES,
  GOLD_TASKS,
  PREFERENCE_PAIRS,
  committalRate,
  scoreExtraction,
} from "@/demo/annotation-data";
import type {
  ActionType,
  AnnotationTaskId,
  ExtractionDraft,
  TradeDirection,
} from "@/demo/types";
import { DemoHeader, type DemoView } from "./demo-header";
import { DIRECTION_META, Stars } from "./demo-workbench";
import { RewardMeter } from "./reward-meter";

const DIRECTIONS: TradeDirection[] = [
  "bullish",
  "bearish",
  "neutral",
  "watchlist",
  "risk_warning",
];

const ACTION_OPTIONS: { value: ActionType; label: string }[] = [
  { value: "long", label: "做多 long" },
  { value: "short", label: "做空 short" },
  { value: "hold", label: "持有 hold" },
  { value: "watch", label: "观望 watch" },
];

const TASKS: { id: AnnotationTaskId; tag: string; title: string; role: string; blurb: string }[] = [
  {
    id: "gold",
    tag: "任务一 · 验证集",
    title: "评测集 Gold 标注",
    role: "人工验证集",
    blurb: "对 held-out 段落人工判定方向/标的/信念，证据不足时弃权。产出模型从未见过的考卷。",
  },
  {
    id: "preference",
    tag: "任务二 · 训练集",
    title: "DPO 偏好对抽检",
    role: "RLHF × RLVR",
    blurb: "对 (rejected, chosen) 偏好对抽检：接受 / 修改 / 剔除。右侧 verifier 给出可验证奖励。",
  },
  {
    id: "f6",
    tag: "任务三 · 环 B",
    title: "F6 字段级修正",
    role: "真实反馈飞轮",
    blurb: "模型 F5 抽取进回测前人工纠错，corrections 组装为 chosen=修正 / rejected=模型原错。",
  },
];

const num = (v: number | null) => (v == null ? "null" : String(v));

// ---- shared draft editor ----------------------------------------------------

function DraftEditor({
  draft,
  onChange,
}: {
  draft: ExtractionDraft;
  onChange: (patch: Partial<ExtractionDraft>) => void;
}) {
  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
          direction
        </div>
        <div className="flex flex-wrap gap-1.5">
          {DIRECTIONS.map((d) => {
            const on = draft.direction === d;
            return (
              <button
                key={d}
                type="button"
                onClick={() => onChange({ direction: d })}
                className={cn(
                  "rounded-sm border px-2 py-1 text-[11px] font-semibold transition-colors",
                  on
                    ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.06)] text-morningstar-red"
                    : "border-[var(--table-border)] bg-white text-foreground/60 hover:border-foreground/30",
                )}
              >
                {DIRECTION_META[d].label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
            ticker
          </div>
          <input
            type="text"
            value={draft.ticker}
            onChange={(e) => onChange({ ticker: e.target.value })}
            placeholder="600519.SH / NONE"
            className="w-full rounded-sm border border-[var(--table-border)] bg-white px-2 py-1.5 font-mono text-[12px] text-foreground outline-none focus:border-morningstar-red/50"
          />
        </div>
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
            action
          </div>
          <select
            value={draft.action}
            onChange={(e) => onChange({ action: e.target.value as ActionType })}
            className="w-full rounded-sm border border-[var(--table-border)] bg-white px-2 py-1.5 text-[12px] text-foreground outline-none focus:border-morningstar-red/50"
          >
            {ACTION_OPTIONS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
          <span>conviction</span>
          <span className="font-mono text-foreground/70">{draft.conviction.toFixed(2)}</span>
        </div>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={draft.conviction}
          onChange={(e) => onChange({ conviction: Number(e.target.value) })}
          className="w-full accent-morningstar-red"
        />
      </div>
    </div>
  );
}

function DraftReadout({ draft }: { draft: ExtractionDraft }) {
  const dir = DIRECTION_META[draft.direction];
  return (
    <div className="space-y-1.5 font-mono text-[11px] text-foreground/80">
      <div className="flex items-center gap-2">
        <span className="text-foreground/45">ticker</span>
        <span>{draft.ticker}</span>
        <span className={cn("rounded-sm px-1.5 py-0.5 text-[10px] font-bold", dir.cls)}>
          {dir.label}
        </span>
      </div>
      <div>
        <span className="text-foreground/45">conviction</span> {draft.conviction.toFixed(2)} ·{" "}
        <span className="text-foreground/45">action</span> {draft.action}
      </div>
      {(draft.target_price_low != null || draft.target_price_high != null) && (
        <div>
          <span className="text-foreground/45">target</span> [{num(draft.target_price_low)},{" "}
          {num(draft.target_price_high)}]
        </div>
      )}
      <div className="leading-5 text-[var(--ink-soft)]">「{draft.rationale}」</div>
    </div>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <div className="text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
      {children}
    </div>
  );
}

function SourceCard({ text }: { text: string }) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1.5">
        <FileText className="h-3.5 w-3.5 text-foreground/45" strokeWidth={1.8} />
        <SectionTitle>原文 · evidence_text</SectionTitle>
      </div>
      <div className="rounded-sm border border-[var(--grid-line)] bg-[var(--surface-strong)] p-3 text-[13px] leading-7 text-foreground/90">
        {text}
      </div>
    </div>
  );
}

// ---- main -------------------------------------------------------------------

export function AnnotationWorkbench({
  view,
  onViewChange,
}: {
  view: DemoView;
  onViewChange: (v: DemoView) => void;
}) {
  const [task, setTask] = useState<AnnotationTaskId>("gold");
  const [progress, setProgress] = useState({ gold: 0, pairs: 0, f6: 0 });

  // task 1 — gold
  const goldTask = GOLD_TASKS[0];
  const [gDir, setGDir] = useState<TradeDirection | null>(null);
  const [gTicker, setGTicker] = useState("");
  const [gConv, setGConv] = useState(0.5);
  const [gAbstain, setGAbstain] = useState(false);
  const [gSubmitted, setGSubmitted] = useState(false);

  // task 2 — preference
  const [pairIdx, setPairIdx] = useState(0);
  const pair = PREFERENCE_PAIRS[pairIdx];
  const [pVerdict, setPVerdict] = useState<"accept" | "edit" | "reject" | null>(null);
  const [pChosen, setPChosen] = useState<ExtractionDraft>(PREFERENCE_PAIRS[0].chosen);

  // task 3 — f6
  const [f6Idx, setF6Idx] = useState(0);
  const f6 = F6_CASES[f6Idx];
  const [f6Draft, setF6Draft] = useState<ExtractionDraft>({ ...F6_CASES[0].model_output });
  const [f6Rating, setF6Rating] = useState<number | null>(null);
  const [f6Submitted, setF6Submitted] = useState(false);

  function selectPair(i: number) {
    setPairIdx(i);
    setPVerdict(null);
    setPChosen(PREFERENCE_PAIRS[i].chosen);
  }
  function selectF6(i: number) {
    setF6Idx(i);
    setF6Draft({ ...F6_CASES[i].model_output });
    setF6Rating(null);
    setF6Submitted(false);
  }

  // ---- right-rail verifier items (reactive to current drafts) ----
  const verifier = useMemo(() => {
    if (task === "preference") {
      return {
        items: [
          { label: "chosen", tone: "chosen" as const, reward: scoreExtraction(pChosen, pair.prompt) },
          { label: "rejected", tone: "rejected" as const, reward: scoreExtraction(pair.rejected, pair.prompt) },
        ],
        caption: "verifier 确定性打分（structure 门 + grounding/calibration/abstention）；编辑 chosen 分数实时变化。",
      };
    }
    if (task === "f6") {
      return {
        items: [
          { label: "修正后 chosen", tone: "chosen" as const, reward: scoreExtraction(f6Draft, f6.passage) },
          { label: "模型原错 rejected", tone: "rejected" as const, reward: scoreExtraction(f6.model_output, f6.passage) },
        ],
        caption: "人工修正即 chosen，模型原错即 rejected；verifier 量化二者差距。",
      };
    }
    return null;
  }, [task, pChosen, pair, f6Draft, f6]);

  const chosenEqualsRejected =
    pVerdict === "edit" &&
    pChosen.ticker === pair.rejected.ticker &&
    pChosen.direction === pair.rejected.direction &&
    pChosen.conviction === pair.rejected.conviction;

  return (
    <div className="flex h-[100dvh] flex-col">
      <DemoHeader view={view} onViewChange={onViewChange} />

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
        {/* left: task nav + progress + flow */}
        <aside className="shrink-0 overflow-y-auto border-b border-[var(--table-border)] bg-[var(--surface-strong)] finer-scrollbar lg:w-64 lg:border-b-0 lg:border-r">
          <div className="p-3">
            <div className="px-1 pb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-foreground/40">
              标注全流程
            </div>
            <div className="space-y-1.5">
              {TASKS.map((t) => {
                const on = t.id === task;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTask(t.id)}
                    className={cn(
                      "w-full rounded-sm border px-3 py-2.5 text-left transition-colors",
                      on
                        ? "border-l-2 border-morningstar-red bg-white shadow-[var(--shadow-soft)]"
                        : "border-[var(--table-border)] bg-white/40 hover:bg-white",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold tracking-wider text-foreground/40">
                        {t.tag}
                      </span>
                      <span className="rounded-sm bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-bold text-foreground/55">
                        {t.role}
                      </span>
                    </div>
                    <div className="mt-1 text-[14px] font-bold text-foreground">{t.title}</div>
                    <p className="mt-1 text-[11px] leading-5 text-[var(--ink-soft)]">{t.blurb}</p>
                  </button>
                );
              })}
            </div>

            {/* accumulated progress */}
            <div className="mt-4 rounded-sm border border-[var(--table-border)] bg-white p-3">
              <SectionTitle>本次累积（演示）</SectionTitle>
              <dl className="mt-2 grid grid-cols-3 gap-px overflow-hidden rounded-sm border border-[var(--grid-line)] bg-[var(--grid-line)] text-center">
                {[
                  ["gold", progress.gold],
                  ["pairs", progress.pairs],
                  ["f6", progress.f6],
                ].map(([k, v]) => (
                  <div key={k as string} className="bg-white px-2 py-1.5">
                    <dt className="text-[9px] text-foreground/45">{k}</dt>
                    <dd className="mt-0.5 font-mono text-[15px] font-bold text-foreground">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>

            {/* flow rail */}
            <div className="mt-4 rounded-sm border border-[var(--table-border)] bg-white p-3">
              <SectionTitle>数据流</SectionTitle>
              <div className="mt-2 space-y-1 text-[11px] text-foreground/70">
                {["原文 evidence", "三类人工标注", "(chosen, rejected) 偏好对", "RLVR verifier 打分", "DPO 训练包 · ChatML"].map(
                  (s, i, arr) => (
                    <div key={s} className="flex items-center gap-1.5">
                      <span className="font-mono text-[9px] text-foreground/35">{i + 1}</span>
                      <span>{s}</span>
                      {i < arr.length - 1 && (
                        <ArrowRight className="ml-auto h-3 w-3 text-foreground/20" strokeWidth={2} />
                      )}
                    </div>
                  ),
                )}
              </div>
            </div>
          </div>
        </aside>

        {/* center: current task workbench */}
        <main className="min-w-0 flex-1 overflow-y-auto finer-scrollbar">
          <div className="mx-auto max-w-[720px] px-5 py-5">
            {/* === TASK 1: GOLD === */}
            {task === "gold" && (
              <div>
                <h1 className="text-[20px] font-bold tracking-tight text-foreground">评测集 Gold 标注</h1>
                <p className="mt-1 text-[13px] text-[var(--ink-soft)]">
                  {goldTask.persona} · 对原文人工判定，不给字段默认值——证据不足就弃权。
                </p>

                <div className="mt-4">
                  <SourceCard text={goldTask.passage} />
                </div>

                {!gSubmitted ? (
                  <div className="mt-4 rounded-sm border border-[var(--table-border)] bg-white p-4">
                    <div className="flex items-center justify-between">
                      <SectionTitle>你的 Gold 判断</SectionTitle>
                      <button
                        type="button"
                        onClick={() => setGAbstain((v) => !v)}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-sm border px-2 py-1 text-[11px] font-semibold transition-colors",
                          gAbstain
                            ? "border-[var(--accent-gold)]/50 bg-[rgba(155,123,69,0.1)] text-[var(--accent-gold)]"
                            : "border-[var(--table-border)] bg-white text-foreground/55 hover:border-foreground/30",
                        )}
                      >
                        <Ban className="h-3.5 w-3.5" strokeWidth={2} /> A · 弃权
                      </button>
                    </div>

                    {gAbstain ? (
                      <p className="mt-3 rounded-sm bg-[var(--surface-strong)] p-3 text-[12px] leading-6 text-[var(--ink-soft)]">
                        已弃权：证据不足时观望是诚实的标注。将记为{" "}
                        <span className="font-mono">direction=watchlist · ticker=NONE</span>，低信念。
                      </p>
                    ) : (
                      <div className="mt-3 space-y-3">
                        <div>
                          <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
                            direction
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {DIRECTIONS.map((d) => (
                              <button
                                key={d}
                                type="button"
                                onClick={() => setGDir(d)}
                                className={cn(
                                  "rounded-sm border px-2 py-1 text-[11px] font-semibold transition-colors",
                                  gDir === d
                                    ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.06)] text-morningstar-red"
                                    : "border-[var(--table-border)] bg-white text-foreground/60 hover:border-foreground/30",
                                )}
                              >
                                {DIRECTION_META[d].label}
                              </button>
                            ))}
                          </div>
                        </div>
                        <div>
                          <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
                            ticker
                          </div>
                          <input
                            type="text"
                            value={gTicker}
                            onChange={(e) => setGTicker(e.target.value)}
                            placeholder="如 600519.SH"
                            className="w-full rounded-sm border border-[var(--table-border)] bg-white px-2 py-1.5 font-mono text-[12px] outline-none focus:border-morningstar-red/50"
                          />
                        </div>
                        <div>
                          <div className="mb-1 flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.12em] text-foreground/40">
                            <span>conviction</span>
                            <span className="font-mono text-foreground/70">{gConv.toFixed(2)}</span>
                          </div>
                          <input
                            type="range"
                            min={0}
                            max={1}
                            step={0.05}
                            value={gConv}
                            onChange={(e) => setGConv(Number(e.target.value))}
                            className="w-full accent-morningstar-red"
                          />
                        </div>
                      </div>
                    )}

                    <button
                      type="button"
                      disabled={!gAbstain && (gDir == null || gTicker.trim() === "")}
                      onClick={() => {
                        setGSubmitted(true);
                        setProgress((p) => ({ ...p, gold: p.gold + 1 }));
                      }}
                      className="mt-4 w-full rounded-sm bg-morningstar-red px-3 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-morningstar-red/90 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      保存为 Gold
                    </button>
                  </div>
                ) : (
                  <div className="mt-4 space-y-3">
                    <div className="rounded-sm border border-[#0f9b6c]/30 bg-[rgba(16,185,129,0.06)] p-3">
                      <div className="flex items-center gap-1.5 text-[12px] font-semibold text-[#0f9b6c]">
                        <Check className="h-4 w-4" strokeWidth={2} /> 已写入 eval_set.jsonl（演示，未落库）
                      </div>
                      <pre className="mt-2 overflow-x-auto rounded-sm bg-white/70 p-2 font-mono text-[10px] leading-5 text-foreground/75">
{`{"id":"${goldTask.id}","direction":"${gAbstain ? "watchlist" : gDir}","ticker":"${gAbstain ? "NONE" : gTicker}","conviction":${gAbstain ? 0.2 : gConv.toFixed(2)},"expected_abstain":${gAbstain},"reviewer_id":"you_demo"}`}
                      </pre>
                    </div>
                    <div className="flex items-start gap-2 rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] p-3">
                      <Lock className="mt-0.5 h-4 w-4 shrink-0 text-foreground/55" strokeWidth={1.8} />
                      <p className="text-[11px] leading-5 text-[var(--ink-soft)]">
                        gold 是模型从未见过的考卷，与训练集 id 求交集后零重叠才可用——这条记录不会进训练，只进评测。
                      </p>
                    </div>
                    <div className="rounded-sm border border-[var(--table-border)] bg-white p-3">
                      <SectionTitle>参考判断（非评分，提交后揭示）</SectionTitle>
                      <p className="mt-1.5 text-[12px] leading-6 text-foreground/75">
                        {goldTask.reference_gold.note}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setGSubmitted(false);
                        setGDir(null);
                        setGTicker("");
                        setGConv(0.5);
                        setGAbstain(false);
                      }}
                      className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-foreground/60 hover:text-morningstar-red"
                    >
                      <RotateCw className="h-3.5 w-3.5" strokeWidth={2} /> 再标一条
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* === TASK 2: PREFERENCE === */}
            {task === "preference" && (
              <div>
                <div className="flex items-center justify-between">
                  <h1 className="text-[20px] font-bold tracking-tight text-foreground">DPO 偏好对抽检</h1>
                  <div className="flex gap-1">
                    {PREFERENCE_PAIRS.map((p, i) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => selectPair(i)}
                        className={cn(
                          "h-7 w-7 rounded-sm border text-[11px] font-bold transition-colors",
                          i === pairIdx
                            ? "border-morningstar-red bg-morningstar-red text-white"
                            : "border-[var(--table-border)] bg-white text-foreground/55 hover:border-foreground/30",
                        )}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="mt-1 text-[13px] text-[var(--ink-soft)]">{pair.persona} · 接受 / 修改 / 剔除</p>

                <div className="mt-4">
                  <SourceCard text={pair.prompt} />
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-sm border border-[#ecd1d3] bg-[rgba(159,29,34,0.03)] p-3">
                    <div className="flex items-center gap-1.5 text-[11px] font-bold text-morningstar-red">
                      <X className="h-3.5 w-3.5" strokeWidth={2.5} /> rejected · 模型原错
                    </div>
                    <div className="mt-2">
                      <DraftReadout draft={pair.rejected} />
                    </div>
                  </div>
                  <div className="rounded-sm border border-[#cbe2d8] bg-[rgba(16,185,129,0.03)] p-3">
                    <div className="flex items-center gap-1.5 text-[11px] font-bold text-[#0f9b6c]">
                      <Check className="h-3.5 w-3.5" strokeWidth={2.5} /> chosen · 偏好
                    </div>
                    <div className="mt-2">
                      {pVerdict === "edit" ? (
                        <DraftEditor draft={pChosen} onChange={(patch) => setPChosen((d) => ({ ...d, ...patch }))} />
                      ) : (
                        <DraftReadout draft={pChosen} />
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-3 rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] p-3 text-[12px] leading-6 text-[var(--ink-soft)]">
                  <span className="font-bold text-foreground/70">为什么 chosen ≻ rejected：</span>
                  {pair.rationale}
                </div>

                {chosenEqualsRejected && (
                  <div className="mt-2 rounded-sm border border-[var(--accent-gold)]/40 bg-[rgba(155,123,69,0.08)] p-2.5 text-[11px] leading-5 text-[var(--accent-gold)]">
                    chosen 已被改得与 rejected 一致——偏好信号消失，导出时会自动剔除该对。
                  </div>
                )}

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setPVerdict("accept");
                      setProgress((p) => ({ ...p, pairs: p.pairs + 1 }));
                    }}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-sm border px-3 py-1.5 text-[12px] font-semibold transition-colors",
                      pVerdict === "accept"
                        ? "border-[#0f9b6c]/40 bg-[rgba(16,185,129,0.1)] text-[#0f9b6c]"
                        : "border-[var(--table-border)] bg-white text-foreground/60 hover:border-foreground/30",
                    )}
                  >
                    <Check className="h-3.5 w-3.5" strokeWidth={2} /> A · 接受
                  </button>
                  <button
                    type="button"
                    onClick={() => setPVerdict("edit")}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-sm border px-3 py-1.5 text-[12px] font-semibold transition-colors",
                      pVerdict === "edit"
                        ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.06)] text-morningstar-red"
                        : "border-[var(--table-border)] bg-white text-foreground/60 hover:border-foreground/30",
                    )}
                  >
                    <Pencil className="h-3.5 w-3.5" strokeWidth={2} /> E · 修改 chosen
                  </button>
                  <button
                    type="button"
                    onClick={() => setPVerdict("reject")}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-sm border px-3 py-1.5 text-[12px] font-semibold transition-colors",
                      pVerdict === "reject"
                        ? "border-morningstar-red/40 bg-[rgba(225,27,34,0.08)] text-morningstar-red"
                        : "border-[var(--table-border)] bg-white text-foreground/60 hover:border-foreground/30",
                    )}
                  >
                    <X className="h-3.5 w-3.5" strokeWidth={2} /> R · 剔除
                  </button>
                </div>

                {pVerdict === "accept" && (
                  <div className="mt-3 rounded-sm border border-[#0f9b6c]/30 bg-[rgba(16,185,129,0.06)] p-3 font-mono text-[10px] leading-5 text-foreground/75">
                    → 写入 pairs_cleaned.jsonl（演示，未落库）。该对仍需经全量人工审核才进训练包。
                  </div>
                )}
                {pVerdict === "reject" && (
                  <div className="mt-3 rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] p-3 text-[11px] leading-5 text-[var(--ink-soft)]">
                    已剔除：该对不进训练包。verifier 低分或方向理解有误的对，人工有权直接 reject。
                  </div>
                )}
              </div>
            )}

            {/* === TASK 3: F6 === */}
            {task === "f6" && (
              <div>
                <div className="flex items-center justify-between">
                  <h1 className="text-[20px] font-bold tracking-tight text-foreground">F6 字段级修正</h1>
                  <div className="flex gap-1">
                    {F6_CASES.map((c, i) => (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => selectF6(i)}
                        className={cn(
                          "h-7 w-7 rounded-sm border text-[11px] font-bold transition-colors",
                          i === f6Idx
                            ? "border-morningstar-red bg-morningstar-red text-white"
                            : "border-[var(--table-border)] bg-white text-foreground/55 hover:border-foreground/30",
                        )}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="mt-1 text-[13px] text-[var(--ink-soft)]">
                  {f6.persona} · {f6.trade_action_id}
                </p>

                <div className="mt-4">
                  <SourceCard text={f6.passage} />
                </div>

                <div className="mt-3 rounded-sm border border-[#ecd1d3] bg-[rgba(159,29,34,0.03)] p-3">
                  <div className="flex items-center gap-1.5 text-[11px] font-bold text-morningstar-red">
                    <X className="h-3.5 w-3.5" strokeWidth={2.5} /> 模型 F5 抽取（待复核）
                  </div>
                  <div className="mt-2">
                    <DraftReadout draft={f6.model_output} />
                  </div>
                  <p className="mt-2 border-t border-[#ecd1d3] pt-2 text-[11px] leading-5 text-morningstar-red/90">
                    ⚑ {f6.flagged}
                  </p>
                </div>

                {!f6Submitted ? (
                  <div className="mt-3 rounded-sm border border-[var(--table-border)] bg-white p-4">
                    <SectionTitle>字段级修正</SectionTitle>
                    <div className="mt-3">
                      <DraftEditor draft={f6Draft} onChange={(patch) => setF6Draft((d) => ({ ...d, ...patch }))} />
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <span className="text-[12px] text-[var(--ink-soft)]">整体评分</span>
                      <Stars value={f6Rating} onSelect={setF6Rating} />
                    </div>
                    <button
                      type="button"
                      disabled={f6Rating == null}
                      onClick={() => {
                        setF6Submitted(true);
                        setProgress((p) => ({ ...p, f6: p.f6 + 1 }));
                      }}
                      className="mt-3 w-full rounded-sm bg-morningstar-red px-3 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-morningstar-red/90 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      提交修正 → 组装偏好对
                    </button>
                  </div>
                ) : (
                  <div className="mt-3 rounded-sm border border-[#0f9b6c]/30 bg-[rgba(16,185,129,0.06)] p-3">
                    <div className="flex items-center gap-1.5 text-[12px] font-semibold text-[#0f9b6c]">
                      <Check className="h-4 w-4" strokeWidth={2} /> corrections → preference（演示，未落库）
                    </div>
                    <pre className="mt-2 overflow-x-auto rounded-sm bg-white/70 p-2 font-mono text-[10px] leading-5 text-foreground/75">
{`{
  "is_original_correct": false,
  "rating": ${f6Rating},
  "chosen":   {"ticker":"${f6Draft.ticker}","direction":"${f6Draft.direction}","conviction":${f6Draft.conviction.toFixed(2)}},
  "rejected": {"ticker":"${f6.model_output.ticker}","direction":"${f6.model_output.direction}","conviction":${f6.model_output.conviction.toFixed(2)}},
  "reviewer_id": "you_demo"
}`}
                    </pre>
                    <p className="mt-1.5 text-[10px] leading-4 text-foreground/45">
                      环 B 飞轮：真实 F5 错误 + 人工修正 → 偏好对 → 再训。
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </main>

        {/* right: RLVR verifier */}
        <aside className="shrink-0 overflow-y-auto border-t border-[var(--table-border)] bg-[var(--surface-strong)] finer-scrollbar lg:w-80 lg:border-l lg:border-t-0">
          <div className="flex items-center gap-2 border-b border-[var(--table-border)] bg-[var(--table-header-bg)] px-4 py-2.5">
            <GitCompare className="h-3.5 w-3.5 text-morningstar-red" strokeWidth={1.8} />
            <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/55">
              RLVR Verifier · 可验证奖励
            </span>
          </div>
          <div className="px-4 py-3">
            {verifier ? (
              <>
                <p className="mb-3 text-[11px] leading-5 text-[var(--ink-soft)]">
                  确定性 · 免费 · 可复现——规则直接验证，不调用模型。
                </p>
                <RewardMeter items={verifier.items} caption={verifier.caption} />
                <div className="mt-3 flex items-center justify-between rounded-sm border border-[var(--table-border)] bg-white px-3 py-2">
                  <span className="text-[11px] text-foreground/55">committal rate（健康度）</span>
                  <span className="font-mono text-[12px] font-bold tabular-nums text-foreground/80">
                    {(
                      committalRate(
                        task === "preference" ? [pChosen, pair.rejected] : [f6Draft, f6.model_output],
                      ) * 100
                    ).toFixed(0)}
                    %
                  </span>
                </div>
              </>
            ) : (
              <div className="flex items-start gap-2 rounded-sm border border-[var(--accent-gold)]/30 bg-[rgba(155,123,69,0.06)] p-3">
                <ClipboardCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent-gold)]" strokeWidth={1.8} />
                <p className="text-[11px] leading-5 text-[var(--ink-soft)]">
                  这是 <span className="font-bold text-foreground">人工验证集（RLHF）</span>：gold 是评测真相，
                  verifier 不介入打分。RLVR 可验证奖励只对训练候选（任务二/三）生效——这正是两类信号的分工。
                </p>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
