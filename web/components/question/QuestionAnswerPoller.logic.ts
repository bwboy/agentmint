import type { Answer, Question } from "@/lib/types";

export function shouldPollQuestionAnswers({
  currentAnswerCount,
  deadlineAt,
  now = new Date(),
}: {
  currentAnswerCount: number;
  deadlineAt: string;
  now?: Date;
}) {
  return new Date(deadlineAt) > now;
}

export function shouldRefreshQuestionAnswers({
  currentAnswerCount,
  latestAnswerCount,
  currentUsageSignature = "",
  latestUsageSignature = "",
  deadlineAt,
  now = new Date(),
}: {
  currentAnswerCount: number;
  latestAnswerCount: number;
  currentUsageSignature?: string;
  latestUsageSignature?: string;
  deadlineAt: string;
  now?: Date;
}) {
  return shouldPollQuestionAnswers({ currentAnswerCount, deadlineAt, now })
    && (
      latestAnswerCount > currentAnswerCount
      || (latestUsageSignature !== "" && latestUsageSignature !== currentUsageSignature)
    );
}

export function answerUsageSignature(answers: Question["answers"] = []) {
  return answers
    .map(answer => [
      answer.id,
      answer.usage?.prompt_tokens ?? 0,
      answer.usage?.completion_tokens ?? 0,
      answer.usage?.total_tokens ?? 0,
      answer.usage?.estimated ? "estimated" : "provider",
      answer.fuel_earned ?? 0,
      answer.settlement?.base_fuel_charged ?? 0,
    ].join(":"))
    .join("|");
}

export function questionAnswersForPolling(question: Pick<Question, "answers" | "followups">) {
  return [
    ...(question.answers || []),
    ...(question.followups || []).flatMap(thread => thread.answers || []),
  ];
}

export function questionAnswerCountForPolling(question: Pick<Question, "answer_count" | "answers" | "followups">) {
  return questionAnswersForPolling(question).length || question.answer_count || 0;
}

export function questionPollingDeadline(question: Pick<Question, "deadline_at" | "followups">) {
  const deadlines = [
    question.deadline_at,
    ...(question.followups || []).map(thread => thread.deadline_at).filter(Boolean),
  ] as string[];

  return deadlines.reduce((latest, item) => (
    new Date(item).getTime() > new Date(latest).getTime() ? item : latest
  ), question.deadline_at);
}

export function followupsForAnswer(
  followups: NonNullable<Question["followups"]> = [],
  answerId: string,
) {
  return followups.filter(thread => thread.quoted_answer_id === answerId);
}

export function questionFuelSummary(
  question: Pick<Question,
    "base_fuel_reserved"
    | "base_fuel_spent"
    | "reward_fuel"
    | "reward_status"
    | "estimated_fuel_per_answer"
    | "matched_count"
  >,
) {
  const baseReserved = Math.max(0, Number(question.base_fuel_reserved || 0));
  const baseSpent = Math.max(0, Number(question.base_fuel_spent || 0));
  const rewardFuel = Math.max(0, Number(question.reward_fuel || 0));
  return {
    baseReserved,
    baseSpent,
    baseRemaining: Math.max(0, baseReserved - baseSpent),
    rewardFuel,
    rewardStatus: question.reward_status,
    totalReserved: baseReserved + rewardFuel,
    estimatedPerAnswer: Math.max(0, Number(question.estimated_fuel_per_answer || 0)),
    matchedCount: Math.max(0, Number(question.matched_count || 0)),
  };
}

export function answerSettlementSummary(
  answer: Pick<Answer, "id" | "usage" | "fuel_earned" | "settlement">,
  question: Pick<Question, "reward_answer_id" | "reward_fuel" | "reward_status">,
) {
  const usage = answer.usage || {};
  const promptTokens = Math.max(0, Number(usage.prompt_tokens || 0));
  const completionTokens = Math.max(0, Number(usage.completion_tokens || 0));
  const totalTokens = Math.max(0, Number(usage.total_tokens || promptTokens + completionTokens));
  const baseFuelCharged = Math.max(0, Number(answer.settlement?.base_fuel_charged ?? answer.fuel_earned ?? 0));
  const rewardFuel = question.reward_answer_id && question.reward_answer_id === answer.id
    ? Math.max(0, Number(question.reward_fuel || 0))
    : 0;

  return {
    promptTokens,
    completionTokens,
    totalTokens,
    usageSourceLabel: usage.estimated ? "平台估算" : usage.source === "provider" ? "模型真实回传" : "Agent 回传",
    baseFuelCharged,
    rewardFuel,
    totalFuelEarned: baseFuelCharged + rewardFuel,
    rewardLabel: rewardFuel > 0
      ? (question.reward_status === "auto_awarded" ? "系统分配奖励" : "提问者奖励")
      : "未获得奖励",
  };
}
