"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { AnswerMarkdown } from "@/components/answer/AnswerMarkdown";

interface ReviewItem {
  request_id: string;
  answer_id: string;
  question: { title: string; body: string; tags: string[] };
  asker: { nickname: string; trust_level: number };
  content: { text: string };
  model: string;
  usage: { total_tokens: number };
  created_at: string;
  deadline_at: string | null;
}

export function ReviewQueue({ agentId }: { agentId: string }) {
  const router = useRouter();
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const t = getToken();
    if (!t) { router.push("/login"); return; }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      const r = await api<{ data: ReviewItem[] }>(`/api/my/agents/${agentId}/review-queue`, { token });
      setItems(r.data);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
    }
  }

  async function act(request_id: string, kind: "approve" | "reject") {
    const token = getToken();
    if (!token) return;
    setBusy(request_id);
    try {
      await api(`/api/my/agents/${agentId}/review-queue/${request_id}/${kind}`, { method: "POST", token });
      await refresh();
    } finally {
      setBusy(null);
    }
  }

  if (items === null) return <p className="text-gray-400 text-sm">加载中…</p>;
  if (items.length === 0) {
    return <p className="text-gray-400 text-sm">审核队列为空 — 当前没有待审核的回答。</p>;
  }

  return (
    <div className="space-y-4">
      {items.map(it => (
        <div key={it.request_id} className="bg-white rounded-2xl border border-gray-100 p-6">
          <div className="mb-3">
            <div className="text-xs text-gray-400">来自 {it.asker.nickname}（TL{it.asker.trust_level}）· {new Date(it.created_at).toLocaleString()}</div>
            <h3 className="font-semibold mt-1">Q: {it.question.title}</h3>
            {it.question.body && <p className="text-sm text-gray-600 mt-1 whitespace-pre-wrap">{it.question.body}</p>}
            <div className="flex flex-wrap gap-1 mt-2">
              {it.question.tags?.map(t => (
                <span key={t} className="px-2 py-0.5 rounded bg-gray-100 text-gray-500 text-xs">#{t}</span>
              ))}
            </div>
          </div>
          <div className="border-t border-gray-100 pt-4">
            <AnswerMarkdown text={it.content.text || ""} />
          </div>
          <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between">
            <span className="text-xs text-gray-400">{it.model} · {it.usage.total_tokens} tokens</span>
            <div className="flex gap-2">
              <button onClick={() => act(it.request_id, "reject")} disabled={busy === it.request_id}
                className="px-4 py-1.5 rounded-lg bg-gray-100 text-gray-600 text-sm hover:bg-red-50 hover:text-red-500">
                拒绝
              </button>
              <button onClick={() => act(it.request_id, "approve")} disabled={busy === it.request_id}
                className="px-4 py-1.5 rounded-lg bg-primary text-white text-sm hover:bg-primary-dark">
                通过发布
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
