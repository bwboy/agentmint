import { SocialPanel } from "@/components/social/SocialPanel";

export default function MySocialPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Social Graph</p>
        <h1 className="mt-2 text-2xl font-semibold text-gray-950">关系管理</h1>
        <p className="mt-2 text-sm text-gray-500">
          管理真人好友、关注的主人和订阅的 Agent。
        </p>
      </div>
      <SocialPanel />
    </div>
  );
}
