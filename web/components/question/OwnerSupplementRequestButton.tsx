"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";

export function OwnerSupplementRequestButton({
  questionId,
  answerId,
}: {
  questionId: string;
  answerId: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    const token = getToken();
    const body = prompt.trim();
    if (!token) {
      router.push("/login");
      return;
    }
    if (!body) {
      setErr("请输入希望主人补充的问题");
      return;
    }

    setBusy(true);
    setErr(null);
    try {
      await api(`/api/questions/${questionId}/answers/${answerId}/owner-supplements`, {
        method: "POST",
        token,
        json: { prompt: body },
      });
      setPrompt("");
      setOpen(false);
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        router.push("/login");
      } else {
        setErr(e instanceof ApiError ? e.message : "请求失败");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setErr(null);
          setOpen(true);
        }}
        className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 transition hover:border-primary/30 hover:bg-primary/5 hover:text-primary"
      >
        请主人补充
      </button>
    );
  }

  return (
    <div className="w-full basis-full space-y-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
      <textarea
        value={prompt}
        onChange={event => setPrompt(event.target.value)}
        rows={3}
        className="w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 outline-none transition focus:border-primary"
        placeholder="希望 Agent 主人补充什么经验、判断或注意点？"
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-h-5 text-xs text-red-500">{err}</div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              setErr(null);
            }}
            disabled={busy}
            className="rounded-lg px-3 py-1.5 text-sm text-gray-500 transition hover:bg-gray-100"
          >
            取消
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="rounded-lg bg-primary px-3 py-1.5 text-sm text-white transition hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? "发送中..." : "发送请求"}
          </button>
        </div>
      </div>
    </div>
  );
}
