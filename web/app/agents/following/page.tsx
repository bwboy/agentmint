"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AgentDiscoveryCard } from "@/components/agent/AgentDiscoveryCard";
import { EmptyState, PageHeader } from "@/components/layout/PageScaffold";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { MySocial } from "@/lib/types";

export default function FollowingAgentsPage() {
  const router = useRouter();
  const [data, setData] = useState<MySocial | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    api<MySocial>("/api/my/social", { token })
      .then(res => {
        setData(res);
        setErr(null);
      })
      .catch((e: any) => {
        if (e instanceof ApiError && e.status === 401) router.push("/login");
        else setErr(e.message || "加载失败");
      });
  }, [router]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Agent"
        title="已关注 Agent"
        description="你订阅过的 Agent 会集中在这里，方便后续定向提问。"
      />

      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-sm text-red-600">{err}</div>}
      {!data ? (
        <div className="surface-card p-8 text-center text-sm text-text-tertiary">加载中...</div>
      ) : data.agent_subscriptions.length === 0 ? (
        <EmptyState
          title="你还没有订阅 Agent。"
          action={
          <button onClick={() => router.push("/agents")} className="stateful mt-4 rounded-md bg-brand px-4 py-2 text-sm font-medium text-canvas hover:bg-brand-hover">
            去发现 Agent
          </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {data.agent_subscriptions.map(item => <AgentDiscoveryCard key={item.id} agent={item.agent} />)}
        </div>
      )}
    </div>
  );
}
