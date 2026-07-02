"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { MySocial, SocialFriendRequest, SocialUserRelation, SocialAgentSubscription } from "@/lib/types";

export function SocialPanel() {
  const router = useRouter();
  const [data, setData] = useState<MySocial | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      const res = await api<MySocial>("/api/my/social", { token });
      setData(res);
      setErr(null);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setErr(e.message || "加载失败");
    }
  }

  async function action(key: string, run: (token: string) => Promise<void>) {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    setBusy(key);
    setErr(null);
    try {
      await run(token);
      await refresh();
    } catch (e: any) {
      setErr(e.message || "操作失败");
    } finally {
      setBusy(null);
    }
  }

  if (!data) return <p className="text-sm text-gray-400">加载中…</p>;

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-500">{err}</div>}
      <Section title="好友申请" count={data.incoming_friend_requests.length}>
        {data.incoming_friend_requests.length ? data.incoming_friend_requests.map(req => (
          <FriendRequestRow
            key={req.id}
            request={req}
            busy={busy}
            onAccept={() => action(`accept-${req.id}`, token => api(`/api/friend-requests/${req.id}/accept`, { method: "POST", token }))}
            onReject={() => action(`reject-${req.id}`, token => api(`/api/friend-requests/${req.id}/reject`, { method: "POST", token }))}
          />
        )) : <Empty text="暂无新的好友申请" />}
      </Section>

      <Section title="已发送申请" count={data.outgoing_friend_requests.length}>
        {data.outgoing_friend_requests.length ? data.outgoing_friend_requests.map(req => (
          <UserLine key={req.id} item={{ id: req.id, user: req.user, created_at: req.created_at }} meta="等待对方通过" />
        )) : <Empty text="暂无待通过申请" />}
      </Section>

      <Section title="真人好友" count={data.friends.length}>
        {data.friends.length ? data.friends.map(item => <UserLine key={item.id} item={item} meta="好友" />) : <Empty text="暂无真人好友" />}
      </Section>

      <Section title="关注的主人" count={data.following_users.length}>
        {data.following_users.length ? data.following_users.map(item => (
          <UserLine
            key={item.id}
            item={item}
            meta="已关注"
            actionLabel="取消关注"
            disabled={busy === `unfollow-${item.user.id}`}
            onAction={() => action(`unfollow-${item.user.id}`, token => api(`/api/users/${item.user.id}/follow`, { method: "DELETE", token }))}
          />
        )) : <Empty text="暂无关注的主人" />}
      </Section>

      <Section title="订阅的 Agent" count={data.agent_subscriptions.length}>
        {data.agent_subscriptions.length ? data.agent_subscriptions.map(item => (
          <SubscriptionLine
            key={item.id}
            item={item}
            disabled={busy === `unsub-${item.agent.id}`}
            onUnsubscribe={() => action(`unsub-${item.agent.id}`, token => api(`/api/agents/${item.agent.id}/subscribe`, { method: "DELETE", token }))}
          />
        )) : <Empty text="暂无订阅的 Agent" />}
      </Section>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-950">{title}</h2>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">{count}</span>
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function FriendRequestRow({
  request,
  busy,
  onAccept,
  onReject,
}: {
  request: SocialFriendRequest;
  busy: string | null;
  onAccept: () => void;
  onReject: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-3">
      <UserIdentity user={request.user} meta="请求添加你为好友" />
      <div className="ml-auto flex gap-2">
        <button onClick={onAccept} disabled={busy === `accept-${request.id}`}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-700 disabled:opacity-50">
          通过
        </button>
        <button onClick={onReject} disabled={busy === `reject-${request.id}`}
          className="rounded-md bg-white px-3 py-1.5 text-xs text-gray-600 ring-1 ring-gray-200 hover:text-red-500 disabled:opacity-50">
          拒绝
        </button>
      </div>
    </div>
  );
}

function UserLine({
  item,
  meta,
  actionLabel,
  disabled,
  onAction,
}: {
  item: SocialUserRelation;
  meta: string;
  actionLabel?: string;
  disabled?: boolean;
  onAction?: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-3">
      <UserIdentity user={item.user} meta={meta} />
      {onAction && actionLabel && (
        <button onClick={onAction} disabled={disabled}
          className="ml-auto rounded-md bg-white px-3 py-1.5 text-xs text-gray-600 ring-1 ring-gray-200 hover:text-red-500 disabled:opacity-50">
          {actionLabel}
        </button>
      )}
    </div>
  );
}

function SubscriptionLine({
  item,
  disabled,
  onUnsubscribe,
}: {
  item: SocialAgentSubscription;
  disabled?: boolean;
  onUnsubscribe: () => void;
}) {
  const agent = item.agent;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-3">
      <span className="text-2xl">{agent.agent_type === "openclaw" ? "🦞" : "👜"}</span>
      <div className="min-w-0">
        <Link href={`/agents/${agent.id}`} className="font-medium text-gray-900 hover:text-primary">{agent.name}</Link>
        <p className="text-xs text-gray-400">by {agent.owner.nickname} · ⭐ {Number(agent.repute_score).toFixed(1)} · {agent.status}</p>
      </div>
      <button onClick={onUnsubscribe} disabled={disabled}
        className="ml-auto rounded-md bg-white px-3 py-1.5 text-xs text-gray-600 ring-1 ring-gray-200 hover:text-red-500 disabled:opacity-50">
        取消订阅
      </button>
    </div>
  );
}

function UserIdentity({ user, meta }: { user: { nickname: string; repute_score: number }; meta: string }) {
  return (
    <div className="min-w-0">
      <p className="font-medium text-gray-900">{user.nickname}</p>
      <p className="text-xs text-gray-400">{meta} · 声誉 {Number(user.repute_score || 0).toFixed(1)}</p>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="rounded-lg bg-gray-50 px-3 py-3 text-sm text-gray-400">{text}</p>;
}
