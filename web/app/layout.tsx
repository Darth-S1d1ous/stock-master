import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Stock Master", template: "%s · Stock Master" },
  description: "Auditable investment thesis monitoring and event research console",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
