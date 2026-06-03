import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://finer.t800.click";
const TITLE = "Finer OS — AI-native 投研自动化流水线";
const DESCRIPTION =
  "把财经 KOL 的社交媒体内容转化为结构化、可回测、可审计的投资事件。F0-F8 canonical pipeline，证据链可追溯。";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: TITLE,
    template: "%s · Finer OS",
  },
  description: DESCRIPTION,
  keywords: [
    "Finer OS",
    "投研自动化",
    "KOL",
    "投资回测",
    "证据链",
    "AI-native",
    "F0-F8",
    "RLHF",
  ],
  authors: [{ name: "Finer OS" }],
  alternates: { canonical: SITE_URL },
  openGraph: {
    type: "website",
    locale: "zh_CN",
    url: SITE_URL,
    siteName: "Finer OS",
    title: TITLE,
    description: DESCRIPTION,
    images: [
      {
        url: "/og/finer-social-preview.png",
        width: 1280,
        height: 670,
        alt: "Finer OS — 把 KOL 内容变成可回测、可审计的投资事件",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/og/finer-social-preview.png"],
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="antialiased">
      <body className="finer-scrollbar min-h-screen bg-background text-foreground">
        {children}
      </body>
    </html>
  );
}
