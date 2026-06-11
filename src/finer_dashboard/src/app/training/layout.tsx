import type { Metadata } from "next";
import { AppShell } from "@/components/layout/app-shell";

export const metadata: Metadata = {
  title: "训练数据 · 人工标注与 RLHF | Finer OS",
  description:
    "人工标注与 RLHF 如何沉淀为 DPO 训练数据：两类标注任务、训练集与人工验证集的区分、证据对齐的偏好原则、三项评测指标，以及百炼 DPO 训练线的真实进展。",
};

export default function TrainingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppShell>{children}</AppShell>;
}
