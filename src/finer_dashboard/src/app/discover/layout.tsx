import { AppShell } from "@/components/layout/app-shell";

/**
 * /discover 此前不套 AppShell：进去之后没有任何返回路径，全页零个链接指向
 * 工作台（`/ticker/[symbol]` 至少还有一个「返回」，`/audit` 自带顶栏）。
 * 合规的消费面反而是最难走出去的页面。
 */
export default function DiscoverLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppShell>{children}</AppShell>;
}
