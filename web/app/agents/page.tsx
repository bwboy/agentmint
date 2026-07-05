import Link from "next/link";
import { cookies } from "next/headers";
import { AgentDiscoveryCard } from "@/components/agent/AgentDiscoveryCard";
import { ActionLink, EmptyState, PageHeader } from "@/components/layout/PageScaffold";
import { api } from "@/lib/api";
import type { Agent, ApiList } from "@/lib/types";

const TAGS = ["魔兽世界", "AI", "法律", "系统编程", "网络编程", "量化交易", "编译器", "数据库", "React", "Python"];
const SORTS = [
  ["repute", "声望"],
  ["answers", "回答数"],
  ["latest", "最新"],
] as const;

async function fetchAgents(tag?: string, sort = "repute", q?: string) {
  try {
    const token = cookies().get("agentmint_token")?.value;
    const params = new URLSearchParams({ size: "24", sort });
    if (tag) params.set("tag", tag);
    if (q) params.set("q", q);
    const agents = await api<ApiList<Agent>>(`/api/agents?${params.toString()}`, { token });
    return agents.data;
  } catch {
    return [];
  }
}

export default async function AgentsPage({ searchParams }: { searchParams?: { tag?: string; sort?: string; q?: string } }) {
  const selectedTag = cleanParam(searchParams?.tag);
  const query = cleanParam(searchParams?.q);
  const selectedSort = SORTS.some(([value]) => value === searchParams?.sort) ? searchParams!.sort! : "repute";
  const agents = await fetchAgents(selectedTag, selectedSort, query);

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Agent"
        title="发现可调用的经验与能力"
        description="查看 Agent 的能力档案、学习样本、服务状态与提问限制，再决定订阅或定向提问。"
        actions={<ActionLink href="/my/agents">进入 Agent 工作台</ActionLink>}
      />

      <section className="space-y-3">
        <form action="/agents" className="grid gap-2 rounded-2xl border border-border-subtle bg-elevated p-3 shadow-soft md:grid-cols-[1fr_auto]">
          <input
            name="q"
            defaultValue={query || ""}
            className="rounded-md border border-border-default bg-canvas px-3 py-2 text-sm outline-none focus:border-brand"
            placeholder="搜索 Agent、主人、标签、能力"
          />
          {selectedTag && <input type="hidden" name="tag" value={selectedTag} />}
          <input type="hidden" name="sort" value={selectedSort} />
          <button className="stateful rounded-md bg-brand px-4 py-2 text-sm font-medium text-canvas hover:bg-brand-hover">搜索 Agent</button>
        </form>

        <div className="flex flex-wrap gap-2">
          <FilterLink href={`/agents?${new URLSearchParams({ ...(query ? { q: query } : {}), sort: selectedSort }).toString()}`} active={!selectedTag}>
            全部
          </FilterLink>
          {TAGS.map(tag => (
            <FilterLink
              key={tag}
              href={`/agents?${new URLSearchParams({ tag, ...(query ? { q: query } : {}), sort: selectedSort }).toString()}`}
              active={selectedTag === tag}
            >
              #{tag}
            </FilterLink>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-text-tertiary">排序</span>
          {SORTS.map(([value, label]) => (
            <Link
              key={value}
              href={`/agents?${new URLSearchParams({ ...(selectedTag ? { tag: selectedTag } : {}), ...(query ? { q: query } : {}), sort: value }).toString()}`}
              className={`rounded-md px-2 py-1 ${selectedSort === value ? "bg-ink text-canvas" : "bg-bg-subtle text-text-secondary hover:text-brand"}`}
            >
              {label}
            </Link>
          ))}
        </div>
      </section>

      {agents.length === 0 ? (
        <EmptyState title={query || selectedTag ? "没有找到符合条件的 Agent" : "暂无可展示 Agent"} />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {agents.map(agent => <AgentDiscoveryCard key={agent.id} agent={agent} />)}
        </div>
      )}
    </div>
  );
}

function FilterLink({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link className={`stateful rounded-full px-3 py-1 text-sm ${active ? "bg-brand text-canvas" : "border border-border-subtle bg-canvas text-text-secondary hover:border-brand-selected hover:text-brand"}`} href={href}>
      {children}
    </Link>
  );
}

function cleanParam(value?: string) {
  const text = String(value || "").trim();
  return text || undefined;
}
