"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AgentDiscoveryCard } from "@/components/agent/AgentDiscoveryCard";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Agent } from "@/lib/types";

export default function MineAgentsPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    api<{ data: Agent[] }>("/api/my/agents", { token })
      .then(res => {
        setAgents(res.data || []);
        setErr(null);
      })
      .catch((e: any) => {
        if (e instanceof ApiError && e.status === 401) router.push("/login");
        else setErr(e.message || "加载失败");
      });
  }, [router]);

  return (
    <div className="space-y-6">
      <section className="surface-card p-6 md:p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-medium text-brand">Agent</p>
            <h1 className="mt-3 text-4xl font-bold tracking-[-0.02em] text-ink">我的 Agent</h1>
            <p className="mt-3 text-sm text-text-secondary">这里是 Agent 模块里的展示视图；注册、Token、配额和能力档案编辑仍在工作台处理。</p>
          </div>
          <Link href="/my/agents" className="stateful inline-flex h-10 items-center justify-center rounded-md bg-brand px-4 text-sm font-medium text-canvas hover:bg-brand-hover">
            进入管理工作台
          </Link>
        </div>
      </section>

      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-sm text-red-600">{err}</div>}
      {!agents ? (
        <div className="surface-card p-8 text-center text-sm text-text-tertiary">加载中...</div>
      ) : agents.length === 0 ? (
        <div className="surface-card p-8 text-center">
          <p className="text-sm text-text-tertiary">你还没有注册 Agent。</p>
          <Link href="/my/agents" className="stateful mt-4 inline-flex rounded-md bg-brand px-4 py-2 text-sm font-medium text-canvas hover:bg-brand-hover">
            注册 Agent
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {agents.map(agent => <AgentDiscoveryCard key={agent.id} agent={agent} />)}
        </div>
      )}
    </div>
  );
}
