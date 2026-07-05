import { NotificationCenter } from "@/components/notification/NotificationCenter";
import { PageHeader, PageShell } from "@/components/layout/PageScaffold";

export default function MyNotificationsPage() {
  return (
    <PageShell>
      <PageHeader
        eyebrow="Event Stream"
        title="通知中心"
        description="查看回答完成、定向提问、订阅和好友相关事件。"
        compact
      />
      <NotificationCenter />
    </PageShell>
  );
}
