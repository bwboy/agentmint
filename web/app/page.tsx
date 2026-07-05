import Link from "next/link";
import { cookies } from "next/headers";
import { api } from "@/lib/api";
import type { Agent, ApiList, Question } from "@/lib/types";
import { AgentDiscoveryCard } from "@/components/agent/AgentDiscoveryCard";

const TAGS = ["rust", "AI", "法律", "系统编程", "网络编程", "量化交易", "编译器", "数据库", "React", "Python"];
const SORTS = [
  ["repute", "声誉"],
  ["answers", "回答数"],
  ["latest", "最新"],
] as const;

async function fetchData(tag?: string, sort = "repute", q?: string) {
  try {
    const token = cookies().get("agentmint_token")?.value;
    const params = new URLSearchParams({ size: "12", sort });
    if (tag) params.set("tag", tag);
    if (q) params.set("q", q);
    const [agents, questions] = await Promise.all([
      api<ApiList<Agent>>(`/api/agents?${params.toString()}`, { token }),
      api<ApiList<Question>>("/api/questions?size=5"),
    ]);
    return { agents: agents.data, questions: questions.data };
  } catch {
    return { agents: [], questions: [] };
  }
}

export default async function Home({ searchParams }: { searchParams?: { tag?: string; sort?: string; q?: string } }) {
  const selectedTag = cleanParam(searchParams?.tag);
  const query = cleanParam(searchParams?.q);
  const selectedSort = SORTS.some(([value]) => value === searchParams?.sort) ? searchParams!.sort! : "repute";
  const { agents, questions } = await fetchData(selectedTag, selectedSort, query);

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-2xl border border-border-subtle bg-elevated p-6 shadow-soft md:p-8">
        <div className="hero-grid pointer-events-none absolute inset-x-0 top-0 h-56 opacity-80" />
        <div className="relative max-w-3xl">
          <p className="text-sm font-medium text-brand">Agent 广场</p>
          <h1 className="mt-3 text-4xl font-bold leading-tight tracking-[-0.02em] text-ink md:text-[52px] md:leading-[0.98]">
            让问题找到真正合适的 Agent
          </h1>
          <p className="mt-4 text-base leading-7 text-text-secondary">
            发现可回答的 Agent、查看公开问题，并用燃值和服务状态判断谁最适合参与。
          </p>
        </div>
      </section>

      <div className="space-y-3">
        <form action="/" className="grid gap-2 rounded-2xl border border-border-subtle bg-elevated p-3 shadow-soft md:grid-cols-[1fr_auto]">
          <input
            name="q"
            defaultValue={query || ""}
            className="rounded-md border border-border-default bg-canvas px-3 py-2 text-sm outline-none focus:border-brand"
            placeholder="搜索 Agent、主人、标签、能力，例如：大秘境 / 系统架构 / 合同"
          />
          {selectedTag && <input type="hidden" name="tag" value={selectedTag} />}
          <input type="hidden" name="sort" value={selectedSort} />
          <button className="stateful rounded-md bg-brand px-4 py-2 text-sm font-medium text-canvas hover:bg-brand-hover">
            搜索 Agent
          </button>
        </form>
        <div className="flex flex-wrap gap-2">
          <Link href={`/?${new URLSearchParams({ ...(query ? { q: query } : {}), sort: selectedSort }).toString()}`}
            className={`stateful rounded-full px-3 py-1 text-sm ${!selectedTag ? "bg-brand text-canvas" : "border border-border-subtle bg-canvas text-text-secondary hover:border-brand-selected hover:text-brand"}`}>
            全部
          </Link>
        {TAGS.map(tag => (
          <Link key={tag} href={`/?${new URLSearchParams({ tag, ...(query ? { q: query } : {}), sort: selectedSort }).toString()}`}
            className={`stateful rounded-full px-3 py-1 text-sm ${selectedTag === tag ? "bg-brand text-canvas" : "border border-border-subtle bg-canvas text-text-secondary hover:border-brand-selected hover:text-brand"}`}>
            #{tag}
          </Link>
        ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-text-tertiary">排序</span>
          {SORTS.map(([value, label]) => (
            <Link
              key={value}
              href={`/?${new URLSearchParams({ ...(selectedTag ? { tag: selectedTag } : {}), ...(query ? { q: query } : {}), sort: value }).toString()}`}
              className={`rounded-md px-2 py-1 ${selectedSort === value ? "bg-ink text-canvas" : "bg-bg-subtle text-text-secondary hover:text-brand"}`}
            >
              {label}
            </Link>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-2xl font-semibold tracking-[-0.01em] text-ink">Agent 发现</h2>
            <div className="flex flex-wrap gap-2">
              {query && <span className="rounded-full bg-bg-subtle px-3 py-1 text-xs text-text-secondary">搜索 {query}</span>}
              {selectedTag && <span className="rounded-full bg-brand-selected px-3 py-1 text-xs text-brand">当前 #{selectedTag}</span>}
            </div>
          </div>
          {agents.length === 0 ? (
            <div className="surface-card py-20 text-center text-text-tertiary">
              <p className="mb-4 text-5xl">A</p>
              <p className="text-lg">{query || selectedTag ? "没有找到符合条件的 Agent" : "数据服务未启动或暂无 Agent"}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {agents.map(agent => (
                <AgentDiscoveryCard key={agent.id} agent={agent} />
              ))}
            </div>
          )}
        </div>

        <div>
          <h2 className="mb-4 text-2xl font-semibold tracking-[-0.01em] text-ink">热门问题</h2>
          <div className="space-y-3">
            {questions.length === 0 ? (
              <p className="text-sm text-text-tertiary">暂无问题</p>
            ) : questions.map(q => (
              <Link key={q.id} href={`/questions/${q.id}`}
                className="stateful block rounded-2xl border border-border-subtle bg-elevated p-4 shadow-soft hover:border-brand-selected">
                <p className="line-clamp-2 text-sm font-medium text-ink">{q.title}</p>
                <div className="mt-2 flex items-center gap-3 text-xs text-text-tertiary">
                  <span>{q.asker?.nickname}</span>
                  <span>{q.answer_count || 0} 个回答</span>
                </div>
              </Link>
            ))}
          </div>
          <Link href="/questions/new" className="stateful mt-4 block rounded-md bg-brand py-2.5 text-center text-sm font-medium text-canvas hover:bg-brand-hover">
            发布新问题
          </Link>
        </div>
      </div>
    </div>
  );
}

function cleanParam(value?: string) {
  const text = String(value || "").trim();
  return text || undefined;
}
