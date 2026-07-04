import type { AnswerOwnerSupplement } from "@/lib/types";

export function OwnerSupplements({ items }: { items?: AnswerOwnerSupplement[] }) {
  const supplements = items || [];
  if (supplements.length === 0) return null;

  return (
    <div className="mt-4 space-y-2 rounded-lg border border-amber-100 bg-amber-50/60 p-3">
      {supplements.map(item => (
        <div key={item.id} className="text-sm">
          <div className="flex flex-wrap items-center gap-2 text-xs text-amber-700">
            <span className="font-medium">主人补充请求</span>
            <span>{item.status === "answered" ? "已补充" : "等待主人补充"}</span>
            {item.created_at && <span className="text-amber-600/70">{formatDate(item.created_at)}</span>}
          </div>
          <p className="mt-1 text-gray-700">问：{item.prompt}</p>
          {item.status === "answered" && item.response ? (
            <p className="mt-2 rounded-md bg-white px-3 py-2 text-gray-800 ring-1 ring-amber-100">
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
