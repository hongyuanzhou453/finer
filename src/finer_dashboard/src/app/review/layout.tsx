import { AppShell } from "@/components/layout/app-shell";

export default function ReviewLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppShell>{children}</AppShell>;
}
