import type { OwnerSupplementSummary, OwnerSupplementType } from "@/lib/types";

export function OwnerSupplementSignal({
  summary,
  compact = false,
}: {
  summary?: OwnerSupplementSummary;
  compact?: boolean;
}) {
  if (!summary?.total) return null;
  const entries = (["correction", "version_update", "risk_note", "experience"] as OwnerSupplementType[])
    .map(type => ({ type, count: summary.types?.[type] || 0 }))
    .filter(item => item.count > 0);

  return (
    <div className={compact ? "flex flex-wrap items-center gap-1.5 text-xs" : "rounded-xl border border-amber-100 bg-amber-50 p-4"}>
      <span className={compact ? "font-medium text-amber-700" : "text-sm font-semibold text-amber-900"}>
        主人经验 {summary.total}
      </span>
      <div className={compact ? "flex flex-wrap gap-1" : "mt-2 flex flex-wrap gap-1.5"}>
        {entries.map(item => (
          <span key={item.type} className="rounded bg-white px-2 py-0.5 text-xs text-amber-700 ring-1 ring-amber-100">
            {supplementTypeLabel(item.type)} {item.count}
          </span>
        ))}
      </div>
    </div>
  );
}

function supplementTypeLabel(value: OwnerSupplementType) {
  return {
    experience: "经验",
    correction: "纠错",
    version_update: "版本",
    risk_note: "风险",
  }[value] || "经验";
}
