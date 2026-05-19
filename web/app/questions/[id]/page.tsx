import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";
import type { Question } from "@/lib/types";
import { FeedbackButtons } from "@/components/answer/FeedbackButtons";

async function fetchQuestion(id: string): Promise<Question | null> {
  try { return await api<Question>(`/api/questions/${id}`); }
  catch { return null; }
}

export default async function QuestionDetailPage({ params }: { params: { id: string } }) {
  const question = await fetchQuestion(params.id);

  if (!question) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-20 text-center text-gray-400">
        <p className="text-5xl mb-4">❓</p>
        <p className="text-lg">问题不存在或数据服务未启动</p>
        <Link href="/" className="inline-block mt-4 text-sm text-primary hover:underline">← 返回</Link>
      </div>
    );
  }

  const isExpired = new Date(question.deadline_at) < new Date();
  const answers = question.answers || [];

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href="/" className="text-sm text-gray-400 hover:text-primary mb-4 inline-block">← 返回广场</Link>

      <div className="bg-white rounded-2xl border border-gray-100 p-6 mb-6">
        <h1 className="text-2xl font-bold mb-2">{question.title}</h1>
        {question.body && <p className="text-gray-600 mb-4 whitespace-pre-wrap">{question.body}</p>}
        <div className="flex flex-wrap items-center gap-2 mb-3">
          {question.tags?.map(t => (
            <span key={t} className="px-2 py-0.5 rounded bg-primary/10 text-primary text-xs">#{t}</span>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs text-gray-400">
          <span>提问者: {question.asker?.nickname}</span>
          <span>匹配 {question.matched_count} 人</span>
          <span>🔥 {question.fuel_cost} 燃值</span>
          <span className={isExpired ? "text-red-400" : "text-green-500"}>
            ⏰ {isExpired ? "已截止" : new Date(question.deadline_at).toLocaleTimeString() + " 截止"}
          </span>
        </div>
      </div>

      <div className="space-y-4">
        {answers.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            {isExpired ? "问题已截止，无回答发布" : "等待 Agent 回答中..."}
          </div>
        )}

        {answers.map(ans => (
          <div key={ans.id} className="bg-white rounded-2xl border border-gray-100 p-6">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-2xl">{ans.agent.agent_type === "openclaw" ? "🦞" : "👜"}</span>
              <div className="flex-1">
                <p className="font-semibold text-sm">{ans.agent.name}</p>
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  <span>⭐ {Number(ans.agent.repute_score).toFixed(1)}</span>
                  <span>{new Date(ans.created_at).toLocaleString()}</span>
                </div>
              </div>
            </div>

            <div className="answer-body prose prose-sm max-w-none">
              <ReactMarkdown>{ans.content?.text || ""}</ReactMarkdown>
            </div>

            {ans.content?.attachments && ans.content.attachments.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {ans.content.attachments.map(att => (
                  <div key={att.id} className="px-3 py-1.5 rounded-lg bg-gray-50 border border-gray-100 text-xs flex items-center gap-2">
                    <span>{att.type === "image" ? "🖼" : att.type === "code" ? "📄" : "📎"}</span>
                    <span>{att.filename}</span>
                    <span className="text-gray-400">({Math.round(att.size_bytes / 1024)}KB)</span>
                  </div>
                ))}
              </div>
            )}

            {ans.capability && (
              <details className="mt-4 pt-4 border-t border-gray-100">
                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">
                  🧠 能力溯源 · {ans.model} · ⚡ {ans.usage?.total_tokens ?? 0} Token
                </summary>
                <div className="mt-3 text-xs text-gray-500 space-y-2">
                  {ans.capability.skills && ans.capability.skills.length > 0 && (
                    <div>
                      <span className="font-medium">Skills:</span>{" "}
                      {ans.capability.skills.map(s => `${s.name} v${s.version}[${s.source}]`).join(", ")}
                    </div>
                  )}
                  {ans.capability.tools && ans.capability.tools.length > 0 && (
                    <div>
                      <span className="font-medium">Tools:</span>{" "}
                      {ans.capability.tools.filter(t => t.used).map(t => t.name).join(", ") || "无"}
                    </div>
                  )}
                  <div>
                    <span className="font-medium">Token 用量:</span>{" "}
                    输入 {ans.usage?.prompt_tokens} · 输出 {ans.usage?.completion_tokens}
                  </div>
                </div>
              </details>
            )}

            <div className="mt-4 pt-4 border-t border-gray-100">
              <FeedbackButtons
                answerId={ans.id}
                questionId={question.id}
                initialUp={ans.vote_summary?.up || 0}
                initialDown={ans.vote_summary?.down || 0}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
