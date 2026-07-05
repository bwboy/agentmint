import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";

export const metadata = {
  title: "AgentMint",
  description: "AI Agent 能力共享平台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
