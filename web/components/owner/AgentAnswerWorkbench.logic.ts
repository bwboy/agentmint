import type { MyAgentAnswerItem } from "@/lib/types";

export type AgentHealthRiskLevel = "healthy" | "watch" | "high";

export type AgentHealthSummary = {
  agentId: string;
  agentName: string;
  totalAnswers: number;
  attentionAnswers: number;
  negativeFeedback: number;
  pendingOwnerRequests: number;
  ownerCorrections: number;
  ownerRiskNotes: number;
  staleAnswers: number;
  riskLevel: AgentHealthRiskLevel;
  reasons: string[];
};

export function buildAgentHealthSummaries(items: Array<Partial<MyAgentAnswerItem>>) {
  const byAgent = new Map<string, AgentHealthSummary>();

  for (const item of items) {
    const agentId = String(item.agent_id || "");
    if (!agentId) continue;
    const current = byAgent.get(agentId) || {
      agentId,
      agentName: String(item.agent_name || agentId),
      totalAnswers: 0,
      attentionAnswers: 0,
      negativeFeedback: 0,
      pendingOwnerRequests: 0,
      ownerCorrections: 0,
      ownerRiskNotes: 0,
      staleAnswers: 0,
      riskLevel: "healthy" as AgentHealthRiskLevel,
      reasons: [],
    };

    const signals = item.quality_signals || {};
    current.totalAnswers += 1;
    if (signals.needs_attention) current.attentionAnswers += 1;
    current.negativeFeedback += Number(signals.negative_feedback || 0);
    current.pendingOwnerRequests += Number(signals.pending_owner_requests || 0);
    current.ownerCorrections += Number(signals.owner_corrections || 0);
    current.ownerRiskNotes += Number(signals.owner_risk_notes || 0);
    if (item.owner_quality_mark === "stale") current.staleAnswers += 1;
    for (const reason of signals.reasons || []) {
      if (!current.reasons.includes(reason)) current.reasons.push(reason);
    }

    byAgent.set(agentId, current);
  }

  return Array.from(byAgent.values())
    .map(summary => ({
      ...summary,
      riskLevel: agentHealthRiskLevel(summary),
    }))
    .sort((a, b) => (
      riskRank(b.riskLevel) - riskRank(a.riskLevel)
      || b.attentionAnswers - a.attentionAnswers
      || a.agentName.localeCompare(b.agentName)
    ));
}

function agentHealthRiskLevel(summary: AgentHealthSummary): AgentHealthRiskLevel {
  if (
    summary.staleAnswers > 0
    || summary.ownerCorrections >= 2
    || summary.negativeFeedback >= 2
    || summary.attentionAnswers >= 2
  ) return "high";
  if (summary.attentionAnswers > 0 || summary.pendingOwnerRequests > 0 || summary.ownerRiskNotes > 0) return "watch";
  return "healthy";
}

function riskRank(level: AgentHealthRiskLevel) {
  if (level === "high") return 2;
  if (level === "watch") return 1;
  return 0;
}
