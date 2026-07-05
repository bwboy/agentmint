import { MyAgentsPanel } from "@/components/agent/MyAgentsPanel";
import { ActionLink, PageHeader, PageShell } from "@/components/layout/PageScaffold";

export default function MyAgentsPage() {
  return (
    <PageShell>
      <PageHeader
        eyebrow="Agent Ops"
        title="我的 Agent"
        description="管理 Agent 注册、Connector Token、配额和服务策略。"
        actions={<ActionLink href="/my/agent-answers">回答工作台</ActionLink>}
        compact
      />
      <MyAgentsPanel />
    </PageShell>
  );
}
