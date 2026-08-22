"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Radar,
  Users,
  ScrollText,
  Search,
  ShieldCheck,
  CalendarClock,
  LineChart,
  ClipboardCheck,
  ListChecks,
  GraduationCap,
  Settings,
  MoreHorizontal,
  Database,
} from "lucide-react";

/**
 * 全局导航。**排序即产品表态**：执行 CRD-2 效力门的消费面在前，转向前的
 * 旧口径页在后。
 *
 * 2026-08-16 手术：
 * - 加入 `/discover` `/ticker` `/audit`。此前它们只在**首页侧边栏**有入口
 *   （main 0814fd31 加的），而侧边栏只挂在 `/`——从任何 AppShell 页面出发
 *   都走不到这三页，用户的默认落点是按信誉分排名的 `/radar`。
 * - 摘除 `/kol/compare`：四个 KOL 分数硬编码、零网络调用，还给最优值打 ★。
 *   路由本身的去留见同批次的死资产清理。
 * - `/radar` 后移：它按信誉分排名、无 sufficiency、无区间、无「不构成预测」
 *   声明，是转向前的形态（main 已在侧边栏做过同样降级）。页面本身未改造。
 *
 * 2026-08-22：加入 `/timeline` 后平铺 12 项在 1600 宽下溢出（「设置」被挤出
 * 屏幕）。改为**分组**而不是继续挤：主栏只放消费面与在用的流水线工具，
 * 旧口径页与配置收进「更多」。分组边界即产品表态——`/radar` 落在「更多」
 * 里不是因为它不重要，是因为它是转向前的形态。
 */
const primaryNav = [
  { href: "/", label: "工作台", icon: LayoutDashboard },
  { href: "/discover", label: "信源记录", icon: ScrollText },
  { href: "/ticker", label: "个股共识", icon: Search },
  { href: "/timeline", label: "时间线", icon: CalendarClock },
  { href: "/audit", label: "审计台", icon: ShieldCheck },
  { href: "/review", label: "复核", icon: ListChecks },
  { href: "/annotation", label: "标注", icon: ClipboardCheck },
  { href: "/backtest", label: "回测", icon: LineChart },
];

/** 旧口径页与配置。`/radar` 与 `/kol` 未接效力门，`/training` 是公开站的陈旧副本。 */
const secondaryNav = [
  { href: "/kol", label: "KOL", icon: Users },
  { href: "/radar", label: "雷达", icon: Radar },
  { href: "/training", label: "训练数据", icon: GraduationCap },
  { href: "/settings", label: "设置", icon: Settings },
];

export function Header() {
  const pathname = usePathname();

  // Determine active state
  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b border-stone-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/60">
      {/* overflow-visible：容器原为 overflow-hidden，会把「更多」下拉裁掉 */}
      <div className="container flex h-14 items-center gap-3">
        {/* Logo */}
        <Link href="/" className="mr-1 flex shrink-0 items-center gap-2 sm:mr-5">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-morningstar-red">
            <Database className="w-4 h-4 text-white" strokeWidth={2} />
          </div>
          <span className="hidden text-lg font-bold tracking-tight sm:inline">
            Finer OS
          </span>
        </Link>

        {/* Navigation */}
        <nav className="finer-scrollbar flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {primaryNav.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex shrink-0 items-center gap-2 rounded-md px-2.5 py-2 text-sm font-medium transition-colors sm:px-3",
                  active
                    ? "bg-stone-100 text-foreground"
                    : "text-foreground/60 hover:text-foreground hover:bg-stone-50"
                )}
              >
                <Icon className="w-4 h-4" strokeWidth={1.5} />
                <span className="hidden sm:inline">{item.label}</span>
              </Link>
            );
          })}

        </nav>

        {/* 「更多」必须放在 <nav> **外面**：nav 有 overflow-x-auto，
            绝对定位的下拉会被它裁掉。用原生 details 而不是引下拉库——
            自带点击外部收起与键盘可达。 */}
        <span aria-hidden className="mx-1 h-5 w-px shrink-0 bg-stone-200" />
        <details className="group relative shrink-0">
          <summary
            className={cn(
              "flex cursor-pointer list-none items-center gap-2 rounded-md px-2.5 py-2 text-sm font-medium transition-colors sm:px-3",
              secondaryNav.some((i) => isActive(i.href))
                ? "bg-stone-100 text-foreground"
                : "text-foreground/60 hover:bg-stone-50 hover:text-foreground",
            )}
          >
            <MoreHorizontal className="h-4 w-4" strokeWidth={1.5} />
            <span className="hidden sm:inline">更多</span>
          </summary>
          <div className="absolute right-0 z-50 mt-1 min-w-[180px] rounded-md border border-stone-200 bg-white py-1 shadow-[var(--shadow-soft)]">
            {secondaryNav.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 text-sm transition-colors",
                    isActive(item.href)
                      ? "bg-stone-100 text-foreground"
                      : "text-foreground/70 hover:bg-stone-50 hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" strokeWidth={1.5} />
                  {item.label}
                </Link>
              );
            })}
          </div>
        </details>

        {/* 原本这里有一句装饰性 tagline，且占着 flex-1——导航在 1280 宽下
            只分到 498px（需要 908px）而被迫横向滚动，加入三个消费面入口后
            「设置」直接被挤出可视区。导航是功能面，装饰不该与它抢位置；
            产品身份已由左侧 logo 承担，故整块移除。 */}
      </div>
    </header>
  );
}
