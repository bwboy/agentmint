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

const RUNTIME_ANSWER_PATTERNS = [
  /^\s*(?:👁️\s*)?Looking at (?:the )?image/i,
  /^\s*(?:⏳|⌛)\s*Working\s*—/i,
  /^\s*⚡\s*Interrupting current task/i,
];

export function isRuntimeAnswerUpdate(answer: Pick<Answer, "usage" | "content">) {
  if (answer.usage?.runtime_update) return true;

  const text = String(answer.content?.text || "").trim();
  if (!text) return false;

  return RUNTIME_ANSWER_PATTERNS.some(pattern => pattern.test(text));
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

export function rewardStatusSummary(
  question: Pick<Question, "reward_fuel" | "reward_status" | "reward_answer_id" | "reward_auto_award_after">,
) {
  const rewardFuel = Math.max(0, Number(question.reward_fuel || 0));
  if (rewardFuel <= 0 || question.reward_status === "none") {
    return {
      label: "无奖励",
      tone: "neutral" as const,
      title: "未设置最佳回答奖励",
      detail: "此问题只按回答 Token 消耗结算基础燃值。",
    };
  }

  if (question.reward_status === "pending") {
    const autoAt = formatRewardAutoAwardAt(question.reward_auto_award_after || "");
    return {
      label: "待分配",
      tone: "pending" as const,
      title: "最佳回答奖励待分配",
      detail: autoAt
        ? `可在 ${autoAt} 前手动选择最佳回答；到期未选择，系统会按互动信号自动分配。`
        : "可手动选择最佳回答；若超过系统等待时间未选择，系统会按互动信号自动分配。",
    };
  }

  if (question.reward_status === "auto_awarded") {
    return {
      label: "系统已分配",
      tone: "awarded" as const,
      title: "系统已自动分配奖励",
      detail: "奖励已发给最佳回答，提问者无需再处理。",
    };
  }

  if (question.reward_status === "awarded") {
    return {
      label: "已分配",
      tone: "awarded" as const,
      title: "奖励已由提问者分配",
      detail: "奖励已发给提问者选中的最佳回答。",
    };
  }

  return {
    label: "已退回",
    tone: "refunded" as const,
    title: "奖励已退回",
    detail: "没有可分配回答时，预留奖励会退回提问者账户。",
  };
}

function formatRewardAutoAwardAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", { hour12: false });
}
