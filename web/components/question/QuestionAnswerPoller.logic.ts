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
