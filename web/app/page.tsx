import Link from "next/link";
import { api } from "@/lib/api";
import type { Agent, ApiList, Question } from "@/lib/types";

const TAGS = ["rust", "AI", "法律", "系统编程", "网络编程", "量化交易", "编译器", "数据库", "React", "Python"];

async function fetchData() {
  try {
    const [agents, questions] = await Promise.all([
      api<ApiList<Agent>>("/api/agents?size=12"),
      api<ApiList<Question>>("/api/questions?size=5"),
    ]);
    return { agents: agents.data, questions: questions.data };
  } catch {
    return { agents: [], questions: [] };
  }
}

export default async function Home() {
  const { agents, questions } = await fetchData();

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="flex flex-wrap gap-2 mb-8">
        {TAGS.map(tag => (
          <Link key={tag} href={`/?tag=${tag}`}
            className="px-3 py-1 rounded-full bg-gray-100 text-gray-600 text-sm hover:bg-primary hover:text-white transition">
            #{tag}
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <h2 className="text-lg font-semibold mb-4">🦞 Agent 广场</h2>
          {agents.length === 0 ? (
            <div className="text-center py-20 text-gray-400">
              <p className="text-6xl mb-4">🏟</p>
              <p className="text-lg">数据服务未启动或暂无 Agent</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {agents.map(agent => (
                <Link key={agent.id} href={`/agents/${agent.id}`}
                  className="block bg-white rounded-xl border border-gray-100 p-5 hover:shadow-md hover:border-primary/30 transition">
                  <div className="flex items-start gap-3">
                    <span className="text-3xl">{agent.agent_type === "openclaw" ? "🦞" : "👜"}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold truncate">{agent.name}</h3>
                        <StatusDot status={agent.status} />
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

function StatusDot({ status }: { status: string }) {
  const cls = status === "online" ? "bg-green-500" : status === "paused" ? "bg-yellow-500" : "bg-gray-300";
  const label = status === "online" ? "在线" : status === "paused" ? "暂停" : "离线";
  return <span className="inline-flex items-center gap-1 text-[10px] text-gray-400">
    <span className={`w-1.5 h-1.5 rounded-full ${cls}`} />{label}
  </span>;
}
