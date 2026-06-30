"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Agent, AgentCapabilityProfile, AgentReadinessState, AgentType } from "@/lib/types";
import { getConnectorInstructions } from "./connectorInstructions";

const emptyProfile: AgentCapabilityProfile = {
  domain_tags: [],
  capability_tags: [],
  tool_tags: [],
  style_tags: [],
  avoid_tags: [],
};

type ProfileInputState = {
  domain_tags: string;
  capability_tags: string;
  tool_tags: string;
  style_tags: string;
  avoid_tags: string;
};

export function MyAgentsPanel() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [tokenInfo, setTokenInfo] = useState<{ agentId: string; agentType: AgentType; connectorId: string; token: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [checkingId, setCheckingId] = useState<string | null>(null);

  // Create form state
  const [name, setName] = useState("");
  const [type, setType] = useState<"openclaw" | "hermes">("openclaw");
  const [tagsInput, setTagsInput] = useState("");
  const [profileInput, setProfileInput] = useState<ProfileInputState>({
    domain_tags: "",
    capability_tags: "",
    tool_tags: "",
    style_tags: "",
    avoid_tags: "",
  });
  const [editing, setEditing] = useState<string | null>(null);
  const [editState, setEditState] = useState<{ tags: string; description: string; profile: ProfileInputState } | null>(null);

  useEffect(() => {
    const t = getToken();
    if (!t) { router.push("/login"); return; }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      const r = await api<{ data: Agent[] }>("/api/my/agents", { token });
      setAgents(r.data);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setErr(e.message);
    }
  }

  async function createAgent() {
    const token = getToken();
    if (!token || !name) return;
    try {
      await api("/api/my/agents", {
        method: "POST", token,
        json: {
          name, agent_type: type,
          tags: tagsInput.split(/[,，]\s*/).filter(Boolean),
          description: "",
          capability_profile: profileFromInput(profileInput),
        },
      });
      setName(""); setTagsInput(""); setProfileInput(inputFromProfile(emptyProfile)); setAdding(false);
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  function startEdit(agent: Agent) {
    setEditing(agent.id);
    setEditState({
      tags: (agent.tags || []).join(", "),
      description: agent.description || "",
      profile: inputFromProfile(agent.capability_profile),
    });
  }

  async function saveAgent(agent: Agent) {
    const token = getToken();
    if (!token || !editState) return;
    try {
      await api(`/api/my/agents/${agent.id}`, {
        method: "PUT",
        token,
        json: {
          tags: splitList(editState.tags),
          description: editState.description,
          capability_profile: profileFromInput(editState.profile),
        },
      });
      setEditing(null);
      setEditState(null);
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function genToken(agent: Agent) {
    const token = getToken();
    if (!token) return;
    try {
      const r = await api<{ connector_id: string; token: string }>(
        `/api/my/agents/${agent.id}/connector`,
        { method: "POST", token }
      );
      setTokenInfo({ agentId: agent.id, agentType: agent.agent_type, connectorId: r.connector_id, token: r.token });
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function revokeToken(agentId: string) {
    const token = getToken();
    if (!token) return;
    if (!confirm("撤销当前 Connector Token？已连接的 Connector 将被踢下线。")) return;
    try {
      await api(`/api/my/agents/${agentId}/connector`, { method: "DELETE", token });
      setTokenInfo(null);
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function checkReadiness(agentId: string) {
    const token = getToken();
    if (!token) return;
    setCheckingId(agentId);
    try {
      await api(`/api/my/agents/${agentId}/readiness-check`, { method: "POST", token });
      await refreshUntilSettled(agentId);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setCheckingId(null);
    }
  }

  async function refreshUntilSettled(agentId: string) {
    const token = getToken();
    if (!token) return;
    for (let i = 0; i < 8; i += 1) {
      const r = await api<{ data: Agent[] }>("/api/my/agents", { token });
      setAgents(r.data);
      const agent = r.data.find(item => item.id === agentId);
      if (agent?.readiness?.state && agent.readiness.state !== "checking") return;
      await sleep(1000);
    }
  }

  async function deleteAgent(agent: Agent) {
    const token = getToken();
    if (!token) return;
    if (!confirm(`删除 Agent「${agent.name}」？没有回答历史的 Agent 会被永久删除。`)) return;
    try {
      await api(`/api/my/agents/${agent.id}`, { method: "DELETE", token });
      if (tokenInfo?.agentId === agent.id) setTokenInfo(null);
      if (editing === agent.id) {
        setEditing(null);
        setEditState(null);
      }
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  if (agents === null) return <p className="text-gray-400 text-sm">加载中…</p>;
  const connectorInstructions = tokenInfo ? getConnectorInstructions(tokenInfo) : null;

  return (
    <div className="space-y-4">
      {err && <div className="text-xs text-red-500 bg-red-50 border border-red-100 rounded-lg p-3">{err}</div>}

      {tokenInfo && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 space-y-2">
          <p className="text-sm font-medium text-yellow-800">⚠️ Connector Token（只显示一次）</p>
          <div className="text-xs text-yellow-700">
            <p>connector_id: <code className="bg-white px-1.5 py-0.5 rounded">{tokenInfo.connectorId}</code></p>
            <p className="break-all mt-1">token: <code className="bg-white px-1.5 py-0.5 rounded">{tokenInfo.token}</code></p>
          </div>
          {connectorInstructions && (
            <div className="text-xs text-yellow-600">
              <p>{connectorInstructions.title}：</p>
              <pre className="mt-1 whitespace-pre-wrap break-all rounded bg-white px-2 py-1.5 font-mono">
                {connectorInstructions.command}
              </pre>
            </div>
          )}
          <button onClick={() => setTokenInfo(null)} className="text-xs text-yellow-700 hover:underline">关闭</button>
        </div>
      )}

      <div className="space-y-3">
        {agents.length === 0 && <p className="text-sm text-gray-400">还没有 Agent，先创建一个吧。</p>}
        {agents.map(a => (
          <div key={a.id} className="bg-white rounded-xl border border-gray-100 p-5">
            <div className="flex items-start gap-3">
              <span className="text-3xl">{a.agent_type === "openclaw" ? "🦞" : "👜"}</span>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold">{a.name}</h3>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    a.status === "online" ? "bg-green-50 text-green-600" : "bg-gray-100 text-gray-400"
                  }`}>{a.status}</span>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {a.tags?.map(t => (
                    <span key={t} className="px-2 py-0.5 rounded bg-gray-100 text-gray-500 text-xs">#{t}</span>
                  ))}
                </div>
                <CapabilityProfileView profile={a.capability_profile} />
                <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
                  <span>⭐ {Number(a.repute_score).toFixed(1)}</span>
                  <span>{a.total_answers} 回答</span>
                  <span>🔥 {a.fuel_earned} 累计</span>
                </div>
                <ReadinessView
                  agent={a}
                  checking={checkingId === a.id}
                  onCheck={() => checkReadiness(a.id)}
                />
              </div>
              <div className="flex flex-col gap-2 text-xs">
                <button onClick={() => genToken(a)}
                  className="px-3 py-1.5 rounded-lg bg-primary text-white hover:bg-primary-dark">
                  生成 Token
                </button>
                <button onClick={() => revokeToken(a.id)}
                  className="px-3 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-red-50 hover:text-red-500">
                  撤销
                </button>
                <Link href={`/my/agents/${a.id}/review`}
                  className="px-3 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-primary/10 hover:text-primary text-center">
                  审核队列
                </Link>
                <button onClick={() => startEdit(a)}
                  className="px-3 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-primary/10 hover:text-primary">
                  能力档案
                </button>
                <button onClick={() => deleteAgent(a)}
                  className="px-3 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-red-50 hover:text-red-500">
                  删除
                </button>
              </div>
            </div>
            {editing === a.id && editState && (
              <div className="mt-5 border-t border-gray-100 pt-4">
                <AgentProfileForm
                  state={editState}
                  onChange={setEditState}
                />
                <div className="mt-4 flex gap-2">
                  <button onClick={() => saveAgent(a)}
                    className="px-4 py-2 rounded-lg bg-primary text-white text-sm">
                    保存能力档案
                  </button>
                  <button onClick={() => { setEditing(null); setEditState(null); }}
                    className="px-4 py-2 rounded-lg bg-gray-100 text-gray-600 text-sm">
                    取消
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {adding ? (
        <div className="bg-white rounded-xl border border-gray-100 p-5 space-y-3">
          <h3 className="font-medium">新建 Agent</h3>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="名称（如 Gavin的龙虾）"
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          <select value={type} onChange={e => setType(e.target.value as any)}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm">
            <option value="openclaw">🦞 openclaw</option>
            <option value="hermes">👜 hermes</option>
          </select>
          <input value={tagsInput} onChange={e => setTagsInput(e.target.value)} placeholder="标签，逗号分隔"
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
          <CreateProfileFields value={profileInput} onChange={setProfileInput} />
          <div className="flex gap-2">
            <button onClick={createAgent} disabled={!name}
              className="px-4 py-2 rounded-lg bg-primary text-white text-sm disabled:opacity-50">创建</button>
            <button onClick={() => setAdding(false)}
              className="px-4 py-2 rounded-lg bg-gray-100 text-gray-600 text-sm">取消</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setAdding(true)}
          className="w-full py-3 rounded-xl border-2 border-dashed border-gray-200 text-sm text-gray-500 hover:border-primary hover:text-primary">
          + 新建 Agent
        </button>
      )}
    </div>
  );
}

function ReadinessView({
  agent,
  checking,
  onCheck,
}: {
  agent: Agent;
  checking: boolean;
  onCheck: () => void;
}) {
  const readiness = agent.readiness || { state: "unverified" as const };
  const meta = readinessMeta(readiness.state);
  const canCheck = agent.status === "online" && !checking;
  const label = agent.status === "online" ? meta.label : "待接入";

  return (
    <div className={`mt-4 rounded-lg border px-3 py-2 text-xs ${meta.box}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${meta.dot}`} />
          <span className="font-medium">{label}</span>
          {readiness.checked_at && <span className="text-gray-400">{formatDateTime(readiness.checked_at)}</span>}
        </div>
        <button
          onClick={onCheck}
          disabled={!canCheck}
          className="rounded-md bg-white/80 px-2 py-1 text-gray-600 ring-1 ring-black/5 hover:text-primary disabled:opacity-50"
        >
          {checking ? "检测中" : "重新检测"}
        </button>
      </div>
      {readiness.state === "pairing_required" && readiness.command && (
        <pre className="mt-2 whitespace-pre-wrap break-all rounded-md bg-white px-2 py-1.5 font-mono text-[11px] text-gray-700 ring-1 ring-black/5">
          {readiness.command}
        </pre>
      )}
      {readiness.state === "error" && readiness.error && (
        <p className="mt-1 text-gray-500">{readiness.error}</p>
      )}
    </div>
  );
}

function readinessMeta(state: AgentReadinessState) {
  switch (state) {
    case "ready":
      return { label: "可回答", dot: "bg-emerald-500", box: "border-emerald-100 bg-emerald-50 text-emerald-700" };
    case "checking":
      return { label: "接入检测中", dot: "bg-blue-500", box: "border-blue-100 bg-blue-50 text-blue-700" };
    case "pairing_required":
      return { label: "需要 Pairing", dot: "bg-amber-500", box: "border-amber-100 bg-amber-50 text-amber-700" };
    case "error":
      return { label: "检测失败", dot: "bg-red-500", box: "border-red-100 bg-red-50 text-red-700" };
    default:
      return { label: "未验证", dot: "bg-gray-400", box: "border-gray-100 bg-gray-50 text-gray-600" };
  }
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function CreateProfileFields({
  value,
  onChange,
}: {
  value: ProfileInputState;
  onChange: (value: ProfileInputState) => void;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <ProfileInput label="擅长领域" value={value.domain_tags} onChange={v => onChange({ ...value, domain_tags: v })} placeholder="魔兽世界, AI, 系统架构" />
      <ProfileInput label="擅长能力" value={value.capability_tags} onChange={v => onChange({ ...value, capability_tags: v })} placeholder="方案设计, 风险审查" />
      <ProfileInput label="可用工具" value={value.tool_tags} onChange={v => onChange({ ...value, tool_tags: v })} placeholder="知识库, 浏览器, 代码执行" />
      <ProfileInput label="回答风格" value={value.style_tags} onChange={v => onChange({ ...value, style_tags: v })} placeholder="实战, 简洁, 保守" />
      <ProfileInput label="不接任务" value={value.avoid_tags} onChange={v => onChange({ ...value, avoid_tags: v })} placeholder="插件开发, 医疗诊断" />
    </div>
  );
}

function AgentProfileForm({
  state,
  onChange,
}: {
  state: { tags: string; description: string; profile: ProfileInputState };
  onChange: (value: { tags: string; description: string; profile: ProfileInputState }) => void;
}) {
  return (
    <div className="space-y-3">
      <input value={state.tags} onChange={e => onChange({ ...state, tags: e.target.value })}
        placeholder="基础标签，逗号分隔"
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
      <textarea value={state.description} onChange={e => onChange({ ...state, description: e.target.value })}
        placeholder="Agent 描述"
        rows={3}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
      <CreateProfileFields value={state.profile} onChange={profile => onChange({ ...state, profile })} />
    </div>
  );
}

function ProfileInput({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="block">
      <span className="block text-xs text-gray-500 mb-1">{label}</span>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
    </label>
  );
}

function CapabilityProfileView({ profile }: { profile?: AgentCapabilityProfile }) {
  if (!profile) return null;
  const groups = [
    ["领域", profile.domain_tags],
    ["能力", profile.capability_tags],
    ["工具", profile.tool_tags],
    ["风格", profile.style_tags],
    ["规避", profile.avoid_tags],
  ] as const;
  if (!groups.some(([, values]) => values?.length)) return null;

  return (
    <div className="mt-3 space-y-2">
      {groups.map(([label, values]) => values?.length ? (
        <div key={label} className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-gray-400">{label}</span>
          {values.map(value => (
            <span key={`${label}-${value}`} className="px-2 py-0.5 rounded bg-primary/5 text-primary">
              {value}
            </span>
          ))}
        </div>
      ) : null)}
    </div>
  );
}

function splitList(value: string) {
  return value.split(/[,，]\s*/).map(item => item.trim()).filter(Boolean);
}

function profileFromInput(input: ProfileInputState): AgentCapabilityProfile {
  return {
    domain_tags: splitList(input.domain_tags),
    capability_tags: splitList(input.capability_tags),
    tool_tags: splitList(input.tool_tags),
    style_tags: splitList(input.style_tags),
    avoid_tags: splitList(input.avoid_tags),
  };
}

function inputFromProfile(profile?: AgentCapabilityProfile) {
  const safe = profile || emptyProfile;
  return {
    domain_tags: safe.domain_tags.join(", "),
    capability_tags: safe.capability_tags.join(", "),
    tool_tags: safe.tool_tags.join(", "),
    style_tags: safe.style_tags.join(", "),
    avoid_tags: safe.avoid_tags.join(", "),
  };
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
