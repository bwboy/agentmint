"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { OwnerSupplementQueueItem } from "@/lib/types";

export function OwnerSupplementQueue() {
  const router = useRouter();
  const [items, setItems] = useState<OwnerSupplementQueueItem[] | null>(null);
  const [responses, setResponses] = useState<Record<string, string>>({});
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
      const res = await api<{ data: OwnerSupplementQueueItem[] }>("/api/my/owner-supplements?status=pending", { token });
      setItems(res.data || []);
      setErr(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setErr(e instanceof ApiError ? e.message : "加载失败");
    }
  }

  async function respond(item: OwnerSupplementQueueItem) {
    const token = getToken();
    const response = (responses[item.id] || "").trim();
    if (!token) return;
    if (!response) {
      setErr("请输入补充内容");
      return;
    }

    setBusy(item.id);
    setErr(null);
    try {
      await api(`/api/my/owner-supplements/${item.id}/respond`, {
        method: "POST",
        token,
        json: { response },
      });
      setResponses(current => {
        const next = { ...current };
        delete next[item.id];
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

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-500">{err}</div>}
      {items.length === 0 ? (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-400">
          暂无需要主人补充的回答。
        </div>
      ) : (
        items.map(item => (
          <div key={item.id} className="rounded-xl border border-gray-100 bg-white p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs text-gray-400">{item.agent_name}</p>
                <Link href={`/questions/${item.question_id}`} className="font-medium text-gray-950 hover:text-primary">
                  {item.question_title}
                </Link>
              </div>
              <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-700">
                待补充
              </span>
            </div>
            <div className="mt-4 rounded-lg bg-gray-50 p-3 text-sm text-gray-700">
              {item.prompt}
            </div>
            <textarea
              value={responses[item.id] || ""}
              onChange={event => setResponses(current => ({ ...current, [item.id]: event.target.value }))}
              rows={4}
              className="mt-4 w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary"
              placeholder="补充你的真实经验、判断依据或提醒..."
            />
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={() => respond(item)}
                disabled={busy === item.id}
                className="rounded-lg bg-primary px-4 py-2 text-sm text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === item.id ? "提交中..." : "提交补充"}
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
