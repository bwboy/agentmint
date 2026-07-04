import assert from "node:assert/strict";
import { test } from "node:test";

import { buildAgentHealthSummaries } from "./AgentAnswerWorkbench.logic.ts";

test("builds per-agent health summaries from answer quality signals", () => {
  const summaries = buildAgentHealthSummaries([
    {
      id: "ans_1",
      agent_id: "a_1",
      agent_name: "Mac Hermes",
      owner_quality_mark: "needs_improvement",
      vote_summary: { up: 1, down: 2 },
      quality_signals: {
        needs_attention: true,
        reasons: ["negative_feedback", "owner_correction"],
        negative_feedback: 2,
        pending_owner_requests: 1,
        owner_corrections: 1,
        owner_risk_notes: 0,
      },
    },
    {
      id: "ans_2",
      agent_id: "a_1",
      agent_name: "Mac Hermes",
      owner_quality_mark: "stale",
      vote_summary: { up: 0, down: 0 },
      quality_signals: {
        needs_attention: true,
        reasons: ["owner_mark_stale", "owner_risk_note"],
        negative_feedback: 0,
        pending_owner_requests: 0,
        owner_corrections: 0,
        owner_risk_notes: 1,
      },
    },
    {
      id: "ans_3",
      agent_id: "a_2",
      agent_name: "Linux Hermes",
      owner_quality_mark: "excellent",
      vote_summary: { up: 3, down: 0 },
      quality_signals: { needs_attention: false, reasons: [] },
    },
  ]);

  assert.deepEqual(summaries, [
    {
      agentId: "a_1",
      agentName: "Mac Hermes",
      totalAnswers: 2,
      attentionAnswers: 2,
      negativeFeedback: 2,
      pendingOwnerRequests: 1,
      ownerCorrections: 1,
      ownerRiskNotes: 1,
      staleAnswers: 1,
      riskLevel: "high",
      reasons: ["negative_feedback", "owner_correction", "owner_mark_stale", "owner_risk_note"],
    },
    {
      agentId: "a_2",
      agentName: "Linux Hermes",
      totalAnswers: 1,
      attentionAnswers: 0,
      negativeFeedback: 0,
      pendingOwnerRequests: 0,
      ownerCorrections: 0,
      ownerRiskNotes: 0,
      staleAnswers: 0,
      riskLevel: "healthy",
      reasons: [],
    },
  ]);
});
