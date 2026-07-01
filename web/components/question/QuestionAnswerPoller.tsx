"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Question } from "@/lib/types";
import {
  answerUsageSignature,
  questionAnswersForPolling,
  shouldPollQuestionAnswers,
  shouldRefreshQuestionAnswers,
} from "./QuestionAnswerPoller.logic";

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
        const latestAnswers = questionAnswersForPolling(latest);
        const latestAnswerCount = latestAnswers.length;
        const latestUsageSignature = answerUsageSignature(latestAnswers);
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
