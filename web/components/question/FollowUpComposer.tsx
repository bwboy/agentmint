"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Answer } from "@/lib/types";

export function FollowUpComposer({
  questionId,
  quotedAnswer,
  approvedAnswers,
}: {
  questionId: string;
  quotedAnswer: Answer;
  approvedAnswers: Answer[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([quotedAnswer.agent.id]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const agents = useMemo(() => {
    const byId = new Map<string, Answer["agent"]>();
    for (const answer of approvedAnswers) {
      if (!byId.has(answer.agent.id)) byId.set(answer.agent.id, answer.agent);
    }
    if (!byId.has(quotedAnswer.agent.id)) byId.set(quotedAnswer.agent.id, quotedAnswer.agent);
    return Array.from(byId.values());
  }, [approvedAnswers, quotedAnswer.agent]);

  function toggleAgent(agentId: string) {
    setSelectedAgentIds(current => (
      current.includes(agentId)
        ? current.filter(id => id !== agentId)
        : [...current, agentId]
    ));
  }

  async function submit() {
    const token = getToken();
    const body = text.trim();

    if (!token) {
      setErr("请先登录");
      router.push("/login");
      return;
    }
    if (!body) {
      setErr("请输入追问内容");
      return;
    }
    if (selectedAgentIds.length === 0) {
      setErr("请选择至少一个 Agent");
      return;
    }

    setBusy(true);
    setErr(null);
    try {
      await api(`/api/questions/${questionId}/followups`, {
        method: "POST",
        token,
        json: {
          quoted_answer_id: quotedAnswer.id,
          agent_ids: selectedAgentIds,
          text: body,
          deadline_minutes: 30,
        },
      });
      setText("");
      setOpen(false);
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setErr("请先登录");
        router.push("/login");
      } else {
        setErr(e instanceof ApiError ? e.message : "追问失败");
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
        追问
      </button>
    );
  }

  return (
    <div className="w-full basis-full space-y-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
      <div className="flex flex-wrap gap-2">
        {agents.map(agent => {
          const selected = selectedAgentIds.includes(agent.id);
          return (
            <button
              key={agent.id}
              type="button"
              onClick={() => toggleAgent(agent.id)}
              className={`rounded-full border px-3 py-1 text-xs transition ${
                selected
                  ? "border-primary/30 bg-primary/10 text-primary"
                  : "border-gray-200 bg-white text-gray-500 hover:border-gray-300 hover:text-gray-700"
              }`}
            >
              {agent.name}
            </button>
          );
        })}
      </div>

      <textarea
        value={text}
        onChange={event => setText(event.target.value)}
        rows={3}
        className="w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 outline-none transition focus:border-primary"
        placeholder="继续追问这个回答..."
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
            {busy ? "提交中..." : "提交追问"}
          </button>
        </div>
      </div>
    </div>
  );
}
