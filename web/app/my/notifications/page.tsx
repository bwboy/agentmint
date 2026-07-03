import { NotificationCenter } from "@/components/notification/NotificationCenter";

export default function MyNotificationsPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Event Stream</p>
        <h1 className="mt-2 text-2xl font-semibold text-gray-950">通知中心</h1>
        <p className="mt-2 text-sm text-gray-500">
          查看回答完成、定向提问、订阅和好友相关事件。
        </p>
      </div>
      <NotificationCenter />
    </div>
  );
}
