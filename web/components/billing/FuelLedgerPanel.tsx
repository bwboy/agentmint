"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { ApiList, FuelLedgerEntry } from "@/lib/types";

export function FuelLedgerPanel() {
  const router = useRouter();
  const [items, setItems] = useState<FuelLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    api<ApiList<FuelLedgerEntry>>("/api/auth/my/fuel-ledger?size=80", { token })
      .then(res => {
        setItems(res.data || []);
        setTotal(res.pagination?.total || 0);
        setErr(null);
      })
      .catch((e: any) => {
        if (e instanceof ApiError && e.status === 401) router.push("/login");
        else setErr(e.message || "加载燃值流水失败");
      })
      .finally(() => setLoading(false));
  }, [router]);

  const income = items.filter(item => item.direction === "credit").reduce((sum, item) => sum + Number(item.amount || 0), 0);
  const expense = items.filter(item => item.direction === "debit").reduce((sum, item) => sum + Number(item.amount || 0), 0);

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-500">{err}</div>}
      <div className="grid gap-3 md:grid-cols-3">
        <Metric label="近期收入" value={income} tone="credit" />
        <Metric label="近期支出" value={expense} tone="debit" />
        <Metric label="流水数量" value={total} tone="neutral" />
      </div>
      <div className="rounded-lg border border-gray-100 bg-white shadow-sm">
        {loading ? (
          <p className="px-4 py-6 text-sm text-gray-400">加载中...</p>
        ) : items.length ? (
          <div className="divide-y divide-gray-100">
            {items.map(item => <LedgerRow key={item.id} item={item} />)}
          </div>
        ) : (
          <p className="px-4 py-6 text-sm text-gray-400">暂无燃值流水</p>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: "credit" | "debit" | "neutral" }) {
  const color = tone === "credit" ? "text-emerald-600" : tone === "debit" ? "text-rose-600" : "text-gray-950";
  return (
    <div className="rounded-lg border border-gray-100 bg-white p-4 shadow-sm">
      <p className="text-xs text-gray-400">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${color}`}>{value}</p>
    </div>
  );
}

function LedgerRow({ item }: { item: FuelLedgerEntry }) {
  const isCredit = item.direction === "credit";
  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3">
      <div className={`flex h-9 w-9 items-center justify-center rounded-lg text-sm font-semibold ${isCredit ? "bg-emerald-50 text-emerald-600" : "bg-rose-50 text-rose-600"}`}>
        {isCredit ? "+" : "-"}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-950">{eventLabel(item.event_type)}</p>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-400">
          <span>{formatDate(item.created_at || "")}</span>
          {item.question_id && <Link href={`/questions/${item.question_id}`} className="hover:text-primary">问题 {item.question_id}</Link>}
          {item.agent_id && <span>Agent {item.agent_id}</span>}
        </div>
      </div>
      <span className={`text-sm font-semibold ${isCredit ? "text-emerald-600" : "text-rose-600"}`}>
        {isCredit ? "+" : "-"}{item.amount}
      </span>
    </div>
  );
}

function eventLabel(type: string) {
  const labels: Record<string, string> = {
    question_reserved: "问题预留支出",
    question_refunded: "未投递退款",
    answer_earned: "回答收入",
    base_reserved: "基础回答预留",
    base_settled: "基础回答结算",
    base_refunded: "基础预留退回",
    answer_base_earned: "基础回答收入",
    reward_reserved: "最佳回答奖励预留",
    reward_awarded: "最佳回答奖励收入",
    reward_auto_awarded: "系统分配奖励收入",
    reward_refunded: "奖励退回",
    usage_correction: "Token 用量修正",
  };
  return labels[type] || type;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
