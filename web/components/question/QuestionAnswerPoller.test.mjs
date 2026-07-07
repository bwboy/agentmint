import assert from "node:assert/strict";
import { test } from "node:test";

import {
  answerSettlementSummary,
  answerUsageSignature,
  answerDisplayParts,
  followupsForAnswer,
  isRuntimeAnswerUpdate,
  questionPollingDeadline,
  questionFuelSummary,
  rewardStatusSummary,
  questionAnswerCountForPolling,
  questionAnswersForPolling,
  shouldRefreshQuestionAnswers,
} from "./QuestionAnswerPoller.logic.ts";

test("detects structured runtime answer updates", () => {
  assert.equal(
    isRuntimeAnswerUpdate({
      usage: { runtime_update: true },
      content: { text: "👁️ Looking at the image..." },
    }),
    true,
  );
});

test("detects legacy Hermes runtime answer text", () => {
  assert.equal(
    isRuntimeAnswerUpdate({
      usage: { total_tokens: 0 },
      content: { text: "👁️ Looking at the image..." },
    }),
    true,
  );
});

test("does not treat normal image answers as runtime updates", () => {
  assert.equal(
    isRuntimeAnswerUpdate({
      usage: { total_tokens: 250 },
      content: { text: "我看了图片，这几个人分别是 Arthur、Dutch 和 Hosea。" },
    }),
    false,
  );
});

test("returns all answer display parts including runtime updates", () => {
  assert.deepEqual(
    answerDisplayParts({
      content: {
        text: "处理中\n\n最终第一段\n\n最终第二段",
        parts: [
          { text: "⏳ Working — 1 min — iteration 1/10, waiting for stream response", runtime_update: true },
          { text: "最终第一段", runtime_update: false },
          { text: "最终第二段", runtime_update: false },
        ],
      },
      usage: { total_tokens: 100 },
    }).map(part => part.text),
    ["⏳ Working — 1 min — iteration 1/10, waiting for stream response", "最终第一段", "最终第二段"],
  );
});

test("falls back to content text when answer has no parts", () => {
  assert.deepEqual(
    answerDisplayParts({
      content: { text: "单段回答" },
      usage: { total_tokens: 20 },
    }).map(part => part.text),
    ["单段回答"],
  );
});

test("refreshes while the question can still receive answers and a new answer appears", () => {
  assert.equal(
    shouldRefreshQuestionAnswers({
      currentAnswerCount: 0,
      latestAnswerCount: 1,
      deadlineAt: "2026-06-21T12:01:00.000Z",
      now: new Date("2026-06-21T12:00:00.000Z"),
    }),
    true,
  );
});

test("does not refresh when the latest answer count has not increased", () => {
  assert.equal(
    shouldRefreshQuestionAnswers({
      currentAnswerCount: 1,
      latestAnswerCount: 1,
      deadlineAt: "2026-06-21T12:01:00.000Z",
      now: new Date("2026-06-21T12:00:00.000Z"),
    }),
    false,
  );
});

test("refreshes when answer usage changes before the deadline", () => {
  assert.equal(
    shouldRefreshQuestionAnswers({
      currentAnswerCount: 1,
      latestAnswerCount: 1,
      currentUsageSignature: "ans_1:75:990:1065:estimated:0:0:0:0",
      latestUsageSignature: "ans_1:70:816:886:provider:0:0:0:0",
      deadlineAt: "2026-06-21T12:01:00.000Z",
      now: new Date("2026-06-21T12:00:00.000Z"),
    }),
    true,
  );
});

test("does not refresh after the question deadline has passed", () => {
  assert.equal(
    shouldRefreshQuestionAnswers({
      currentAnswerCount: 0,
      latestAnswerCount: 1,
      deadlineAt: "2026-06-21T11:59:00.000Z",
      now: new Date("2026-06-21T12:00:00.000Z"),
    }),
    false,
  );
});

test("builds an answer usage signature from token counts and estimate state", () => {
  assert.equal(
    answerUsageSignature([
      {
        id: "ans_1",
        usage: {
          prompt_tokens: 75,
          completion_tokens: 990,
          total_tokens: 1065,
          estimated: true,
        },
        fuel_earned: 50,
        settlement: { base_fuel_charged: 50 },
      },
      {
        id: "ans_2",
        usage: {
          prompt_tokens: 70,
          completion_tokens: 816,
          total_tokens: 886,
          estimated: false,
        },
        fuel_earned: 1702,
        settlement: { base_fuel_charged: 1702 },
      },
    ]),
    "ans_1:75:990:1065:estimated:50:50:0:0|ans_2:70:816:886:provider:1702:1702:0:0",
  );
});

test("refreshes when answer settlement changes before the deadline", () => {
  assert.equal(
    shouldRefreshQuestionAnswers({
      currentAnswerCount: 1,
      latestAnswerCount: 1,
      currentUsageSignature: "ans_1:70:816:886:provider:0:0:0:0",
      latestUsageSignature: "ans_1:70:816:886:provider:1702:1702:0:0",
      deadlineAt: "2026-06-21T12:01:00.000Z",
      now: new Date("2026-06-21T12:00:00.000Z"),
    }),
    true,
  );
});

test("includes follow-up answers when provided in the combined answer array", () => {
  assert.equal(
    answerUsageSignature([
      {
        id: "ans_root",
        usage: {
          prompt_tokens: 40,
          completion_tokens: 120,
          total_tokens: 160,
          estimated: false,
        },
        fuel_earned: 400,
        settlement: { base_fuel_charged: 400 },
      },
      {
        id: "ans_followup",
        turn_type: "followup",
        parent_answer_id: "ans_root",
        usage: {
          prompt_tokens: 30,
          completion_tokens: 90,
          total_tokens: 120,
          estimated: true,
        },
        fuel_earned: 220,
        settlement: { base_fuel_charged: 220 },
      },
    ]),
    "ans_root:40:120:160:provider:400:400:0:0|ans_followup:30:90:120:estimated:220:220:0:0",
  );
});

test("builds the polling answer list from root and follow-up answers", () => {
  assert.deepEqual(
    questionAnswersForPolling({
      answers: [{ id: "ans_root" }],
      followups: [
        { id: "fu_1", answers: [{ id: "ans_followup_1" }, { id: "ans_followup_2" }] },
        { id: "fu_2", answers: [] },
      ],
    }).map(answer => answer.id),
    ["ans_root", "ans_followup_1", "ans_followup_2"],
  );
});

test("uses answer_count as the polling count fallback when answers are not hydrated", () => {
  assert.equal(
    questionAnswerCountForPolling({
      answer_count: 3,
      answers: [],
      followups: [],
    }),
    3,
  );
});

test("uses the latest follow-up deadline when it extends beyond the root question", () => {
  assert.equal(
    questionPollingDeadline({
      deadline_at: "2026-07-01T12:00:00.000Z",
      followups: [
        { id: "fu_old", deadline_at: "2026-07-01T11:30:00.000Z", answers: [] },
        { id: "fu_new", deadline_at: "2026-07-01T12:30:00.000Z", answers: [] },
      ],
    }),
    "2026-07-01T12:30:00.000Z",
  );
});

test("finds follow-up threads for any quoted answer id", () => {
  const followups = [
    { id: "fu_root", quoted_answer_id: "ans_root", answers: [{ id: "ans_fu" }] },
    { id: "fu_nested", quoted_answer_id: "ans_fu", answers: [{ id: "ans_nested" }] },
  ];

  assert.deepEqual(
    followupsForAnswer(followups, "ans_fu").map(thread => thread.id),
    ["fu_nested"],
  );
});

test("summarizes question fuel reservation and reward state", () => {
  assert.deepEqual(
    questionFuelSummary({
      base_fuel_reserved: 4500,
      base_fuel_spent: 1800,
      reward_fuel: 500,
      reward_status: "pending",
      estimated_fuel_per_answer: 900,
      matched_count: 3,
    }),
    {
      baseReserved: 4500,
      baseSpent: 1800,
      baseRemaining: 2700,
      rewardFuel: 500,
      rewardStatus: "pending",
      totalReserved: 5000,
      estimatedPerAnswer: 900,
      matchedCount: 3,
    },
  );
});

test("summarizes per-answer token usage and fuel settlement", () => {
  assert.deepEqual(
    answerSettlementSummary(
      {
        id: "ans_1",
        usage: {
          prompt_tokens: 70,
          completion_tokens: 816,
          total_tokens: 886,
          estimated: false,
          source: "provider",
        },
        fuel_earned: 1702,
        settlement: { base_fuel_charged: 1702 },
      },
      {
        reward_answer_id: "ans_1",
        reward_fuel: 500,
        reward_status: "auto_awarded",
      },
    ),
    {
      promptTokens: 70,
      completionTokens: 816,
      totalTokens: 886,
      usageSourceLabel: "模型真实回传",
      baseFuelCharged: 1702,
      rewardFuel: 500,
      totalFuelEarned: 2202,
      rewardLabel: "系统分配奖励",
    },
  );
});

test("explains pending reward auto-award timing", () => {
  assert.deepEqual(
    rewardStatusSummary({
      reward_fuel: 500,
      reward_status: "pending",
      reward_answer_id: null,
      reward_auto_award_after: "2026-07-04T12:00:00.000Z",
    }),
    {
      label: "待分配",
      tone: "pending",
      title: "最佳回答奖励待分配",
      detail: "可在 2026/7/4 20:00:00 前手动选择最佳回答；到期未选择，系统会按互动信号自动分配。",
    },
  );
});

test("explains auto-awarded reward state", () => {
  assert.deepEqual(
    rewardStatusSummary({
      reward_fuel: 500,
      reward_status: "auto_awarded",
      reward_answer_id: "ans_1",
      reward_auto_award_after: "2026-07-04T12:00:00.000Z",
    }),
    {
      label: "系统已分配",
      tone: "awarded",
      title: "系统已自动分配奖励",
      detail: "奖励已发给最佳回答，提问者无需再处理。",
    },
  );
});
