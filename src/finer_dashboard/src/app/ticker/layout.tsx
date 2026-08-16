import { AppShell } from "@/components/layout/app-shell";

/**
 * 覆盖 /ticker 与 /ticker/[symbol]。详情页原有的「返回」只指向 `/`，
 * 套上 AppShell 后可以直接横跳到其他消费面，不必先回工作台。
 */
export default function TickerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppShell>{children}</AppShell>;
}
