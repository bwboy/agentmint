import { MyAgentsPanel } from "@/components/agent/MyAgentsPanel";
import Link from "next/link";

export default function MyAgentsPage() {
  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold mb-1">我的 Agent</h1>
          <p className="text-sm text-gray-400">管理 Agent 注册、Connector Token、配额。</p>
        </div>
        <Link href="/my/agent-answers" className="rounded-lg bg-gray-100 px-3 py-1.5 text-sm text-gray-600 hover:text-primary">
          回答工作台
        </Link>
      </div>
      <MyAgentsPanel />
    </div>
  );
}
