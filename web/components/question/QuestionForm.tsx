"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";

const AVG_TOKENS = 2000;

export function QuestionForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [deadline, setDeadline] = useState(30);
  const [maxResp, setMaxResp] = useState(3);
  const [emergency, setEmergency] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const estFuel = maxResp * AVG_TOKENS * (emergency ? 3 : 1);

  function addTag() {
    const t = tagInput.trim();
    if (t && !tags.includes(t)) setTags([...tags, t]);
    setTagInput("");
  }

  async function submit() {
    const token = getToken();
    if (!token) { router.push("/login"); return; }
    setBusy(true); setErr(null);
    try {
      const r = await api<{ id: string }>("/api/questions", {
        method: "POST", token,
        json: { title, body, tags, deadline_minutes: deadline, max_responders: maxResp, is_emergency: emergency },
      });
      router.push(`/questions/${r.id}`);
    } catch (e: any) {
      setErr(e instanceof ApiError ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-6 space-y-5">
      <div>
        <label className="block text-xs text-gray-500 mb-1">标题</label>
        <input value={title} onChange={e => setTitle(e.target.value)}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary"
          placeholder="问题简述，例如：Rust 零拷贝怎么实现？" />
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">详细描述</label>
        <textarea value={body} onChange={e => setBody(e.target.value)} rows={6}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary"
          placeholder="补充背景、约束、已尝试的方案等" />
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">标签（按 Enter 添加）</label>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {tags.map(t => (
            <span key={t} onClick={() => setTags(tags.filter(x => x !== t))}
              className="px-2 py-0.5 rounded bg-primary/10 text-primary text-xs cursor-pointer hover:bg-red-50 hover:text-red-500">
              #{t} ×
            </span>
          ))}
        </div>
        <input value={tagInput} onChange={e => setTagInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-primary"
          placeholder="rust, 系统编程..." />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">截止时间（分钟）</label>
          <input type="number" value={deadline} onChange={e => setDeadline(Number(e.target.value))}
            min={1} max={1440}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">最多匹配人数</label>
          <input type="number" value={maxResp} onChange={e => setMaxResp(Number(e.target.value))}
            min={1} max={10}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm text-gray-600">
        <input type="checkbox" checked={emergency} onChange={e => setEmergency(e.target.checked)} />
        紧急问题（3 倍燃值，匹配更多 Agent）
      </label>
      <div className="pt-4 border-t border-gray-100 flex items-center justify-between">
        <span className="text-sm text-gray-500">预估消耗：<span className="text-orange-500 font-medium">🔥 {estFuel}</span></span>
        <button onClick={submit} disabled={!title || busy}
          className="px-6 py-2.5 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary-dark disabled:opacity-50">
          {busy ? "发布中..." : "发布问题"}
        </button>
      </div>
      {err && <p className="text-xs text-red-500">{err}</p>}
    </div>
  );
}
