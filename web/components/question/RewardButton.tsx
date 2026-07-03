"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";

export function RewardButton({
  questionId,
  answerId,
  rewardFuel,
}: {
  questionId: string;
  answerId: string;
  rewardFuel: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function award() {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/questions/${questionId}/answers/${answerId}/reward`, {
        method: "POST",
        token,
      });
      router.refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "奖励失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={award}
        disabled={busy}
        className="rounded-lg border border-orange-200 bg-orange-50 px-3 py-1.5 text-sm font-medium text-orange-600 transition hover:border-orange-300 hover:bg-orange-100 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? "奖励中..." : `奖励此回答 🔥 ${rewardFuel}`}
      </button>
      {err && <span className="text-xs text-red-500">{err}</span>}
    </div>
  );
}
