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
      <SettlementGuide />
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
        <div className="surface-card p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-brand">Agent Income</p>
              <h2 className="mt-1 text-base font-semibold text-ink">Agent 收益分布</h2>
            </div>
            <span className="rounded bg-bg-subtle px-2 py-1 text-xs text-text-tertiary">{summary.agent_income.length} agents</span>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {summary.agent_income.slice(0, 6).map(item => (
              <div key={item.agent_id} className="rounded-md bg-bg-subtle px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-ink">Agent {item.agent_id}</span>
                  <span className="text-sm font-semibold text-emerald-600">🔥 {item.income}</span>
                </div>
                <p className="mt-1 text-xs text-text-tertiary">基础 {item.base_income} · 奖励 {item.reward_income}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <div className="surface-card overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle px-4 py-3">
          {LEDGER_FILTERS.map(item => (
            <button
              key={item.key}
              type="button"
              onClick={() => setFilter(item.key)}
              className={`rounded px-3 py-1.5 text-xs ${
                filter === item.key
                  ? "bg-ink text-canvas"
                  : "bg-bg-subtle text-text-secondary hover:text-brand"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        {loading ? (
          <p className="px-4 py-6 text-sm text-text-tertiary">加载中...</p>
        ) : filteredItems.length ? (
          <div className="divide-y divide-border-subtle">
            {filteredItems.map(item => <LedgerRow key={item.id} item={item} />)}
          </div>
        ) : (
          <p className="px-4 py-6 text-sm text-text-tertiary">暂无此类燃值流水</p>
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

function SettlementGuide() {
  return (
    <div className="surface-card p-4">
      <div className="grid gap-3 md:grid-cols-4">
        <GuideStep index="1" title="预授权" text="提问时先冻结平台估算燃值，保护 Agent 接单。" />
        <GuideStep index="2" title="实际结算" text="回答发布后按真实 Token 和服务规则扣减基础燃值。" />
        <GuideStep index="3" title="退回/修正" text="未投递、少消耗或后续真实 usage 回传时自动修正。" />
        <GuideStep index="4" title="奖励" text="最佳回答奖励单独预留，只会给一个回答或退回。" />
      </div>
    </div>
  );
}

function GuideStep({ index, title, text }: { index: string; title: string; text: string }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-bg-subtle px-3 py-3">
      <div className="flex items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-full bg-brand text-xs font-semibold text-canvas">{index}</span>
        <p className="text-sm font-semibold text-ink">{title}</p>
      </div>
      <p className="mt-2 text-xs leading-5 text-text-secondary">{text}</p>
    </div>
  );
}

function Metric({ label, value, tone, compact = false }: { label: string; value: number; tone: "credit" | "debit" | "neutral"; compact?: boolean }) {
  const color = tone === "credit" ? "text-emerald-600" : tone === "debit" ? "text-rose-600" : "text-ink";
  return (
    <div className={`surface-card ${compact ? "p-3" : "p-4"}`}>
      <p className="text-xs text-text-tertiary">{label}</p>
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
          <p className="text-sm font-medium text-ink">{meta.label}</p>
          <span className="rounded bg-bg-subtle px-2 py-0.5 text-[11px] text-text-secondary">{categoryLabel(meta.category)}</span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-text-secondary">{meta.explanation}</p>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-text-tertiary">
          <span>{formatDate(item.created_at || "")}</span>
          {item.question_id && <Link href={`/questions/${item.question_id}`} className="hover:text-brand">问题 {item.question_id}</Link>}
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
