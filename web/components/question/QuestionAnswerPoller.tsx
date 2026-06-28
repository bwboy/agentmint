"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Question } from "@/lib/types";
import { shouldPollQuestionAnswers, shouldRefreshQuestionAnswers } from "./QuestionAnswerPoller.logic";

const POLL_INTERVAL_MS = 3000;

export function QuestionAnswerPoller({
  questionId,
  currentAnswerCount,
  currentUsageSignature,
  deadlineAt,
}: {
  questionId: string;
  currentAnswerCount: number;
  currentUsageSignature: string;
  deadlineAt: string;
}) {
  const router = useRouter();

  useEffect(() => {
    if (!shouldPollQuestionAnswers({ currentAnswerCount, deadlineAt })) return;

    let cancelled = false;

    async function checkForAnswers() {
      try {
        const latest = await api<Question>(`/api/questions/${questionId}`);
        const latestAnswerCount = latest.answers?.length ?? latest.answer_count ?? 0;
        const latestUsageSignature = answerUsageSignature(latest.answers || []);
        if (!cancelled && shouldRefreshQuestionAnswers({
          currentAnswerCount,
          latestAnswerCount,
          currentUsageSignature,
          latestUsageSignature,
          deadlineAt,
        })) {
          router.refresh();
        }
      } catch {
        // Keep the server-rendered page usable if one poll fails.
      }
    }

    const timer = window.setInterval(checkForAnswers, POLL_INTERVAL_MS);
    void checkForAnswers();

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [currentAnswerCount, currentUsageSignature, deadlineAt, questionId, router]);

  return null;
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
