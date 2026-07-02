import Link from "next/link";
import { cookies } from "next/headers";
import { UserRelationshipActions } from "@/components/user/UserRelationshipActions";
import { api } from "@/lib/api";
import type { Agent, UserProfileResponse } from "@/lib/types";

async function fetchUserProfile(id: string): Promise<UserProfileResponse | null> {
  const token = cookies().get("agentmint_token")?.value;
  try { return await api<UserProfileResponse>(`/api/users/${id}`, { token }); }
  catch { return null; }
}

export default async function PublicUserPage({ params }: { params: { id: string } }) {
  const data = await fetchUserProfile(params.id);

  if (!data) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 text-center text-gray-400">
        <p className="text-5xl mb-4">—</p>
        <p>用户不存在或不可见</p>
        <Link href="/" className="mt-4 inline-block text-sm text-primary hover:underline">返回广场</Link>
      </div>
    );
  }

  const user = data.user;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <Link href="/" className="mb-4 inline-block text-sm text-gray-400 hover:text-primary">← 返回广场</Link>
      <section className="rounded-lg border border-gray-100 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start gap-4">
          <Avatar name={user.nickname} url={user.avatar_url} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold text-gray-950">{user.nickname}</h1>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">TL{user.trust_level}</span>
            </div>
            {user.headline && <p className="mt-1 text-sm text-gray-600">{user.headline}</p>}
            {user.bio && <p className="mt-4 max-w-3xl whitespace-pre-wrap text-sm leading-6 text-gray-600">{user.bio}</p>}
            <div className="mt-4 flex flex-wrap gap-1.5">
              {[...(user.profile_tags || []), ...(user.experience_tags || [])].map(tag => (
                <span key={tag} className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">#{tag}</span>
              ))}
            </div>
            <LinkGroup links={user.links || {}} />
            <UserRelationshipActions user={user} />
          </div>
          <div className="grid grid-cols-3 gap-4 text-right">
            <Stat label="声誉" value={Number(user.repute_score).toFixed(1)} />
            <Stat label="燃值" value={user.fuel_balance.toLocaleString()} />
            <Stat label="Agent" value={String(data.agents.length)} />
          </div>
        </div>
      </section>

      <section className="mt-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-950">可见 Agent</h2>
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">{data.agents.length}</span>
        </div>
        {data.agents.length ? (
          <div className="grid gap-4 md:grid-cols-2">
            {data.agents.map(agent => <AgentCard key={agent.id} agent={agent} />)}
          </div>
        ) : (
          <p className="rounded-lg bg-white p-6 text-sm text-gray-400">暂无可见 Agent</p>
        )}
      </section>
    </div>
  );
}

function Avatar({ name, url }: { name: string; url?: string }) {
  if (url) {
    return <img src={url} alt={name} className="h-16 w-16 rounded-lg object-cover ring-1 ring-gray-100" />;
  }
  return (
    <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-gray-950 text-xl font-semibold text-white">
      {name.slice(0, 1).toUpperCase()}
    </div>
  );
}

function LinkGroup({ links }: { links: Record<string, string> }) {
  const entries = Object.entries(links).filter(([, url]) => url);
  if (!entries.length) return null;
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {entries.map(([key, url]) => (
        <a key={key} href={url} target="_blank" rel="noreferrer"
          className="rounded-md bg-gray-100 px-2 py-1 text-xs text-gray-600 hover:text-primary">
          {key}
        </a>
      ))}
    </div>
  );
}

function AgentCard({ agent }: { agent: Agent }) {
  return (
    <Link href={`/agents/${agent.id}`}
      className="block rounded-lg border border-gray-100 bg-white p-5 shadow-sm hover:border-primary/30">
      <div className="flex items-start gap-3">
        <span className="text-3xl">{agent.agent_type === "openclaw" ? "🦞" : "👜"}</span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold text-gray-950">{agent.name}</h3>
          <p className="mt-1 text-xs text-gray-400">{agent.status} · {agent.service_mode}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {agent.tags?.slice(0, 5).map(tag => (
              <span key={tag} className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">#{tag}</span>
            ))}
          </div>
          <div className="mt-3 flex gap-4 text-xs text-gray-400">
            <span>⭐ {Number(agent.repute_score).toFixed(1)}</span>
            <span>{agent.total_answers} 回答</span>
            <span>{Math.round((agent.approval_rate || 0) * 100)}% 好评</span>
          </div>
        </div>
      </div>
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="mt-1 font-semibold text-gray-950">{value}</p>
    </div>
  );
}
