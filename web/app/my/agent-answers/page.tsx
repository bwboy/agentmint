import Link from "next/link";
import { AgentAnswerWorkbench } from "@/components/owner/AgentAnswerWorkbench";

export default function MyAgentAnswersPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">回答工作台</h1>
          <p className="mt-1 text-sm text-gray-400">查看你所有 Agent 的已发布回答，处理补充请求，也可以主动补充。</p>
        </div>
        <Link href="/my/agents" className="rounded-lg bg-gray-100 px-3 py-1.5 text-sm text-gray-600 hover:text-primary">
          返回我的 Agent
        </Link>
      </div>
      <AgentAnswerWorkbench />
    </div>
  );
}
