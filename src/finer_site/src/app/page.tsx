import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Boxes,
  Check,
  ClipboardCheck,
  Cpu,
  GitBranch,
  GraduationCap,
  LayoutGrid,
  LineChart,
  Mail,
  MonitorPlay,
  Network,
  Puzzle,
  Radio,
  RotateCw,
  ShieldCheck,
  Sparkles,
  Target,
  UserCheck,
  Wand2,
} from "lucide-react";
import { ProductFrame } from "@/components/landing/product-frame";
import { PipelineStrip } from "@/components/landing/pipeline-strip";
import {
  CONTACT_EMAIL,
  SiteFooter,
  SiteHeader,
} from "@/components/landing/site-chrome";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "#pipeline", label: "流水线" },
  { href: "#records", label: "记录与共识" },
  { href: "#demo", label: "在线演示" },
  { href: "#proof", label: "结算记录" },
  { href: "#capabilities", label: "能力" },
  { href: "#human-loop", label: "标注训练" },
  { href: "#engineering", label: "技术" },
];

const RECORD_VIEWS: {
  src: string;
  alt: string;
  label: string;
  title: string;
  tagline: string;
  points: string[];
  href?: string;
}[] = [
  {
    src: "/landing/record-discover.png",
    href: "/records",
    alt: "Finer OS /discover 信源记录卡：按已结算样本量排列的记录卡与口径开关（真实语料）",
    label: "finer.os / discover",
    title: "/discover · 信源记录卡",
    tagline: "每张卡是一份历史记录，不是推荐。",
    points: [
      "默认按已结算样本量排列——是稳定的输出序，不是排名",
      "命中率并排 95% 区间；样本不足只报计数",
      "个股评级 / 板块观点两种口径不混算（口径开关）",
      "页头常驻持续性检验声明",
    ],
  },
  {
    src: "/landing/record-ticker.png",
    alt: "Finer OS /ticker 个股共识：NVDA 多源记录、目标价区间与陈旧度横幅（真实语料）",
    label: "finer.os / ticker/NVDA",
    title: "/ticker · 个股共识",
    tagline: "谁说过什么，截至哪一天。",
    points: [
      "等权聚合，每个信源只计最新一篇",
      "目标价给最低 / 中位 / 最高；NVDA 9 家信源（USD 205/284/350）",
      "陈旧度横幅置于页头，逐行 intent_id 下钻",
      "无法诚实聚合时显式拒绝——AZN.L 因镑/便士单位混存拒绝聚合目标价",
    ],
  },
  {
    src: "/landing/record-audit.png",
    alt: "Finer OS /audit 证据审计：TradeAction 到原文证据片段的全链下钻（真实语料）",
    label: "finer.os / audit",
    title: "/audit · 证据审计",
    tagline: "每个数字回到原文。",
    points: [
      "TradeAction → F3 意图 → F4 策略 trace → F2 证据片段字符区间 → 原文",
      "canonical_trace_status 全链校验",
      "每个数字 3 次点击内到达原文证据",
    ],
  },
];

const RECORD_STATS = [
  { k: "研报 PDF 静态档案", v: "28,565 份" },
  { k: "canonical TradeAction · 三向审计 100%", v: "4,919 条" },
  { k: "evidence span 证据片段", v: "128,905 个" },
];

const CAPABILITIES = [
  {
    icon: Radio,
    stage: "F0 · F1",
    title: "采集与归一化",
    body: "飞书、B站、券商研报 PDF 等多源内容统一接入（微信为存量归档），标准化为 ContentEnvelope + ContentBlock，保留来源锚点与原始归档。",
  },
  {
    icon: Network,
    stage: "F2",
    title: "锚定证据链",
    body: "实体解析、时间锚定、证据片段（EvidenceSpan）抽取。每个判断都能反查到原文的字符区间与来源时间。",
  },
  {
    icon: Target,
    stage: "F3 · F4 · F5",
    title: "意图 → 策略 → 执行",
    body: "投资意图提取 → Policy 映射 → 生成 TradeAction。每条交易动作携带 intent_id / policy_id / evidence_span_ids 与四时钟执行时间。",
  },
  {
    icon: LineChart,
    stage: "F8",
    title: "回测与结算记录",
    body: "把观点落成可结算、可下钻的记录；比率一律携带样本充分性判定，样本不足只报计数，不构成对未来的预测。",
  },
];

const ENGINEERING = [
  {
    icon: ShieldCheck,
    title: "可审计的证据链",
    body: "从 TradeAction 一路回溯到 Intent、Policy、EvidenceSpan、ContentEnvelope 直到原始内容。canonical_trace_status 校验保证证据链不断裂。",
  },
  {
    icon: GitBranch,
    title: "F-stage 契约架构",
    body: "F0-F8 分层边界用契约冻结，每层声明输入/输出 Schema 与禁止职责。多 Agent 并行开发在可审计边界内收束，杜绝跨层调用。",
  },
  {
    icon: Cpu,
    title: "LLM 工程",
    body: "MiMo-V2.5 负责视觉/OCR，GLM-5.1 与 Qwen 负责富化与结构化提取，Instructor + Pydantic 约束结构化输出，ModelRouter 自动降级。",
  },
];

const STACK = [
  "Python 3.11+",
  "FastAPI",
  "Pydantic v2",
  "Next.js 16",
  "React 19",
  "TailwindCSS 4",
  "ECharts",
  "MiMo-V2.5 / GLM-5.1 / Qwen",
];

const ROADMAP_NODES: { label: string; done: boolean }[] = [
  { label: "RLHFFeedback", done: true },
  { label: "DPO 数据导出", done: true },
  { label: "Prompt 工程", done: false },
  { label: "插件 / 工具调用", done: false },
  { label: "模型微调", done: true },
];

const ROADMAP_PLANNED = [
  {
    icon: Wand2,
    title: "Prompt 工程",
    body: "持续优化各阶段 LLM 提示词与约束解码，提升抽取的一致性与稳定性。",
  },
  {
    icon: Puzzle,
    title: "插件 / 工具调用",
    body: "接入外部金融数据源与工具链，扩展 F2 锚定与 F5 执行的能力边界。",
  },
  {
    icon: Cpu,
    title: "模型微调 · 扩量第二轮",
    body: "第一轮 DPO-LoRA 已实跑（小样本方向验证，数字见 /case）；扩量第二轮规划中。",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* ===== Nav ===== */}
      <SiteHeader links={NAV_LINKS} />

      {/* ===== Hero ===== */}
      <section className="mx-auto max-w-[1200px] px-6 pt-16 pb-12 lg:pt-24">
        <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
          <div>
            <div className="text-[12px] font-bold uppercase tracking-[0.22em] text-morningstar-red">
              AI-NATIVE 投研审计流水线
            </div>
            <h1 className="mt-5 text-[40px] font-bold leading-[1.12] tracking-tight text-foreground lg:text-[52px]">
              不告诉你谁更准。
              <br />
              让你查得清，
              <br />
              谁说过什么。
            </h1>
            <p className="mt-6 max-w-xl text-[16px] leading-7 text-[var(--ink-soft)]">
              Finer 不告诉你谁更准。它让你查得清每一句话是谁在什么时候说的、
              后来发生了什么、以及说的和做的是否一致。F0-F8 流水线把 KOL
              与券商研报内容变成带证据链的结构化记录。
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/demo"
                className="inline-flex items-center gap-2 rounded-sm bg-morningstar-red px-5 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
              >
                启动在线演示
                <ArrowUpRight className="h-4 w-4" strokeWidth={2} />
              </Link>
              <a
                href="#records"
                className="inline-flex items-center gap-2 rounded-sm border border-[var(--table-border)] bg-white px-5 py-3 text-[14px] font-semibold text-foreground transition-colors hover:border-foreground/30"
              >
                看记录与共识
              </a>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-[12px] text-foreground/45">
              <span>每个数字 3 次点击到原文证据</span>
              <span className="h-1 w-1 rounded-full bg-foreground/20" />
              <span>样本不足就说不足</span>
              <span className="h-1 w-1 rounded-full bg-foreground/20" />
              <span>F0-F8 canonical pipeline</span>
            </div>
          </div>

          <ProductFrame
            src="/landing/demo-hero.png"
            alt="Finer OS 工作台：KOL 研究视图、累计收益曲线与证据链溯源（演示数据）"
            width={1440}
            height={900}
            label="finer.os / workbench"
            priority
          />
        </div>
      </section>

      {/* ===== Pipeline ===== */}
      <section id="pipeline" className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
        <div className="mx-auto max-w-[1200px] px-6 py-14">
          <div className="mb-8 max-w-2xl">
            <h2 className="text-[26px] font-bold tracking-tight text-foreground">
              一条内容，走完 F0 → F8
            </h2>
            <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
              每一阶段都有冻结的输入/输出契约。原始内容进来，结构化判断出去，
              中间产物逐层落盘可供人工复核——不是黑箱。
            </p>
          </div>
          <PipelineStrip />
        </div>
      </section>

      {/* ===== Records & consensus — real-corpus read-only views ===== */}
      <section id="records" className="mx-auto max-w-[1200px] px-6 py-16 lg:py-20">
        <div className="mb-10 max-w-2xl">
          <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
            RECORDS &amp; CONSENSUS
          </div>
          <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
            记录与共识：真实语料上的三个只读视图
          </h2>
          <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
            下面三个视图消费的是真实语料，不是演示数据。它们各自回答一个问题：
            这家信源说过什么、这只标的被谁说过、这个数字从哪里来。
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-3 lg:gap-6">
          {RECORD_VIEWS.map((v) => (
            <div key={v.title} className="flex flex-col">
              {v.href ? (
                <Link href={v.href} className="group block">
                  <ProductFrame
                    src={v.src}
                    alt={v.alt}
                    width={1440}
                    height={900}
                    label={v.label}
                    className="transition-transform duration-200 group-hover:-translate-y-0.5"
                  />
                </Link>
              ) : (
                <ProductFrame
                  src={v.src}
                  alt={v.alt}
                  width={1440}
                  height={900}
                  label={v.label}
                />
              )}
              <h3 className="mt-4 text-[16px] font-bold tracking-tight text-foreground">
                {v.title}
              </h3>
              <p className="mt-1 text-[13px] font-medium text-morningstar-red">{v.tagline}</p>
              <ul className="mt-3 space-y-2 text-[13px] leading-6 text-[var(--ink-soft)]">
                {v.points.map((p) => (
                  <li key={p} className="flex items-start gap-2.5">
                    <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-morningstar-red" />
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* /records CTA */}
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <Link
            href="/records"
            className="inline-flex items-center gap-2 rounded-sm bg-morningstar-red px-6 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
          >
            点开每家信源的完整记录
            <ArrowRight className="h-4 w-4" strokeWidth={2} />
          </Link>
          <span className="text-[12px] text-foreground/45">
            冻结快照 · 2026-08-10 · 含每条记录的评级、目标价与结算结果
          </span>
        </div>

        {/* numbers strip */}
        <div className="mt-10 grid gap-px overflow-hidden rounded-sm border border-[var(--table-border)] bg-[var(--table-border)] sm:grid-cols-3">
          {RECORD_STATS.map((s) => (
            <div key={s.k} className="bg-white px-6 py-5">
              <div className="tabular-nums text-[26px] font-bold tracking-tight text-foreground">
                {s.v}
              </div>
              <div className="mt-1 text-[12px] leading-5 text-[var(--ink-soft)]">{s.k}</div>
            </div>
          ))}
        </div>

        {/* honest statistics */}
        <div className="mt-6 border-t-2 border-morningstar-red bg-white p-6 shadow-[var(--shadow-soft)]">
          <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-morningstar-red">
            诚实的统计
          </div>
          <p className="mt-3 max-w-3xl text-[14px] leading-7 text-[var(--ink-soft)]">
            我们在 2,983 条已结算 action 上检验过「券商历史超额能否预测未来超额」：
            两个指标、六个切分点、预声明判据，双双不成立。判据先于结果写死在
            <span className="font-mono text-[13px] text-foreground/80">
              {" "}scripts/test_credibility_persistence.py{" "}
            </span>
            里。我们把这个否定结果公开，并据此把产品改写为如实记录。
          </p>
          <p className="mt-3 max-w-3xl text-[13px] leading-6 text-foreground/70">
            本平台未观测到信源历史表现的跨期持续性；所有比率均为历史记录，不构成对未来的预测。
          </p>
        </div>

        <div className="mt-4 text-[12px] text-foreground/45">
          真实语料 · 2026-08-10 截图 · 页头陈旧度横幅为产品功能：语料是静态档案，记录截至哪一天就标注到哪一天
        </div>
      </section>

      {/* ===== Interactive demo entry ===== */}
      <section id="demo" className="mx-auto max-w-[1200px] px-6 py-16 lg:py-20">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-center">
          <div>
            <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
              INTERACTIVE DEMO
            </div>
            <h2 className="mt-4 text-[28px] font-bold leading-snug tracking-tight text-foreground">
              在浏览器里，
              <br />
              直接走一遍 F0 → F8
            </h2>
            <p className="mt-5 text-[15px] leading-7 text-[var(--ink-soft)]">
              不用注册、不用部署。打开在线演示，亲手点一条 KOL 观点如何逐层变成
              可溯源的交易动作，看回测曲线如何生成。演示展示 F0-F8 流水线能力；
              当前产品消费面以「记录与共识」的三个只读视图为准。
              所有数据均为演示数据，不连接真实后端。
            </p>
            <ul className="mt-6 space-y-3 text-[14px] text-foreground/80">
              {[
                "F0-F8 流水线逐阶段走查",
                "KOL 记录视图 + 已结算样本与累计收益曲线（演示数据）",
                "点 TradeAction 高亮回溯到原文证据",
                "回测曲线、夏普、最大回撤、胜率（历史记录口径）",
              ].map((t) => (
                <li key={t} className="flex items-start gap-2.5">
                  <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-morningstar-red" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
            <div className="mt-8">
              <Link
                href="/demo"
                className="inline-flex items-center gap-2 rounded-sm bg-morningstar-red px-6 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
              >
                <MonitorPlay className="h-4 w-4" strokeWidth={2} />
                启动在线演示
              </Link>
              <div className="mt-3 text-[12px] text-foreground/45">
                演示数据 · Sample data only · 不连接真实后端
              </div>
            </div>
          </div>

          <Link href="/demo" className="group block">
            <ProductFrame
              src="/landing/demo-entry.png"
              alt="Finer OS 在线演示：mock 工作台（演示数据）"
              width={1440}
              height={900}
              label="finer.os / demo"
              className="transition-transform duration-200 group-hover:-translate-y-0.5"
            />
          </Link>
        </div>
      </section>

      {/* ===== Workflow proof / money shot ===== */}
      <section id="proof" className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
        <div className="mx-auto max-w-[1200px] px-6 py-16 lg:py-20">
          <div className="grid gap-10 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:items-center">
            <ProductFrame
              src="/landing/demo-proof.png"
              alt="Finer OS 工作台：累计收益曲线与右栏证据链溯源、四时钟执行时间（演示数据）"
              width={1440}
              height={900}
              label="finer.os / workbench"
            />
            <div className="lg:pl-4">
              <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
                F8 BACKTEST AUDIT
              </div>
              <h2 className="mt-4 text-[28px] font-bold leading-snug tracking-tight text-foreground">
                收益曲线是历史记录，
                <br />
                不是承诺
              </h2>
              <p className="mt-5 text-[15px] leading-7 text-[var(--ink-soft)]">
                每条进入回测的 TradeAction 都满足 canonical 契约：可反查到 F3 投资意图、
                F4 策略映射、F2 证据片段，以及四个明确区分的执行时钟。
                曲线与比率呈现的是「后来发生了什么」，不构成对未来的预测。
              </p>
              <ul className="mt-6 space-y-3 text-[14px] text-foreground/80">
                {[
                  "累计收益、年化、夏普、最大回撤逐笔可审计",
                  "比率随样本充分性呈现——样本不足只报计数",
                  "次开盘成交模型 + 显式费用/滑点假设",
                  "intent_id / policy_id / evidence_span_ids 全程贯穿",
                  "每个数字可回溯到原始内容，不构成对未来的预测",
                ].map((t) => (
                  <li key={t} className="flex items-start gap-2.5">
                    <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-morningstar-red" />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Capabilities ===== */}
      <section id="capabilities" className="mx-auto max-w-[1200px] px-6 py-16 lg:py-20">
        <div className="mb-10 max-w-2xl">
          <h2 className="text-[26px] font-bold tracking-tight text-foreground">
            四个不可约的能力
          </h2>
          <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
            从噪声到证据，从意图到执行，最终落到可验证的市场结果。
          </p>
        </div>
        <div className="grid gap-px overflow-hidden rounded-sm border border-[var(--table-border)] bg-[var(--table-border)] sm:grid-cols-2 lg:grid-cols-4">
          {CAPABILITIES.map((c) => {
            const Icon = c.icon;
            return (
              <div key={c.title} className="flex flex-col gap-3 bg-white p-6">
                <Icon className="h-7 w-7 text-morningstar-red" strokeWidth={1.5} />
                <div className="text-[11px] font-bold tabular-nums tracking-[0.16em] text-foreground/40">
                  {c.stage}
                </div>
                <h3 className="text-[16px] font-bold text-foreground">{c.title}</h3>
                <p className="text-[13px] leading-6 text-[var(--ink-soft)]">{c.body}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* ===== AI · Human-in-the-loop / RLHF ===== */}
      <section id="human-loop" className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
        <div className="mx-auto max-w-[1200px] px-6 py-16 lg:py-20">
          <div className="mb-10 max-w-2xl">
            <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
              AI · HUMAN-IN-THE-LOOP
            </div>
            <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
              AI 抽取，人类裁决，反馈成为训练数据
            </h2>
            <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
              AI 在每个阶段做具体可验证的事；进入回测的硬门是三向审计闭环
              （intent / policy / evidence 100% 可反查）；F6 人工裁决按需、抽样进行，
              以结构化字段记录并沉淀为 DPO 训练数据——这是 Finer
              对「黑箱 AI」最具体的反话术。
            </p>
          </div>

          {/* Annotation workbench feature */}
          <div className="mb-10 grid gap-6 lg:grid-cols-[minmax(0,1.18fr)_minmax(320px,0.82fr)] lg:items-center">
            <ProductFrame
              src="/landing/annotation-workbench.png"
              alt="Finer OS 标注工作台：原文证据、Gold 表单、质量闸和 Formal export 阻断"
              width={1440}
              height={980}
              label="finer.os / annotation"
            />
            <div className="border-t-2 border-morningstar-red bg-white p-6 shadow-[var(--shadow-soft)]">
              <div className="flex items-center gap-2">
                <ClipboardCheck className="h-7 w-7 text-morningstar-red" strokeWidth={1.5} />
                <span className="rounded-sm border border-[rgba(225,27,34,0.18)] bg-[rgba(225,27,34,0.08)] px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-morningstar-red">
                  HUMAN LABELING
                </span>
              </div>
              <h3 className="mt-4 text-[20px] font-bold tracking-tight text-foreground">
                标注台不是外包页面，是训练资产入口
              </h3>
              <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
                评测集 Gold、DPO chosen 侧抽检、F6 字段级纠错都在同一套工作台里落盘。
                每条记录都带 reviewer_id / reviewed_at，可重建、可 diff、可导出。
              </p>
              <div className="mt-4 space-y-2 text-[12px] leading-5 text-foreground/70">
                {[
                  "Gold 标注：独立 held-out 考卷，不喂给模型",
                  "偏好抽检：chosen / rejected 的质量闸",
                  "RLHF 纠错：真实 F5 错误回流成 DPO pairs",
                ].map((item) => (
                  <div key={item} className="flex items-start gap-2">
                    <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-morningstar-red" />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <Link
                  href="/training"
                  className="inline-flex items-center gap-2 rounded-sm bg-morningstar-red px-4 py-2.5 text-[13px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
                >
                  <GraduationCap className="h-4 w-4" strokeWidth={1.8} />
                  看训练数据页
                </Link>
                <Link
                  href="/demo"
                  className="inline-flex items-center gap-2 rounded-sm border border-[var(--table-border)] bg-white px-4 py-2.5 text-[13px] font-semibold text-foreground transition-colors hover:border-foreground/30"
                >
                  在演示里试 F6 复核
                </Link>
              </div>
            </div>
          </div>

          {/* Three concept columns */}
          <div className="grid gap-6 lg:grid-cols-3">
            {/* AI does what */}
            <div className="border-t-2 border-[var(--foreground)] bg-white p-6">
              <div className="flex items-center gap-2">
                <Sparkles className="h-7 w-7 text-foreground" strokeWidth={1.4} />
                <span className="rounded-sm border border-[rgba(225,27,34,0.18)] bg-[rgba(225,27,34,0.08)] px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-morningstar-red">
                  AI
                </span>
              </div>
              <h3 className="mt-4 text-[17px] font-bold tracking-tight text-foreground">
                AI 做什么
              </h3>
              <ul className="mt-3 space-y-2 text-[13px] leading-6 text-[var(--ink-soft)]">
                <li>
                  <span className="font-mono text-foreground/80">F1</span> 视觉/OCR：MiMo-V2.5
                  处理图片、PDF、截图
                </li>
                <li>
                  <span className="font-mono text-foreground/80">F1.5</span> 主题组装：constrained
                  LLM 提议 + 确定性 validator 兜底
                </li>
                <li>
                  <span className="font-mono text-foreground/80">F3</span> 投资意图：LLM 从证据片段
                  提取结构化 stance / conviction
                </li>
                <li>
                  <span className="font-mono text-foreground/80">F5</span> TradeAction：LLM
                  + 规则共同构造 canonical 动作
                </li>
              </ul>
            </div>

            {/* Human intervenes */}
            <div className="border-t-2 border-[var(--accent-gold)] bg-white p-6">
              <div className="flex items-center gap-2">
                <UserCheck className="h-7 w-7 text-foreground" strokeWidth={1.4} />
                <span className="rounded-sm border border-[rgba(155,123,69,0.25)] bg-[rgba(155,123,69,0.12)] px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-[var(--accent-gold)]">
                  人
                </span>
              </div>
              <h3 className="mt-4 text-[17px] font-bold tracking-tight text-foreground">
                人在哪儿介入
              </h3>
              <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
                <span className="font-mono text-foreground/80">F6</span> RLHF
                复核台。进入回测的硬门是三向审计闭环；人工裁决按需、抽样进行，
                每条裁决包含：
              </p>
              <ul className="mt-2 space-y-2 text-[13px] leading-6 text-[var(--ink-soft)]">
                <li>整体 1-5 星评分 + <span className="font-mono">is_correct</span> 判断</li>
                <li>字段级修正：direction / ticker / action chain</li>
                <li>自由文本备注 + 快捷标签</li>
                <li>reviewer_id / reviewed_at 全程可审计</li>
              </ul>
            </div>

            {/* Feedback persists */}
            <div className="border-t-2 border-[var(--foreground)] bg-white p-6">
              <div className="flex items-center gap-2">
                <RotateCw className="h-7 w-7 text-foreground" strokeWidth={1.4} />
                <span className="rounded-sm border border-[var(--table-border)] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-[var(--ink-soft)]">
                  反馈
                </span>
              </div>
              <h3 className="mt-4 text-[17px] font-bold tracking-tight text-foreground">
                反馈如何沉淀
              </h3>
              <ul className="mt-3 space-y-2 text-[13px] leading-6 text-[var(--ink-soft)]">
                <li>持久化为 <span className="font-mono">RLHFFeedback</span> 记录</li>
                <li>
                  <span className="font-mono">GET /api/rlhf/export</span> 导出为 DPO 训练数据
                </li>
                <li>
                  第一轮微调已实跑，前后对比见
                  <Link href="/case" className="font-semibold text-morningstar-red hover:underline">
                    /case
                  </Link>
                  ；
                  <Link href="/training" className="font-semibold text-morningstar-red hover:underline">
                    训练数据页
                  </Link>
                  讲清全貌
                </li>
              </ul>
            </div>
          </div>

          {/* Loop strip */}
          <div className="mt-10 rounded-sm border border-[var(--table-border)] bg-[var(--surface-strong)] p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-foreground/45">
                RLHF Loop
              </span>
              <span className="font-mono text-[11px] text-foreground/40">
                POST /api/rlhf/submit → GET /api/rlhf/export
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                { tag: "AI", label: "AI 抽取", body: "F1-F5 LLM" },
                { tag: "人", label: "人工裁决", body: "F6 RLHF Panel" },
                { tag: "记录", label: "RLHFFeedback", body: "结构化字段" },
                { tag: "导出", label: "DPO 训练数据", body: "JSONL pairs" },
              ].map((step, i, arr) => (
                <div key={step.label} className="relative">
                  <div className="border border-[var(--table-border)] bg-white px-3 py-3">
                    <div className="text-[10px] font-bold tracking-wider text-morningstar-red">
                      {step.tag}
                    </div>
                    <div className="mt-1 text-[13px] font-semibold text-foreground">
                      {step.label}
                    </div>
                    <div className="mt-0.5 font-mono text-[10px] text-[var(--ink-soft)]">
                      {step.body}
                    </div>
                  </div>
                  {i < arr.length - 1 && (
                    <div className="pointer-events-none absolute -right-2 top-1/2 hidden -translate-y-1/2 text-foreground/30 sm:block">
                      <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-3 text-[11px] leading-5 text-[var(--ink-soft)]">
              DPO 数据格式、导出 API、偏好对流水线与三指标评测器已实现；第一轮微调已实跑
              （小样本方向验证，数字见 /case），扩量轮待做。我们更愿意把已建成与未建成都说清楚。
            </div>
          </div>

          {/* Schema preview + F6 screenshot */}
          <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
            {/* RLHFFeedback schema preview card */}
            <div className="overflow-hidden rounded-sm border border-[var(--table-border)] bg-white">
              <div className="flex items-center justify-between border-b border-[var(--table-border)] bg-[var(--table-header-bg)] px-4 py-2.5">
                <span className="font-mono text-[12px] font-bold text-foreground">
                  RLHFFeedback
                </span>
                <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-foreground/40">
                  schema · example record
                </span>
              </div>
              <dl className="divide-y divide-[var(--grid-line)] font-mono text-[12px]">
                {[
                  ["rating", "4 / 5  ★★★★"],
                  ["is_correct", "true"],
                  ["corrected_direction", "bearish → bullish"],
                  ["corrected_ticker", "(unchanged)"],
                  ["corrections", "[\"target price range too narrow\"]"],
                  ["review_notes", "\"Time horizon should be 6mo, not 3mo.\""],
                  ["reviewer_id", "reviewer_demo"],
                  ["reviewed_at", "2026-05-28T14:32:18Z"],
                ].map(([k, v]) => (
                  <div key={k} className="flex items-baseline gap-3 px-4 py-2">
                    <dt className="w-44 shrink-0 text-foreground/55">{k}</dt>
                    <dd className="min-w-0 truncate text-foreground/90">{v}</dd>
                  </div>
                ))}
              </dl>
              <div className="border-t border-[var(--grid-line)] bg-[var(--surface-muted)] px-4 py-2 text-[11px] text-[var(--ink-soft)]">
                字段来自 <span className="font-mono">src/finer/schemas/trade_action.py</span> 的
                <span className="font-mono"> RLHFFeedback</span>。示例值仅用于展示。
              </div>
            </div>

            {/* F6 review queue screenshot */}
            <ProductFrame
              src="/landing/review.png"
              alt="Finer OS F6 RLHF 审核台：标记为 NEEDS REVIEW 的资产队列与审核工作台入口"
              width={1440}
              height={900}
              label="finer.os / workbench?tier=F6"
            />
          </div>

          {/* Roadmap — training-loop honesty as an editorial timeline */}
          <div className="mt-12 overflow-hidden rounded-sm border border-[var(--table-border)] bg-white">
            <div className="flex flex-wrap items-end justify-between gap-3 border-b border-[var(--table-border)] bg-[var(--table-header-bg)] px-6 py-4">
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
                  Training Loop · Roadmap
                </div>
                <h3 className="mt-1 text-[18px] font-bold tracking-tight text-foreground">
                  训练闭环：已建成 → 下一步规划
                </h3>
              </div>
              <div className="flex items-center gap-4 text-[11px] text-[var(--ink-soft)]">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-morningstar-red" /> 已建成
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full border-2 border-[var(--accent-gold)] bg-white" />{" "}
                  规划中
                </span>
              </div>
            </div>

            {/* horizontal progress axis */}
            <div className="overflow-x-auto px-6 py-7 finer-scrollbar">
              <div className="flex min-w-[640px] items-start">
                {ROADMAP_NODES.map((node, i) => {
                  const prev = ROADMAP_NODES[i - 1];
                  const next = ROADMAP_NODES[i + 1];
                  const leftSolid = Boolean(prev?.done && node.done);
                  const rightSolid = Boolean(node.done && next?.done);
                  return (
                    <div key={node.label} className="flex flex-1 flex-col items-center">
                      <div className="flex w-full items-center">
                        <span
                          className={cn(
                            "h-px flex-1",
                            i === 0
                              ? "opacity-0"
                              : leftSolid
                                ? "bg-morningstar-red"
                                : "border-t border-dashed border-[var(--accent-gold)]/60",
                          )}
                        />
                        {node.done ? (
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-morningstar-red">
                            <Check className="h-4 w-4 text-white" strokeWidth={2.4} />
                          </span>
                        ) : (
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 border-[var(--accent-gold)] bg-white text-[11px] font-bold text-[var(--accent-gold)]">
                            {i - 1}
                          </span>
                        )}
                        <span
                          className={cn(
                            "h-px flex-1",
                            i === ROADMAP_NODES.length - 1
                              ? "opacity-0"
                              : rightSolid
                                ? "bg-morningstar-red"
                                : "border-t border-dashed border-[var(--accent-gold)]/60",
                          )}
                        />
                      </div>
                      <div className="mt-2.5 text-center">
                        <div className="text-[12px] font-semibold text-foreground">{node.label}</div>
                        <div
                          className={cn(
                            "mt-0.5 text-[10px] font-bold uppercase tracking-wider",
                            node.done ? "text-morningstar-red" : "text-[var(--accent-gold)]",
                          )}
                        >
                          {node.done ? "已建成" : "规划中"}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* planned detail cards */}
            <div className="grid gap-px border-t border-[var(--table-border)] bg-[var(--table-border)] sm:grid-cols-3">
              {ROADMAP_PLANNED.map((p) => {
                const Icon = p.icon;
                return (
                  <div
                    key={p.title}
                    className="flex flex-col gap-2 border-t-2 border-dashed border-[var(--accent-gold)] bg-white p-5"
                  >
                    <div className="flex items-center gap-2">
                      <Icon className="h-6 w-6 text-foreground" strokeWidth={1.5} />
                      <span className="rounded-sm border border-[rgba(155,123,69,0.3)] bg-[rgba(155,123,69,0.1)] px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-[var(--accent-gold)]">
                        规划中
                      </span>
                    </div>
                    <h4 className="text-[15px] font-bold tracking-tight text-foreground">{p.title}</h4>
                    <p className="text-[12px] leading-6 text-[var(--ink-soft)]">{p.body}</p>
                  </div>
                );
              })}
            </div>

            <div className="border-t border-[var(--grid-line)] bg-[var(--surface-muted)] px-6 py-3 text-[12px] leading-6 text-[var(--ink-soft)]">
              <span className="font-semibold text-foreground">RLHFFeedback 记录、DPO 数据导出与评测/训练脚本地基已实现</span>
              ；Prompt 工程、插件调用为规划中，模型微调
              <strong className="text-foreground">第一轮已出小样本结果（见 /case），扩量第二轮规划中</strong>
              。完整现状见
              <Link href="/training" className="font-semibold text-morningstar-red hover:underline">
                训练数据页
              </Link>
              。
            </div>
          </div>
        </div>
      </section>

      {/* ===== Engineering / recruiting ===== */}
      <section id="engineering" className="mx-auto max-w-[1200px] px-6 py-16 lg:py-20">
        <div className="mb-10 max-w-2xl">
          <div className="text-[12px] font-bold uppercase tracking-[0.2em] text-morningstar-red">
            ENGINEERING
          </div>
          <h2 className="mt-4 text-[26px] font-bold tracking-tight text-foreground">
            工程上，我们认真对待「可信」
          </h2>
          <p className="mt-3 text-[15px] leading-7 text-[var(--ink-soft)]">
            投研系统的可信不来自视觉装饰，而来自清晰的信息架构、硬契约、
            可追溯的证据和诚实的不确定性。
          </p>
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          {ENGINEERING.map((e) => {
            const Icon = e.icon;
            return (
              <div key={e.title} className="border-t-2 border-[var(--foreground)] bg-white p-6">
                <Icon className="h-8 w-8 text-foreground" strokeWidth={1.4} />
                <h3 className="mt-4 text-[17px] font-bold tracking-tight text-foreground">
                  {e.title}
                </h3>
                <p className="mt-2 text-[14px] leading-6 text-[var(--ink-soft)]">{e.body}</p>
              </div>
            );
          })}
        </div>
        <div className="mt-8 flex flex-wrap items-center gap-2">
          <span className="mr-1 text-[12px] font-bold uppercase tracking-[0.14em] text-foreground/40">
            Stack
          </span>
          {STACK.map((s) => (
            <span
              key={s}
              className="rounded-sm border border-[var(--table-border)] bg-white px-2.5 py-1 font-mono text-[12px] text-foreground/70"
            >
              {s}
            </span>
          ))}
        </div>
      </section>

      {/* ===== Gallery ===== */}
      <section className="border-t border-[var(--table-border)] bg-[var(--surface-strong)]">
        <div className="mx-auto max-w-[1200px] px-6 py-16">
          <div className="mb-8 flex items-end justify-between gap-4">
            <h2 className="text-[26px] font-bold tracking-tight text-foreground">
              工作台即产品
            </h2>
            <Link
              href="/demo"
              className="hidden items-center gap-1.5 text-[13px] font-semibold text-morningstar-red hover:underline sm:inline-flex"
            >
              <LayoutGrid className="h-4 w-4" strokeWidth={1.8} />
              启动在线演示
            </Link>
          </div>
          <ProductFrame
            src="/landing/workbench.png"
            alt="Finer OS 工作台：F0-F8 工作流导航、资产网格与证据溯源面板"
            width={1440}
            height={900}
            label="finer.os / workbench"
          />
        </div>
      </section>

      {/* ===== Join CTA ===== */}
      <section id="join" className="mx-auto max-w-[1200px] px-6 py-20">
        <div className="rounded-sm border-t-2 border-morningstar-red bg-white px-8 py-12 text-center shadow-[var(--shadow-soft)] lg:px-16 lg:py-16">
          <Boxes className="mx-auto h-9 w-9 text-morningstar-red" strokeWidth={1.4} />
          <h2 className="mx-auto mt-5 max-w-2xl text-[28px] font-bold leading-snug tracking-tight text-foreground">
            如果你也想把混乱的内容，变成可信的判断
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-7 text-[var(--ink-soft)]">
            我们在找认真对待数据契约、证据链和金融语义的工程师与研究者。
            如果上面的东西让你眼睛发亮，欢迎聊聊。
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
              href={`mailto:${CONTACT_EMAIL}`}
              className="inline-flex items-center gap-2 rounded-sm border border-[var(--table-border)] bg-white px-6 py-3 text-[14px] font-semibold text-foreground transition-colors hover:border-foreground/30"
            >
              <Mail className="h-4 w-4" strokeWidth={1.8} />
              联系我们
            </a>
          </div>
        </div>
      </section>

      {/* ===== Footer ===== */}
      <SiteFooter />
    </div>
  );
}
