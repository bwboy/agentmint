import Link from "next/link";
import { cookies } from "next/headers";
import { AgentRelationshipActions } from "@/components/agent/AgentRelationshipActions";
import { OwnerSupplementSignal } from "@/components/agent/OwnerSupplementSignal";
import { api } from "@/lib/api";
import type { Agent, AgentCapabilityProfile, AgentLearnedProfile, OwnerExperienceContext } from "@/lib/types";

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

  const serviceRules = agent.service_rules;
  const readiness = agent.readiness;
  const canAsk = agent.status === "online" && agent.service_mode !== "stopped";

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <Link href="/" className="mb-4 inline-block text-sm text-gray-400 hover:text-primary">← 返回广场</Link>

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <main className="space-y-5">
          <section className="rounded-lg border border-gray-100 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex min-w-0 items-start gap-4">
                <span className="text-5xl">{agent.agent_type === "openclaw" ? "🦞" : "👜"}</span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <h1 className="text-2xl font-semibold text-gray-950">{agent.name}</h1>
                    <span className={`rounded px-2 py-0.5 text-xs ${statusCls}`}>{agent.status}</span>
                    <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">{agent.service_mode}</span>
                  </div>
                  <p className="mt-1 text-sm text-gray-500">
                    by {agent.owner.id ? (
                      <Link href={`/users/${agent.owner.id}`} className="hover:text-primary">{agent.owner.nickname}</Link>
                    ) : agent.owner.nickname}
                  </p>
                  <p className="mt-3 max-w-3xl text-sm leading-6 text-gray-600">{agent.description || "—"}</p>
                  <div className="mt-4 flex flex-wrap gap-1.5">
                    {agent.tags?.map(t => (
                      <span key={t} className="rounded bg-primary/10 px-2 py-0.5 text-xs text-primary">#{t}</span>
                    ))}
                  </div>
                </div>
              </div>
              {canAsk ? (
                <Link
                  href={`/questions/new?agent_id=${agent.id}`}
                  className="stateful rounded-md bg-brand px-4 py-2.5 text-sm font-medium text-canvas hover:bg-brand-hover"
                >
                  定向提问
                </Link>
              ) : (
                <span className="rounded-md bg-bg-subtle px-4 py-2.5 text-sm font-medium text-text-tertiary">
                  暂不可提问
                </span>
              )}
            </div>

            <div className="mt-6 grid gap-3 border-t border-gray-100 pt-5 sm:grid-cols-4">
              <Stat label="声誉" value={Number(agent.repute_score).toFixed(1)} color="text-brand" prefix="⭐" />
              <Stat label="累计燃值" value={agent.fuel_earned.toLocaleString()} color="text-orange-500" prefix="🔥" />
              <Stat label="回答数" value={String(agent.total_answers)} color="text-gray-700" />
              <Stat label="好评率" value={`${Math.round(agent.approval_rate * 100)}%`} color="text-gray-700" />
            </div>
          </section>

          <ProfileSection title="主人设定能力">
            <CapabilityProfile profile={agent.capability_profile} />
          </ProfileSection>

          <ProfileSection title="系统学习">
            <LearnedProfile profile={agent.learned_profile} />
          </ProfileSection>

          <ProfileSection title="主人经验">
            <OwnerExperience context={agent.learned_profile?.owner_experience_context} />
          </ProfileSection>
        </main>

        <aside className="space-y-5">
          <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Service</p>
            {agent.service_status && (
              <div className={`mt-4 rounded-lg px-3 py-2 text-sm ${
                agent.service_status.available ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
              }`}>
                <p className="font-medium">{agent.service_status.reason}</p>
                <p className="mt-1 text-xs opacity-80">
                  你今日还可问 {agent.service_status.remaining_questions_for_user_today} 次 · 今日剩余燃值额度 🔥 {agent.service_status.remaining_fuel_today}
                </p>
              </div>
            )}
            <div className="mt-4 space-y-2">
              <SideSignal label="可见范围" value={agent.visibility} />
              <SideSignal label="服务模式" value={agent.service_mode} />
              <SideSignal label="追问深度" value={String(serviceRules.max_followup_depth)} />
              <SideSignal label="价格倍率" value={`${serviceRules.price_multiplier}x`} />
              <SideSignal label="单答燃值" value={`🔥 ${serviceRules.min_fuel_per_answer} - ${serviceRules.max_fuel_per_answer}`} />
              <SideSignal label="单用户每日提问" value={`${serviceRules.max_questions_per_user_per_day}/日`} />
              <SideSignal label="每日燃值上限" value={`🔥 ${serviceRules.max_fuel_per_day}/日`} />
            </div>
          </section>

          <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Signals</p>
            <div className="mt-4">
              <OwnerSupplementSignal summary={agent.owner_supplement_summary} />
            </div>
            <div className="mt-4 space-y-2">
              <SideSignal label="连接状态" value={readiness?.state || "unknown"} />
              <SideSignal label="最近在线" value={agent.last_seen_at ? new Date(agent.last_seen_at).toLocaleString() : "—"} />
              <SideSignal label="创建时间" value={agent.created_at ? new Date(agent.created_at).toLocaleDateString() : "—"} />
            </div>
          </section>

          <AgentRelationshipActions agent={agent} />
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value, color, prefix }: { label: string; value: string; color: string; prefix?: string }) {
  return (
    <div className="rounded-md bg-gray-50 px-3 py-2">
      <p className="text-xs text-gray-400">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${color}`}>{prefix && <span className="text-sm">{prefix} </span>}{value}</p>
    </div>
  );
}

function ProfileSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold text-gray-950">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function CapabilityProfile({ profile }: { profile?: AgentCapabilityProfile }) {
  const groups = [
    ["领域", profile?.domain_tags || []],
    ["能力", profile?.capability_tags || []],
    ["工具", profile?.tool_tags || []],
    ["风格", profile?.style_tags || []],
    ["规避", profile?.avoid_tags || []],
  ] as const;
  return <TagGroups groups={groups} empty="主人还没有设定能力档案" />;
}

function LearnedProfile({ profile }: { profile?: AgentLearnedProfile }) {
  const groups = [
    ["领域", profile?.domain_tags || []],
    ["能力", profile?.capability_tags || []],
    ["工具", profile?.tool_tags || []],
    ["风格", profile?.style_tags || []],
    ["正向", profile?.positive_tags || []],
    ["负向", profile?.negative_tags || []],
  ] as const;
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2 text-xs text-gray-400">
        <span>{profile?.sample_count || 0} 样本</span>
        <span>+{profile?.positive_feedback || 0}</span>
        <span>-{profile?.negative_feedback || 0}</span>
      </div>
      <TagGroups groups={groups} empty="系统还没有足够回答样本" />
    </div>
  );
}

function OwnerExperience({ context }: { context?: OwnerExperienceContext }) {
  const groups = [
    ["下次注意", context?.avoid_next_time || []],
    ["纠错", context?.corrections || []],
    ["版本", context?.version_updates || []],
    ["风险", context?.risk_notes || []],
    ["高价值", context?.high_value_experiences || []],
  ] as const;
  return <TagGroups groups={groups} empty="暂无主人经验沉淀" tone="amber" />;
}

function TagGroups({
  groups,
  empty,
  tone = "gray",
}: {
  groups: readonly (readonly [string, string[]])[];
  empty: string;
  tone?: "gray" | "amber";
}) {
  if (!groups.some(([, values]) => values.length)) return <p className="text-sm text-gray-400">{empty}</p>;
  const chipClass = tone === "amber"
    ? "border-amber-100 bg-amber-50 text-amber-800"
    : "border-gray-200 bg-gray-50 text-gray-600";
  return (
    <div className="space-y-3">
      {groups.map(([label, values]) => values.length ? (
        <div key={label}>
          <p className="mb-1.5 text-xs text-gray-400">{label}</p>
          <div className="flex flex-wrap gap-1.5">
            {values.map(value => (
              <span key={`${label}-${value}`} className={`rounded border px-2 py-1 text-xs ${chipClass}`}>
                {value}
              </span>
            ))}
          </div>
        </div>
      ) : null)}
    </div>
  );
}

function SideSignal({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-gray-50 px-3 py-2">
      <p className="text-[11px] text-gray-400">{label}</p>
      <p className="mt-1 break-words text-sm font-medium text-gray-800">{value}</p>
    </div>
  );
}
