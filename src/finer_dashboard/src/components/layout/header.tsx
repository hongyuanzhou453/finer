"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Users,
  GitCompare,
  LineChart,
  ClipboardCheck,
  GraduationCap,
  Settings,
  Database,
} from "lucide-react";

const navItems = [
  { href: "/", label: "工作台", icon: LayoutDashboard },
  { href: "/kol", label: "KOL", icon: Users },
  { href: "/kol/compare", label: "对比", icon: GitCompare },
  { href: "/backtest", label: "回测", icon: LineChart },
  { href: "/annotation", label: "标注", icon: ClipboardCheck },
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
      <div className="container flex h-14 items-center gap-3 overflow-hidden">
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
          {navItems.map((item) => {
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

        {/* Right side - can add user menu, etc */}
        <div className="hidden flex-1 items-center justify-end gap-4 lg:flex">
          <span className="text-xs text-foreground/40 font-medium">
            AI-native 投研流水线
          </span>
        </div>
      </div>
    </header>
  );
}
