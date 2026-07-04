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
  const [filter, setFilter] = useState<LedgerFilter>("all");
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
  const filteredItems = items.filter(item => ledgerCategory(item.event_type) === filter || filter === "all");
  const reserve = items.filter(item => ledgerCategory(item.event_type) === "reserve").reduce((sum, item) => sum + Number(item.amount || 0), 0);
  const settlement = items.filter(item => ledgerCategory(item.event_type) === "settlement").reduce((sum, item) => sum + Number(item.amount || 0), 0);
  const refund = items.filter(item => ledgerCategory(item.event_type) === "refund").reduce((sum, item) => sum + Number(item.amount || 0), 0);
  const reward = items.filter(item => ledgerCategory(item.event_type) === "reward").reduce((sum, item) => sum + Number(item.amount || 0), 0);

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-500">{err}</div>}
      <div className="grid gap-3 md:grid-cols-3">
        <Metric label="近期收入" value={income} tone="credit" />
        <Metric label="近期支出" value={expense} tone="debit" />
        <Metric label="流水数量" value={total} tone="neutral" />
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <Metric label="预授权" value={reserve} tone="debit" compact />
        <Metric label="基础结算" value={settlement} tone="credit" compact />
        <Metric label="退款" value={refund} tone="credit" compact />
        <Metric label="奖励" value={reward} tone="credit" compact />
      </div>
      <div className="rounded-lg border border-gray-100 bg-white shadow-sm">
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-100 px-4 py-3">
          {LEDGER_FILTERS.map(item => (
            <button
              key={item.key}
              type="button"
              onClick={() => setFilter(item.key)}
              className={`rounded px-3 py-1.5 text-xs ${
                filter === item.key
                  ? "bg-gray-950 text-white"
                  : "bg-gray-100 text-gray-500 hover:text-primary"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        {loading ? (
          <p className="px-4 py-6 text-sm text-gray-400">加载中...</p>
        ) : filteredItems.length ? (
          <div className="divide-y divide-gray-100">
            {filteredItems.map(item => <LedgerRow key={item.id} item={item} />)}
          </div>
        ) : (
          <p className="px-4 py-6 text-sm text-gray-400">暂无此类燃值流水</p>
        )}
      </div>
    </div>
  );
}

type LedgerFilter = "all" | "reserve" | "settlement" | "refund" | "reward" | "correction" | "other";

const LEDGER_FILTERS: { key: LedgerFilter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "reserve", label: "预授权" },
  { key: "settlement", label: "结算" },
  { key: "refund", label: "退款" },
  { key: "reward", label: "奖励" },
  { key: "correction", label: "修正" },
  { key: "other", label: "其他" },
];

function Metric({ label, value, tone, compact = false }: { label: string; value: number; tone: "credit" | "debit" | "neutral"; compact?: boolean }) {
  const color = tone === "credit" ? "text-emerald-600" : tone === "debit" ? "text-rose-600" : "text-gray-950";
  return (
    <div className={`rounded-lg border border-gray-100 bg-white shadow-sm ${compact ? "p-3" : "p-4"}`}>
      <p className="text-xs text-gray-400">{label}</p>
      <p className={`mt-2 font-semibold ${color} ${compact ? "text-lg" : "text-2xl"}`}>{value}</p>
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
    base_extra_charged: "基础回答补扣",
    answer_base_earned: "基础回答收入",
    reward_reserved: "最佳回答奖励预留",
    reward_awarded: "最佳回答奖励收入",
    reward_auto_awarded: "系统分配奖励收入",
    reward_refunded: "奖励退回",
    usage_correction: "Token 用量修正",
  };
  return labels[type] || type;
}

function ledgerCategory(type: string): LedgerFilter {
  if (["base_reserved", "reward_reserved", "question_reserved"].includes(type)) return "reserve";
  if (["answer_base_earned", "base_settled", "answer_earned", "base_extra_charged"].includes(type)) return "settlement";
  if (["base_refunded", "reward_refunded", "question_refunded"].includes(type)) return "refund";
  if (["reward_awarded", "reward_auto_awarded"].includes(type)) return "reward";
  if (["usage_correction"].includes(type)) return "correction";
  return "other";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
