"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Agent, AgentCapabilityProfile, AgentLearnedProfile, AgentPermissionProfile, AgentProfileTagField, AgentReadinessState, AgentServiceMode, AgentServiceRules, AgentType, AgentVisibility, KnowledgeScope, RuntimeNode } from "@/lib/types";
import { OwnerSupplementSignal } from "./OwnerSupplementSignal";
import { getRuntimeNodeInstructions, getRuntimeProfileInstructions } from "./connectorInstructions";

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

type AgentEditState = {
  tags: string;
  description: string;
  profile: ProfileInputState;
  visibility: AgentVisibility;
  service_mode: AgentServiceMode;
  service_rules: AgentServiceRules;
  daily_quota_config: { max: number; auto_threshold: number; emergency_reserve: number };
  permission_profile: AgentPermissionProfile;
};

export function MyAgentsPanel() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [runtimeNodes, setRuntimeNodes] = useState<RuntimeNode[]>([]);
  const [tokenInfo, setTokenInfo] = useState<{ runtimeNodeId: string; runtimeType: AgentType; token: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [addingNode, setAddingNode] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [checkingId, setCheckingId] = useState<string | null>(null);

  // Create form state
  const [name, setName] = useState("");
  const [type, setType] = useState<"openclaw" | "hermes">("hermes");
  const [editing, setEditing] = useState<string | null>(null);
  const [editState, setEditState] = useState<AgentEditState | null>(null);
  const [nodeName, setNodeName] = useState("");
  const [nodeType, setNodeType] = useState<AgentType>("hermes");

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
      const [agentRes, nodeRes] = await Promise.all([
        api<{ data: Agent[] }>("/api/my/agents", { token }),
        api<{ data: RuntimeNode[] }>("/api/my/runtime-nodes", { token }),
      ]);
      setAgents(agentRes.data);
      setRuntimeNodes(nodeRes.data);
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setErr(e.message);
    }
  }

  async function createAgent() {
    const token = getToken();
    if (!token || !name) return;
    try {
      const created = await api<Agent>("/api/my/agents", {
        method: "POST", token,
        json: {
          name, agent_type: type,
          tags: [],
          description: "",
          capability_profile: emptyProfile,
        },
      });
      if (created.runtime_node?.token) {
        setTokenInfo({
          runtimeNodeId: created.runtime_node.id,
          runtimeType: created.runtime_node.runtime_type,
          token: created.runtime_node.token,
        });
      }
      setName(""); setType("hermes"); setAdding(false);
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
      visibility: agent.visibility || "public",
      service_mode: agent.service_mode || "auto_match",
      service_rules: normalizeServiceRules(agent.service_rules),
      daily_quota_config: normalizeQuota(agent.daily_quota_config),
      permission_profile: normalizePermissionProfile(agent.permission_profile),
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
          visibility: editState.visibility,
          service_mode: editState.service_mode,
          service_rules: normalizeServiceRules(editState.service_rules),
          daily_quota_config: normalizeQuota(editState.daily_quota_config),
          permission_profile: normalizePermissionProfile(editState.permission_profile),
        },
      });
      setEditing(null);
      setEditState(null);
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function createRuntimeNode() {
    const token = getToken();
    if (!token) return;
    try {
      const r = await api<RuntimeNode & { token: string }>(
        "/api/my/runtime-nodes",
        {
          method: "POST",
          token,
          json: { name: nodeName || `${nodeType === "hermes" ? "Hermes" : "OpenClaw"} 本地节点`, runtime_type: nodeType },
        }
      );
      setTokenInfo({ runtimeNodeId: r.id, runtimeType: r.runtime_type, token: r.token });
      setNodeName("");
      setNodeType("hermes");
      setAddingNode(false);
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function rotateRuntimeNodeToken(node: RuntimeNode) {
    const token = getToken();
    if (!token) return;
    if (!confirm(`重置「${node.name}」的接入 token？当前连接会断开，需要在本机重新配置。`)) return;
    try {
      const r = await api<RuntimeNode & { token: string }>(`/api/my/runtime-nodes/${node.id}/token`, { method: "POST", token });
      setTokenInfo({ runtimeNodeId: r.id, runtimeType: r.runtime_type, token: r.token });
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function deleteRuntimeNode(node: RuntimeNode) {
    const token = getToken();
    if (!token) return;
    if (!confirm(`删除本地节点「${node.name}」？删除前必须先解绑所有 Agent。`)) return;
    try {
      await api(`/api/my/runtime-nodes/${node.id}`, { method: "DELETE", token });
      if (tokenInfo?.runtimeNodeId === node.id) setTokenInfo(null);
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function bindRuntime(agent: Agent, patch: { runtime_node_id?: string; runtime_profile?: string; runtime_workspace?: string; knowledge_scope?: KnowledgeScope }) {
    const token = getToken();
    if (!token) return;
    const current = agent.runtime_binding;
    const runtimeNodeId = patch.runtime_node_id ?? current?.runtime_node_id ?? "";
    if (!runtimeNodeId) {
      await unbindRuntime(agent);
      return;
    }
    try {
      await api(`/api/my/agents/${agent.id}/runtime-binding`, {
        method: "PUT",
        token,
        json: {
          runtime_node_id: runtimeNodeId,
          runtime_profile: patch.runtime_profile ?? current?.runtime_profile ?? "",
          runtime_workspace: patch.runtime_workspace ?? current?.runtime_workspace ?? "",
          knowledge_scope: patch.knowledge_scope ?? current?.knowledge_scope ?? "private",
          status: current?.status ?? "active",
        },
      });
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function unbindRuntime(agent: Agent) {
    const token = getToken();
    if (!token) return;
    try {
      await api(`/api/my/agents/${agent.id}/runtime-binding`, { method: "DELETE", token });
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
    if (!confirm(`删除 Agent「${agent.name}」？有回答历史的 Agent 会从管理列表移除并停止服务，历史回答仍会保留。`)) return;
    try {
      await api(`/api/my/agents/${agent.id}`, { method: "DELETE", token });
      if (editing === agent.id) {
        setEditing(null);
        setEditState(null);
      }
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function reviewLearnedTag(agent: Agent, field: AgentProfileTagField, value: string, action: "accept" | "reject") {
    const token = getToken();
    if (!token) return;
    try {
      await api(`/api/my/agents/${agent.id}/learned-profile-review`, {
        method: "POST",
        token,
        json: {
          accept: action === "accept" ? { [field]: [value] } : {},
          reject: action === "reject" ? { [field]: [value] } : {},
        },
      });
      await refresh();
    } catch (e: any) {
      setErr(e.message || "处理系统学习标签失败");
    }
  }

  if (agents === null) return <p className="text-gray-400 text-sm">加载中…</p>;
  const runtimeInstructions = tokenInfo ? getRuntimeNodeInstructions({
    runtimeType: tokenInfo.runtimeType,
    runtimeNodeId: tokenInfo.runtimeNodeId,
    token: tokenInfo.token,
    permissionProfile: "balanced",
  }) : null;

  return (
    <div className="space-y-4">
      {err && <div className="text-xs text-red-500 bg-red-50 border border-red-100 rounded-lg p-3">{err}</div>}

      {tokenInfo && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 space-y-2">
          <p className="text-sm font-medium text-yellow-800">⚠️ Runtime Node Token（只显示一次）</p>
          <div className="text-xs text-yellow-700">
            <p>runtime_node_id: <code className="bg-white px-1.5 py-0.5 rounded">{tokenInfo.runtimeNodeId}</code></p>
            <p className="break-all mt-1">token: <code className="bg-white px-1.5 py-0.5 rounded">{tokenInfo.token}</code></p>
          </div>
          {runtimeInstructions && (
            <div className="text-xs text-yellow-600">
              <p>{runtimeInstructions.title}：</p>
              <pre className="mt-1 whitespace-pre-wrap break-all rounded bg-white px-2 py-1.5 font-mono">
                {runtimeInstructions.command}
              </pre>
            </div>
          )}
          <button onClick={() => setTokenInfo(null)} className="text-xs text-yellow-700 hover:underline">关闭</button>
        </div>
      )}

      <AgentCreateSection
        adding={adding}
        name={name}
        type={type}
        onAddToggle={setAdding}
        onNameChange={setName}
        onTypeChange={setType}
        onCreate={createAgent}
      />

      <div className="space-y-3">
        {agents.length === 0 && <p className="rounded-xl border border-dashed border-gray-200 bg-white p-5 text-sm text-gray-400">还没有 Agent。先在上方创建 Agent，系统会同时生成本机接入 Token；接入成功后再创建能力档案。</p>}
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
                <LearnedProfileView profile={a.learned_profile} />
                <div className="mt-3">
                  <OwnerSupplementSignal summary={a.owner_supplement_summary} compact />
                </div>
                <AgentHealthView agent={a} />
                <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
                  <span>⭐ {Number(a.repute_score).toFixed(1)}</span>
                  <span>{a.total_answers} 回答</span>
                  <span>🔥 {a.fuel_earned} 累计</span>
                </div>
                <ServiceSummary agent={a} />
                <ReadinessView
                  agent={a}
                  checking={checkingId === a.id}
                  onCheck={() => checkReadiness(a.id)}
                />
                <RuntimeBindingSummary agent={a} />
              </div>
              <div className="flex flex-col gap-2 text-xs">
                <Link href={`/my/agents/${a.id}/review`}
                  className="px-3 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-primary/10 hover:text-primary text-center">
                  审核队列
                </Link>
                <button onClick={() => startEdit(a)}
                  className="px-3 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-primary/10 hover:text-primary">
                  Profile
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
                <RuntimeBindingEditor
                  agent={a}
                  nodes={runtimeNodes.filter(node => node.runtime_type === a.agent_type)}
                  onBind={patch => bindRuntime(a, patch)}
                  onUnbind={() => unbindRuntime(a)}
                />
                <PermissionSettingsFields
                  agent={a}
                  state={editState}
                  onChange={setEditState}
                />
                <LearnedProfileReviewPanel
                  agent={a}
                  onReview={(field, value, action) => reviewLearnedTag(a, field, value, action)}
                />
                <div className="mt-4 flex gap-2">
                  <button onClick={() => saveAgent(a)}
                    className="px-4 py-2 rounded-lg bg-primary text-white text-sm">
                    保存 Profile
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

      <RuntimeNodeSection
        nodes={runtimeNodes}
        adding={addingNode}
        nodeName={nodeName}
        nodeType={nodeType}
        onAddToggle={setAddingNode}
        onNameChange={setNodeName}
        onTypeChange={setNodeType}
        onCreate={createRuntimeNode}
        onRotate={rotateRuntimeNodeToken}
        onDelete={deleteRuntimeNode}
      />
    </div>
  );
}

function ServiceSummary({ agent }: { agent: Agent }) {
  const rules = normalizeServiceRules(agent.service_rules);
  const quota = normalizeQuota(agent.daily_quota_config);
  return (
    <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
      <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-500">{visibilityLabel(agent.visibility)}</span>
      <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-500">{serviceModeLabel(agent.service_mode)}</span>
      <span className="rounded bg-orange-50 px-2 py-0.5 text-orange-600">x{rules.price_multiplier} 计费</span>
      <span className="rounded bg-blue-50 px-2 py-0.5 text-blue-600">追问 {rules.max_followup_depth} 层</span>
      <span className="rounded bg-indigo-50 px-2 py-0.5 text-indigo-600">单用户 {rules.max_questions_per_user_per_day}/日</span>
      <span className="rounded bg-teal-50 px-2 py-0.5 text-teal-600">燃值 {rules.max_fuel_per_day}/日</span>
      <span className="rounded bg-emerald-50 px-2 py-0.5 text-emerald-600">每日 {quota.max} 次</span>
    </div>
  );
}

function AgentCreateSection({
  adding,
  name,
  type,
  onAddToggle,
  onNameChange,
  onTypeChange,
  onCreate,
}: {
  adding: boolean;
  name: string;
  type: AgentType;
  onAddToggle: (value: boolean) => void;
  onNameChange: (value: string) => void;
  onTypeChange: (value: AgentType) => void;
  onCreate: () => void;
}) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">1. 创建 Agent 并接入本机</h3>
          <p className="mt-1 text-xs text-gray-500">创建后系统会生成本机接入 Token；具体能回答什么，在后续能力档案里配置。</p>
        </div>
        <button
          onClick={() => onAddToggle(!adding)}
          className="rounded-lg bg-gray-950 px-3 py-2 text-xs font-medium text-white hover:bg-gray-800"
        >
          {adding ? "收起" : "新建 Agent"}
        </button>
      </div>
      {adding && (
        <div className="grid gap-3 rounded-lg border border-gray-100 bg-gray-50 p-3 md:grid-cols-[1fr_180px_auto]">
          <input
            value={name}
            onChange={e => onNameChange(e.target.value)}
            placeholder="Agent 名称，例如 Mac上的爱马仕"
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
          />
          <select
            value={type}
            onChange={e => onTypeChange(e.target.value as AgentType)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
          >
            <option value="hermes">Hermes</option>
            <option value="openclaw">OpenClaw</option>
          </select>
          <button
            onClick={onCreate}
            disabled={!name.trim()}
            className="rounded-lg bg-primary px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            创建 Agent
          </button>
        </div>
      )}
    </div>
  );
}

function RuntimeNodeSection({
  nodes,
  adding,
  nodeName,
  nodeType,
  onAddToggle,
  onNameChange,
  onTypeChange,
  onCreate,
  onRotate,
  onDelete,
}: {
  nodes: RuntimeNode[];
  adding: boolean;
  nodeName: string;
  nodeType: AgentType;
  onAddToggle: (value: boolean) => void;
  onNameChange: (value: string) => void;
  onTypeChange: (value: AgentType) => void;
  onCreate: () => void;
  onRotate: (node: RuntimeNode) => void;
  onDelete: (node: RuntimeNode) => void;
}) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">高级：本机接入管理</h3>
          <p className="mt-1 text-xs text-gray-500">创建 Agent 时会自动生成本机接入 Token。这里用于复用已有接入、重置 Token 或清理节点。</p>
        </div>
        <button
          onClick={() => onAddToggle(!adding)}
          className="rounded-lg bg-gray-950 px-3 py-2 text-xs font-medium text-white hover:bg-gray-800"
        >
          {adding ? "收起" : "新建节点"}
        </button>
      </div>
      {adding && (
        <div className="mb-4 grid gap-3 rounded-lg border border-gray-100 bg-gray-50 p-3 md:grid-cols-[1fr_180px_auto]">
          <input
            value={nodeName}
            onChange={e => onNameChange(e.target.value)}
            placeholder="节点名称，例如 Mac 上的 Hermes"
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
          />
          <select
            value={nodeType}
            onChange={e => onTypeChange(e.target.value as AgentType)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
          >
            <option value="hermes">Hermes</option>
            <option value="openclaw">OpenClaw</option>
          </select>
          <button
            onClick={onCreate}
            className="rounded-lg bg-primary px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            创建并生成 Token
          </button>
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {nodes.length === 0 && <p className="text-sm text-gray-400">还没有本机接入。创建 Agent 后会自动生成接入 Token。</p>}
        {nodes.map(node => (
          <div key={node.id} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${node.status === "online" ? "bg-emerald-500" : "bg-gray-400"}`} />
                  <span className="font-medium text-gray-900">{node.name}</span>
                  <span className="rounded bg-white px-2 py-0.5 text-[11px] text-gray-500">{node.runtime_type}</span>
                </div>
                <p className="mt-1 break-all font-mono text-[11px] text-gray-400">{node.id}</p>
                <p className="mt-2 text-xs text-gray-500">
                  {node.bindings?.length ? `已绑定 ${node.bindings.length} 个 Agent` : "未绑定 Agent"}
                  {node.last_seen_at ? ` · ${formatDateTime(node.last_seen_at)}` : ""}
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <button onClick={() => onRotate(node)} className="rounded-md bg-white px-2 py-1 text-xs text-gray-600 ring-1 ring-black/5 hover:text-primary">
                  重置 Token
                </button>
                <button onClick={() => onDelete(node)} className="rounded-md bg-white px-2 py-1 text-xs text-gray-600 ring-1 ring-black/5 hover:text-red-500">
                  删除
                </button>
              </div>
            </div>
            {!!node.bindings?.length && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {node.bindings.map(binding => (
                  <span key={binding.agent_id} className="rounded bg-white px-2 py-0.5 text-xs text-gray-500">
                    {binding.agent_name || binding.agent_id}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function RuntimeBindingSummary({ agent }: { agent: Agent }) {
  const binding = agent.runtime_binding;
  if (!binding) {
    return (
      <div className="mt-3 rounded-lg border border-dashed border-violet-100 bg-violet-50 px-3 py-2 text-xs text-violet-600">
        还没有能力档案。打开 Profile 后选择本机接入，并初始化 Hermes Profile / OpenClaw Workspace。
      </div>
    );
  }
  const space = agent.agent_type === "hermes" ? binding.runtime_profile : binding.runtime_workspace;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
      <span className="rounded bg-violet-50 px-2 py-0.5 text-violet-700">
        {agent.agent_type === "hermes" ? "Hermes Profile" : "OpenClaw Workspace"}：{space || "未命名"}
      </span>
      <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-500">
        节点 {binding.runtime_node?.name || binding.runtime_node_id}
      </span>
      <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-500">
        知识 {knowledgeScopeLabel(binding.knowledge_scope)}
      </span>
    </div>
  );
}

function RuntimeBindingEditor({
  agent,
  nodes,
  onBind,
  onUnbind,
}: {
  agent: Agent;
  nodes: RuntimeNode[];
  onBind: (patch: { runtime_node_id?: string; runtime_profile?: string; runtime_workspace?: string; knowledge_scope?: KnowledgeScope }) => void;
  onUnbind: () => void;
}) {
  const binding = agent.runtime_binding;
  const selectedNodeId = binding?.runtime_node_id || "";
  const selectedNode = nodes.find(node => node.id === selectedNodeId);
  const profileLabel = agent.agent_type === "hermes" ? "Hermes Profile" : "OpenClaw Workspace";
  const spaceValue = agent.agent_type === "hermes" ? binding?.runtime_profile || "" : binding?.runtime_workspace || "";
  const defaultSpace = defaultRuntimeSpaceName(agent.name, agent.id);
  const trimmedSpace = spaceValue.trim();
  const setupInstructions = trimmedSpace
    ? getRuntimeProfileInstructions({
        runtimeType: agent.agent_type,
        profileName: trimmedSpace,
        workspaceName: trimmedSpace,
      })
    : null;
  const [copied, setCopied] = useState(false);

  async function copyCommand(command: string) {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-violet-100 bg-violet-50 p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="text-xs font-medium text-violet-800">2. 能力档案接入</span>
          <p className="mt-1 text-[11px] text-violet-600">能力档案绑定到已接入的 Hermes profile / OpenClaw workspace；一个 Agent 后续可以扩展多个档案。</p>
        </div>
        {binding && (
          <button onClick={onUnbind} className="rounded-md bg-white px-2 py-1 text-xs text-violet-700 ring-1 ring-violet-100 hover:text-red-500">
            解绑
          </button>
        )}
      </div>
      {!selectedNodeId && nodes.length === 0 && (
        <div className="mb-3 rounded-lg border border-amber-100 bg-amber-50 p-3 text-xs text-amber-700">
          还没有在线或已创建的本机接入。先使用创建 Agent 后生成的 Token 在本机执行接入命令。
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-[1fr_1fr_150px]">
        <label className="block">
          <span className="mb-1 block text-xs text-violet-700">使用已有接入</span>
          <select
            value={selectedNodeId}
            onChange={e => onBind({ runtime_node_id: e.target.value })}
            className="w-full rounded-lg border border-violet-100 bg-white px-3 py-2 text-sm"
          >
            <option value="">未接入</option>
            {nodes.map(node => (
              <option key={node.id} value={node.id}>{node.name} · {node.status}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-violet-700">{profileLabel}</span>
          <input
            value={spaceValue}
            disabled={!selectedNodeId}
            onChange={e => agent.agent_type === "hermes"
              ? onBind({ runtime_profile: e.target.value })
              : onBind({ runtime_workspace: e.target.value })}
            placeholder={defaultSpace}
            className="w-full rounded-lg border border-violet-100 bg-white px-3 py-2 text-sm disabled:bg-gray-100"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-violet-700">知识范围</span>
          <select
            value={binding?.knowledge_scope || "private"}
            disabled={!selectedNodeId}
            onChange={e => onBind({ knowledge_scope: e.target.value as KnowledgeScope })}
            className="w-full rounded-lg border border-violet-100 bg-white px-3 py-2 text-sm disabled:bg-gray-100"
          >
            <option value="private">仅本 Agent</option>
            <option value="shared">共享知识</option>
            <option value="disabled">不用知识</option>
          </select>
        </label>
      </div>
      {selectedNodeId && (
        <div className="mt-3 grid gap-2 text-[11px] text-violet-700 md:grid-cols-4">
          <SetupStep active done label="Agent 已创建" />
          <SetupStep active done={Boolean(selectedNode)} label={selectedNode?.status === "online" ? "节点在线" : "节点已绑定"} />
          <SetupStep active={Boolean(trimmedSpace)} done={Boolean(trimmedSpace)} label={agent.agent_type === "hermes" ? "Profile 已命名" : "Workspace 已命名"} />
          <SetupStep active={Boolean(trimmedSpace)} done={agent.readiness?.state === "ready"} label={agent.readiness?.state === "ready" ? "检测通过" : "等待检测"} />
        </div>
      )}
      {selectedNodeId && setupInstructions && (
        <div className="mt-3 rounded-md bg-white p-2 ring-1 ring-violet-100">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="text-[11px] font-medium text-violet-800">{setupInstructions.title}</span>
              <p className="mt-0.5 text-[11px] text-violet-500">
                {agent.agent_type === "hermes"
                  ? "Hermes 已确认支持 profile；在 Agent 本机创建后，平台会按该 profile 路由问题。"
                  : "在 OpenClaw 运行端使用这个 workspace 隔离知识和会话。"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => copyCommand(setupInstructions.command)}
              className="rounded-md bg-violet-50 px-2 py-1 text-[11px] font-medium text-violet-700 hover:bg-violet-100"
            >
              {copied ? "已复制" : "复制命令"}
            </button>
          </div>
          <code className="block max-w-full overflow-x-auto whitespace-pre rounded bg-gray-950 px-3 py-2 font-mono text-[12px] leading-5 text-white">
            {setupInstructions.command}
          </code>
        </div>
      )}
      {selectedNodeId && !setupInstructions && (
        <p className="mt-2 text-[11px] text-violet-600">
          当前接入：{selectedNode?.name || selectedNodeId}。填写 {profileLabel} 后会生成本机初始化命令。
        </p>
      )}
    </div>
  );
}

function SetupStep({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <div className={`rounded-md border px-2 py-1 ${done ? "border-emerald-100 bg-emerald-50 text-emerald-700" : active ? "border-violet-100 bg-white text-violet-700" : "border-gray-100 bg-white/60 text-gray-400"}`}>
      <span className={`mr-1 inline-block h-1.5 w-1.5 rounded-full ${done ? "bg-emerald-500" : active ? "bg-violet-500" : "bg-gray-300"}`} />
      {label}
    </div>
  );
}

function AgentHealthView({ agent }: { agent: Agent }) {
  const health = agent.health_summary;
  if (!health) return null;
  const riskClass = health.risk_level === "high"
    ? "border-red-100 bg-red-50 text-red-700"
    : health.risk_level === "watch"
      ? "border-amber-100 bg-amber-50 text-amber-700"
      : "border-emerald-100 bg-emerald-50 text-emerald-700";
  return (
    <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${riskClass}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">健康状态：{agentHealthLabel(health.risk_level)}</span>
        {health.needs_review && <span className="rounded bg-white/70 px-2 py-0.5">自动匹配转人工审核</span>}
      </div>
      <div className="mt-1 flex flex-wrap gap-2 opacity-90">
        <span>负反馈 {health.negative_feedback}</span>
        <span>纠错 {health.owner_corrections}</span>
        <span>风险 {health.owner_risk_notes}</span>
        <span>下次注意 {health.avoid_next_time_count}</span>
      </div>
    </div>
  );
}

function agentHealthLabel(value: NonNullable<Agent["health_summary"]>["risk_level"]) {
  return {
    healthy: "健康",
    watch: "观察",
    high: "高风险",
  }[value];
}

function visibilityLabel(value: AgentVisibility) {
  return {
    public: "公开发现",
    followers: "关注者可见",
    friends: "好友可见",
    archived: "停止服务",
  }[value] || "公开发现";
}

function serviceModeLabel(value: AgentServiceMode) {
  return {
    auto_match: "可自动匹配",
    direct_only: "仅定向提问",
    stopped: "不提供服务",
  }[value] || "可自动匹配";
}

function knowledgeScopeLabel(value: KnowledgeScope) {
  return {
    private: "仅本 Agent",
    shared: "共享知识",
    disabled: "不用知识",
  }[value] || "仅本 Agent";
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
  const canCheck = !checking;
  const label = agent.status === "online" ? meta.label : "待接入";
  const boxClass = agent.status === "online" ? meta.box : "border-gray-100 bg-gray-50 text-gray-600";
  const dotClass = agent.status === "online" ? meta.dot : "bg-gray-400";
  const [copied, setCopied] = useState(false);

  async function copyCommand(command: string) {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className={`mt-4 rounded-lg border px-3 py-2 text-xs ${boxClass}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${dotClass}`} />
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
        <div className="mt-3 rounded-md bg-white p-2 ring-1 ring-black/5">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-[11px] font-medium text-amber-700">在 Hermes Agent 机器执行下面命令</span>
            <button
              type="button"
              onClick={() => copyCommand(readiness.command || "")}
              className="rounded-md bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-100"
            >
              {copied ? "已复制" : "复制命令"}
            </button>
          </div>
          <code className="block max-w-full overflow-x-auto whitespace-pre rounded bg-gray-950 px-3 py-2 font-mono text-[12px] leading-5 text-white">
            {readiness.command}
          </code>
        </div>
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
  state: AgentEditState;
  onChange: (value: AgentEditState) => void;
}) {
  return (
    <div className="space-y-3">
      <div>
        <h4 className="text-sm font-semibold text-gray-900">2. 配置 Profile 能力</h4>
        <p className="mt-1 text-xs text-gray-500">这里定义这个 Profile 具体擅长回答什么、能用哪些工具、哪些问题不接。</p>
      </div>
      <input value={state.tags} onChange={e => onChange({ ...state, tags: e.target.value })}
        placeholder="匹配标签，例如 魔兽世界、游戏攻略、AI"
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
      <textarea value={state.description} onChange={e => onChange({ ...state, description: e.target.value })}
        placeholder="Profile 说明，例如这个分身适合回答哪些问题、依据什么知识回答"
        rows={3}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" />
      <CreateProfileFields value={state.profile} onChange={profile => onChange({ ...state, profile })} />
      <ServiceSettingsFields state={state} onChange={onChange} />
      <QuotaSettingsFields state={state} onChange={onChange} />
    </div>
  );
}

function ServiceSettingsFields({
  state,
  onChange,
}: {
  state: AgentEditState;
  onChange: (value: AgentEditState) => void;
}) {
  const rules = state.service_rules;
  const updateRule = (key: keyof AgentServiceRules, value: number) => {
    onChange({ ...state, service_rules: normalizeServiceRules({ ...rules, [key]: value }) });
  };

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium text-gray-600">服务设置</span>
        <span className="text-gray-400">控制谁能看到、是否自动匹配、以及回答计费边界</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block">
          <span className="block text-xs text-gray-500 mb-1">可见范围</span>
          <select
            value={state.visibility}
            onChange={e => onChange({ ...state, visibility: e.target.value as AgentVisibility })}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-white text-sm"
          >
            <option value="public">公开发现</option>
            <option value="followers">关注者可见</option>
            <option value="friends">好友可见</option>
            <option value="archived">停止服务</option>
          </select>
        </label>
        <label className="block">
          <span className="block text-xs text-gray-500 mb-1">服务模式</span>
          <select
            value={state.service_mode}
            onChange={e => onChange({ ...state, service_mode: e.target.value as AgentServiceMode })}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-white text-sm"
          >
            <option value="auto_match">可自动匹配</option>
            <option value="direct_only">仅定向提问</option>
            <option value="stopped">不提供服务</option>
          </select>
        </label>
        <NumberField label="价格倍率" value={rules.price_multiplier} min={0.1} max={10} step={0.1} onChange={v => updateRule("price_multiplier", v)} />
        <NumberField label="最大追问深度" value={rules.max_followup_depth} min={0} max={10} step={1} onChange={v => updateRule("max_followup_depth", v)} />
        <NumberField label="单次最低燃值" value={rules.min_fuel_per_answer} min={0} max={100000} step={100} onChange={v => updateRule("min_fuel_per_answer", v)} />
        <NumberField label="单次最高燃值" value={rules.max_fuel_per_answer} min={1} max={100000} step={100} onChange={v => updateRule("max_fuel_per_answer", v)} />
        <NumberField label="单用户每日提问" value={rules.max_questions_per_user_per_day} min={1} max={100} step={1} onChange={v => updateRule("max_questions_per_user_per_day", v)} />
        <NumberField label="每日燃值上限" value={rules.max_fuel_per_day} min={1} max={1000000} step={1000} onChange={v => updateRule("max_fuel_per_day", v)} />
      </div>
    </div>
  );
}

function QuotaSettingsFields({
  state,
  onChange,
}: {
  state: AgentEditState;
  onChange: (value: AgentEditState) => void;
}) {
  const quota = normalizeQuota(state.daily_quota_config);
  const updateQuota = (key: keyof AgentEditState["daily_quota_config"], value: number) => {
    onChange({ ...state, daily_quota_config: normalizeQuota({ ...quota, [key]: value }) });
  };

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium text-gray-600">每日门限</span>
        <span className="text-gray-400">超过自动阈值后进入审核，达到上限后停止匹配</span>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <NumberField label="每日上限" value={quota.max} min={1} max={1000} step={1} onChange={v => updateQuota("max", v)} />
        <NumberField label="自动回答阈值" value={quota.auto_threshold} min={0} max={1000} step={1} onChange={v => updateQuota("auto_threshold", v)} />
        <NumberField label="紧急保留" value={quota.emergency_reserve} min={0} max={1000} step={1} onChange={v => updateQuota("emergency_reserve", v)} />
      </div>
    </div>
  );
}

function PermissionSettingsFields({
  agent,
  state,
  onChange,
}: {
  agent: Agent;
  state: AgentEditState;
  onChange: (value: AgentEditState) => void;
}) {
  const profile = normalizePermissionProfile(state.permission_profile);
  const update = (patch: Partial<AgentPermissionProfile>) => {
    onChange({ ...state, permission_profile: normalizePermissionProfile({ ...profile, ...patch }) });
  };
  const command = permissionApplyCommand(profile);

  return (
    <div className="mt-4 rounded-lg border border-cyan-100 bg-cyan-50 p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium text-cyan-800">运行权限</span>
        <span className="text-cyan-600">网页只定义策略；真正授权需要在 Agent 所在机器执行脚本</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block">
          <span className="block text-xs text-cyan-700 mb-1">权限档位</span>
          <select
            value={profile.level}
            onChange={e => update({ level: e.target.value as AgentPermissionProfile["level"] })}
            className="w-full px-3 py-2 border border-cyan-100 rounded-lg bg-white text-sm"
          >
            <option value="strict">严格：只回答，不主动用工具</option>
            <option value="balanced">平衡：允许读取平台附件</option>
            <option value="expanded">扩展：可做更多本机辅助分析</option>
          </select>
        </label>
        <NumberField
          label="最长运行分钟"
          value={profile.max_runtime_minutes}
          min={1}
          max={120}
          step={1}
          onChange={v => update({ max_runtime_minutes: v })}
        />
        <SelectPermissionField
          label="网络范围"
          value={profile.network_scope}
          onChange={v => update({ network_scope: v as AgentPermissionProfile["network_scope"] })}
          options={[["none", "不主动联网"], ["agentmint_files", "仅平台附件"], ["web", "允许网页检索"]]}
        />
        <SelectPermissionField
          label="Shell 范围"
          value={profile.shell_scope}
          onChange={v => update({ shell_scope: v as AgentPermissionProfile["shell_scope"] })}
          options={[["none", "禁止"], ["python_readonly", "只允许本地 Python 分析"], ["owner_approval", "需要主人审批"]]}
        />
        <SelectPermissionField
          label="文件范围"
          value={profile.file_scope}
          onChange={v => update({ file_scope: v as AgentPermissionProfile["file_scope"] })}
          options={[["none", "不读文件"], ["agentmint_temp", "仅 AgentMint 临时附件"]]}
        />
        <label className="flex items-center gap-2 rounded-lg border border-cyan-100 bg-white px-3 py-2 text-sm text-cyan-800">
          <input
            type="checkbox"
            checked={profile.allow_high_risk}
            disabled={profile.level !== "expanded"}
            onChange={e => update({ allow_high_risk: e.target.checked })}
          />
          允许高风险动作提示
        </label>
      </div>
      <div className="mt-3 rounded-lg border border-cyan-100 bg-white p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-cyan-800">Agent 端执行</span>
          <span className="text-[11px] text-cyan-600">保存后，在运行 {agent.name} 的机器执行</span>
        </div>
        <pre className="whitespace-pre-wrap break-all rounded bg-gray-950 px-3 py-2 font-mono text-xs text-cyan-50">{command}</pre>
      </div>
    </div>
  );
}

function SelectPermissionField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="block">
      <span className="block text-xs text-cyan-700 mb-1">{label}</span>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full px-3 py-2 border border-cyan-100 rounded-lg bg-white text-sm"
      >
        {options.map(([key, labelText]) => (
          <option key={key} value={key}>{labelText}</option>
        ))}
      </select>
    </label>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block">
      <span className="block text-xs text-gray-500 mb-1">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-white text-sm"
      />
    </label>
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

function LearnedProfileView({ profile }: { profile?: AgentLearnedProfile }) {
  if (!profile) return null;
  const groups = [
    ["领域", profile.domain_tags],
    ["能力", profile.capability_tags],
    ["工具", profile.tool_tags],
    ["风格", profile.style_tags],
    ["正向", profile.positive_tags],
    ["负向", profile.negative_tags],
  ] as const;
  const context = profile.owner_experience_context;
  const contextGroups = [
    ["纠错", context?.corrections],
    ["版本", context?.version_updates],
    ["风险", context?.risk_notes],
    ["高价值", context?.high_value_experiences],
  ] as const;
  if (
    !profile.sample_count
    && !groups.some(([, values]) => values?.length)
    && !contextGroups.some(([, values]) => values?.length)
  ) return null;

  return (
    <div className="mt-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium text-gray-600">系统学习</span>
        <span className="text-gray-400">{profile.sample_count || 0} 样本</span>
        <span className="text-gray-400">+{profile.positive_feedback || 0}</span>
        <span className="text-gray-400">-{profile.negative_feedback || 0}</span>
      </div>
      <div className="space-y-1.5">
        {groups.map(([label, values]) => values?.length ? (
          <div key={label} className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-gray-400">{label}</span>
            {values.map(value => (
              <span key={`${label}-${value}`} className="rounded bg-white px-2 py-0.5 text-gray-600">
                {value}
              </span>
            ))}
          </div>
        ) : null)}
        {contextGroups.map(([label, values]) => values?.length ? (
          <div key={label} className="flex flex-wrap items-start gap-1.5 text-xs">
            <span className="mt-0.5 text-gray-400">{label}</span>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              {values.map(value => (
                <span key={`${label}-${value}`} className="rounded border border-amber-100 bg-amber-50 px-2 py-1 text-amber-800">
                  {value}
                </span>
              ))}
            </div>
          </div>
        ) : null)}
      </div>
    </div>
  );
}

function LearnedProfileReviewPanel({
  agent,
  onReview,
}: {
  agent: Agent;
  onReview: (field: AgentProfileTagField, value: string, action: "accept" | "reject") => void;
}) {
  const review = agent.learned_profile_review;
  if (!review) return null;
  const groups = [
    ["领域", "domain_tags"],
    ["能力", "capability_tags"],
    ["工具", "tool_tags"],
    ["风格", "style_tags"],
    ["正向", "positive_tags"],
    ["负向", "negative_tags"],
  ] as const;
  const hasPending = groups.some(([, field]) => review.pending?.[field]?.length);
  const hasAccepted = groups.some(([, field]) => review.accepted?.[field]?.length);
  const hasRejected = groups.some(([, field]) => review.rejected?.[field]?.length);
  if (!hasPending && !hasAccepted && !hasRejected) return null;

  return (
    <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium text-blue-700">系统学习审核</span>
        <span className="text-blue-500">确认后会进入主人设定；拒绝后不再作为建议显示</span>
      </div>
      <div className="space-y-3">
        {groups.map(([label, field]) => {
          const pending = review.pending?.[field] || [];
          const accepted = review.accepted?.[field] || [];
          const rejected = review.rejected?.[field] || [];
          if (!pending.length && !accepted.length && !rejected.length) return null;
          return (
            <div key={field} className="space-y-1.5">
              <p className="text-xs font-medium text-gray-500">{label}</p>
              {pending.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {pending.map(value => (
                    <span key={`${field}-${value}`} className="inline-flex items-center gap-1 rounded bg-white px-2 py-1 text-xs text-gray-700 ring-1 ring-blue-100">
                      {value}
                      <button type="button" onClick={() => onReview(field, value, "accept")} className="text-emerald-600 hover:underline">确认</button>
                      <button type="button" onClick={() => onReview(field, value, "reject")} className="text-red-500 hover:underline">拒绝</button>
                    </span>
                  ))}
                </div>
              )}
              {accepted.length > 0 && (
                <ReviewTagRow label="已确认" values={accepted} className="bg-emerald-50 text-emerald-700" />
              )}
              {rejected.length > 0 && (
                <ReviewTagRow label="已拒绝" values={rejected} className="bg-red-50 text-red-500" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ReviewTagRow({ label, values, className }: { label: string; values: string[]; className: string }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-gray-400">{label}</span>
      {values.map(value => (
        <span key={`${label}-${value}`} className={`rounded px-2 py-0.5 ${className}`}>
          {value}
        </span>
      ))}
    </div>
  );
}

function splitList(value: string) {
  return value.split(/[,\n;；，、]+/).map(item => item.trim()).filter(Boolean);
}

function defaultRuntimeSpaceName(name: string, fallbackId: string) {
  const cleaned = (name || "").trim().replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return cleaned.slice(0, 48) || fallbackId;
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

function normalizeServiceRules(rules?: Partial<AgentServiceRules>): AgentServiceRules {
  const price = Number(rules?.price_multiplier ?? 1);
  const depth = Math.trunc(Number(rules?.max_followup_depth ?? 2));
  const minFuel = Math.trunc(Number(rules?.min_fuel_per_answer ?? 0));
  const maxFuel = Math.trunc(Number(rules?.max_fuel_per_answer ?? 100000));
  const maxQuestionsPerUser = Math.trunc(Number(rules?.max_questions_per_user_per_day ?? 20));
  const maxFuelPerDay = Math.trunc(Number(rules?.max_fuel_per_day ?? 1000000));
  const safeMax = Number.isFinite(maxFuel) && maxFuel > 0 ? Math.min(maxFuel, 100000) : 100000;
  const safeMin = Number.isFinite(minFuel) && minFuel >= 0 ? Math.min(minFuel, safeMax) : 0;
  return {
    price_multiplier: Number.isFinite(price) && price > 0 ? Math.min(price, 10) : 1,
    max_followup_depth: Number.isFinite(depth) ? Math.max(0, Math.min(depth, 10)) : 2,
    min_fuel_per_answer: safeMin,
    max_fuel_per_answer: safeMax,
    max_questions_per_user_per_day: Number.isFinite(maxQuestionsPerUser) && maxQuestionsPerUser > 0 ? Math.min(maxQuestionsPerUser, 100) : 20,
    max_fuel_per_day: Number.isFinite(maxFuelPerDay) && maxFuelPerDay > 0 ? Math.min(maxFuelPerDay, 1000000) : 1000000,
  };
}

function normalizePermissionProfile(profile?: Partial<AgentPermissionProfile>): AgentPermissionProfile {
  const level = profile?.level;
  const network = profile?.network_scope;
  const shell = profile?.shell_scope;
  const files = profile?.file_scope;
  const runtime = Math.trunc(Number(profile?.max_runtime_minutes ?? 10));
  const safeLevel: AgentPermissionProfile["level"] =
    level === "strict" || level === "balanced" || level === "expanded" ? level : "balanced";
  return {
    level: safeLevel,
    network_scope: network === "none" || network === "agentmint_files" || network === "web" ? network : "agentmint_files",
    shell_scope: shell === "none" || shell === "python_readonly" || shell === "owner_approval" ? shell : "none",
    file_scope: files === "none" || files === "agentmint_temp" ? files : "agentmint_temp",
    max_runtime_minutes: Number.isFinite(runtime) ? Math.max(1, Math.min(runtime, 120)) : 10,
    allow_high_risk: safeLevel === "expanded" && Boolean(profile?.allow_high_risk),
  };
}

function permissionApplyCommand(profile: AgentPermissionProfile) {
  return [
    "git pull",
    `python connector/hermes-plugin/permissions.py apply --profile ${profile.level}`,
    "python connector/hermes-plugin/permissions.py doctor",
    "hermes gateway",
  ].join("\n");
}

function normalizeQuota(quota?: Partial<AgentEditState["daily_quota_config"]>) {
  const max = Math.trunc(Number(quota?.max ?? 50));
  const auto = Math.trunc(Number(quota?.auto_threshold ?? 40));
  const reserve = Math.trunc(Number(quota?.emergency_reserve ?? 3));
  const safeMax = Number.isFinite(max) && max > 0 ? Math.min(max, 1000) : 50;
  const safeAuto = Number.isFinite(auto) ? Math.max(0, Math.min(auto, safeMax)) : Math.min(40, safeMax);
  return {
    max: safeMax,
    auto_threshold: safeAuto,
    emergency_reserve: Number.isFinite(reserve) ? Math.max(0, Math.min(reserve, safeMax)) : 3,
  };
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
