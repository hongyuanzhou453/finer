import { DemoShell } from "@/components/demo/demo-shell";

export const metadata = {
  title: "在线演示",
  description:
    "Finer OS 交互式演示——研究·回测工作台（F0-F8 流水线、KOL 研究视图、证据溯源、回测曲线）与标注全流程（Gold 标注 / DPO 偏好对 / F6 修正 + RLVR verifier）。所有数据均为演示数据，不连接真实后端。",
};

export default function DemoPage() {
  return <DemoShell />;
}
