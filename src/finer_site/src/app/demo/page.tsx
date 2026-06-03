import { DemoWorkbench } from "@/components/demo/demo-workbench";

export const metadata = {
  title: "在线演示",
  description:
    "Finer OS 交互式演示——F0-F8 流水线走查、KOL 研究视图、证据溯源、回测曲线。所有数据均为演示数据，不连接真实后端。",
};

export default function DemoPage() {
  return <DemoWorkbench />;
}
