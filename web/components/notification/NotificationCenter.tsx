"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { ApiList, Notification } from "@/lib/types";

type FilterMode = "all" | "unread";

export function NotificationCenter() {
  const router = useRouter();
  const [items, setItems] = useState<Notification[]>([]);
  const [filter, setFilter] = useState<FilterMode>("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    refresh(filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function refresh(mode = filter) {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      const query = mode === "unread" ? "?unread=1&size=50" : "?size=50";
      const res = await api<ApiList<Notification>>(`/api/notifications${query}`, { token });
      setItems(res.data || []);
      setTotal(res.pagination?.total || 0);
      setErr(null);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setErr(e.message || "加载通知失败");
    } finally {
      setLoading(false);
    }
  }

  async function markRead(item: Notification) {
    if (item.read) return;
    const token = getToken();
    if (!token) return;
    setBusy(item.id);
    try {
      await api(`/api/notifications/${item.id}/read`, { method: "PUT", token });
      await refresh();
    } catch (e: any) {
      setErr(e.message || "标记失败");
    } finally {
      setBusy(null);
    }
  }

  async function markAllRead() {
    const token = getToken();
    if (!token) return;
    setBusy("all");
    try {
      await api("/api/notifications/read-all", { method: "PUT", token });
      await refresh();
    } catch (e: any) {
      setErr(e.message || "标记失败");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-500">{err}</div>}

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 bg-white p-3 shadow-sm">
        <div className="flex rounded-lg bg-gray-100 p-1 text-xs">
          <button
            onClick={() => setFilter("all")}
            className={`rounded-md px-3 py-1.5 ${filter === "all" ? "bg-white text-gray-950 shadow-sm" : "text-gray-500"}`}
          >
            全部
          </button>
          <button
            onClick={() => setFilter("unread")}
            className={`rounded-md px-3 py-1.5 ${filter === "unread" ? "bg-white text-gray-950 shadow-sm" : "text-gray-500"}`}
          >
            未读
          </button>
        </div>
        <span className="text-xs text-gray-400">共 {total} 条</span>
        <button
          onClick={markAllRead}
          disabled={busy === "all" || !items.some(item => !item.read)}
          className="ml-auto rounded-md bg-gray-950 px-3 py-1.5 text-xs text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          全部已读
        </button>
      </div>

      <div className="space-y-2">
        {loading ? (
          <p className="rounded-lg bg-white px-4 py-6 text-sm text-gray-400">加载中...</p>
        ) : items.length ? (
          items.map(item => <NotificationRow key={item.id} item={item} busy={busy === item.id} onMarkRead={() => markRead(item)} />)
        ) : (
          <p className="rounded-lg bg-white px-4 py-6 text-sm text-gray-400">暂无通知</p>
        )}
      </div>
    </div>
  );
}

function NotificationRow({
  item,
  busy,
  onMarkRead,
}: {
  item: Notification;
  busy: boolean;
  onMarkRead: () => void;
}) {
  const href = hrefForNotification(item);
  return (
    <div className={`rounded-lg border p-4 shadow-sm ${item.read ? "border-gray-100 bg-white" : "border-primary/20 bg-primary/5"}`}>
      <div className="flex flex-wrap items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-gray-950 text-xs font-semibold text-white">
          {iconForNotification(item.type)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link href={href} className="font-medium text-gray-950 hover:text-primary">{item.title}</Link>
            {!item.read && <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] text-white">未读</span>}
          </div>
          {item.body && <p className="mt-1 text-sm text-gray-500">{item.body}</p>}
          <p className="mt-2 text-xs text-gray-400">{formatDate(item.created_at)}</p>
        </div>
        {!item.read && (
          <button
            onClick={onMarkRead}
            disabled={busy}
            className="rounded-md bg-white px-3 py-1.5 text-xs text-gray-600 ring-1 ring-gray-200 hover:text-primary disabled:opacity-50"
          >
            已读
          </button>
        )}
      </div>
    </div>
  );
}

function hrefForNotification(item: Notification) {
  if (["answer_ready", "direct_question", "answer_feedback"].includes(item.type) && item.ref_id) {
    return `/questions/${item.ref_id}`;
  }
  if (item.type === "agent_subscribed" && item.ref_id) {
    return `/agents/${item.ref_id}`;
  }
  if (item.type === "review_needed" && item.ref_id) {
    return "/my/agents";
  }
  if (item.type.startsWith("friend_request")) {
    return "/my/social";
  }
  return "/my/notifications";
}

function iconForNotification(type: string) {
  if (type === "answer_ready") return "答";
  if (type === "direct_question") return "问";
  if (type === "answer_feedback") return "评";
  if (type === "agent_subscribed") return "订";
  if (type.startsWith("friend_request")) return "友";
  if (type === "review_needed") return "审";
  return "通";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
