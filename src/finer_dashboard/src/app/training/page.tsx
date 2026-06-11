import Link from "next/link";
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
  RotateCw,
  Scale,
  ShieldCheck,
  Target,
  X,
} from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// 纯静态叙事页。所有结构与数字均取自仓库内已落地的 spec / schema / 脚本：
//   docs/specs/2026-06-07-dpo-bailian-training-line.md
//   docs/specs/2026-06-07-f6-rlhf-to-dpo-mapping.md
//   docs/specs/2026-06-10-annotation-workbench.md
//   src/finer/schemas/{annotation,trade_action}.py
// 红线：不编造模型提升数字。eval_compare --demo 为玩具数据，本页不作为真实成绩展示；
// 真实微调数字留待百炼实跑回填。
// ─────────────────────────────────────────────────────────────────────────────

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
  { stage: "数据②", deliver: "to_bailian.py 百炼 ChatML 转换", status: "done", detail: "闸③已核实格式 + Qwen3-8B 支持 DPO LoRA" },
  { stage: "数据①", deliver: "harvest rejected → 校准 chosen", status: "pending", detail: "闸②烧钱待授权（DashScope qwen3-8b 真实跑）" },
  { stage: "实跑", deliver: "百炼上传 / 训练 / 部署 / 评测", status: "user", detail: "仅用户可做，回填 after.jsonl 出真实数字" },
];

const STATUS_STYLE: Record<string, { label: string; cls: string }> = {
  done: { label: "已就绪", cls: "bg-[rgba(16,185,129,0.12)] text-[#0f7a54]" },
  pending: { label: "待授权", cls: "bg-[rgba(155,123,69,0.14)] text-[var(--accent-gold)]" },
  user: { label: "待用户", cls: "bg-[var(--surface-muted)] text-foreground/55" },
};

// 验证集轨道与训练集轨道（两条数据流）
const EVAL_TRACK = [
  { node: "passages.jsonl", note: "held-out 段落" },
  { node: "人工 Gold 标注", note: "/annotation" },
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

export default function TrainingPage() {
  return (
    <div className="finer-scrollbar min-h-full bg-background">
      {/* ===== Hero ===== */}
      <section className="mx-auto max-w-[1200px] px-6 pt-12 pb-10 lg:pt-16">
        <div className="text-[12px] font-bold uppercase tracking-[0.22em] text-morningstar-red">
          人工标注 · RLHF · DPO 训练数据
        </div>
        <h1 className="mt-5 max-w-3xl text-[34px] font-bold leading-[1.15] tracking-tight text-foreground lg:text-[44px]">
          人工标注与 RLHF，
          <br />
          如何沉淀为 DPO 训练数据
        </h1>
        <p className="mt-6 max-w-2xl text-[16px] leading-7 text-[var(--ink-soft)]">
          模型抽取的投资判断，在进入回测前都要被人类裁决。这些裁决与标注被结构化记录，
          一路沉淀为两类资产——喂给模型学习的 <strong className="text-foreground">DPO 训练集</strong>，
          与模型从未见过、用来诚实打分的 <strong className="text-foreground">人工验证集</strong>。
          这一页讲清楚标注了什么、为什么把训练与验证严格分开、以及百炼 DPO 训练线现在走到了哪一步。
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/annotation"
            className="inline-flex items-center gap-2 rounded-sm bg-morningstar-red px-5 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
          >
            打开标注工作台
            <ArrowUpRight className="h-4 w-4" strokeWidth={2} />
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
          <span>不编造提升数字</span>
        </div>
      </section>

      {/* ===== 各类人工标注 ===== */}
      <section className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
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
      <section className="mx-auto max-w-[1200px] px-6 py-16">
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
      <section className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
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
      <section className="border-y border-[var(--table-border)] bg-[var(--surface-strong)]">
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
              地基与数据脚本已就绪并验证；真实实跑由用户执行。已建成与未建成，都说清楚。
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
                <span className="font-mono"> eval_compare </span>结果——这一格目前留白，待用户实跑回填。
              </p>
              <p className="mt-3 text-[12px] leading-5 text-foreground/50">
                密钥不进代码、不进日志、不进会话；harvest / 推理失败如实报告，不用 mock 数据冒充真实结果。
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
              href="/annotation"
              className="inline-flex items-center gap-2 rounded-sm bg-morningstar-red px-6 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
            >
              打开标注工作台
              <ArrowUpRight className="h-4 w-4" strokeWidth={2} />
            </Link>
            <Link
              href="/"
              className="inline-flex items-center gap-2 rounded-sm border border-[var(--table-border)] bg-white px-6 py-3 text-[14px] font-semibold text-foreground transition-colors hover:border-foreground/30"
            >
              返回工作台
            </Link>
          </div>
          <p className="mx-auto mt-8 max-w-xl text-[11px] leading-5 text-foreground/35">
            方法论与字段映射见 docs/specs/2026-06-07-dpo-bailian-training-line.md、
            2026-06-07-f6-rlhf-to-dpo-mapping.md、2026-06-10-annotation-workbench.md。
            数据与训练结果仅供研究，不构成投资建议。
          </p>
        </div>
      </section>
    </div>
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
