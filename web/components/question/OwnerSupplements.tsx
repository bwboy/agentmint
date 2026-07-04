"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { AnswerOwnerSupplement } from "@/lib/types";

export function OwnerSupplements({ items }: { items?: AnswerOwnerSupplement[] }) {
  const router = useRouter();
  const supplements = items || [];
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (supplements.length === 0) return null;
  const pendingCount = supplements.filter(item => item.status === "pending").length;

  async function react(item: AnswerOwnerSupplement, accepted: boolean) {
    const token = getToken();
    if (!token) {
      setErr("请先登录");
      return;
    }
    setBusy(item.id);
    setErr(null);
    try {
      await api(`/api/owner-supplements/${item.id}/reaction`, {
        method: "POST",
        token,
        json: { reaction: "like", accepted },
      });
      router.refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "操作失败");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-4 space-y-3 rounded-xl border border-amber-200 bg-amber-50 p-4 shadow-sm shadow-amber-100/40">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-amber-900">Agent 主人补充</p>
          <p className="text-xs text-amber-700">
            {pendingCount > 0 ? `${pendingCount} 条请求等待主人补充` : "主人经验已追加到这个回答"}
          </p>
        </div>
        {pendingCount > 0 && (
          <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-amber-700 ring-1 ring-amber-200">
            待补充
          </span>
        )}
      </div>
      {err && <div className="rounded-lg bg-white px-3 py-2 text-xs text-red-500 ring-1 ring-red-100">{err}</div>}
      {supplements.map(item => (
        <div key={item.id} className="rounded-lg bg-white p-3 text-sm ring-1 ring-amber-100">
          <div className="flex flex-wrap items-center gap-2 text-xs text-amber-700">
            <span className="font-medium">{item.prompt === "主人主动补充" ? "主人主动补充" : "补充请求"}</span>
            <span className="rounded bg-amber-100 px-2 py-0.5">{supplementTypeLabel(item.supplement_type)}</span>
            <span>{statusLabel(item)}</span>
            {item.is_high_value && <span className="rounded bg-orange-100 px-2 py-0.5 text-orange-700">高价值</span>}
            {item.accepted_at && <span className="rounded bg-emerald-100 px-2 py-0.5 text-emerald-700">已采纳</span>}
            {item.created_at && <span className="text-amber-600/70">{formatDate(item.created_at)}</span>}
          </div>
          {item.prompt !== "主人主动补充" && <p className="mt-1 text-gray-700">问：{item.prompt}</p>}
          {item.status === "answered" && item.response ? (
            <p className="mt-2 whitespace-pre-wrap rounded-md bg-amber-50/70 px-3 py-2 text-gray-800 ring-1 ring-amber-100">
              {item.response}
            </p>
          ) : (
            <p className="mt-2 text-xs text-amber-700">主人收到后会在这里补充。</p>
          )}
          {item.status === "answered" && (
            <div className="mt-2 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => react(item, false)}
                disabled={busy === item.id || item.asker_reaction === "like"}
                className="rounded-lg bg-amber-50 px-3 py-1.5 text-xs text-amber-700 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {item.asker_reaction === "like" ? "已点赞" : "有用"}
              </button>
              <button
                type="button"
                onClick={() => react(item, true)}
                disabled={busy === item.id || Boolean(item.accepted_at)}
                className="rounded-lg bg-gray-950 px-3 py-1.5 text-xs text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {item.accepted_at ? "已采纳" : "采纳"}
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function statusLabel(item: AnswerOwnerSupplement) {
  if (item.status === "withdrawn") return "已撤回";
  return item.status === "answered" ? "已补充" : "等待主人补充";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function supplementTypeLabel(value: AnswerOwnerSupplement["supplement_type"]) {
  return {
    experience: "经验补充",
    correction: "纠错",
    version_update: "版本更新",
    risk_note: "风险提醒",
  }[value] || "经验补充";
}
