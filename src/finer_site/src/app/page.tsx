import Link from "next/link";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Boxes,
  Check,
  Cpu,
  GitBranch,
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
import { cn } from "@/lib/utils";

/** GitHub octocat mark (lucide dropped brand icons for trademark reasons). */
function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222 0 1.606-.014 2.898-.014 3.293 0 .322.216.694.825.576C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
    </svg>
  );
}

const GITHUB_URL = "https://github.com/kelipovanatalja453-bot/finer";
const CONTACT_EMAIL = "kelipovanatalja453@gmail.com";

const NAV_LINKS = [
  { href: "#pipeline", label: "流水线" },
  { href: "#demo", label: "在线演示" },
  { href: "#proof", label: "回测证据" },
  { href: "#capabilities", label: "能力" },
  { href: "#human-loop", label: "AI · 人" },
  { href: "#engineering", label: "技术" },
];

const CAPABILITIES = [
  {
    icon: Radio,
    stage: "F0 · F1",
    title: "采集与归一化",
    body: "飞书、微信公众号、B站等多源 KOL 内容统一接入，标准化为 ContentEnvelope + ContentBlock，保留来源锚点与原始归档。",
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
    title: "回测与评分",
    body: "把语言观点映射到市场结果，模拟完全跟单者的收益曲线，输出夏普、回撤、胜率等可审计绩效指标。",
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
  { label: "模型微调", done: false },
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
    title: "模型微调",
    body: "基于 RLHFFeedback 的 DPO 微调，让模型真正从人工裁决中学习。",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      {/* ===== Nav ===== */}
      <header className="sticky top-0 z-30 border-b border-[var(--table-border)] bg-[rgba(243,239,231,0.86)] backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-sm bg-morningstar-red">
              <Activity className="h-4 w-4 text-white" strokeWidth={1.8} />
            </div>
            <span className="text-[17px] font-bold tracking-tight text-foreground">
              Finer OS
            </span>
          </div>
          <nav className="hidden items-center gap-7 md:flex">
            {NAV_LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="text-[13px] font-medium text-foreground/65 transition-colors hover:text-morningstar-red"
              >
                {l.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="GitHub"
              className="hidden h-9 w-9 items-center justify-center rounded-sm border border-[var(--table-border)] bg-white text-foreground/70 transition-colors hover:border-foreground/30 hover:text-foreground sm:inline-flex"
            >
              <GitHubMark className="h-4 w-4" />
            </a>
            <Link
              href="/demo"
              className="inline-flex items-center gap-1.5 rounded-sm bg-morningstar-red px-3.5 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
            >
              在线演示
              <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
            </Link>
          </div>
        </div>
      </header>

      {/* ===== Hero ===== */}
      <section className="mx-auto max-w-[1200px] px-6 pt-16 pb-12 lg:pt-24">
        <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
          <div>
            <div className="text-[12px] font-bold uppercase tracking-[0.22em] text-morningstar-red">
              AI-NATIVE 投研自动化流水线
            </div>
            <h1 className="mt-5 text-[40px] font-bold leading-[1.12] tracking-tight text-foreground lg:text-[52px]">
              把财经 KOL 的内容，
              <br />
              变成可回测、可审计的
              <br />
              投资事件。
            </h1>
            <p className="mt-6 max-w-xl text-[16px] leading-7 text-[var(--ink-soft)]">
              Finer OS 沿 F0-F8 流水线，将任意平台的 KOL 社交媒体内容
              转化为结构化投资意图、可执行交易动作，并以完全跟单者视角回测，
              验证「跟随这个 KOL」的真实收益与市场表现。
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
                href="#proof"
                className="inline-flex items-center gap-2 rounded-sm border border-[var(--table-border)] bg-white px-5 py-3 text-[14px] font-semibold text-foreground transition-colors hover:border-foreground/30"
              >
                看回测证据
              </a>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-[12px] text-foreground/45">
              <span>证据链可追溯</span>
              <span className="h-1 w-1 rounded-full bg-foreground/20" />
              <span>AI 抽取 · 人工裁决</span>
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
              可溯源的交易动作，看回测曲线如何生成。界面与真实产品一致，
              但所有数据均为演示数据，不连接真实后端。
            </p>
            <ul className="mt-6 space-y-3 text-[14px] text-foreground/80">
              {[
                "F0-F8 流水线逐阶段走查",
                "KOL 研究视图 + 评分与累计收益曲线",
                "点 TradeAction 高亮回溯到原文证据",
                "回测曲线、夏普、最大回撤、胜率",
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
                收益曲线背后，
                <br />
                是完整的证据链
              </h2>
              <p className="mt-5 text-[15px] leading-7 text-[var(--ink-soft)]">
                每条进入回测的 TradeAction 都满足 canonical 契约：可反查到 F3 投资意图、
                F4 策略映射、F2 证据片段，以及四个明确区分的执行时钟。
              </p>
              <ul className="mt-6 space-y-3 text-[14px] text-foreground/80">
                {[
                  "累计收益、年化、夏普、最大回撤、胜率全部可审计",
                  "次开盘成交模型 + 显式费用/滑点假设",
                  "intent_id / policy_id / evidence_span_ids 全程贯穿",
                  "每个数字可回溯到原始 KOL 内容",
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
              AI 在每个阶段做具体可验证的事；每一条 AI 输出在进入回测前都必须经过
              F6 复核台被人类裁决；裁决以结构化字段记录，导出为 DPO
              训练数据——这是 Finer 对「黑箱 AI」最具体的反话术。
            </p>
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
                <span className="font-mono text-foreground/80">F6</span> RLHF 复核台。每条进入回测的
                TradeAction 都必须经过：
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
                  训练循环为 contract-only：DPO 数据格式与导出 API 已就绪，
                  <strong className="text-foreground">下一步规划见下方 Roadmap</strong>
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
              训练循环写明 contract-only：DPO 数据格式与导出 API 已实现，模型微调待启动。
              我们更愿意把已建成与未建成都说清楚。
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
              <span className="font-semibold text-foreground">RLHFFeedback 记录与 DPO 数据导出已实现</span>
              ；Prompt 工程、插件调用、模型微调均为
              <strong className="text-foreground">规划中、尚未实现</strong>
              。我们更愿意把已建成与未建成都说清楚。
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
      <footer className="border-t border-[var(--table-border)] bg-[var(--surface-strong)]">
        <div className="mx-auto max-w-[1200px] px-6 py-10">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div className="max-w-sm">
              <div className="flex items-center gap-2.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-morningstar-red">
                  <Activity className="h-4 w-4 text-white" strokeWidth={1.8} />
                </div>
                <span className="text-[15px] font-bold tracking-tight text-foreground">
                  Finer OS
                </span>
              </div>
              <p className="mt-3 text-[13px] leading-6 text-[var(--ink-soft)]">
                AI-native 投研自动化流水线。把 KOL 内容转化为结构化、可回测、
                可审计的投资事件。
              </p>
            </div>
            <div className="grid grid-cols-2 gap-x-12 gap-y-2 text-[13px]">
              <div className="space-y-2">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/40">
                  产品
                </div>
                <Link href="/demo" className="block text-foreground/70 hover:text-morningstar-red">
                  在线演示
                </Link>
                <a href="#proof" className="block text-foreground/70 hover:text-morningstar-red">
                  回测证据
                </a>
                <a href="#capabilities" className="block text-foreground/70 hover:text-morningstar-red">
                  能力
                </a>
              </div>
              <div className="space-y-2">
                <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/40">
                  联系
                </div>
                <a
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-foreground/70 hover:text-morningstar-red"
                >
                  GitHub
                </a>
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="block text-foreground/70 hover:text-morningstar-red"
                >
                  邮箱
                </a>
              </div>
            </div>
          </div>
          <div className="mt-8 border-t border-[var(--grid-line)] pt-5 text-[12px] text-foreground/40">
            内部研究系统原型 · 数据与回测结果仅供研究，不构成投资建议。
          </div>
        </div>
      </footer>
    </div>
  );
}
