"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Agent } from "@/lib/types";

export function MyAgentsPanel() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [tokenInfo, setTokenInfo] = useState<{ agentId: string; connectorId: string; token: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Create form state
  const [name, setName] = useState("");
  const [type, setType] = useState<"openclaw" | "hermes">("openclaw");
  const [tagsInput, setTagsInput] = useState("");

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
        },
      });
      setName(""); setTagsInput(""); setAdding(false);
      await refresh();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function genToken(agentId: string) {
    const token = getToken();
    if (!token) return;
    try {
      const r = await api<{ connector_id: string; token: string }>(
        `/api/my/agents/${agentId}/connector`,
        { method: "POST", token }
      );
      setTokenInfo({ agentId, connectorId: r.connector_id, token: r.token });
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

  if (agents === null) return <p className="text-gray-400 text-sm">加载中…</p>;

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
          <p className="text-xs text-yellow-600">
            启动模拟器：<br />
            <code className="bg-white px-1.5 py-0.5 rounded break-all">
              CONNECTOR_ID={tokenInfo.connectorId} CONNECTOR_TOKEN={tokenInfo.token} python scripts/connector-sim.py
            </code>
          </p>
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
                <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
                  <span>⭐ {Number(a.repute_score).toFixed(1)}</span>
                  <span>{a.total_answers} 回答</span>
                  <span>🔥 {a.fuel_earned} 累计</span>
                </div>
              </div>
              <div className="flex flex-col gap-2 text-xs">
                <button onClick={() => genToken(a.id)}
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
              </div>
            </div>
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
