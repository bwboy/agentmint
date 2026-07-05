"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Agent, QuestionVisibility } from "@/lib/types";

const DEFAULT_ESTIMATED_FUEL_PER_ANSWER = 900;
const DEFAULT_BASE_CAP_MULTIPLIER = 1.5;

type FuelEstimate = {
  estimated_fuel_per_answer: number;
  base_cap_multiplier: number;
  preauthorized_fuel_per_answer: number;
  sample_window_days: number;
};

export function QuestionForm({ targetAgent }: { targetAgent?: Agent | null }) {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [deadline, setDeadline] = useState(30);
  const [maxResp, setMaxResp] = useState(3);
  const [emergency, setEmergency] = useState(false);
  const [visibility, setVisibility] = useState<QuestionVisibility>(targetAgent ? "private" : "public");
  const [fuelEstimate, setFuelEstimate] = useState<FuelEstimate | null>(null);
  const [rewardFuel, setRewardFuel] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const targetAgentIds = targetAgent ? [targetAgent.id] : [];
  const responderCount = targetAgent ? 1 : maxResp;
  const safeReward = Math.max(0, Number(rewardFuel || 0));
  const basePlatformEstimate = Math.max(100, Number(fuelEstimate?.estimated_fuel_per_answer || DEFAULT_ESTIMATED_FUEL_PER_ANSWER));
  const baseMultiplier = Number(fuelEstimate?.base_cap_multiplier || DEFAULT_BASE_CAP_MULTIPLIER);
  const platformEstimate = basePlatformEstimate * (emergency ? 3 : 1);
  const preauthPerAnswer = Math.round(platformEstimate * baseMultiplier);
  const baseReserve = responderCount * preauthPerAnswer;
  const expectedBaseSpend = responderCount * platformEstimate;
  const estFuel = baseReserve + safeReward;
  const previewCapabilities = inferCapabilityPreview(`${title} ${body} ${tags.join(" ")}`);

  useEffect(() => {
    let alive = true;
    api<FuelEstimate>("/api/questions/fuel-estimate")
      .then(data => {
        if (alive) setFuelEstimate(data);
      })
      .catch(() => {
        if (alive) setFuelEstimate(null);
      });
    return () => { alive = false; };
  }, []);

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
        json: {
          title,
          body,
          tags,
          deadline_minutes: deadline,
          max_responders: responderCount,
          is_emergency: emergency,
          agent_ids: targetAgentIds,
          visibility,
          reward_fuel: safeReward,
        },
      });
      router.push(`/questions/${r.id}`);
    } catch (e: any) {
      setErr(e instanceof ApiError ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
      <div className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Task Command</span>
          <span className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-500">
            {targetAgent ? "定向提问" : maxResp > 1 ? "选角透明" : "智能路由"}
          </span>
        </div>
      <div>
          <label className="mb-1 block text-xs text-gray-500">任务一句话</label>
        <input value={title} onChange={e => setTitle(e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-3 py-3 text-base focus:border-primary focus:outline-none"
            placeholder="例如：帮我设计 AI Agent 平台的提问和匹配逻辑" />
      </div>
        <div className="mt-4">
          <label className="mb-1 block text-xs text-gray-500">补充上下文</label>
        <textarea value={body} onChange={e => setBody(e.target.value)} rows={6}
            className="w-full rounded-lg border border-gray-200 px-3 py-3 text-sm focus:border-primary focus:outline-none"
            placeholder="补充背景、约束、希望输出格式、已经尝试过的方案等" />
        </div>
      </div>

      <div className="space-y-4">
        {targetAgent && (
          <section className="rounded-lg border border-primary/20 bg-primary/5 p-5 shadow-sm">
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Direct Agent</p>
            <div className="mt-3 flex items-start gap-3">
              <span className="text-3xl">{targetAgent.agent_type === "openclaw" ? "🦞" : "👜"}</span>
              <div className="min-w-0">
                <h2 className="truncate text-base font-semibold text-gray-950">{targetAgent.name}</h2>
                <p className="mt-1 text-xs text-gray-500">by {targetAgent.owner.nickname}</p>
                <p className="mt-2 text-xs text-gray-500">本次问题只会发给这个 Agent，默认私密，可切换公开。</p>
              </div>
            </div>
            <div className="mt-4 grid gap-2 text-xs text-gray-500 sm:grid-cols-2">
              <span className="rounded-md bg-white/70 px-2 py-1">价格倍率 {targetAgent.service_rules.price_multiplier}x</span>
              <span className="rounded-md bg-white/70 px-2 py-1">追问 {targetAgent.service_rules.max_followup_depth} 层</span>
              <span className="rounded-md bg-white/70 px-2 py-1">单用户 {targetAgent.service_rules.max_questions_per_user_per_day}/日</span>
              <span className="rounded-md bg-white/70 px-2 py-1">每日燃值 🔥 {targetAgent.service_rules.max_fuel_per_day}</span>
            </div>
          </section>
        )}
        <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Routing Signals</p>
          <h2 className="mt-1 text-base font-semibold text-gray-950">匹配信号</h2>
          <div className="mt-4">
            <label className="mb-1 block text-xs text-gray-500">领域标签（按 Enter 添加）</label>
            <div className="mb-2 flex flex-wrap gap-1.5">
          {tags.map(t => (
            <span key={t} onClick={() => setTags(tags.filter(x => x !== t))}
                    className="cursor-pointer rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary hover:bg-red-50 hover:text-red-500">
              #{t} ×
            </span>
          ))}
        </div>
        <input value={tagInput} onChange={e => setTagInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addTag(); } }}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
                placeholder="AI, 产品设计, 系统架构..." />
          </div>
          <div className="mt-4">
            <p className="mb-2 text-xs text-gray-500">系统预判能力</p>
            <div className="flex flex-wrap gap-2">
              {previewCapabilities.map(capability => (
                <span key={capability} className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600">
                  {capability}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Controls</p>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-xs text-gray-500">截止时间（分钟）</label>
              <input type="number" value={deadline} onChange={e => setDeadline(Number(e.target.value))}
                min={1} max={1440}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">回答阵容</label>
              <input type="number" value={maxResp} onChange={e => setMaxResp(Number(e.target.value))}
                min={1} max={10}
                disabled={!!targetAgent}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
            </div>
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm text-gray-600">
            <input type="checkbox" checked={emergency} onChange={e => setEmergency(e.target.checked)} />
            紧急调度（3 倍燃值，优先推送）
          </label>
          <div className="mt-4 grid grid-cols-2 gap-2 rounded-lg bg-gray-50 p-1">
            {(["public", "private"] as const).map(mode => (
              <button
                key={mode}
                type="button"
                onClick={() => setVisibility(mode)}
                className={`rounded-md px-3 py-2 text-sm transition ${
                  visibility === mode
                    ? "bg-white text-primary shadow-sm"
                    : "text-gray-500 hover:text-gray-800"
                }`}
              >
                {mode === "public" ? "公开问题" : "私密问题"}
              </button>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
              <p className="text-xs text-gray-500">平台单答基准</p>
              <p className="mt-1 text-sm font-semibold text-gray-950">🔥 {platformEstimate}</p>
              <p className="mt-1 text-[11px] text-gray-400">近 {fuelEstimate?.sample_window_days || 2} 天均值 · 预授权 {baseMultiplier}x：🔥 {preauthPerAnswer}</p>
            </div>
            <div>
              <label className="mb-1 block text-xs text-gray-500">最佳回答奖励</label>
              <input
                type="number"
                value={rewardFuel}
                onChange={e => setRewardFuel(Number(e.target.value))}
                min={0}
                max={1000000}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="mt-4 border-t border-gray-100 pt-4">
            <div className="mb-3 space-y-2 text-sm">
              <div className="flex items-center justify-between text-gray-500">
                <span>基础预授权</span>
                <span>🔥 {baseReserve}</span>
              </div>
              <div className="flex items-center justify-between text-gray-400">
                <span>预计基础结算</span>
                <span>约 🔥 {expectedBaseSpend}</span>
              </div>
              <div className="flex items-center justify-between text-gray-500">
                <span>单一奖励</span>
                <span>🔥 {safeReward}</span>
              </div>
              <div className="flex items-center justify-between border-t border-gray-100 pt-2">
                <span className="text-gray-500">本次预留</span>
                <span className="font-medium text-orange-500">🔥 {estFuel}</span>
              </div>
            </div>
            <button onClick={submit} disabled={!title || busy}
              className="w-full rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-dark disabled:opacity-50">
              {busy ? "调度中..." : targetAgent ? "发布并定向提问" : "发布并匹配 Agent"}
            </button>
          </div>
          {err && <p className="mt-3 text-xs text-red-500">{err}</p>}
        </section>
      </div>
    </div>
  );
}

function inferCapabilityPreview(text: string) {
  const normalized = text.toLowerCase();
  const capabilities = [
    ["方案设计", ["方案", "设计", "规划", "策略", "产品"]],
    ["系统架构", ["架构", "系统", "数据库", "接口", "后端"]],
    ["代码实现", ["代码", "实现", "开发", "bug", "报错"]],
    ["风险审查", ["风险", "审查", "检查", "合规", "安全"]],
    ["调研分析", ["调研", "比较", "趋势", "竞品"]],
  ] as const;

  const matched = capabilities
    .filter(([, keywords]) => keywords.some(keyword => normalized.includes(keyword)))
    .map(([capability]) => capability);

  return matched.length ? matched : ["通用问答"];
}
