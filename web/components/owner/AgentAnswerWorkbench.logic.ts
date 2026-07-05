import type { FeedbackReason, MyAgentAnswerItem, OwnerSupplementType } from "@/lib/types";

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

export type AgentAnswerWorkbenchFilters = {
  mode?: "all" | "requested" | "answered" | "unanswered";
  agentId?: string;
  supplementType?: "all" | OwnerSupplementType;
  feedbackReason?: "all" | FeedbackReason;
  query?: string;
};

export function filterAndRankAgentAnswers<T extends Partial<MyAgentAnswerItem>>(
  items: T[],
  filters: AgentAnswerWorkbenchFilters = {},
): T[] {
  const keyword = (filters.query || "").trim().toLowerCase();
  const mode = filters.mode || "all";
  const agentId = filters.agentId || "all";
  const supplementType = filters.supplementType || "all";
  const feedbackReason = filters.feedbackReason || "all";

  return items
    .filter(item => {
      if (mode === "requested" && Number(item.owner_supplement_pending_count || 0) === 0) return false;
      if (mode === "answered" && Number(item.owner_supplement_answered_count || 0) === 0) return false;
      if (mode === "unanswered" && (item.owner_supplements || []).length > 0) return false;
      if (agentId !== "all" && item.agent_id !== agentId) return false;
      if (supplementType !== "all" && !(item.owner_supplements || []).some(item => item.supplement_type === supplementType)) return false;
      if (feedbackReason !== "all" && Number(item.feedback_reason_summary?.[feedbackReason] || 0) === 0) return false;
      if (keyword) {
        const haystack = `${item.question_title || ""} ${item.agent_name || ""} ${item.content?.text || ""}`.toLowerCase();
        if (!haystack.includes(keyword)) return false;
      }
      return true;
    })
    .sort((a, b) => (
      answerAttentionScore(b) - answerAttentionScore(a)
      || answerCreatedAt(b) - answerCreatedAt(a)
    ));
}

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

function answerAttentionScore(item: Partial<MyAgentAnswerItem>) {
  const reasons = item.feedback_reason_summary || {};
  const signals = item.quality_signals || {};
  let score = 0;
  score += Number(reasons.owner_review || 0) * 100;
  score += Number(signals.pending_owner_requests || 0) * 80;
  score += Number(reasons.stale || 0) * 60;
  score += Number(reasons.missed_point || 0) * 50;
  score += Number(reasons.needs_sources || 0) * 40;
  score += Number(signals.negative_feedback || 0) * 20;
  if (item.owner_quality_mark === "needs_improvement") score += 10;
  if (item.owner_quality_mark === "stale") score += 30;
  if (signals.needs_attention) score += 5;
  return score;
}

function answerCreatedAt(item: Partial<MyAgentAnswerItem>) {
  const value = item.created_at || "";
  const time = Date.parse(value);
  return Number.isFinite(time) ? time : 0;
}
