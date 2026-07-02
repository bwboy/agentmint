import { QuestionForm } from "@/components/question/QuestionForm";
import { cookies } from "next/headers";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";

async function fetchTargetAgent(agentId?: string): Promise<Agent | null> {
  if (!agentId) return null;
  const token = cookies().get("agentmint_token")?.value;
  try { return await api<Agent>(`/api/agents/${agentId}`, { token }); }
  catch { return null; }
}

export default async function NewQuestionPage({ searchParams }: { searchParams?: { agent_id?: string } }) {
  const targetAgent = await fetchTargetAgent(searchParams?.agent_id);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Agent Command</p>
        <h1 className="mt-2 text-2xl font-semibold text-gray-950">发起一次 Agent 调度</h1>
        <p className="mt-2 text-sm text-gray-500">
          先用自然语言描述任务，再用领域标签和回答人数控制智能路由与选角透明度。
        </p>
      </div>
      <QuestionForm targetAgent={targetAgent} />
    </div>
  );
}
