import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://finer.t800.click";
const TITLE = "Finer OS — 谁说过什么，后来发生了什么";
const DESCRIPTION =
  "Finer 不告诉你谁更准。它让你查得清每一句话是谁在什么时候说的、后来发生了什么、以及说的和做的是否一致。可下钻的记录 · 诚实的统计 · 言行一致性核查。";

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
    "信源记录",
    "共识",
    "审计",
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
        alt: "Finer OS — 谁说过什么，后来发生了什么",
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
