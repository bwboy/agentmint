"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { AgentServiceMode, AgentServiceRules, AgentVisibility, NotificationPrefs, User } from "@/lib/types";

type ProfileState = {
  nickname: string;
  avatar_url: string;
  headline: string;
  bio: string;
  profile_tags: string;
  experience_tags: string;
  links: Record<string, string>;
  profile_visibility: AgentVisibility;
  default_agent_visibility: AgentVisibility;
  default_agent_service_mode: AgentServiceMode;
  default_agent_service_rules: AgentServiceRules;
  notification_prefs: NotificationPrefs;
};

export function ProfileSettingsPanel() {
  const router = useRouter();
  const [state, setState] = useState<ProfileState | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    api<User>("/api/auth/my/profile", { token })
      .then(user => setState(stateFromUser(user)))
      .catch((e: any) => {
        if (e instanceof ApiError && e.status === 401) router.push("/login");
        else setErr(e.message || "加载失败");
      });
  }, [router]);

  async function save() {
    const token = getToken();
    if (!token || !state) return;
    setSaving(true);
    setErr(null);
    setMessage(null);
    try {
      const updated = await api<User>("/api/auth/my/profile", {
        method: "PUT",
        token,
        json: payloadFromState(state),
      });
      setState(stateFromUser(updated));
      setMessage("已保存");
    } catch (e: any) {
      setErr(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (!state) return <p className="text-sm text-gray-400">加载中…</p>;

  const update = (patch: Partial<ProfileState>) => setState({ ...state, ...patch });
  const updateRules = (patch: Partial<AgentServiceRules>) => update({
    default_agent_service_rules: normalizeRules({ ...state.default_agent_service_rules, ...patch }),
  });
  const updatePrefs = (key: keyof NotificationPrefs, value: boolean) => update({
    notification_prefs: { ...state.notification_prefs, [key]: value },
  });

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-500">{err}</div>}
      {message && <div className="rounded-lg border border-emerald-100 bg-emerald-50 p-3 text-xs text-emerald-600">{message}</div>}

      <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-gray-950">身份名片</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <TextField label="昵称" value={state.nickname} onChange={v => update({ nickname: v })} />
          <TextField label="头像 URL" value={state.avatar_url} onChange={v => update({ avatar_url: v })} />
          <TextField label="一句话身份" value={state.headline} onChange={v => update({ headline: v })} />
          <SelectField label="个人主页可见性" value={state.profile_visibility} onChange={v => update({ profile_visibility: v as AgentVisibility })}
            options={[
              ["public", "公开"],
              ["followers", "关注者可见"],
              ["friends", "好友可见"],
              ["archived", "关闭主页"],
            ]} />
        </div>
        <label className="mt-3 block">
          <span className="mb-1 block text-xs text-gray-500">个人简介</span>
          <textarea value={state.bio} onChange={e => update({ bio: e.target.value })} rows={5}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
        </label>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <TextField label="擅长领域标签" value={state.profile_tags} onChange={v => update({ profile_tags: v })} placeholder="AI, 产品, 魔兽世界" />
          <TextField label="经验标签" value={state.experience_tags} onChange={v => update({ experience_tags: v })} placeholder="实战, 研究, 长期玩家" />
        </div>
      </section>

      <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-gray-950">外部链接</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {(["website", "github", "x", "bilibili", "youtube", "linkedin"] as const).map(key => (
            <TextField key={key} label={key} value={state.links[key] || ""}
              onChange={v => update({ links: { ...state.links, [key]: v } })} />
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-gray-950">新 Agent 默认策略</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <SelectField label="默认可见范围" value={state.default_agent_visibility}
            onChange={v => update({ default_agent_visibility: v as AgentVisibility })}
            options={[["public", "公开发现"], ["followers", "关注者可见"], ["friends", "好友可见"], ["archived", "停止服务"]]} />
          <SelectField label="默认服务模式" value={state.default_agent_service_mode}
            onChange={v => update({ default_agent_service_mode: v as AgentServiceMode })}
            options={[["auto_match", "可自动匹配"], ["direct_only", "仅定向提问"], ["stopped", "不提供服务"]]} />
          <NumberField label="默认价格倍率" value={state.default_agent_service_rules.price_multiplier} min={0.1} max={10} step={0.1}
            onChange={v => updateRules({ price_multiplier: v })} />
          <NumberField label="默认追问深度" value={state.default_agent_service_rules.max_followup_depth} min={0} max={10} step={1}
            onChange={v => updateRules({ max_followup_depth: v })} />
          <NumberField label="默认最低燃值" value={state.default_agent_service_rules.min_fuel_per_answer} min={0} max={100000} step={100}
            onChange={v => updateRules({ min_fuel_per_answer: v })} />
          <NumberField label="默认最高燃值" value={state.default_agent_service_rules.max_fuel_per_answer} min={1} max={100000} step={100}
            onChange={v => updateRules({ max_fuel_per_answer: v })} />
        </div>
      </section>

      <section className="rounded-lg border border-gray-100 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-gray-950">通知偏好</h2>
        <div className="mt-4 grid gap-2 md:grid-cols-2">
          <CheckField label="好友申请" checked={state.notification_prefs.friend_request} onChange={v => updatePrefs("friend_request", v)} />
          <CheckField label="Agent 被订阅" checked={state.notification_prefs.agent_subscribed} onChange={v => updatePrefs("agent_subscribed", v)} />
          <CheckField label="定向提问" checked={state.notification_prefs.direct_question} onChange={v => updatePrefs("direct_question", v)} />
          <CheckField label="回答反馈" checked={state.notification_prefs.answer_feedback} onChange={v => updatePrefs("answer_feedback", v)} />
        </div>
      </section>

      <button onClick={save} disabled={saving || !state.nickname.trim()}
        className="rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-white hover:bg-primary-dark disabled:opacity-50">
        {saving ? "保存中..." : "保存个人设定"}
      </button>
    </div>
  );
}

function TextField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-gray-500">{label}</span>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
    </label>
  );
}

function SelectField({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<[string, string]> }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-gray-500">{label}</span>
      <select value={value} onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm">
        {options.map(([key, labelText]) => <option key={key} value={key}>{labelText}</option>)}
      </select>
    </label>
  );
}

function NumberField({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-gray-500">{label}</span>
      <input type="number" value={value} min={min} max={max} step={step}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm" />
    </label>
  );
}

function CheckField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-600">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function stateFromUser(user: User): ProfileState {
  return {
    nickname: user.nickname || "",
    avatar_url: user.avatar_url || "",
    headline: user.headline || "",
    bio: user.bio || "",
    profile_tags: (user.profile_tags || []).join(", "),
    experience_tags: (user.experience_tags || []).join(", "),
    links: user.links || {},
    profile_visibility: user.profile_visibility || "public",
    default_agent_visibility: user.default_agent_visibility || "public",
    default_agent_service_mode: user.default_agent_service_mode || "auto_match",
    default_agent_service_rules: normalizeRules(user.default_agent_service_rules),
    notification_prefs: user.notification_prefs || {
      friend_request: true,
      agent_subscribed: true,
      direct_question: true,
      answer_feedback: true,
    },
  };
}

function payloadFromState(state: ProfileState) {
  return {
    ...state,
    profile_tags: splitList(state.profile_tags),
    experience_tags: splitList(state.experience_tags),
    default_agent_service_rules: normalizeRules(state.default_agent_service_rules),
  };
}

function splitList(value: string) {
  return value.split(/[,，]\s*/).map(item => item.trim()).filter(Boolean);
}

function normalizeRules(rules?: Partial<AgentServiceRules>): AgentServiceRules {
  const maxFuel = Math.trunc(Number(rules?.max_fuel_per_answer ?? 100000));
  return {
    price_multiplier: Math.max(0.1, Math.min(Number(rules?.price_multiplier ?? 1), 10)),
    max_followup_depth: Math.max(0, Math.min(Math.trunc(Number(rules?.max_followup_depth ?? 2)), 10)),
    min_fuel_per_answer: Math.max(0, Math.trunc(Number(rules?.min_fuel_per_answer ?? 0))),
    max_fuel_per_answer: Number.isFinite(maxFuel) && maxFuel > 0 ? Math.min(maxFuel, 100000) : 100000,
  };
}
