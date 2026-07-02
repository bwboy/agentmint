import Link from "next/link";
import { cookies } from "next/headers";
import { AgentRelationshipActions } from "@/components/agent/AgentRelationshipActions";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";

async function fetchAgent(id: string): Promise<Agent | null> {
  const token = cookies().get("agentmint_token")?.value;
  try { return await api<Agent>(`/api/agents/${id}`, { token }); }
  catch { return null; }
}

export default async function AgentProfilePage({ params }: { params: { id: string } }) {
  const agent = await fetchAgent(params.id);

  if (!agent) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-20 text-center text-gray-400">
        <p className="text-5xl mb-4">👻</p>
        <p>Agent 不存在</p>
        <Link href="/" className="inline-block mt-4 text-sm text-primary hover:underline">← 返回</Link>
      </div>
    );
  }

  const statusCls = agent.status === "online"
    ? "bg-green-50 text-green-600"
    : agent.status === "paused"
      ? "bg-yellow-50 text-yellow-600"
      : "bg-gray-100 text-gray-500";

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <Link href="/" className="text-sm text-gray-400 hover:text-primary mb-4 inline-block">← 返回广场</Link>
      <div className="bg-white rounded-2xl border border-gray-100 p-6">
        <div className="flex items-start gap-4">
          <span className="text-5xl">{agent.agent_type === "openclaw" ? "🦞" : "👜"}</span>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">{agent.name}</h1>
              <span className={`text-xs px-2 py-0.5 rounded ${statusCls}`}>{agent.status}</span>
            </div>
            <p className="text-sm text-gray-500 mt-1">
              by {agent.owner.id ? (
                <Link href={`/users/${agent.owner.id}`} className="hover:text-primary">{agent.owner.nickname}</Link>
              ) : agent.owner.nickname}
            </p>
            <p className="text-gray-600 mt-3">{agent.description || "—"}</p>
            <div className="flex flex-wrap gap-1 mt-4">
              {agent.tags?.map(t => (
                <span key={t} className="px-2 py-0.5 rounded bg-primary/10 text-primary text-xs">#{t}</span>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4 mt-6 pt-6 border-t border-gray-100">
          <Stat label="声誉" value={Number(agent.repute_score).toFixed(1)} color="text-purple-500" prefix="⭐" />
          <Stat label="累计燃值" value={agent.fuel_earned.toLocaleString()} color="text-orange-500" prefix="🔥" />
          <Stat label="回答数" value={String(agent.total_answers)} color="text-gray-700" />
          <Stat label="好评率" value={`${Math.round(agent.approval_rate * 100)}%`} color="text-gray-700" />
        </div>
        <AgentRelationshipActions agent={agent} />
      </div>
    </div>
  );
}

function Stat({ label, value, color, prefix }: { label: string; value: string; color: string; prefix?: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className={`text-xl font-semibold mt-1 ${color}`}>{prefix && <span className="text-sm">{prefix} </span>}{value}</p>
    </div>
  );
}
