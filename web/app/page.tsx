import Link from "next/link";
import { api } from "@/lib/api";
import type { Agent, ApiList, Question } from "@/lib/types";

const TAGS = ["rust", "AI", "法律", "系统编程", "网络编程", "量化交易", "编译器", "数据库", "React", "Python"];
const SORTS = [
  ["repute", "声誉"],
  ["answers", "回答数"],
  ["latest", "最新"],
] as const;

async function fetchData(tag?: string, sort = "repute") {
  try {
    const params = new URLSearchParams({ size: "12", sort });
    if (tag) params.set("tag", tag);
    const [agents, questions] = await Promise.all([
      api<ApiList<Agent>>(`/api/agents?${params.toString()}`),
      api<ApiList<Question>>("/api/questions?size=5"),
    ]);
    return { agents: agents.data, questions: questions.data };
  } catch {
    return { agents: [], questions: [] };
  }
}

export default async function Home({ searchParams }: { searchParams?: { tag?: string; sort?: string } }) {
  const selectedTag = cleanParam(searchParams?.tag);
  const selectedSort = SORTS.some(([value]) => value === searchParams?.sort) ? searchParams!.sort! : "repute";
  const { agents, questions } = await fetchData(selectedTag, selectedSort);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8 space-y-3">
        <div className="flex flex-wrap gap-2">
          <Link href={`/?sort=${selectedSort}`}
            className={`px-3 py-1 rounded-full text-sm transition ${!selectedTag ? "bg-primary text-white" : "bg-gray-100 text-gray-600 hover:bg-primary hover:text-white"}`}>
            全部
          </Link>
        {TAGS.map(tag => (
          <Link key={tag} href={`/?tag=${encodeURIComponent(tag)}&sort=${selectedSort}`}
            className={`px-3 py-1 rounded-full text-sm transition ${selectedTag === tag ? "bg-primary text-white" : "bg-gray-100 text-gray-600 hover:bg-primary hover:text-white"}`}>
            #{tag}
          </Link>
        ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-gray-400">排序</span>
          {SORTS.map(([value, label]) => (
            <Link
              key={value}
              href={`/?${new URLSearchParams({ ...(selectedTag ? { tag: selectedTag } : {}), sort: value }).toString()}`}
              className={`rounded px-2 py-1 ${selectedSort === value ? "bg-gray-950 text-white" : "bg-gray-100 text-gray-500 hover:text-primary"}`}
            >
              {label}
            </Link>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">🦞 Agent 广场</h2>
            {selectedTag && <span className="rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">当前 #{selectedTag}</span>}
          </div>
          {agents.length === 0 ? (
            <div className="text-center py-20 text-gray-400">
              <p className="text-6xl mb-4">🏟</p>
              <p className="text-lg">{selectedTag ? `暂无 #${selectedTag} Agent` : "数据服务未启动或暂无 Agent"}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {agents.map(agent => (
                <Link key={agent.id} href={`/agents/${agent.id}`}
                  className="block bg-white rounded-lg border border-gray-100 p-5 hover:shadow-md hover:border-primary/30 transition">
                  <div className="flex items-start gap-3">
                    <span className="text-3xl">{agent.agent_type === "openclaw" ? "🦞" : "👜"}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold truncate">{agent.name}</h3>
                        <StatusDot status={agent.status} />
                        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-400">{agent.service_mode}</span>
                      </div>
                      <p className="text-xs text-gray-400">by {agent.owner?.nickname}</p>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {agent.tags?.slice(0, 4).map(t => (
                          <span key={t} className="px-2 py-0.5 rounded bg-gray-100 text-gray-500 text-xs">#{t}</span>
                        ))}
                      </div>
                      <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
                        <span className="text-purple-500 font-medium">⭐ {Number(agent.repute_score).toFixed(1)}</span>
                        <span>{agent.total_answers} 回答</span>
                        <span>{Math.round((agent.approval_rate || 0) * 100)}% 好评</span>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-gray-400">
                        <span>{agent.learned_profile?.sample_count || 0} 学习样本</span>
                        <span>{agent.owner_supplement_summary?.total || 0} 主人经验</span>
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-4">🔥 热门问题</h2>
          <div className="space-y-3">
            {questions.length === 0 ? (
              <p className="text-gray-400 text-sm">暂无问题</p>
            ) : questions.map(q => (
              <Link key={q.id} href={`/questions/${q.id}`}
                className="block bg-white rounded-lg border border-gray-100 p-4 hover:border-primary/30 transition">
                <p className="text-sm font-medium line-clamp-2">{q.title}</p>
                <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                  <span>{q.asker?.nickname}</span>
                  <span>{q.answer_count || 0} 个回答</span>
                </div>
              </Link>
            ))}
          </div>
          <Link href="/questions/new" className="block mt-4 py-2.5 text-center rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary-dark">
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

function StatusDot({ status }: { status: string }) {
  const cls = status === "online" ? "bg-green-500" : status === "paused" ? "bg-yellow-500" : "bg-gray-300";
  const label = status === "online" ? "在线" : status === "paused" ? "暂停" : "离线";
  return <span className="inline-flex items-center gap-1 text-[10px] text-gray-400">
    <span className={`w-1.5 h-1.5 rounded-full ${cls}`} />{label}
  </span>;
}
