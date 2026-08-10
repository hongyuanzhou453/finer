import Link from "next/link";
import { Activity, ArrowRight } from "lucide-react";

export const GITHUB_URL = "https://github.com/kelipovanatalja453-bot/finer";
export const CONTACT_EMAIL = "kelipovanatalja453@gmail.com";

/** GitHub octocat mark (lucide dropped brand icons for trademark reasons). */
export function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222 0 1.606-.014 2.898-.014 3.293 0 .322.216.694.825.576C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
    </svg>
  );
}

/** Sticky editorial header shared by landing + content pages. */
export function SiteHeader({ links }: { links: { href: string; label: string }[] }) {
  return (
    <header className="sticky top-0 z-30 border-b border-[var(--table-border)] bg-[rgba(243,239,231,0.86)] backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-sm bg-morningstar-red">
            <Activity className="h-4 w-4 text-white" strokeWidth={1.8} />
          </div>
          <span className="text-[17px] font-bold tracking-tight text-foreground">
            Finer OS
          </span>
        </Link>
        <nav className="hidden items-center gap-7 md:flex">
          {links.map((l) => (
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
  );
}

/** Shared footer. Section anchors use /# so they resolve from any route. */
export function SiteFooter() {
  return (
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
              Finer 不告诉你谁更准。它让你查得清每一句话是谁在什么时候说的、
              后来发生了什么、以及说的和做的是否一致。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-x-12 gap-y-2 text-[13px]">
            <div className="space-y-2">
              <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/40">
                产品
              </div>
              <Link href="/#records" className="block text-foreground/70 hover:text-morningstar-red">
                记录与共识
              </Link>
              <Link href="/records" className="block text-foreground/70 hover:text-morningstar-red">
                信源记录
              </Link>
              <Link href="/demo" className="block text-foreground/70 hover:text-morningstar-red">
                在线演示
              </Link>
              <Link href="/training" className="block text-foreground/70 hover:text-morningstar-red">
                训练数据
              </Link>
              <Link href="/#proof" className="block text-foreground/70 hover:text-morningstar-red">
                结算记录
              </Link>
              <Link href="/#capabilities" className="block text-foreground/70 hover:text-morningstar-red">
                能力
              </Link>
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
          内部研究系统原型 · 数据与回测结果仅供研究，不构成投资建议 ·
          所有比率与曲线均为历史记录，不构成对未来的预测。
        </div>
      </div>
    </footer>
  );
}
