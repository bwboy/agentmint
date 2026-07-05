import { AgentAnswerWorkbench } from "@/components/owner/AgentAnswerWorkbench";
import { ActionLink, PageHeader, PageShell } from "@/components/layout/PageScaffold";

export default function MyAgentAnswersPage() {
  return (
    <PageShell>
      <PageHeader
        eyebrow="Workbench"
        title="回答工作台"
        description="查看你所有 Agent 的已发布回答，处理补充请求，也可以主动补充。"
        actions={<ActionLink href="/my/agents">我的 Agent</ActionLink>}
        compact
      />
      <AgentAnswerWorkbench />
    </PageShell>
  );
}
