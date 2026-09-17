import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "灵境导游 AI 数字人",
  description: "面向智慧景区的多模态 AI 数字人导览系统"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
