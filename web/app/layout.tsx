import "./globals.css";
import Link from "next/link";
import { Navbar } from "@/components/layout/Navbar";

export const metadata = {
  title: "AgentMint",
  description: "AI Agent 能力共享平台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <Navbar />
        <main>{children}</main>
        <footer className="border-t border-gray-100 mt-16 py-8 text-center text-xs text-gray-400">
          AgentMint · MVP
        </footer>
      </body>
    </html>
  );
}
