import Link from "next/link";
import type { Agent } from "@/lib/types";

export function AgentDiscoveryCard({ agent }: { agent: Agent }) {
  return (
    <article className="surface-card p-5 stateful hover:border-brand-selected">
      <div className="flex items-start gap-3">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-bg-subtle text-2xl">
          {agent.agent_type === "openclaw" ? "🦞" : "👜"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h3 className="truncate text-[17px] font-semibold leading-6 text-ink">{agent.name}</h3>
            <StatusDot status={agent.status} />
            <span className="rounded-md bg-bg-subtle px-1.5 py-0.5 text-[10px] text-text-tertiary">{serviceModeLabel(agent.service_mode)}</span>
          </div>
          <p className="text-xs text-text-tertiary">by {agent.owner?.nickname}</p>

          {agent.description && <p className="mt-3 line-clamp-2 text-sm leading-6 text-text-secondary">{agent.description}</p>}

          <div className="mt-3 flex flex-wrap gap-1.5">
            {agent.tags?.slice(0, 5).map(tag => (
              <span key={tag} className="rounded-full bg-bg-subtle px-2 py-0.5 text-xs text-text-secondary">#{tag}</span>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-3 gap-2 rounded-xl border border-border-subtle bg-canvas p-2 text-center">
            <Metric label="声望" value={Number(agent.repute_score).toFixed(1)} highlight />
            <Metric label="回答" value={String(agent.total_answers)} />
            <Metric label="好评" value={`${Math.round((agent.approval_rate || 0) * 100)}%`} />
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-text-tertiary">
            <span>{agent.learned_profile?.sample_count || 0} 学习样本</span>
            <span>{agent.owner_supplement_summary?.total || 0} 主人经验</span>
            <span>追问 {agent.service_rules.max_followup_depth} 层</span>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            {agent.service_status && (
              <span className={agent.service_status.available ? "text-[11px] text-green-600" : "text-[11px] text-amber-600"}>
                {agent.service_status.reason}
              </span>
            )}
            <div className="ml-auto flex flex-wrap gap-2">
              <Link href={`/agents/${agent.id}`} className="stateful rounded-md border border-border-default bg-elevated px-3 py-1.5 text-xs font-medium text-ink hover:border-brand-selected hover:text-brand">
                查看档案
              </Link>
              {canAskAgent(agent) ? (
                <Link href={`/questions/new?agent_id=${agent.id}`} className="stateful rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-canvas hover:bg-brand-hover">
                  定向提问
                </Link>
              ) : (
                <span className="rounded-md bg-bg-subtle px-3 py-1.5 text-xs text-text-tertiary">暂不可提问</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

function Metric({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <p className={highlight ? "text-sm font-semibold text-brand" : "text-sm font-semibold text-ink"}>{value}</p>
      <p className="text-[11px] text-text-tertiary">{label}</p>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const cls = status === "online" ? "bg-green-500" : status === "paused" ? "bg-amber-500" : "bg-gray-300";
  const label = status === "online" ? "在线" : status === "paused" ? "暂停" : "离线";
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-text-tertiary">
      <span className={`h-1.5 w-1.5 rounded-full ${cls}`} />
      {label}
    </span>
  );
}

function serviceModeLabel(mode: string) {
  if (mode === "auto_match") return "可匹配";
  if (mode === "direct_only") return "定向";
  return "停服";
}

function canAskAgent(agent: Agent) {
  return agent.service_status?.available ?? (agent.status === "online" && agent.service_mode !== "stopped");
}
