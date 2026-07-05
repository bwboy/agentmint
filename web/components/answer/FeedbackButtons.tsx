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
  const [downOpen, setDownOpen] = useState(false);
  const [reasons, setReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");

  async function vote(v: "up" | "down", opts?: { reasons?: string[]; comment?: string }) {
    const token = getToken();
    if (!token) { router.push("/login"); return; }
    setBusy(true);
    try {
      await api(`/api/questions/${questionId}/answers/${answerId}/feedback`, {
        method: "POST", token, json: { vote: v, comment: opts?.comment || "", reasons: opts?.reasons || [] },
      });
      if (v === "up") {
        setUp(u => voted === "up" ? u : u + 1);
        if (voted === "down") setDown(d => Math.max(0, d - 1));
      } else {
        setDown(d => voted === "down" ? d : d + 1);
        if (voted === "up") setUp(u => Math.max(0, u - 1));
      }
      setVoted(v);
      if (v === "down") setDownOpen(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
    } finally {
      setBusy(false);
    }
  }

  function toggleReason(value: string) {
    setReasons(current => (
      current.includes(value)
        ? current.filter(item => item !== value)
        : [...current, value]
    ));
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <button onClick={() => vote("up")} disabled={busy}
          className={`flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg transition ${
            voted === "up" ? "bg-green-50 text-green-600" : "bg-gray-50 text-gray-500 hover:bg-green-50 hover:text-green-600"
          }`}>
          👍 <span>{up}</span>
        </button>
        <button onClick={() => setDownOpen(current => !current)} disabled={busy}
          className={`flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg transition ${
            voted === "down" ? "bg-red-50 text-red-600" : "bg-gray-50 text-gray-500 hover:bg-red-50 hover:text-red-600"
          }`}>
          👎 <span>{down}</span>
        </button>
      </div>
      {downOpen && (
        <div className="max-w-md rounded-lg border border-red-100 bg-red-50 p-3">
          <p className="text-xs font-medium text-red-700">哪里需要改进？</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {FEEDBACK_REASONS.map(reason => (
              <label key={reason.value} className="flex cursor-pointer items-center gap-1.5 rounded bg-white px-2 py-1 text-xs text-gray-600 ring-1 ring-red-100">
                <input
                  type="checkbox"
                  checked={reasons.includes(reason.value)}
                  onChange={() => toggleReason(reason.value)}
                />
                {reason.label}
              </label>
            ))}
          </div>
          <textarea
            value={comment}
            onChange={event => setComment(event.target.value)}
            rows={2}
            placeholder="补充说明，可选"
            className="mt-2 w-full resize-y rounded border border-red-100 bg-white px-2 py-1.5 text-xs outline-none focus:border-red-300"
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setDownOpen(false)}
              className="rounded bg-white px-3 py-1.5 text-xs text-gray-500"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => vote("down", { reasons, comment })}
              disabled={busy}
              className="rounded bg-red-600 px-3 py-1.5 text-xs text-white disabled:opacity-60"
            >
              提交反馈
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const FEEDBACK_REASONS = [
  { value: "stale", label: "内容过期" },
  { value: "missed_point", label: "没答到点" },
  { value: "needs_sources", label: "需要来源" },
  { value: "owner_review", label: "建议主人修正" },
];
