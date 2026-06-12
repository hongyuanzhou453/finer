import Image from "next/image";
import Link from "next/link";
import type { Metadata } from "next";
import {
  Anchor,
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  Beaker,
  Check,
  ClipboardCheck,
  Cpu,
  Gauge,
  GitCompare,
  ListChecks,
  Lock,
  MonitorPlay,
  RotateCw,
  Scale,
  ShieldCheck,
  Target,
  X,
} from "lucide-react";
import { ProductFrame } from "@/components/landing/product-frame";
import {
  GITHUB_URL,
  GitHubMark,
  SiteFooter,
  SiteHeader,
} from "@/components/landing/site-chrome";

// ─────────────────────────────────────────────────────────────────────────────
// 纯静态叙事页（宣传站版）。所有结构与数字均取自仓库内已落地的 spec / schema / 脚本：
//   docs/specs/2026-06-07-dpo-bailian-training-line.md
//   docs/specs/2026-06-07-f6-rlhf-to-dpo-mapping.md
//   docs/specs/2026-06-10-annotation-workbench.md
//   docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md（RLHF × RLVR 协同，rev2）
//   src/finer/schemas/{annotation,trade_action}.py
// 红线：不编造模型提升数字。真实微调数字留待百炼实跑回填。
// 标注工作台是内部工具，本页 CTA 指向在线演示（F6 复核模拟）与 GitHub。
// ─────────────────────────────────────────────────────────────────────────────

export const metadata: Metadata = {
  title: "训练数据",
  description:
    "RLHF 人类偏好与 RLVR 可验证奖励如何协同沉淀为 DPO 训练数据：三类标注任务、确定性 verifier、训练集与人工验证集的零泄漏分离、证据对齐的偏好原则、三项评测指标与百炼 DPO 训练线现状。",
};

const NAV_LINKS = [
  { href: "#annotation", label: "人工标注" },
  { href: "#train-eval", label: "训练 ≠ 验证" },
  { href: "#preference", label: "偏好原则" },
  { href: "#rlvr", label: "RLHF × RLVR" },
  { href: "#metrics", label: "评测指标" },
  { href: "#status", label: "训练线进展" },
];

type AnnotationTask = {
  icon: typeof ClipboardCheck;
  tag: string;
  title: string;
  role: string;
  body: string;
  output: string;
  consumer: string;
  meta: string[];
};

const ANNOTATION_TASKS: AnnotationTask[] = [
  {
    icon: ListChecks,
    tag: "任务一 · 环 A",
    title: "held-out 评测集 Gold 标注",
    role: "人工验证集",
    body: "对独立 held-out 段落人工判定 direction / ticker / conviction / action chain，证据不足时按 A 键弃权。产出的 gold 标签，是模型从未见过的评测真相。",
    output: "eval_set.jsonl",
    consumer: "eval_compare.py",
    meta: ["A=弃权 · 1-5=方向 · Enter=保存下一条", "direction / ticker 不给默认值，强制人工判断"],
  },
  {
    icon: GitCompare,
    tag: "任务二 · 环 A",
    title: "DPO 偏好对 chosen 侧抽检",
    role: "训练集质检",
    body: "对 (rejected, chosen) 偏好对的 chosen 侧抽样质检：A=合格 / E=修正 / R=剔除。编辑后若 chosen==rejected（丧失偏好信号），自动剔除。",
    output: "pairs_cleaned.jsonl",
    consumer: "to_bailian.py",
    meta: ["抽样质检，不要求全量过审", "reject 剔除 · edit 替换 · accept/未审保留"],
  },
  {
    icon: RotateCw,
    tag: "任务三 · 环 B",
    title: "F6 RLHF 复核台字段级修正",
    role: "真实反馈 → 偏好对",
    body: "真实 F5 抽取在进入回测前经 RLHFReviewPanel 人工裁决：1-5 星评分、是否正确、direction / ticker / action chain 字段级修正、备注与快捷标签。corrections 自动组装为偏好对。",
    output: "RLHFFeedback → preference",
    consumer: "DPOExporter",
    meta: ["reviewer_id / reviewed_at 全程可审计", "corrections → build_preference 接线桥已打通"],
  },
];

const PRINCIPLE_ROWS = [
  {
    evidence: "证据充分",
    chosen: "给对方向 + 挂上原文可溯证据（ticker / 价位 span）+ schema 合规",
    rejected: "方向错 / 丢证据 / 结构破格",
  },
  {
    evidence: "证据不足",
    chosen: "hold / watchlist + 低 conviction + 诚实 rationale（敢弃权）",
    rejected: "弱证据硬给 buy / sell、编造原文没有的 ticker / 价位",
  },
];

const METRICS = [
  {
    icon: BadgeCheck,
    name: "结构合规率",
    en: "structure_compliance_rate",
    cost: "确定性 · 免费",
    body: "输出能 json.loads 且通过轻量 ExtractionOutput 校验：ticker 非空、direction ∈ TradeDirection、每步 action_type ∈ ActionType、价格 ≥0 且 low ≤ high。",
    note: "枚举真相源 = schemas/trade_action.py，评测不重定义枚举。",
  },
  {
    icon: Anchor,
    name: "证据挂靠率",
    en: "evidence_attachment_rate",
    cost: "确定性 · 免费 · 直测「不编造」",
    body: "仅在承诺性输出上计：ticker 在 evidence_text 可溯（normalized 子串），且输出中所有价位 / 触发条件数字都能在原文找到。",
    note: "附带报告 hallucination_rate（编造 ticker 或价格的承诺占比）。",
  },
  {
    icon: Scale,
    name: "偏好胜率",
    en: "preference_win_rate",
    cost: "需 judge",
    body: "pairwise 判定 after 是否优于 before。ref-match（确定性、需 gold）用于无 API dry-run；LLM judge 以「证据对齐的克制」为 rubric。",
    note: "LLM judge A/B 位置互换跑两遍，仅计一致胜，消除位置偏置。",
  },
];

const STAGES = [
  { stage: "地基①", deliver: "方法论契约 spec", status: "done", detail: "偏好原则 / 数据来源 / 三指标 / 阶段计划锁定" },
  { stage: "地基②", deliver: "eval_compare.py 三指标评测器", status: "done", detail: "--demo dry-run 走通（枚举真相源未漂移）" },
  { stage: "地基③", deliver: "train_dpo.py --smoke-test", status: "done", detail: "tiny 模型 + CPU + 2 步，训练循环可运行" },
  { stage: "数据②", deliver: "to_bailian.py 百炼 ChatML 转换", status: "done", detail: "格式已核实 + Qwen3-8B 支持 DPO LoRA" },
  { stage: "数据①", deliver: "harvest rejected → 校准 chosen", status: "active", detail: "152 对 qwen3-8b 真实 draft 已生成，HQ 全量人工审核进行中" },
  { stage: "实跑", deliver: "百炼上传 / 训练 / 部署 / 评测", status: "user", detail: "真实微调与评测，回填 after.jsonl 出真实数字" },
  { stage: "v2", deliver: "RLVR-guided k-best 采样构对", status: "locked", detail: "任务卡 rev2 已锁定，baseline 出数后启动（rewards.py 统一奖励真相源）" },
];

const STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  done: { label: "已就绪", cls: "bg-[rgba(16,185,129,0.12)] text-[#0f7a54]" },
  pending: { label: "待授权", cls: "bg-[rgba(155,123,69,0.14)] text-[var(--accent-gold)]" },
  user: { label: "待实跑", cls: "bg-[var(--surface-muted)] text-foreground/55" },
  active: { label: "进行中", cls: "bg-[rgba(159,29,34,0.10)] text-morningstar-red" },
  locked: { label: "方法论已锁定", cls: "bg-[rgba(155,123,69,0.14)] text-[var(--accent-gold)]" },
  research: { label: "预研边界", cls: "bg-[var(--surface-muted)] text-foreground/55" },
};

// 验证集轨道与训练集轨道（两条数据流）
const EVAL_TRACK = [
  { node: "passages.jsonl", note: "held-out 段落" },
  { node: "人工 Gold 标注", note: "标注工作台" },
  { node: "eval_set.jsonl", note: "人工验证集" },
  { node: "run_inference", note: "before / after" },
  { node: "eval_compare", note: "三项指标" },
];

const TRAIN_TRACK = [
  { node: "candidates.jsonl", note: "真实 KOL 原文" },
  { node: "harvest rejected", note: "基座真实失败" },
  { node: "pairs.jsonl", note: "(rejected, chosen)" },
  { node: "人工抽检", note: "chosen 侧质检" },
  { node: "to_bailian", note: "百炼 ChatML" },
  { node: "百炼 DPO LoRA", note: "微调模型" },
];

const REAL_PAIR_CASE = {
  source:
    "港股中国能源建设：A 股短期资金炒作，港股到正常目标价，向上空间不大，目前风险大于价值。",
  chosen:
    "ticker=00352.HK · direction=risk_warning · action=hold · target_price=null",
  rejected:
    "同样方向但把无目标价写成 target_price=0，容易把“未知”误读成真实价格。",
  why:
    "chosen 保留风险警示和 hold 判断，同时用 null 表达原文没有价格锚点；这是“证据不足不硬填”的真实偏好原则。",
};

// RLHF × RLVR 协同（方法论真相源：docs/specs/2026-06-12-rlvr-guided-dpo-task-card.md rev2）
const REWARD_AXES = [
  {
    icon: ClipboardCheck,
    tag: "RLHF · 人类偏好",
    title: "人做最终裁决，管 verifier 测不到的轴",
    body: "方向解读对不对、rationale 是否言之有物、该不该弃权——这些没有确定性判据，只能由人裁决。三类标注任务与 F6 复核台产出的偏好对，是训练包的主体与最终 truth。",
    points: [
      "HQ 偏好对全量人工审核（A / E / R）",
      "F6 字段级修正 → 偏好对（环 B 飞轮）",
      "verifier 只能排序与筛选，不能替代人工签核",
    ],
  },
  {
    icon: BadgeCheck,
    tag: "RLVR · 可验证奖励",
    title: "任务天然可验证，奖励确定性、免费",
    body: "抽取任务的大部分质量轴对错有判据，可由规则直接验证：JSON 结构是否合规、ticker 与价位能否回到原文、conviction 是否与证据强度匹配。这些 verifier 已在仓库里运行——评测三指标与 HQ 质量门用的就是它们。",
    points: [
      "结构合规：schema 与枚举即真相源（硬门）",
      "证据溯源：标的 / 价位逐一回原文比对",
      "信念校准：conviction 阶梯 0.8 / 0.6 / 0.45 / 0.3",
    ],
  },
];

const SYNERGY_STEPS = [
  {
    step: "01",
    title: "k-best 采样",
    body: "对同一段 KOL 原文采样多个候选输出，温度放开，让模型暴露真实的输出分布——好与坏的样本都来自模型自己（on-policy）。",
  },
  {
    step: "02",
    title: "verifier 打分构对",
    body: "可验证奖励逐项打分：高分且全过硬门的做 chosen 候选，破门或低分的做 rejected；分差不足转人工，不硬凑偏好对，也不用 verifier 的修补结果冒充学习目标。",
  },
  {
    step: "03",
    title: "人工审核后混合",
    body: "verifier 构造的偏好对仍需全量人工审核，再与人工偏好对、难例按约 6 : 3 : 1 混入同一个 DPO 训练包——RLHF 与 RLVR 在数据层合流。",
  },
];

const RLVR_ROADMAP = [
  {
    phase: "v1 · RLHF 主导",
    deliver: "152 对 HQ draft 全量人工审核 → 百炼 DPO LoRA baseline",
    status: "active",
  },
  {
    phase: "v2 · RLVR-guided DPO",
    deliver: "rewards.py 统一奖励真相源 + k-best 采样构对 + 混合训练包",
    status: "locked",
  },
  {
    phase: "路径 B · 在线 RL",
    deliver: "百炼 RL API（gspo / grpo）+ HTTP 奖励服务，或自管 TRL GRPO",
    status: "research",
  },
];

export default function TrainingPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader links={NAV_LINKS} />

      {/* ===== Hero ===== */}
      <section className="mx-auto max-w-[1200px] px-6 pt-12 pb-10 lg:pt-16">
        <div className="text-[12px] font-bold uppercase tracking-[0.22em] text-morningstar-red">
          人工标注 · RLHF × RLVR · DPO 训练数据
        </div>
        <h1 className="mt-5 max-w-3xl text-[34px] font-bold leading-[1.15] tracking-tight text-foreground lg:text-[44px]">
          RLHF 偏好 × RLVR 可验证奖励，
          <br />
          协同沉淀为 DPO 训练数据
        </h1>
        <p className="mt-6 max-w-2xl text-[16px] leading-7 text-[var(--ink-soft)]">
          模型抽取的投资判断，在进入回测前都要被人类裁决；而结构合规、证据溯源这些「对错有判据」的轴，
          交给确定性 verifier 自动验证。两类奖励信号——
          <strong className="text-foreground">RLHF 的人类偏好</strong>与
          <strong className="text-foreground">RLVR 的可验证奖励</strong>——协同沉淀为同一条
          DPO 训练线上的训练集与人工验证集。这一页讲清楚两类信号各管什么、怎么协同、
          以及训练线现在走到了哪一步。
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/demo"
            className="inline-flex items-center gap-2 rounded-sm bg-morningstar-red px-5 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
          >
            <MonitorPlay className="h-4 w-4" strokeWidth={2} />
            在演示里体验 F6 复核
          </Link>
          <a
            href="#status"
            className="inline-flex items-center gap-2 rounded-sm border border-[var(--table-border)] bg-white px-5 py-3 text-[14px] font-semibold text-foreground transition-colors hover:border-foreground/30"
          >
            看训练线进展
          </a>
        </div>
        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-[12px] text-foreground/45">
          <span>文件即真相源，标注落盘可重建</span>
          <span className="h-1 w-1 rounded-full bg-foreground/20" />
          <span>训练 / 验证零泄漏</span>
          <span className="h-1 w-1 rounded-full bg-foreground/20" />
          <span>奖励可验证 · 确定性可复现</span>
          <span className="h-1 w-1 rounded-full bg-foreground/20" />
          <span>不编造提升数字</span>
        </div>
      </section>

      {/* ===== 各类人工标注 ===== */}
      <section id="annotation" className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
        <div className="mx-auto max-w-[1200px] px-6 py-14">
          <div className="mb-9 max-w-2xl">
            <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
              HUMAN ANNOTATION
            </div>
            <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
              三类人工标注，各有去向
            </h2>
            <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
              没有引入外部标注平台。标注对象是「中文段落 → 结构化表单」，直接对齐
              TradeDirection / ActionType 枚举与数据契约，零转换层。标注全部落为
              append-only JSONL，可 diff、可重建、不动 SQLite。
            </p>
          </div>

          <div className="mb-8 grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)] lg:items-center">
            <ProductFrame
              src="/landing/annotation-workbench.png"
              alt="Finer OS 标注工作台：左侧原文证据，右侧 Gold 结构化表单与 Formal export 阻断"
              width={1440}
              height={980}
              label="finer.os / annotation"
              className="bg-white"
              priority
            />
            <div className="border-t-2 border-morningstar-red bg-white p-6 shadow-[var(--shadow-soft)]">
              <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-morningstar-red">
                REAL WORKBENCH
              </div>
              <h3 className="mt-3 text-[20px] font-bold tracking-tight text-foreground">
                标注对象就是原文证据与结构化表单
              </h3>
              <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
                左侧保留 KOL 原文、上下文扩展和实体检测；右侧直接填
                ticker / direction / action chain。Formal 导出被质量闸拦住时，
                页面点名未标样本、弱信号和 gold 数量，不允许悄悄产出训练文件。
              </p>
              <dl className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-[var(--grid-line)] bg-[var(--grid-line)] text-[12px]">
                {[
                  ["当前任务源", "30 条"],
                  ["已处理", "9 条"],
                  ["有效 gold", "2 条"],
                  ["Formal 闸", "blocked"],
                ].map(([k, v]) => (
                  <div key={k} className="bg-[var(--surface-strong)] px-3 py-2">
                    <dt className="text-foreground/45">{k}</dt>
                    <dd className="mt-0.5 font-mono font-bold text-foreground">{v}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-[11px] leading-5 text-foreground/40">
                内部标注工作台真实快照——质量闸把 Formal 导出拦在 gold 不足时，
                正是我们想展示的工作方式。
              </p>
            </div>
          </div>

          <div className="grid gap-px overflow-hidden rounded-sm border border-[var(--table-border)] bg-[var(--table-border)] lg:grid-cols-3">
            {ANNOTATION_TASKS.map((t) => {
              const Icon = t.icon;
              return (
                <div key={t.title} className="flex flex-col bg-white p-6">
                  <div className="flex items-center justify-between">
                    <Icon className="h-7 w-7 text-morningstar-red" strokeWidth={1.5} />
                    <span className="rounded-sm bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold tracking-wider text-foreground/55">
                      {t.role}
                    </span>
                  </div>
                  <div className="mt-4 text-[11px] font-bold tracking-[0.14em] text-foreground/40">
                    {t.tag}
                  </div>
                  <h3 className="mt-1 text-[17px] font-bold tracking-tight text-foreground">
                    {t.title}
                  </h3>
                  <p className="mt-2 flex-1 text-[13px] leading-6 text-[var(--ink-soft)]">
                    {t.body}
                  </p>
                  <ul className="mt-3 space-y-1.5">
                    {t.meta.map((m) => (
                      <li key={m} className="flex items-start gap-2 text-[12px] leading-5 text-foreground/60">
                        <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-foreground/25" />
                        {m}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-4 flex items-center gap-2 border-t border-[var(--grid-line)] pt-3 font-mono text-[11px]">
                    <span className="text-foreground/80">{t.output}</span>
                    <ArrowRight className="h-3 w-3 text-foreground/30" strokeWidth={2} />
                    <span className="text-foreground/45">{t.consumer}</span>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="mt-4 text-[12px] leading-5 text-foreground/45">
            标注时还可把选中原文一键存入 KOL Profile 速记（
            <span className="font-mono">data/kol_profiles/notes/&#123;creator&#125;.jsonl</span>），供 KOL 页后续聚合——附带产物，不属主链路。
          </p>
        </div>
      </section>

      {/* ===== 训练集 vs 人工验证集 ===== */}
      <section id="train-eval" className="mx-auto max-w-[1200px] px-6 py-16">
        <div className="mb-9 max-w-2xl">
          <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
            TRAIN ≠ EVAL
          </div>
          <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
            训练集与人工验证集，刻意分开
          </h2>
          <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
            两类数据服务完全不同的目的：一类喂模型学习，一类给模型从未见过的考卷。
            混在一起，所谓「提升」就只是自我循环的幻觉。
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {/* 训练集 */}
          <div className="overflow-hidden rounded-sm border border-[var(--table-border)] bg-white">
            <div className="border-t-2 border-morningstar-red px-6 py-5">
              <div className="flex items-center gap-2.5">
                <Cpu className="h-6 w-6 text-morningstar-red" strokeWidth={1.5} />
                <h3 className="text-[18px] font-bold tracking-tight text-foreground">DPO 训练集</h3>
              </div>
              <p className="mt-2 text-[13px] leading-6 text-[var(--ink-soft)]">
                偏好对 (prompt, chosen, rejected)，提供学习信号——让模型学到「证据对齐的克制」。
              </p>
            </div>
            <dl className="divide-y divide-[var(--grid-line)] text-[13px]">
              {[
                ["产物文件", "pairs.jsonl → data.jsonl"],
                ["格式", "百炼 ChatML（chosen / rejected 为 assistant 对象）"],
                ["来源", "环 A 半真实（真原文 + 基座真实失败）/ 环 B 真实反馈"],
                ["目标规模", "≥120 条 · 覆盖矩阵 12 格（每格 ~10）· 百炼 DPO 下限上百条"],
              ].map(([k, v]) => (
                <div key={k} className="flex gap-3 px-6 py-2.5">
                  <dt className="w-20 shrink-0 text-foreground/45">{k}</dt>
                  <dd className="min-w-0 text-foreground/85">{v}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* 验证集 */}
          <div className="overflow-hidden rounded-sm border border-[var(--table-border)] bg-white">
            <div className="border-t-2 border-[var(--accent-gold)] px-6 py-5">
              <div className="flex items-center gap-2.5">
                <Gauge className="h-6 w-6 text-[var(--accent-gold)]" strokeWidth={1.5} />
                <h3 className="text-[18px] font-bold tracking-tight text-foreground">人工验证集</h3>
              </div>
              <p className="mt-2 text-[13px] leading-6 text-[var(--ink-soft)]">
                held-out gold 标签，是微调前后对比的真相——模型从未见过，才有资格当考卷。
              </p>
            </div>
            <dl className="divide-y divide-[var(--grid-line)] text-[13px]">
              {[
                ["产物文件", "eval_set.jsonl"],
                ["字段", "id / prompt / evidence_text / expected_abstain / gold"],
                ["来源", "独立来源；真实数据未就绪前用「不同种子的半真实」兜底"],
                ["当前规模", "30 段 · 与训练集 150 个 id 零重叠"],
              ].map(([k, v]) => (
                <div key={k} className="flex gap-3 px-6 py-2.5">
                  <dt className="w-20 shrink-0 text-foreground/45">{k}</dt>
                  <dd className="min-w-0 text-foreground/85">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>

        {/* 两条红线 */}
        <div className="mt-6 grid gap-6 sm:grid-cols-2">
          <div className="flex gap-3 rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] p-5">
            <Lock className="h-6 w-6 shrink-0 text-foreground/70" strokeWidth={1.5} />
            <div>
              <h4 className="text-[14px] font-bold text-foreground">防自我循环</h4>
              <p className="mt-1.5 text-[12px] leading-5 text-[var(--ink-soft)]">
                评测集必须训练未见、独立来源。偏好胜率的 LLM judge 还会 A/B 位置互换跑两遍，
                只承认一致胜，避免位置偏置把分数刷虚。
              </p>
            </div>
          </div>
          <div className="flex gap-3 rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] p-5">
            <ShieldCheck className="h-6 w-6 shrink-0 text-foreground/70" strokeWidth={1.5} />
            <div>
              <h4 className="text-[14px] font-bold text-foreground">防泄漏</h4>
              <p className="mt-1.5 text-[12px] leading-5 text-[var(--ink-soft)]">
                eval 任务源缺失时只给 fix_hint，绝不回退训练集。导出时对训练集 id 求交集，
                重叠 id 在 API 响应与前端黄色警告里点名。
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== 偏好原则 ===== */}
      <section id="preference" className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
        <div className="mx-auto max-w-[1200px] px-6 py-16">
          <div className="grid gap-10 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:items-start">
            <div>
              <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
                PREFERENCE AXIS
              </div>
              <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
                偏好轴 = 证据对齐的克制
              </h2>
              <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
                每个偏好对里 chosen ≻ rejected 编码同一条原则：有证据就给方向并挂上原文可溯证据，
                没证据就敢说 hold。对投研系统而言，「证据不足时敢观望」比「猜对方向」更有价值。
              </p>
              <p className="mt-4 text-[13px] leading-6 text-foreground/55">
                一条原则同时驱动三项指标：证据挂靠率 ← chosen 挂证据；结构合规率 ← chosen 合规；
                偏好胜率 ← chosen 的克制被判更优。直接服务「不编造」红线。
              </p>
              <div className="mt-5 rounded-sm border border-[var(--table-border)] bg-white p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/40">
                  覆盖矩阵 · ≥120 条
                </div>
                <p className="mt-2 text-[12px] leading-5 text-[var(--ink-soft)]">
                  方向 &#123;buy, sell, hold&#125; × 证据 &#123;足, 不足&#125; × 周期 &#123;长, 短&#125; = 12 格，
                  每格约 10 条。其中「证据不足 × 本应 buy/sell」（chosen=hold）是信号最强的格子，重点配比。
                </p>
              </div>
            </div>

            <div className="space-y-4">
              {/* 2x2 原则矩阵 */}
              <div className="overflow-hidden rounded-sm border border-[var(--table-border)] bg-white">
                <div className="grid grid-cols-[88px_1fr_1fr] bg-[var(--table-header-bg)] text-[12px] font-bold text-foreground/55">
                  <div className="px-4 py-3" />
                  <div className="border-l border-[var(--grid-line)] px-4 py-3">
                    <span className="inline-flex items-center gap-1.5 text-[#0f7a54]">
                      <Check className="h-3.5 w-3.5" strokeWidth={2.5} /> chosen（偏好）
                    </span>
                  </div>
                  <div className="border-l border-[var(--grid-line)] px-4 py-3">
                    <span className="inline-flex items-center gap-1.5 text-morningstar-red">
                      <X className="h-3.5 w-3.5" strokeWidth={2.5} /> rejected（拒绝）
                    </span>
                  </div>
                </div>
                {PRINCIPLE_ROWS.map((r, i) => (
                  <div
                    key={r.evidence}
                    className={`grid grid-cols-[88px_1fr_1fr] text-[12px] leading-5 ${
                      i > 0 ? "border-t border-[var(--grid-line)]" : ""
                    }`}
                  >
                    <div className="flex items-center px-4 py-4 font-bold text-foreground/70">
                      {r.evidence}
                    </div>
                    <div className="border-l border-[var(--grid-line)] bg-[rgba(16,185,129,0.04)] px-4 py-4 text-foreground/85">
                      {r.chosen}
                    </div>
                    <div className="border-l border-[var(--grid-line)] bg-[rgba(159,29,34,0.04)] px-4 py-4 text-foreground/85">
                      {r.rejected}
                    </div>
                  </div>
                ))}
              </div>

              <div className="border-t-2 border-[var(--accent-gold)] bg-white p-5 shadow-[var(--shadow-soft)]">
                <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-foreground/40">
                  REAL PAIR CASE · data/dpo/pairs.jsonl
                </div>
                <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
                  <span className="font-bold text-foreground">原文：</span>
                  {REAL_PAIR_CASE.source}
                </p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-sm border border-[#cbe2d8] bg-[rgba(16,185,129,0.04)] p-3">
                    <div className="flex items-center gap-1.5 text-[12px] font-bold text-[#0f7a54]">
                      <Check className="h-3.5 w-3.5" strokeWidth={2.5} /> chosen
                    </div>
                    <p className="mt-2 font-mono text-[11px] leading-5 text-foreground/80">
                      {REAL_PAIR_CASE.chosen}
                    </p>
                  </div>
                  <div className="rounded-sm border border-[#ecd1d3] bg-[rgba(159,29,34,0.04)] p-3">
                    <div className="flex items-center gap-1.5 text-[12px] font-bold text-morningstar-red">
                      <X className="h-3.5 w-3.5" strokeWidth={2.5} /> rejected
                    </div>
                    <p className="mt-2 font-mono text-[11px] leading-5 text-foreground/80">
                      {REAL_PAIR_CASE.rejected}
                    </p>
                  </div>
                </div>
                <p className="mt-3 text-[12px] leading-5 text-foreground/55">
                  {REAL_PAIR_CASE.why}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== RLHF × RLVR 协同 ===== */}
      <section id="rlvr" className="mx-auto max-w-[1200px] px-6 py-16">
        <div className="mb-9 max-w-2xl">
          <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
            RLHF × RLVR
          </div>
          <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
            两类奖励信号，灌进同一条 DPO 训练线
          </h2>
          <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
            人类偏好（RLHF）与可验证奖励（RLVR）不是两条训练线，而是同一条 DPO 线上的两类信号：
            verifier 负责对错有判据的轴——确定性、免费、可复现；人负责 verifier
            测不到的最终裁决。投研抽取任务的特殊之处在于，它的大部分质量轴天然可验证。
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {REWARD_AXES.map((a) => {
            const Icon = a.icon;
            return (
              <div key={a.tag} className="rounded-sm border border-[var(--table-border)] bg-white p-6">
                <div className="flex items-center justify-between">
                  <Icon className="h-7 w-7 text-morningstar-red" strokeWidth={1.5} />
                  <span className="rounded-sm bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold tracking-wider text-foreground/55">
                    {a.tag}
                  </span>
                </div>
                <h3 className="mt-4 text-[17px] font-bold tracking-tight text-foreground">{a.title}</h3>
                <p className="mt-2 text-[13px] leading-6 text-[var(--ink-soft)]">{a.body}</p>
                <ul className="mt-3 space-y-1.5">
                  {a.points.map((p) => (
                    <li key={p} className="flex items-start gap-2 text-[12px] leading-5 text-foreground/60">
                      <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-foreground/25" />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        <div className="mt-6 grid gap-px overflow-hidden rounded-sm border border-[var(--table-border)] bg-[var(--table-border)] lg:grid-cols-3">
          {SYNERGY_STEPS.map((s) => (
            <div key={s.step} className="bg-white p-6">
              <div className="font-mono text-[12px] font-bold text-foreground/35">{s.step}</div>
              <h3 className="mt-2 text-[15px] font-bold tracking-tight text-foreground">{s.title}</h3>
              <p className="mt-2 text-[13px] leading-6 text-[var(--ink-soft)]">{s.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="rounded-sm border-t-2 border-morningstar-red bg-white p-6 shadow-[var(--shadow-soft)]">
            <div className="flex items-center gap-2.5">
              <ShieldCheck className="h-5 w-5 text-foreground" strokeWidth={1.6} />
              <h3 className="text-[15px] font-bold tracking-tight text-foreground">
                为什么不做纯 RLVR
              </h3>
            </div>
            <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
              单一可验证信号会被「塌缩」利用——迭代 1 里校准器过严，89% 真实承诺被清零成观望，
              模型差点学成「无脑弃权」。所以 verifier 信号必须多维加权，committal
              率、非承诺构成漂移、幻觉率全部进 reward health 监控，触线即阻止导出；
              人类偏好轴永远保留最终裁决权。
            </p>
          </div>

          <div className="overflow-hidden rounded-sm border border-[var(--table-border)] bg-white">
            <div className="bg-[var(--table-header-bg)] px-5 py-3 text-[11px] font-bold uppercase tracking-[0.12em] text-foreground/45">
              协同训练路线
            </div>
            {RLVR_ROADMAP.map((r, i) => {
              const st = STATUS_STYLE[r.status];
              return (
                <div
                  key={r.phase}
                  className={`flex items-center justify-between gap-4 px-5 py-3.5 ${
                    i > 0 ? "border-t border-[var(--grid-line)]" : ""
                  }`}
                >
                  <div className="min-w-0">
                    <div className="text-[13px] font-bold text-foreground">{r.phase}</div>
                    <div className="mt-0.5 text-[12px] leading-5 text-[var(--ink-soft)]">{r.deliver}</div>
                  </div>
                  <span className={`shrink-0 rounded-sm px-2 py-0.5 text-[11px] font-bold ${st.cls}`}>
                    {st.label}
                  </span>
                </div>
              );
            })}
            <p className="border-t border-[var(--grid-line)] bg-[var(--surface-muted)] px-5 py-2.5 text-[11px] leading-5 text-foreground/45">
              市场收益 / 回测结果永不进入抽取模型的训练奖励——抽取的职责是忠实记录 KOL
              说了什么，不是预测市场。真实提升数字仍只来自实跑后的 eval_compare 报告。
            </p>
          </div>
        </div>
      </section>

      {/* ===== 两个环 ===== */}
      <section className="mx-auto max-w-[1200px] px-6 py-16">
        <div className="mb-9 max-w-2xl">
          <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
            TWO LOOPS
          </div>
          <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
            环 A 证管线，环 B 才是质量来源
          </h2>
          <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
            两个环区分清楚，避免把「跑通」当成「变好」。
          </p>
        </div>

        <TrainingVisual
          src="/landing/training-loops.svg"
          alt="环 A 半真实 bootstrap 与环 B 真实反馈飞轮的双循环示意图"
          caption="环 A 只证明管线可运行；环 B 才把真实 F5 错误、F6 人工修正和 DPO 导出连成质量飞轮。"
        />

        <div className="grid gap-6 lg:grid-cols-2">
          {/* 环 A */}
          <div className="rounded-sm border border-[var(--table-border)] bg-white p-6">
            <div className="flex items-center gap-2.5">
              <Beaker className="h-6 w-6 text-foreground" strokeWidth={1.5} />
              <h3 className="text-[17px] font-bold tracking-tight text-foreground">环 A · 半真实 bootstrap</h3>
            </div>
            <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
              先做，用来证明「管线通 + 原则可学」，<strong className="text-foreground">不是质量证明</strong>。为压低自我循环：
            </p>
            <ul className="mt-3 space-y-2 text-[13px] leading-6 text-foreground/75">
              <li className="flex gap-2"><span className="mt-[8px] h-1 w-1 shrink-0 rounded-full bg-foreground/30" />evidence_text 取真实 KOL 转写原文，过滤测试桩与噪声</li>
              <li className="flex gap-2"><span className="mt-[8px] h-1 w-1 shrink-0 rounded-full bg-foreground/30" />rejected = 基座 Qwen 的真实失败输出（on-policy 负样本，非虚构稻草人）</li>
              <li className="flex gap-2"><span className="mt-[8px] h-1 w-1 shrink-0 rounded-full bg-foreground/30" />chosen = 把 rejected 校准为「证据对齐的克制」版，证据 span 内联</li>
              <li className="flex gap-2"><span className="mt-[8px] h-1 w-1 shrink-0 rounded-full bg-foreground/30" />人工抽检 chosen 侧（任务二），不逐条标注</li>
            </ul>
          </div>

          {/* 环 B */}
          <div className="rounded-sm border border-[var(--table-border)] bg-white p-6">
            <div className="flex items-center gap-2.5">
              <RotateCw className="h-6 w-6 text-foreground" strokeWidth={1.5} />
              <h3 className="text-[17px] font-bold tracking-tight text-foreground">环 B · 真实反馈飞轮</h3>
            </div>
            <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
              后做，<strong className="text-foreground">真正的质量来源</strong>：真实 F5 抽取 → 人在面板纠错 → 再训。F6 字段映射已锁：
            </p>
            <dl className="mt-3 divide-y divide-[var(--grid-line)] font-mono text-[12px]">
              {[
                ["evidence_text", "→ prompt（format_dpo_prompt 模板）"],
                ["preference.chosen", "→ chosen（修正后输出）"],
                ["preference.rejected", "→ rejected（模型原错）"],
                ["is_original_correct", "筛选闸：必须为 false"],
                ["rating ≥ 3", "筛选闸 + 元数据"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-baseline gap-2 py-1.5">
                  <dt className="w-40 shrink-0 text-foreground/55">{k}</dt>
                  <dd className="min-w-0 text-foreground/85">{v}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-[11px] leading-5 text-foreground/45">
              corrections → preference 接线桥已打通（build_preference）。真实跑等
              <span className="font-mono"> data/rlhf/feedbacks/ </span>有数据。
            </p>
          </div>
        </div>
      </section>

      {/* ===== 三项评测指标 ===== */}
      <section id="metrics" className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
        <div className="mx-auto max-w-[1200px] px-6 py-16">
          <div className="mb-9 max-w-2xl">
            <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
              EVALUATION
            </div>
            <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
              三项指标，两项不花一分钱
            </h2>
            <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
              在人工验证集上对比微调前后。前两项是确定性计算、免费、可复现；只有偏好胜率需要 judge。
            </p>
          </div>

          <TrainingVisual
            src="/landing/training-metrics.svg"
            alt="结构合规率、证据挂靠率、偏好胜率三项评测指标示意图"
            caption="前两项指标直接由 JSON Schema 与原文 evidence_text 计算；偏好胜率才进入 judge，且用 A/B 互换降低位置偏置。"
          />

          <div className="grid gap-px overflow-hidden rounded-sm border border-[var(--table-border)] bg-[var(--table-border)] lg:grid-cols-3">
            {METRICS.map((m) => {
              const Icon = m.icon;
              return (
                <div key={m.en} className="flex flex-col bg-white p-6">
                  <Icon className="h-7 w-7 text-morningstar-red" strokeWidth={1.5} />
                  <h3 className="mt-4 text-[16px] font-bold tracking-tight text-foreground">{m.name}</h3>
                  <div className="mt-1 font-mono text-[11px] text-foreground/40">{m.en}</div>
                  <div className="mt-2 inline-flex w-fit rounded-sm bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold tracking-wider text-foreground/55">
                    {m.cost}
                  </div>
                  <p className="mt-3 flex-1 text-[13px] leading-6 text-[var(--ink-soft)]">{m.body}</p>
                  <p className="mt-3 border-t border-[var(--grid-line)] pt-3 text-[11px] leading-5 text-foreground/50">
                    {m.note}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ===== 数据流 ===== */}
      <section className="mx-auto max-w-[1200px] px-6 py-16">
        <div className="mb-9 max-w-2xl">
          <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
            DATA FLOW
          </div>
          <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
            两条轨道，各自落盘
          </h2>
          <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
            训练轨道与验证轨道平行推进，中间产物逐步落盘，人工标注是两条轨道上唯一的人类节点。
          </p>
        </div>

        <TrainingVisual
          src="/landing/training-tracks.svg"
          alt="训练轨道与验证轨道分别落盘、人工节点高亮、train eval 零重叠的示意图"
          caption="验证轨道生成模型没见过的考卷；训练轨道生成偏好对。两条轨道通过 ID overlap guardrail 防泄漏。"
        />

        <div className="space-y-6">
          <FlowTrack
            label="验证轨道"
            accent="var(--accent-gold)"
            steps={EVAL_TRACK}
            humanIndex={1}
          />
          <FlowTrack
            label="训练轨道"
            accent="var(--morningstar-red)"
            steps={TRAIN_TRACK}
            humanIndex={3}
          />
        </div>
        <p className="mt-4 text-[12px] leading-5 text-foreground/45">
          标注一栏（<Lock className="inline h-3 w-3 -translate-y-px" strokeWidth={2} /> 人类节点）即对应上文三类人工标注任务。
        </p>
      </section>

      {/* ===== 训练线现状 ===== */}
      <section id="status" className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
        <div className="mx-auto max-w-[1200px] px-6 py-16">
          <div className="mb-9 max-w-2xl">
            <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
              BAILIAN DPO LINE · STATUS
            </div>
            <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
              百炼 DPO 训练线，走到哪一步了
            </h2>
            <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
              目标：在阿里云百炼对 Qwen3-8B 跑通真实 DPO-LoRA，产出微调前/后可量化对比。
              地基与数据脚本已就绪并验证；真实实跑尚未发生。已建成与未建成，都说清楚。
            </p>
          </div>

          <div className="overflow-hidden rounded-sm border border-[var(--table-border)] bg-white">
            <div className="hidden grid-cols-[88px_1fr_92px] bg-[var(--table-header-bg)] px-5 py-3 text-[11px] font-bold uppercase tracking-[0.12em] text-foreground/45 sm:grid">
              <div>阶段</div>
              <div>交付</div>
              <div className="text-right">状态</div>
            </div>
            {STAGES.map((s, i) => {
              const st = STATUS_STYLE[s.status];
              return (
                <div
                  key={s.stage}
                  className={`grid grid-cols-[1fr_auto] items-center gap-x-4 px-5 py-4 sm:grid-cols-[88px_1fr_92px] ${
                    i > 0 ? "border-t border-[var(--grid-line)]" : ""
                  }`}
                >
                  <div className="order-1 font-mono text-[12px] font-bold text-foreground/70 sm:order-none">
                    {s.stage}
                  </div>
                  <div className="order-3 col-span-2 mt-1 sm:order-none sm:col-span-1 sm:mt-0">
                    <div className="text-[14px] font-semibold text-foreground">{s.deliver}</div>
                    <div className="mt-0.5 text-[12px] text-[var(--ink-soft)]">{s.detail}</div>
                  </div>
                  <div className="order-2 text-right sm:order-none">
                    <span className={`inline-block rounded-sm px-2 py-0.5 text-[11px] font-bold ${st.cls}`}>
                      {st.label}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 迭代 2 真实结果 + 红线 */}
          <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <div className="rounded-sm border border-[var(--table-border)] bg-white p-6">
              <div className="flex items-center gap-2.5">
                <Target className="h-5 w-5 text-foreground" strokeWidth={1.6} />
                <h3 className="text-[15px] font-bold tracking-tight text-foreground">
                  迭代 2：修过度弃权（真实数据上的校准对比）
                </h3>
              </div>
              <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
                迭代 1 因校准器用字面子串判可溯性，中文「腾讯音乐」对不上模型输出的 TME，89% 真实承诺被清零成
                watchlist，DPO 学成「无脑观望」。迭代 2 改走 entity_registry 中文别名反查 + 降信念而非清零 +
                conviction 分级，在同一批 150 条真实 rejected 上重跑：
              </p>
              <div className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-sm border border-[var(--grid-line)] bg-[var(--grid-line)] text-center">
                {[
                  ["committal（多/空）", "5", "46"],
                  ["watchlist", "56", "8"],
                  ["chosen==rejected", "—", "0 / 150"],
                ].map(([k, before, after]) => (
                  <div key={k} className="bg-white px-3 py-3">
                    <div className="text-[10px] leading-tight text-foreground/45">{k}</div>
                    <div className="mt-1.5 font-mono text-[14px] text-foreground/80">
                      <span className="text-foreground/40">{before}</span>
                      <span className="mx-1 text-foreground/25">→</span>
                      <span className="font-bold text-foreground">{after}</span>
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[11px] leading-5 text-foreground/45">
                这是校准器在真实数据上的行为对比，不是模型微调成绩。
              </p>
            </div>

            <div className="rounded-sm border-t-2 border-morningstar-red bg-white p-6">
              <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-morningstar-red">
                红线
              </div>
              <h3 className="mt-3 text-[16px] font-bold tracking-tight text-foreground">
                不编造提升数字
              </h3>
              <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
                合成 bootstrap 只能证明「管线通 + 原则可学」，不能当质量提升。
                真实的微调前/后数字，只来自百炼实跑后用同一评测集跑出的
                <span className="font-mono"> eval_compare </span>结果——这一格目前留白，待实跑回填。
              </p>
              <p className="mt-3 text-[12px] leading-5 text-foreground/50">
                密钥不进代码、不进日志；harvest / 推理失败如实报告，不用 mock 数据冒充真实结果。
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ===== CTA ===== */}
      <section className="mx-auto max-w-[1200px] px-6 py-16">
        <div className="rounded-sm border-t-2 border-morningstar-red bg-white px-8 py-12 text-center shadow-[var(--shadow-soft)] lg:px-16">
          <ClipboardCheck className="mx-auto h-9 w-9 text-morningstar-red" strokeWidth={1.4} />
          <h2 className="mx-auto mt-5 max-w-2xl text-[26px] font-bold leading-snug tracking-tight text-foreground">
            标注是这条训练线上唯一的人类节点
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-7 text-[var(--ink-soft)]">
            评测集 gold、偏好对抽检、F6 字段修正——每一条都直接决定模型学到什么、又被什么考卷检验。
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href="/demo"
              className="inline-flex items-center gap-2 rounded-sm bg-morningstar-red px-6 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
            >
              启动在线演示
              <ArrowUpRight className="h-4 w-4" strokeWidth={2} />
            </Link>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-sm border border-[var(--table-border)] bg-white px-6 py-3 text-[14px] font-semibold text-foreground transition-colors hover:border-foreground/30"
            >
              <GitHubMark className="h-4 w-4" />
              在 GitHub 看实现
            </a>
          </div>
          <p className="mx-auto mt-8 max-w-xl text-[11px] leading-5 text-foreground/35">
            方法论与字段映射见仓库 docs/specs/2026-06-07-dpo-bailian-training-line.md、
            2026-06-07-f6-rlhf-to-dpo-mapping.md、2026-06-10-annotation-workbench.md、
            2026-06-12-rlvr-guided-dpo-task-card.md。
            数据与训练结果仅供研究，不构成投资建议。
          </p>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}

// ─── 训练页视觉图 ───────────────────────────────────────────────────────────
function TrainingVisual({
  src,
  alt,
  caption,
}: {
  src: string;
  alt: string;
  caption: string;
}) {
  return (
    <figure className="mb-8 overflow-hidden rounded-sm border border-[var(--table-border)] bg-white shadow-[var(--shadow-panel)]">
      <Image
        src={src}
        alt={alt}
        width={1200}
        height={720}
        className="block h-auto w-full"
        sizes="(max-width: 1200px) 100vw, 1200px"
      />
      <figcaption className="border-t border-[var(--grid-line)] bg-[var(--surface-muted)] px-4 py-2 text-[12px] leading-5 text-foreground/50">
        {caption}
      </figcaption>
    </figure>
  );
}

// ─── 数据流轨道（一行步骤，带人类节点高亮）────────────────────────────────────
function FlowTrack({
  label,
  accent,
  steps,
  humanIndex,
}: {
  label: string;
  accent: string;
  steps: { node: string; note: string }[];
  humanIndex: number;
}) {
  return (
    <div className="rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] p-5">
      <div className="mb-3 flex items-center gap-2">
        <span
          className="inline-block h-2.5 w-2.5 rounded-full"
          style={{ backgroundColor: accent }}
        />
        <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-foreground/50">
          {label}
        </span>
      </div>
      <div className="flex flex-wrap items-stretch gap-2">
        {steps.map((s, i) => {
          const human = i === humanIndex;
          return (
            <div key={s.node} className="flex items-stretch gap-2">
              <div
                className={`flex min-w-[112px] flex-col justify-center border px-3 py-2.5 ${
                  human
                    ? "border-foreground/30 bg-white"
                    : "border-[var(--table-border)] bg-white"
                }`}
                style={human ? { borderTopWidth: 2, borderTopColor: accent } : undefined}
              >
                <div className="flex items-center gap-1.5">
                  {human && <Lock className="h-3 w-3 text-foreground/60" strokeWidth={2} />}
                  <span
                    className={`font-mono text-[12px] ${
                      human ? "font-bold text-foreground" : "text-foreground/80"
                    }`}
                  >
                    {s.node}
                  </span>
                </div>
                <span className="mt-0.5 text-[10px] text-[var(--ink-soft)]">{s.note}</span>
              </div>
              {i < steps.length - 1 && (
                <div className="flex items-center text-foreground/25">
                  <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
