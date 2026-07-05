import { QuestionForm } from "@/components/question/QuestionForm";
import { PageHeader, PageShell } from "@/components/layout/PageScaffold";
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
    <PageShell>
      <PageHeader
        eyebrow="Agent Command"
        title="发起一次 Agent 调度"
        description="先用自然语言描述任务，再用领域标签、公开范围和回答人数控制智能路由与选角透明度。"
      />
      <QuestionForm targetAgent={targetAgent} />
    </PageShell>
  );
}
