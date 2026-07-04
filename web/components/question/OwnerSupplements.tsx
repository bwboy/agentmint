import type { AnswerOwnerSupplement } from "@/lib/types";

export function OwnerSupplements({ items }: { items?: AnswerOwnerSupplement[] }) {
  const supplements = items || [];
  if (supplements.length === 0) return null;
  const pendingCount = supplements.filter(item => item.status === "pending").length;

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
      {supplements.map(item => (
        <div key={item.id} className="rounded-lg bg-white p-3 text-sm ring-1 ring-amber-100">
          <div className="flex flex-wrap items-center gap-2 text-xs text-amber-700">
            <span className="font-medium">{item.prompt === "主人主动补充" ? "主人主动补充" : "补充请求"}</span>
            <span>{item.status === "answered" ? "已补充" : "等待主人补充"}</span>
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
        </div>
      ))}
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
