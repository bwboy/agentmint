"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { ApiList, FuelLedgerEntry, FuelSummary } from "@/lib/types";
import { ledgerCategory, ledgerEventMeta, type LedgerFilter } from "@/components/billing/FuelLedgerPanel.logic";

export function FuelLedgerPanel() {
  const router = useRouter();
  const [items, setItems] = useState<FuelLedgerEntry[]>([]);
  const [filter, setFilter] = useState<LedgerFilter>("all");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<FuelSummary | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    Promise.all([
      api<ApiList<FuelLedgerEntry>>("/api/auth/my/fuel-ledger?size=80", { token }),
      api<FuelSummary>("/api/auth/my/fuel-summary", { token }).catch(() => null),
    ])
      .then(([res, fuelSummary]) => {
        setItems(res.data || []);
        setTotal(res.pagination?.total || 0);
        setSummary(fuelSummary);
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
  const totals = summary?.totals;

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-500">{err}</div>}
      <div className="grid gap-3 md:grid-cols-3">
        <Metric label="累计收入" value={totals?.income ?? income} tone="credit" />
        <Metric label="累计支出" value={totals?.spend ?? expense} tone="debit" />
        <Metric label="净变化" value={totals?.net ?? income - expense + refund} tone="neutral" />
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <Metric label="预授权" value={reserve} tone="debit" compact />
        <Metric label="基础收入" value={totals?.base_income ?? settlement} tone="credit" compact />
        <Metric label="退款" value={totals?.refund ?? refund} tone="credit" compact />
        <Metric label="奖励收入" value={totals?.reward_income ?? reward} tone="credit" compact />
      </div>
      {summary?.agent_income?.length ? (
        <div className="rounded-lg border border-gray-100 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Agent Income</p>
              <h2 className="mt-1 text-base font-semibold text-gray-950">Agent 收益分布</h2>
            </div>
            <span className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-500">{summary.agent_income.length} agents</span>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {summary.agent_income.slice(0, 6).map(item => (
              <div key={item.agent_id} className="rounded-md bg-gray-50 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-gray-800">Agent {item.agent_id}</span>
                  <span className="text-sm font-semibold text-emerald-600">🔥 {item.income}</span>
                </div>
                <p className="mt-1 text-xs text-gray-400">基础 {item.base_income} · 奖励 {item.reward_income}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
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
  const meta = ledgerEventMeta(item.event_type);
  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3">
      <div className={`flex h-9 w-9 items-center justify-center rounded-lg text-sm font-semibold ${isCredit ? "bg-emerald-50 text-emerald-600" : "bg-rose-50 text-rose-600"}`}>
        {isCredit ? "+" : "-"}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-gray-950">{meta.label}</p>
          <span className="rounded bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500">{categoryLabel(meta.category)}</span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-gray-500">{meta.explanation}</p>
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

function categoryLabel(category: LedgerFilter) {
  const labels: Record<LedgerFilter, string> = {
    all: "全部",
    reserve: "预授权",
    settlement: "结算",
    refund: "退款",
    reward: "奖励",
    correction: "修正",
    other: "其他",
  };
  return labels[category] || category;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
