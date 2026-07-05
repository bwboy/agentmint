import { ProfileSettingsPanel } from "@/components/user/ProfileSettingsPanel";
import { PageHeader, PageShell } from "@/components/layout/PageScaffold";

export default function MyProfilePage() {
  return (
    <PageShell>
      <PageHeader
        eyebrow="Owner Profile"
        title="个人设定"
        description="定义你作为 Agent 主人的公开身份、默认服务策略和通知偏好。"
        compact
      />
      <ProfileSettingsPanel />
    </PageShell>
  );
}
