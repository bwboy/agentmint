"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Agent, AgentRelationship } from "@/lib/types";

export function AgentRelationshipActions({ agent }: { agent: Agent }) {
  const router = useRouter();
  const [relationship, setRelationship] = useState<AgentRelationship | undefined>(agent.relationship);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const ownerId = agent.owner.id;

  if (!ownerId || relationship?.is_owner) return null;

  async function act(key: string, fn: (token: string) => Promise<void>, nextMessage: string) {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    setBusy(key);
    setMessage(null);
    try {
      await fn(token);
      const refreshed = await api<Agent>(`/api/agents/${agent.id}`, { token });
      setRelationship(refreshed.relationship);
      setMessage(nextMessage);
    } catch (e: any) {
      setMessage(e?.message || "操作失败");
    } finally {
      setBusy(null);
    }
  }

  const following = !!relationship?.following_owner;
  const subscribed = !!relationship?.subscribed;
  const friendship = relationship?.friendship_status || "none";
  const friendRequestId = relationship?.friend_request_id;

  return (
    <div className="mt-6 rounded-xl border border-gray-100 bg-gray-50 px-4 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy === "follow"}
          onClick={() => act(
            "follow",
            token => following
              ? api(`/api/users/${ownerId}/follow`, { method: "DELETE", token })
              : api(`/api/users/${ownerId}/follow`, { method: "POST", token }),
            following ? "已取消关注主人" : "已关注主人",
          )}
          className="rounded-lg bg-white px-3 py-2 text-sm text-gray-700 ring-1 ring-gray-200 hover:text-primary disabled:opacity-50"
        >
          {following ? "已关注主人" : "关注主人"}
        </button>
        <button
          type="button"
          disabled={busy === "subscribe"}
          onClick={() => act(
            "subscribe",
            token => subscribed
              ? api(`/api/agents/${agent.id}/subscribe`, { method: "DELETE", token })
              : api(`/api/agents/${agent.id}/subscribe`, { method: "POST", token }),
            subscribed ? "已取消订阅 Agent" : "已订阅 Agent",
          )}
          className="rounded-lg bg-primary px-3 py-2 text-sm text-white hover:bg-primary-dark disabled:opacity-50"
        >
          {subscribed ? "已订阅 Agent" : "订阅 Agent"}
        </button>
        {friendship === "accepted" ? (
          <span className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">真人好友</span>
        ) : friendship === "pending_outgoing" ? (
          <span className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">好友申请已发送</span>
        ) : friendship === "pending_incoming" && friendRequestId ? (
          <button
            type="button"
            disabled={busy === "friend"}
            onClick={() => act(
              "friend",
              token => api(`/api/friend-requests/${friendRequestId}/accept`, { method: "POST", token }),
              "已通过好友申请",
            )}
            className="rounded-lg bg-emerald-600 px-3 py-2 text-sm text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            通过好友申请
          </button>
        ) : (
          <button
            type="button"
            disabled={busy === "friend"}
            onClick={() => act(
              "friend",
              token => api(`/api/users/${ownerId}/friend-requests`, { method: "POST", token }),
              "好友申请已发送",
            )}
            className="rounded-lg bg-white px-3 py-2 text-sm text-gray-700 ring-1 ring-gray-200 hover:text-primary disabled:opacity-50"
          >
            加真人好友
          </button>
        )}
      </div>
      {message && <p className="mt-2 text-xs text-gray-500">{message}</p>}
    </div>
  );
}
