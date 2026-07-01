import assert from "node:assert/strict";
import { test } from "node:test";

import {
  answerUsageSignature,
  shouldRefreshQuestionAnswers,
} from "./QuestionAnswerPoller.logic.ts";

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
      currentUsageSignature: "ans_1:75:990:1065:estimated",
      latestUsageSignature: "ans_1:70:816:886:provider",
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
      },
      {
        id: "ans_2",
        usage: {
          prompt_tokens: 70,
          completion_tokens: 816,
          total_tokens: 886,
          estimated: false,
        },
      },
    ]),
    "ans_1:75:990:1065:estimated|ans_2:70:816:886:provider",
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
      },
    ]),
    "ans_root:40:120:160:provider|ans_followup:30:90:120:estimated",
  );
});
