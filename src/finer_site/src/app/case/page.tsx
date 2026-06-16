import type { ReactNode } from "react";
import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { GITHUB_URL, SiteFooter, SiteHeader } from "@/components/landing/site-chrome";

// ─────────────────────────────────────────────────────────────────────────────
// 纯静态学术案例页（case study）。受众：bio + ML 硕士导师 / 招生委员会。
// 主语始终是"我（本科生，独立完成）展示的 ML 能力与研究素养，方法论可迁移到 biomedical"。
// 数字均来自仓库内真实产物，每个标清来源：
//   DPO 第一轮 before/after — held-out eval n=29, judge=ref, 训练 20 条 registry-验证精选偏好对
//     编造率 66.7→22.2 / 证据挂靠 33.3→77.8 / 偏好胜率 87.1%(W13/T14/L2) — scripts/eval_compare.py
//   committal 49→18 — 数据处理统计（剔脏数据致偏好塌缩）
//   RLVR 奖励函数 — src/finer/ml/rewards.py（已实现）
//   100 偏好 + 31 文献真值 — 数据资产；20+29 为第一轮实验子集
//   13.03 亿 token — 跨 Finer + ESM 蛋白等全部项目总量，非 Finer 单一项目
// 红线：DPO 第一轮已完成，用真实结果；不夸大、写明局限（小样本/第一轮/方向验证）。
// ─────────────────────────────────────────────────────────────────────────────

const DEMO_URL = "https://finer.t800.click";

export const metadata: Metadata = {
  title: "Finer · 项目案例研究",
  description:
    "本科独立完成的端到端 ML 系统：把噪声社媒文本转成可审计、可回测的结构化信号；方法论（实体标准化、数据质量把关、专家偏好对齐）可迁移到 biomedical NLP。",
};

const NAV_LINKS = [
  { href: "/training", label: "训练线" },
  { href: "/demo", label: "标注全流程" },
];

const STATS = [
  { label: "偏好胜率（DPO 前后）", value: "87.1%", note: "held-out eval · n=29", accent: true },
  { label: "编造率", value: "66.7%→22.2%", note: "微调前 → 后" },
  { label: "数据资产", value: "100 + 31", note: "人工偏好 · 文献真值" },
  { label: "系统", value: "F0–F8", note: "自研标注平台 Finer OS" },
];

const FLOW = ["F0 接入", "F1 标准化", "F2 实体锚定", "F3–F5 抽取", "F6 人工偏好", "对齐训练"];

const CHALLENGES = [
  { found: "禾赛 → 赫斯石油(HES)", kind: "实体歧义错配", bio: "基因符号歧义（同名 / 跨物种）" },
  { found: "速腾 → HSAI（自动修）", kind: "自动修正引入新错", bio: "本体对齐须专家校验" },
  { found: "committal 49%→18%", kind: "剔脏数据致偏好塌缩", bio: "过滤偏差 / 批次效应" },
];

const METRICS = [
  { label: "证据挂靠率（越高越好）", text: "33.3% → 77.8%", width: "77.8%" },
  { label: "编造率（越低越好）", text: "66.7% → 22.2%", width: "22.2%" },
  { label: "结构合规率", text: "100% → 100%", width: "100%" },
];

const TRANSFER = [
  ["实体标准化", "ticker→registry 消歧 ＝ gene / protein / drug normalization"],
  ["数据质量把关", "错配 / 塌缩较真 ＝ 假阳性 / 金标准 / 批次效应"],
  ["专家偏好对齐", "人工偏好 + DPO ＝ 对齐模型到领域专家"],
];

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-morningstar-red">
      {children}
    </p>
  );
}

export default function CasePage() {
  return (
    <div className="bg-white">
      <SiteHeader links={NAV_LINKS} />
      <main className="mx-auto max-w-3xl px-6 py-12 text-[15px] leading-[1.75] text-stone-800 sm:py-16">
        {/* Hero */}
        <header className="pb-10">
          <SectionLabel>Project case study · 本科独立完成</SectionLabel>
          <h1 className="mt-3 text-[28px] font-medium leading-snug text-stone-900 sm:text-[34px]">
            Finer：把噪声社媒文本，
            <span className="text-morningstar-red">转成可审计、可回测的结构化信号</span>
          </h1>
          <p className="mt-3 text-[14px] text-stone-500">
            一个端到端 ML 系统——结构化抽取 → 人工偏好标注 → 可验证奖励 → DPO 对齐。金融 KOL 内容是
            testbed，方法论可迁移到 biomedical NLP。
          </p>
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {STATS.map((s) => (
              <div key={s.label} className="rounded-sm bg-stone-50 p-4">
                <div className="text-[13px] text-stone-500">{s.label}</div>
                <div
                  className={`mt-1 text-[21px] font-medium ${s.accent ? "text-morningstar-red" : "text-stone-900"}`}
                >
                  {s.value}
                </div>
                <div className="mt-0.5 text-[13px] text-stone-500">{s.note}</div>
              </div>
            ))}
          </div>
          <p className="mt-5 font-mono text-[13px]">
            <a href={DEMO_URL} className="text-morningstar-red hover:underline">
              finer.t800.click
            </a>{" "}
            ·{" "}
            <a href={GITHUB_URL} className="text-morningstar-red hover:underline">
              github.com/hongyuanzhou453/finer
            </a>
          </p>
        </header>

        {/* 01 问题与动机 */}
        <section className="border-t border-black/10 py-8">
          <SectionLabel>01 · 问题与动机</SectionLabel>
          <h2 className="mt-1 text-[18px] font-medium text-stone-900">从噪声文本到可审计信号</h2>
          <p className="mt-2">
            把非结构化、口语化、含俚语与歧义实体的文本，转成可溯源、可回测的结构化记录——这是通用的信息抽取问题，biomedical
            文献 / 临床文本同样面对。我用金融 KOL 内容作 testbed，目标三条：实体可溯源、判断可校验、结果可回测。
          </p>
        </section>

        {/* 02 系统设计 */}
        <section className="border-t border-black/10 py-8">
          <SectionLabel>02 · 系统设计</SectionLabel>
          <h2 className="mt-1 text-[18px] font-medium text-stone-900">端到端 ML 流水线（独立搭建）</h2>
          <div className="my-3 flex flex-wrap items-center gap-1.5 font-mono text-[12px]">
            {FLOW.map((f, i) => (
              <span key={f} className="flex items-center gap-1.5">
                <span className="rounded-sm border border-black/15 px-2 py-1">{f}</span>
                {i < FLOW.length - 1 && <ArrowRight className="h-3.5 w-3.5 text-morningstar-red" />}
              </span>
            ))}
          </div>
          <p>
            自研标注平台 <code className="font-mono text-[13px]">Finer OS</code>（结构化抽取 → 人工偏好标注 →
            质量门清洗入库）、实体 registry + 三态 verifier、阿里云百炼 DPO LoRA 训练与 held-out
            评测，全链路独立完成——不是 notebook 调包，是可运行的系统。
          </p>
        </section>

        {/* 03 技术理解 */}
        <section className="border-t border-black/10 py-8">
          <SectionLabel>03 · 技术理解</SectionLabel>
          <h2 className="mt-1 text-[18px] font-medium text-stone-900">DPO / RLHF / RLVR</h2>
          <p className="mt-2">
            <span className="font-medium">DPO</span>：rejected 必须是被训练模型自己的 on-policy
            输出（才能降低它犯该错的概率），chosen 可来自更优的 off-policy 来源。
            <span className="font-medium"> RLHF vs RLVR</span>：前者学人类偏好，后者用可验证奖励、只奖励能回溯证据的输出。
          </p>
          <div className="mt-3 rounded-sm bg-stone-50 p-4 font-mono text-[13px]">
            reward = 结构门 × (0.50·grounding + 0.40·calibration + 0.10·abstention)
          </div>
          <p className="mt-3 border-l-2 border-morningstar-red pl-3 text-[12px] text-stone-500">
            RLVR 奖励只看"是否忠实回溯证据"，不看回测 / 行情 / 未来收益——避免奖励泄漏。已实现。
          </p>
        </section>

        {/* 04 真实挑战 */}
        <section className="border-t border-black/10 py-8">
          <SectionLabel>04 · 真实挑战与解决 ★</SectionLabel>
          <h2 className="mt-1 text-[18px] font-medium text-stone-900">数据质量较真，与一个 bio 同构问题</h2>
          <p className="mt-2">
            过程中我独立发现并系统处理了几类数据陷阱——这正是 biomedical 实体标准化（gene / drug
            normalization）的同构难题：
          </p>
          <table className="my-3 w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-[12px] text-stone-500">
                <th className="border-b border-black/10 px-2 py-2 text-left font-medium">我的发现</th>
                <th className="border-b border-black/10 px-2 py-2 text-left font-medium">性质</th>
                <th className="border-b border-black/10 px-2 py-2 text-left font-medium">biomedical 对应</th>
              </tr>
            </thead>
            <tbody>
              {CHALLENGES.map((c) => (
                <tr key={c.found}>
                  <td className="border-b border-black/10 px-2 py-2 align-top">{c.found}</td>
                  <td className="border-b border-black/10 px-2 py-2 align-top">{c.kind}</td>
                  <td className="border-b border-black/10 px-2 py-2 align-top">{c.bio}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            解决：实体 <code className="font-mono text-[13px]">registry</code> + 三态 verifier（grounded /
            hallucination / registry-gap）+ 人工回填与精选。宁可诚实精选干净子集，也不用脏数据糊出好看的图。
          </p>
        </section>

        {/* 05 结果 */}
        <section className="border-t border-black/10 py-8">
          <SectionLabel>05 · 结果</SectionLabel>
          <h2 className="mt-1 text-[18px] font-medium text-stone-900">DPO 第一轮：微调前后对比</h2>
          <div className="my-4 grid gap-2.5">
            {METRICS.map((m) => (
              <div key={m.label}>
                <div className="flex justify-between text-[13px]">
                  <span>{m.label}</span>
                  <span className="font-mono">{m.text}</span>
                </div>
                <div className="mt-1 h-[7px] overflow-hidden rounded-sm bg-stone-100">
                  <div className="h-full rounded-sm bg-morningstar-red" style={{ width: m.width }} />
                </div>
              </div>
            ))}
          </div>
          <div className="rounded-sm bg-stone-50 p-4">
            <span className="text-[13px] text-stone-500">偏好胜率（after vs before, judge=ref）</span>{" "}
            <span className="font-mono text-[15px]">
              <span className="font-medium text-morningstar-red">87.1%</span> · 胜 13 / 平 14 / 负 2
            </span>
          </div>
          <p className="mt-3 border-l-2 border-morningstar-red pl-3 text-[12px] text-stone-500">
            来源：DPO 微调前（基座 Qwen3-8B）/ 后，held-out eval n=29，judge=ref；训练用 20 条 registry-验证精选偏好对。这是第一轮、小样本的方向验证，不是最终模型水平——after 几乎不退步（负 2）、约半数进步。
          </p>
        </section>

        {/* 06 可迁移性与反思 */}
        <section className="border-t border-black/10 py-8">
          <SectionLabel>06 · 可迁移性与反思</SectionLabel>
          <h2 className="mt-1 text-[18px] font-medium text-stone-900">为什么这对 bio + ML 有意义</h2>
          <table className="my-3 w-full border-collapse text-[13px]">
            <tbody>
              {TRANSFER.map(([k, v]) => (
                <tr key={k}>
                  <td className="w-[38%] border-b border-black/10 px-2 py-2 align-top font-medium">{k}</td>
                  <td className="border-b border-black/10 px-2 py-2 align-top">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            反思：第一轮让我确信——
            <span className="text-morningstar-red">数据质量比模型选择更决定结果</span>
            ；正确的分工是人核语义、registry 核实体代码；评估必须诚实（拆 W/T/L、写明小样本）。下一步把生成端接入
            registry、扩 registry 覆盖、扩量做第二轮自改进闭环。
          </p>
        </section>

        {/* 互链 */}
        <section className="border-t border-black/10 py-8">
          <div className="flex flex-wrap gap-3">
            <a
              href={DEMO_URL}
              className="inline-flex items-center gap-2 rounded-sm bg-morningstar-red px-5 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-morningstar-red/90"
            >
              看在线 demo <ArrowUpRight className="h-4 w-4" />
            </a>
            <Link
              href="/training"
              className="inline-flex items-center gap-2 rounded-sm border border-black/15 px-5 py-3 text-[14px] font-semibold text-stone-800 transition-colors hover:bg-stone-50"
            >
              训练线叙事 <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/demo"
              className="inline-flex items-center gap-2 rounded-sm border border-black/15 px-5 py-3 text-[14px] font-semibold text-stone-800 transition-colors hover:bg-stone-50"
            >
              标注全流程 <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <p className="mt-6 border-t border-black/10 pt-4 text-[12px] text-stone-400">
            真实 agent 工程量：跨 Claude Code / Codex / Gemini 累计 13.03 亿 tokens · 12,045 请求 · 93.6%
            缓存 · ≈ $792.84——为 Finer + ESM 蛋白等全部工作的
            <span className="font-medium">跨项目总量</span>，非 Finer 单一项目。
          </p>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
