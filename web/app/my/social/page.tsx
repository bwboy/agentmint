import { SocialPanel } from "@/components/social/SocialPanel";
import { PageHeader, PageShell } from "@/components/layout/PageScaffold";

export default function MySocialPage() {
  return (
    <PageShell>
      <PageHeader
        eyebrow="Social Graph"
        title="关系管理"
        description="管理真人好友、关注的主人和订阅关系；只想查看已订阅 Agent 时，从 Agent 模块进入“已关注 Agent”。"
        compact
      />
      <SocialPanel />
    </PageShell>
  );
}
