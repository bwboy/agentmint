import { ProfileSettingsPanel } from "@/components/user/ProfileSettingsPanel";

export default function MyProfilePage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Owner Profile</p>
        <h1 className="mt-2 text-2xl font-semibold text-gray-950">个人设定</h1>
        <p className="mt-2 text-sm text-gray-500">
          定义你作为 Agent 主人的公开身份、默认服务策略和通知偏好。
        </p>
      </div>
      <ProfileSettingsPanel />
    </div>
  );
}
