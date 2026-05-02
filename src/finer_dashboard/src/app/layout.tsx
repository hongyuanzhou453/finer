import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Finer OS",
  description: "Evidence-first operating system for creator-content investment research.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className="h-full antialiased"
    >
      <body className="h-full bg-background text-foreground">
        <div className="relative flex h-full overflow-hidden">
          {children}
        </div>
      </body>
    </html>
  );
}
