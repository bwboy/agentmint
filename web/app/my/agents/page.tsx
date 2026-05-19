import { MyAgentsPanel } from "@/components/agent/MyAgentsPanel";

export default function MyAgentsPage() {
  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <h1 className="text-xl font-semibold mb-1">我的 Agent</h1>
      <p className="text-sm text-gray-400 mb-6">管理 Agent 注册、Connector Token、配额。</p>
      <MyAgentsPanel />
    </div>
  );
}
