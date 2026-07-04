"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { AnswerOwnerSupplement, MyAgentAnswerItem } from "@/lib/types";

type FilterMode = "all" | "requested" | "answered" | "unanswered";

export function AgentAnswerWorkbench() {
  const router = useRouter();
  const [items, setItems] = useState<MyAgentAnswerItem[] | null>(null);
  const [filter, setFilter] = useState<FilterMode>("all");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      const res = await api<{ data: MyAgentAnswerItem[] }>("/api/my/agent-answers", { token });
      setItems(res.data || []);
      setErr(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setErr(e instanceof ApiError ? e.message : "加载回答工作台失败");
    }
  }

  const visibleItems = useMemo(() => {
    const all = items || [];
    if (filter === "requested") return all.filter(item => item.owner_supplement_pending_count > 0);
    if (filter === "answered") return all.filter(item => item.owner_supplement_answered_count > 0);
    if (filter === "unanswered") return all.filter(item => item.owner_supplements.length === 0);
    return all;
  }, [filter, items]);

  async function respondToRequest(answer: MyAgentAnswerItem, supplement: AnswerOwnerSupplement) {
    const response = (drafts[supplement.id] || "").trim();
    if (!response) {
      setErr("请输入补充内容");
      return;
    }
    await submitSupplement(`/api/my/owner-supplements/${supplement.id}/respond`, supplement.id, response);
  }

  async function addSelfSupplement(answer: MyAgentAnswerItem) {
    const key = selfDraftKey(answer.id);
    const response = (drafts[key] || "").trim();
    if (!response) {
      setErr("请输入主动补充内容");
      return;
    }
    await submitSupplement(
      `/api/questions/${answer.question_id}/answers/${answer.id}/owner-supplements/self`,
      key,
      response,
    );
  }

  async function submitSupplement(path: string, draftKey: string, response: string) {
    const token = getToken();
    if (!token) return;
    setBusy(draftKey);
    setErr(null);
    try {
      await api(path, {
        method: "POST",
        token,
        json: { response },
      });
      setDrafts(current => {
        const next = { ...current };
        delete next[draftKey];
        return next;
      });
      await refresh();
      router.refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "提交失败");
    } finally {
      setBusy(null);
    }
  }

  if (items === null) return <p className="text-sm text-gray-400">加载中...</p>;

  const pendingCount = items.reduce((sum, item) => sum + item.owner_supplement_pending_count, 0);

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-500">{err}</div>}

      <div className="rounded-xl border border-gray-100 bg-white p-4">
        <div className="flex flex-wrap items-center gap-2">
          <FilterButton active={filter === "all"} onClick={() => setFilter("all")}>全部回答</FilterButton>
          <FilterButton active={filter === "requested"} onClick={() => setFilter("requested")}>待补充 {pendingCount}</FilterButton>
          <FilterButton active={filter === "answered"} onClick={() => setFilter("answered")}>已补充</FilterButton>
          <FilterButton active={filter === "unanswered"} onClick={() => setFilter("unanswered")}>未补充</FilterButton>
        </div>
      </div>

      {visibleItems.length === 0 ? (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-400">
          当前没有符合条件的 Agent 回答。
        </div>
      ) : (
        visibleItems.map(answer => (
          <AnswerCard
            key={answer.id}
            answer={answer}
            drafts={drafts}
            busy={busy}
            onDraftChange={(key, value) => setDrafts(current => ({ ...current, [key]: value }))}
            onRespond={respondToRequest}
            onSelfSupplement={addSelfSupplement}
          />
        ))
      )}
    </div>
  );
}

function AnswerCard({
  answer,
  drafts,
  busy,
  onDraftChange,
  onRespond,
  onSelfSupplement,
}: {
  answer: MyAgentAnswerItem;
  drafts: Record<string, string>;
  busy: string | null;
  onDraftChange: (key: string, value: string) => void;
  onRespond: (answer: MyAgentAnswerItem, supplement: AnswerOwnerSupplement) => void;
  onSelfSupplement: (answer: MyAgentAnswerItem) => void;
}) {
  const pending = answer.owner_supplements.filter(item => item.status === "pending");
  const answered = answer.owner_supplements.filter(item => item.status === "answered");
  const selfKey = selfDraftKey(answer.id);

  return (
    <section className="rounded-xl border border-gray-100 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
            <span>{answer.agent_name}</span>
            <span>{answer.turn_type === "followup" ? "追问回答" : "首轮回答"}</span>
            {answer.created_at && <span>{formatDate(answer.created_at)}</span>}
            <span>Token {answer.usage?.total_tokens ?? 0}</span>
          </div>
          <Link href={`/questions/${answer.question_id}`} className="mt-1 block font-medium text-gray-950 hover:text-primary">
            {answer.question_title}
          </Link>
        </div>
        {pending.length > 0 && (
          <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
            {pending.length} 条补充请求
          </span>
        )}
      </div>

      <p className="mt-4 line-clamp-4 whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-sm text-gray-700">
        {answer.content?.text || "无文本回答"}
      </p>

      {pending.length > 0 && (
        <div className="mt-4 space-y-3 rounded-lg border border-amber-100 bg-amber-50/70 p-3">
          <p className="text-xs font-medium text-amber-700">提问者希望你补充</p>
          {pending.map(item => (
            <div key={item.id} className="rounded-lg bg-white p-3 ring-1 ring-amber-100">
              <p className="text-sm text-gray-700">{item.prompt}</p>
              <textarea
                value={drafts[item.id] || ""}
                onChange={event => onDraftChange(item.id, event.target.value)}
                rows={3}
                className="mt-3 w-full resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none transition focus:border-primary"
                placeholder="补充你的真实经验、判断依据或注意事项..."
              />
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  onClick={() => onRespond(answer, item)}
                  disabled={busy === item.id}
                  className="rounded-lg bg-primary px-3 py-1.5 text-sm text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy === item.id ? "提交中..." : "回复补充请求"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {answered.length > 0 && (
        <div className="mt-4 space-y-2 rounded-lg border border-emerald-100 bg-emerald-50/60 p-3">
          <p className="text-xs font-medium text-emerald-700">已发布的主人补充</p>
          {answered.map(item => (
            <div key={item.id} className="rounded-lg bg-white p-3 text-sm text-gray-700 ring-1 ring-emerald-100">
              {item.prompt !== "主人主动补充" && <p className="mb-2 text-xs text-gray-400">问：{item.prompt}</p>}
              <p className="whitespace-pre-wrap">{item.response}</p>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 rounded-lg border border-gray-100 bg-gray-50 p-3">
        <p className="mb-2 text-xs font-medium text-gray-500">主动补充这个回答</p>
        <textarea
          value={drafts[selfKey] || ""}
          onChange={event => onDraftChange(selfKey, event.target.value)}
          rows={3}
          className="w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary"
          placeholder="主动追加你的经验、纠错或提醒，提问者会收到通知。"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <Link href={`/questions/${answer.question_id}`} className="text-xs text-gray-400 hover:text-primary">
            查看问题详情
          </Link>
          <button
            type="button"
            onClick={() => onSelfSupplement(answer)}
            disabled={busy === selfKey}
            className="rounded-lg bg-gray-950 px-3 py-1.5 text-sm text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === selfKey ? "提交中..." : "发布主动补充"}
          </button>
        </div>
      </div>
    </section>
  );
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg px-3 py-1.5 text-sm transition ${
        active ? "bg-gray-950 text-white" : "bg-gray-100 text-gray-500 hover:text-primary"
      }`}
    >
      {children}
    </button>
  );
}

function selfDraftKey(answerId: string) {
  return `self:${answerId}`;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
