import { ReviewQueue } from "@/components/review/ReviewQueue";
import { ActionLink, PageHeader, PageShell } from "@/components/layout/PageScaffold";

export default function ReviewPage({ params }: { params: { id: string } }) {
  return (
    <PageShell narrow>
      <PageHeader
        eyebrow="Review Queue"
        title="审核队列"
        description="通过的回答会发布给提问者；拒绝则丢弃。"
        actions={<ActionLink href="/my/agents">我的 Agent</ActionLink>}
        compact
      />
      <ReviewQueue agentId={params.id} />
    </PageShell>
  );
}
