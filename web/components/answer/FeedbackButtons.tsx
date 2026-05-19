"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";

export function FeedbackButtons({
  answerId, questionId, initialUp, initialDown,
}: { answerId: string; questionId: string; initialUp: number; initialDown: number }) {
  const router = useRouter();
  const [up, setUp] = useState(initialUp);
  const [down, setDown] = useState(initialDown);
  const [voted, setVoted] = useState<"up" | "down" | null>(null);
  const [busy, setBusy] = useState(false);

  async function vote(v: "up" | "down") {
    const token = getToken();
    if (!token) { router.push("/login"); return; }
    setBusy(true);
    try {
      await api(`/api/questions/${questionId}/answers/${answerId}/feedback`, {
        method: "POST", token, json: { vote: v, comment: "" },
      });
      if (v === "up") {
        setUp(u => voted === "up" ? u : u + 1);
        if (voted === "down") setDown(d => Math.max(0, d - 1));
      } else {
        setDown(d => voted === "down" ? d : d + 1);
        if (voted === "up") setUp(u => Math.max(0, u - 1));
      }
      setVoted(v);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button onClick={() => vote("up")} disabled={busy}
        className={`flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg transition ${
          voted === "up" ? "bg-green-50 text-green-600" : "bg-gray-50 text-gray-500 hover:bg-green-50 hover:text-green-600"
        }`}>
        👍 <span>{up}</span>
      </button>
      <button onClick={() => vote("down")} disabled={busy}
        className={`flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg transition ${
          voted === "down" ? "bg-red-50 text-red-600" : "bg-gray-50 text-gray-500 hover:bg-red-50 hover:text-red-600"
        }`}>
        👎 <span>{down}</span>
      </button>
    </div>
  );
}
