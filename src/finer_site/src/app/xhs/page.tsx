import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, FileSearch, LayoutGrid, MonitorPlay } from "lucide-react";
import { SiteFooter, SiteHeader } from "@/components/landing/site-chrome";

/**
 * 小红书归因落地页。
 *
 * 小红书不给站外跳转数据，用户手打域名过来无 referrer，所以无法归因。
 * 解法是给一个专属短路径（不用 UTM——带参数的长 URL 没人手打，且在私信里
 * 更像广告链接）。Cloudflare 侧看 /xhs 的独立 UV 及其到 /records 的跳转率，
 * 这两个数就是这条渠道的真实产出。
 *
 * noindex 是刻意的：这一页存在的唯一理由是「/xhs 的 UV ≈ 小红书来的人」。
 * 一旦被搜索引擎收录，自然流量会掺进来，这个约等号就不成立了，页面也就
 * 失去了意义。同理它不进 sitemap.ts。
 *
 * 移动优先：小红书流量几乎 100% 来自手机，这一页的桌面端只是不难看而已。
 */
export const metadata: Metadata = {
  title: "从小红书来的",
  description:
    "Finer OS 是一个券商研报与 KOL 观点的公开记录档案：谁在什么时候说过什么，后来发生了什么，每个数字三次点击回到原文。不判断涨跌，不做名次。",
  robots: { index: false, follow: true },
};

const NAV_LINKS = [
  { href: "/records", label: "信源记录" },
  { href: "/demo", label: "在线演示" },
];

const ENTRIES: {
  href: string;
  icon: typeof FileSearch;
  kicker: string;
  title: string;
  body: string;
  cta: string;
}[] = [
  {
    href: "/records",
    icon: LayoutGrid,
    kicker: "先看这个",
    title: "信源记录",
    body:
      "4,587 条记录、2,740 条已结算。每张卡是一份历史记录：这家机构说过什么、后来怎么结算。比率一律并排 95% 区间，样本不足的只报条数。",
    cta: "翻档案",
  },
  {
    href: "/demo",
    icon: MonitorPlay,
    kicker: "想看它怎么跑",
    title: "在线演示",
    body:
      "一条内容从原文进来，到被拆成结构化记录的全过程。F0 到 F8 九个阶段，每一步的中间产物都摊开给你看。",
    cta: "看流水线",
  },
  {
    href: "/kol-check",
    icon: FileSearch,
    kicker: "想看一个具体的人",
    title: "单个 KOL 的公开记录",
    body:
      "一位真实 KOL（已匿名）的完整记录：37 条明确观点、29 笔已结算，以及他自述的交易风格和实盘行为对不对得上。每条都保留原话，可展开到证据链。",
    cta: "看记录",
  },
];

const FAQ: { q: string; a: string }[] = [
  {
    q: "数据是哪来的？是你手打的吗？",
    a: "不是。是 28,565 份公开券商研报 PDF，机器抽取后逐条对回原文——每条记录都存着它在原始 PDF 里的字符区间，所以每个数字点三下能回到原句。KOL 部分来自公开的视频/直播转写。全部是已公开的内容，没有任何非公开信息。",
  },
  {
    q: "那你判断涨跌吗？告诉我该买什么吗？",
    a: "不。这是一个检索工具，不是投顾。我检验过「历史准确率能不能预测未来表现」这件事——两个指标、六个切分点，判据是先写死再看数据的，结果一个都没成立。既然推不出来，我就不做那个功能，也不做名次。这里只回答：谁在什么时候说过什么，后来发生了什么。",
  },
  {
    q: "要钱吗？要注册吗？",
    a: "都不要。打开就能看，没有账号、没有付费墙、没有试用期。它现在也不是一门生意，是一个人做的公开档案。",
  },
  {
    q: "为什么有的地方只给条数，不给百分比？",
    a: "因为样本不够时百分比是噪音。29 笔里对了 8 笔，看着是 28%，但它的 95% 区间是 15%–46%——宽 31 个百分点，说明不了任何事。与其给一个看起来精确的假数字，不如告诉你「29 笔、8 笔为正」。",
  },
];

export default function XhsLandingPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader links={NAV_LINKS} />

      <main className="mx-auto w-full max-w-[720px] px-5 pb-16 pt-10 sm:pt-14">
        {/* ① 入口 */}
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-morningstar-red">
          从小红书来的
        </p>
        <h1 className="mt-3 text-[30px] leading-[1.25] sm:text-[40px]">
          先看这三个。
        </h1>
        <p className="mt-4 text-[15px] leading-relaxed text-[var(--ink-soft)]">
          Finer 是一个公开档案：把券商研报和 KOL 的公开发言，变成可以逐条查、逐条下钻到原文的记录。
          它不判断涨跌，也不排名次——只让你查得清，谁在什么时候说过什么，后来发生了什么。
        </p>

        <div className="mt-8 flex flex-col gap-3">
          {ENTRIES.map((e) => {
            const Icon = e.icon;
            return (
              <Link
                key={e.href}
                href={e.href}
                className="editorial-card group rounded-sm border-t-[3px] border-t-[var(--table-border)] px-5 py-5 transition-colors hover:border-t-morningstar-red"
              >
                <div className="flex items-center gap-2.5">
                  <Icon className="h-4 w-4 text-morningstar-red" strokeWidth={1.9} />
                  <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-[var(--accent-gold)]">
                    {e.kicker}
                  </span>
                </div>
                <div className="mt-2 text-[21px] font-semibold text-foreground">{e.title}</div>
                <p className="mt-1.5 text-[14px] leading-relaxed text-[var(--ink-soft)]">{e.body}</p>
                <span className="mt-3 inline-flex items-center gap-1.5 text-[14px] font-semibold text-morningstar-red">
                  {e.cta}
                  <ArrowRight
                    className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
                    strokeWidth={2}
                  />
                </span>
              </Link>
            );
          })}
        </div>

        {/* ② 三个高频问题 */}
        <section className="mt-12">
          <div className="flex items-baseline gap-3 border-b-2 border-foreground pb-2">
            <span className="text-[11px] font-bold tabular-nums tracking-[0.18em] text-morningstar-red">
              02
            </span>
            <h2 className="text-[19px] font-semibold">你多半想问的</h2>
          </div>
          <dl className="mt-5 flex flex-col gap-6">
            {FAQ.map((f) => (
              <div key={f.q}>
                <dt className="text-[15px] font-semibold text-foreground">{f.q}</dt>
                <dd className="mt-1.5 text-[14px] leading-relaxed text-[var(--ink-soft)]">{f.a}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* ③ 一个人做的 */}
        <section className="mt-12 rounded-sm border-l-4 border-l-[var(--accent-gold)] bg-[var(--surface-muted)] px-5 py-5">
          <h2 className="text-[17px] font-semibold">这是一个人做的</h2>
          <p className="mt-2 text-[14px] leading-relaxed text-[var(--ink-soft)]">
            没有团队，没有融资，也没打算卖给你什么。看到哪里不对、想查某个信源但没查到、
            或者觉得某个数字有问题——回小红书评论区找我，我基本都会回。
            指出错误的那种留言，我尤其想看到。
          </p>
          <p className="mt-3 text-[12px] leading-relaxed text-[var(--ink-soft)]">
            本站内容为公开信息的记录与整理，不含方向性判断，不构成投资建议。
            历史记录不能预测未来。
          </p>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
