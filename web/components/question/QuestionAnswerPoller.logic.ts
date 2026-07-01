import type { Question } from "@/lib/types";

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
