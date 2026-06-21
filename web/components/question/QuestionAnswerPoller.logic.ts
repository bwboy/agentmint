export function shouldPollQuestionAnswers({
  currentAnswerCount,
  deadlineAt,
  now = new Date(),
}: {
  currentAnswerCount: number;
  deadlineAt: string;
  now?: Date;
}) {
  return currentAnswerCount === 0 && new Date(deadlineAt) > now;
}

export function shouldRefreshQuestionAnswers({
  currentAnswerCount,
  latestAnswerCount,
  deadlineAt,
  now = new Date(),
}: {
  currentAnswerCount: number;
  latestAnswerCount: number;
  deadlineAt: string;
  now?: Date;
}) {
  return shouldPollQuestionAnswers({ currentAnswerCount, deadlineAt, now })
    && latestAnswerCount > currentAnswerCount;
}
