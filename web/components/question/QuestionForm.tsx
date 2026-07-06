"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Agent, Attachment, QuestionVisibility } from "@/lib/types";

const DEFAULT_ESTIMATED_FUEL_PER_ANSWER = 900;
const DEFAULT_BASE_CAP_MULTIPLIER = 1.5;
const DEADLINE_PRESETS = [
  { value: 15, label: "15m" },
  { value: 30, label: "30m" },
  { value: 60, label: "1h" },
  { value: 240, label: "4h" },
  { value: 1440, label: "24h" },
];
const RESPONDER_PRESETS = [
  { value: 1, label: "1" },
  { value: 2, label: "2" },
  { value: 3, label: "3" },
  { value: 5, label: "5" },
  { value: 8, label: "8" },
  { value: 10, label: "10" },
];
const REWARD_PRESETS = [
  { value: 0, label: "无" },
  { value: 500, label: "500" },
  { value: 1000, label: "1k" },
  { value: 3000, label: "3k" },
  { value: 10000, label: "10k" },
];

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
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const targetAgentIds = targetAgent ? [targetAgent.id] : [];
  const safeDeadline = clampInt(deadline, 1, 1440);
  const responderCount = targetAgent ? 1 : clampInt(maxResp, 1, 10);
  const safeReward = clampInt(rewardFuel, 0, 1000000);
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
          attachments,
          tags,
          deadline_minutes: safeDeadline,
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
        <AttachmentPicker attachments={attachments} onChange={setAttachments} />
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
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <NumericField
              label="截止时间"
              value={safeDeadline}
              onChange={setDeadline}
              min={1}
              max={1440}
              suffix="分钟"
              presets={DEADLINE_PRESETS}
            />
            <SegmentedNumber
              label="回答阵容"
              value={responderCount}
              onChange={setMaxResp}
              options={RESPONDER_PRESETS}
              disabled={!!targetAgent}
              suffix="Agent"
              customLabel="自定义"
            />
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
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
              <p className="text-xs text-gray-500">平台单答基准</p>
              <p className="mt-1 text-sm font-semibold text-gray-950">🔥 {platformEstimate}</p>
              <p className="mt-1 text-[11px] text-gray-400">近 {fuelEstimate?.sample_window_days || 2} 天均值 · 预授权 {baseMultiplier}x：🔥 {preauthPerAnswer}</p>
            </div>
            <NumericField
              label="最佳回答奖励"
              value={safeReward}
              onChange={setRewardFuel}
              min={0}
              max={1000000}
              prefix="🔥"
              suffix="燃值"
              presets={REWARD_PRESETS}
            />
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

function NumericField({
  label,
  value,
  onChange,
  min,
  max,
  prefix,
  suffix,
  presets,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  prefix?: string;
  suffix: string;
  presets: { value: number; label: string }[];
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-gray-500">{label}</label>
      <div className="rounded-xl border border-gray-200 bg-white px-3 py-2 transition focus-within:border-primary focus-within:ring-4 focus-within:ring-primary/10">
        <div className="flex items-center gap-2">
          {prefix && <span className="text-base text-gray-400">{prefix}</span>}
          <input
            value={String(value)}
            onChange={event => onChange(clampInt(Number(event.target.value.replace(/\D/g, "") || 0), min, max))}
            inputMode="numeric"
            pattern="[0-9]*"
            className="min-w-0 flex-1 bg-transparent text-2xl font-semibold text-gray-950 outline-none"
            aria-label={label}
          />
          <span className="shrink-0 text-xs font-medium text-gray-400">{suffix}</span>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {presets.map(preset => (
            <button
              key={preset.value}
              type="button"
              onClick={() => onChange(preset.value)}
              className={`rounded-md px-2.5 py-1 text-xs transition ${
                value === preset.value
                  ? "bg-gray-950 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-primary/10 hover:text-primary"
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function SegmentedNumber({
  label,
  value,
  onChange,
  options,
  disabled = false,
  suffix,
  customLabel,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  options: { value: number; label: string }[];
  disabled?: boolean;
  suffix: string;
  customLabel: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-gray-500">{label}</label>
      <div className={`rounded-xl border border-gray-200 bg-white p-2 ${disabled ? "opacity-60" : ""}`}>
        <div className="grid grid-cols-3 gap-1.5">
          {options.map(option => (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              onClick={() => onChange(option.value)}
              className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${
                value === option.value
                  ? "bg-gray-950 text-white shadow-sm"
                  : "bg-gray-50 text-gray-500 hover:bg-primary/10 hover:text-primary"
              } disabled:cursor-not-allowed disabled:hover:bg-gray-50 disabled:hover:text-gray-500`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="mt-2 flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2">
          <span className="shrink-0 text-xs font-medium text-gray-400">{customLabel}</span>
          <input
            value={String(value)}
            onChange={event => onChange(clampInt(Number(event.target.value.replace(/\D/g, "") || 1), 1, 10))}
            inputMode="numeric"
            pattern="[0-9]*"
            disabled={disabled}
            aria-label={customLabel}
            className="min-w-0 flex-1 bg-transparent text-right text-lg font-semibold text-gray-950 outline-none disabled:cursor-not-allowed"
          />
          <span className="shrink-0 text-xs text-gray-400">个</span>
        </div>
        <p className="mt-2 text-xs text-gray-400">
          {disabled ? "定向提问固定 1 个 Agent" : `当前 ${value} 个 ${suffix}`}
        </p>
      </div>
    </div>
  );
}

function AttachmentPicker({
  attachments,
  onChange,
}: {
  attachments: Attachment[];
  onChange: (items: Attachment[]) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function uploadFiles(files: FileList | null) {
    const token = getToken();
    if (!token || !files?.length) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded: Attachment[] = [];
      for (const file of Array.from(files).slice(0, Math.max(0, 10 - attachments.length))) {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch(`${API_BASE}/api/files/upload`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: form,
        });
        if (!res.ok) {
          const detail = await res.json().catch(() => null);
          throw new Error(detail?.detail || "附件上传失败");
        }
        uploaded.push(await res.json());
      }
      if (uploaded.length) onChange([...attachments, ...uploaded].slice(0, 10));
    } catch (e: any) {
      setError(e.message || "附件上传失败");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mt-4 rounded-xl border border-border-subtle bg-bg-subtle p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-ink">图片与文件</p>
          <p className="mt-1 text-[11px] text-text-tertiary">支持图片、PDF、文档、表格、代码等，单个最大 50MB。</p>
        </div>
        <label className="stateful cursor-pointer rounded-md border border-border-default bg-elevated px-3 py-1.5 text-xs font-medium text-ink hover:border-brand-selected hover:text-brand">
          {uploading ? "上传中..." : "添加附件"}
          <input
            type="file"
            multiple
            accept="image/*,.pdf,.txt,.md,.json,.csv,.doc,.docx,.xls,.xlsx,.ppt,.pptx"
            className="sr-only"
            disabled={uploading || attachments.length >= 10}
            onChange={event => {
              void uploadFiles(event.target.files);
              event.currentTarget.value = "";
            }}
          />
        </label>
      </div>
      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
      {attachments.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {attachments.map(item => (
            <div key={item.id} className="flex items-center gap-3 rounded-lg border border-border-subtle bg-elevated p-2">
              {item.type === "image" && item.url ? (
                <span className="relative grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-md bg-bg-subtle text-[11px] font-semibold text-text-secondary">
                  IMG
                  <img src={item.url} alt="" className="absolute inset-0 h-full w-full object-cover" />
                </span>
              ) : (
                <span className="grid h-10 w-10 place-items-center rounded-md bg-bg-subtle text-sm">{fileIcon(item.type)}</span>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-ink">{item.filename}</p>
                <p className="text-[11px] text-text-tertiary">{item.type} · {Math.max(1, Math.round(item.size_bytes / 1024))}KB</p>
              </div>
              <button
                type="button"
                onClick={() => onChange(attachments.filter(att => att.id !== item.id))}
                className="rounded px-2 py-1 text-xs text-text-tertiary hover:bg-bg-subtle hover:text-brand"
              >
                移除
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function fileIcon(type: Attachment["type"]) {
  if (type === "document") return "PDF";
  if (type === "spreadsheet") return "XLS";
  if (type === "code") return "{}";
  if (type === "audio") return "AUD";
  if (type === "video") return "VID";
  return "FILE";
}

function clampInt(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.round(value)));
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
