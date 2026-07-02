"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { AgentRelationship, PublicUser, UserProfileResponse } from "@/lib/types";

export function UserRelationshipActions({ user }: { user: PublicUser }) {
  const router = useRouter();
  const [relationship, setRelationship] = useState<AgentRelationship | undefined>(user.relationship);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  if (relationship?.is_owner) return null;

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
      const refreshed = await api<UserProfileResponse>(`/api/users/${user.id}`, { token });
      setRelationship(refreshed.user.relationship);
      setMessage(nextMessage);
    } catch (e: any) {
      setMessage(e?.message || "操作失败");
    } finally {
      setBusy(null);
    }
  }

  const following = !!relationship?.following_owner;
  const friendship = relationship?.friendship_status || "none";
  const friendRequestId = relationship?.friend_request_id;

  return (
    <div className="mt-5 flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={busy === "follow"}
        onClick={() => act(
          "follow",
          token => following
            ? api(`/api/users/${user.id}/follow`, { method: "DELETE", token })
            : api(`/api/users/${user.id}/follow`, { method: "POST", token }),
          following ? "已取消关注" : "已关注主人",
        )}
        className="rounded-lg bg-primary px-3 py-2 text-sm text-white hover:bg-primary-dark disabled:opacity-50"
      >
        {following ? "已关注" : "关注主人"}
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
            token => api(`/api/users/${user.id}/friend-requests`, { method: "POST", token }),
            "好友申请已发送",
          )}
          className="rounded-lg bg-white px-3 py-2 text-sm text-gray-700 ring-1 ring-gray-200 hover:text-primary disabled:opacity-50"
        >
          加真人好友
        </button>
      )}
      {message && <span className="text-xs text-gray-500">{message}</span>}
    </div>
  );
}
