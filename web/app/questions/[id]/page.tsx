import Link from "next/link";
import { cookies } from "next/headers";
import { api } from "@/lib/api";
import type { Question } from "@/lib/types";
import { FeedbackButtons } from "@/components/answer/FeedbackButtons";
import { AnswerMarkdown } from "@/components/answer/AnswerMarkdown";
import { FollowUpComposer } from "@/components/question/FollowUpComposer";
import { OwnerSupplementRequestButton } from "@/components/question/OwnerSupplementRequestButton";
import { OwnerSupplements } from "@/components/question/OwnerSupplements";
import { QuestionAnswerPoller } from "@/components/question/QuestionAnswerPoller";
import { RewardButton } from "@/components/question/RewardButton";
import {
  answerSettlementSummary,
  answerUsageSignature,
  followupsForAnswer,
  questionAnswersForPolling,
  questionFuelSummary,
  questionPollingDeadline,
} from "@/components/question/QuestionAnswerPoller.logic";
import type { Answer, FollowUpThread } from "@/lib/types";

async function fetchQuestion(id: string): Promise<Question | null> {
  const token = cookies().get("agentmint_token")?.value;
  try { return await api<Question>(`/api/questions/${id}`, { token }); }
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
  const followups = question.followups || [];
  const allAnswersForPolling = questionAnswersForPolling(question);
  const pollingDeadlineAt = questionPollingDeadline(question);
  const fuelSummary = questionFuelSummary(question);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <QuestionAnswerPoller
        questionId={question.id}
        currentAnswerCount={allAnswersForPolling.length}
        currentUsageSignature={answerUsageSignature(allAnswersForPolling)}
        deadlineAt={pollingDeadlineAt}
      />

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
          <span>{question.visibility === "private" ? "私密" : "公开"}</span>
          <span>匹配 {question.matched_count} 人</span>
          {question.reward_fuel > 0 && (
            <span className="text-orange-500">
              奖励 🔥 {question.reward_fuel} · {rewardStatusLabel(question.reward_status)}
            </span>
          )}
          <span className={isExpired ? "text-red-400" : "text-green-500"}>
            ⏰ {isExpired ? "已截止" : new Date(question.deadline_at).toLocaleTimeString() + " 截止"}
          </span>
        </div>
        <QuestionFuelPanel summary={fuelSummary} />
      </div>

      <QuestionRoutingWorkbench question={question} />

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

              <AnswerMarkdown text={ans.content?.text || ""} />
              <OwnerSupplements items={ans.owner_supplements} />
              <AnswerSettlementPanel answer={ans} question={question} />

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
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <FeedbackButtons
                    answerId={ans.id}
                    questionId={question.id}
                    initialUp={ans.vote_summary?.up || 0}
                    initialDown={ans.vote_summary?.down || 0}
                  />
                  <div className="flex flex-wrap justify-end gap-2">
                    {question.reward_status === "pending" && question.reward_fuel > 0 && ans.turn_type !== "followup" && (
                      <RewardButton
                        questionId={question.id}
                        answerId={ans.id}
                        rewardFuel={question.reward_fuel}
                      />
                    )}
                    {question.reward_answer_id === ans.id && (
                      <span className="rounded-lg bg-orange-50 px-3 py-1.5 text-sm font-medium text-orange-600">
                        已获奖励 🔥 {question.reward_fuel}
                      </span>
                    )}
                    <FollowUpComposer
                      questionId={question.id}
                      quotedAnswer={ans}
                      approvedAnswers={answers}
                    />
                    <OwnerSupplementRequestButton
                      questionId={question.id}
                      answerId={ans.id}
                    />
                  </div>
                </div>

                <FollowUpThreads
                  questionId={question.id}
                  quotedAnswerId={ans.id}
                  followups={followups}
                  approvedAnswers={answers}
                  rewardQuestion={question}
                  depth={0}
                />
              </div>
            </div>
        ))}
      </div>
    </div>
  );
}

function QuestionFuelPanel({ summary }: { summary: ReturnType<typeof questionFuelSummary> }) {
  return (
    <div className="mt-5 grid gap-2 rounded-lg border border-orange-100 bg-orange-50 p-3 sm:grid-cols-4">
      <FuelSignal label="基础预授权" value={`🔥 ${summary.baseReserved}`} />
      <FuelSignal label="已实际结算" value={`🔥 ${summary.baseSpent}`} />
      <FuelSignal label="待退/待结" value={`🔥 ${summary.baseRemaining}`} />
      <FuelSignal label="最佳奖励" value={summary.rewardFuel > 0 ? `🔥 ${summary.rewardFuel} · ${rewardStatusLabel(summary.rewardStatus)}` : "无"} />
      <p className="sm:col-span-4 text-[11px] leading-relaxed text-orange-700">
        平台按近两天平均值估算单答 🔥 {summary.estimatedPerAnswer}，为 {summary.matchedCount} 个回答预授权；最终按每个回答真实 Token 消耗结算，未消耗部分退回。
      </p>
    </div>
  );
}

function FuelSignal({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-white px-3 py-2">
      <p className="text-[11px] text-orange-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-gray-950">{value}</p>
    </div>
  );
}

function AnswerSettlementPanel({
  answer,
  question,
  compact = false,
}: {
  answer: Answer;
  question: Pick<Question, "reward_answer_id" | "reward_fuel" | "reward_status">;
  compact?: boolean;
}) {
  const summary = answerSettlementSummary(answer, question);
  return (
    <div className={`mt-4 rounded-lg border border-gray-100 bg-gray-50 ${compact ? "p-3" : "p-4"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-gray-500">结算明细</p>
        <span className="rounded bg-white px-2 py-1 text-[11px] text-gray-500">
          {summary.usageSourceLabel}
        </span>
      </div>
      <div className={`mt-3 grid gap-2 ${compact ? "grid-cols-2" : "sm:grid-cols-4"}`}>
        <SettlementSignal label="输入 Token" value={summary.promptTokens} />
        <SettlementSignal label="输出 Token" value={summary.completionTokens} />
        <SettlementSignal label="总 Token" value={summary.totalTokens} />
        <SettlementSignal label="基础结算" value={`🔥 ${summary.baseFuelCharged}`} strong />
      </div>
      {(summary.rewardFuel > 0 || !compact) && (
        <p className="mt-3 text-xs text-gray-500">
          {summary.rewardFuel > 0
            ? `${summary.rewardLabel} 🔥 ${summary.rewardFuel}，本回答合计收入 🔥 ${summary.totalFuelEarned}`
            : "奖励燃值只会分配给最终选中的最佳回答。"}
        </p>
      )}
    </div>
  );
}

function SettlementSignal({ label, value, strong = false }: { label: string; value: number | string; strong?: boolean }) {
  return (
    <div className="rounded-md bg-white px-3 py-2">
      <p className="text-[11px] text-gray-400">{label}</p>
      <p className={`mt-1 text-sm ${strong ? "font-semibold text-orange-600" : "font-medium text-gray-800"}`}>{value}</p>
    </div>
  );
}

function rewardStatusLabel(status: Question["reward_status"]) {
  const labels: Record<string, string> = {
    none: "无奖励",
    pending: "待分配",
    awarded: "已分配",
    auto_awarded: "系统已分配",
    refunded: "已退回",
  };
  return labels[status] || status;
}

function FollowUpThreads({
  questionId,
  quotedAnswerId,
  followups,
  approvedAnswers,
  rewardQuestion,
  depth,
}: {
  questionId: string;
  quotedAnswerId: string;
  followups: FollowUpThread[];
  approvedAnswers: Answer[];
  rewardQuestion: Pick<Question, "reward_answer_id" | "reward_fuel" | "reward_status">;
  depth: number;
}) {
  const threads = followupsForAnswer(followups, quotedAnswerId);
  if (threads.length === 0) return null;

  return (
    <div className="mt-4 space-y-3">
      {threads.map(thread => (
        <div key={thread.id} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
          <p className="text-sm font-medium text-gray-800">追问：{thread.text}</p>
          <div className="mt-3 space-y-3">
            {(thread.answers || []).map(followupAnswer => (
              <div key={followupAnswer.id} className="rounded-lg bg-white px-3 py-3">
                <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-gray-400">
                  <span className="font-medium text-gray-700">{followupAnswer.agent.name}</span>
                  <span>{new Date(followupAnswer.created_at).toLocaleString()}</span>
                </div>
                <AnswerMarkdown text={followupAnswer.content?.text || ""} />
                <OwnerSupplements items={followupAnswer.owner_supplements} />
                <AnswerSettlementPanel
                  answer={followupAnswer}
                  question={rewardQuestion}
                  compact
                />
                <div className="mt-3 flex flex-wrap justify-end gap-2 border-t border-gray-100 pt-3">
                  <FollowUpComposer
                    questionId={questionId}
                    quotedAnswer={followupAnswer}
                    approvedAnswers={approvedAnswers}
                  />
                  <OwnerSupplementRequestButton
                    questionId={questionId}
                    answerId={followupAnswer.id}
                  />
                </div>
                <div className={depth >= 2 ? "ml-0" : "ml-3 sm:ml-5"}>
                  <FollowUpThreads
                    questionId={questionId}
                    quotedAnswerId={followupAnswer.id}
                    followups={followups}
                    approvedAnswers={approvedAnswers}
                    rewardQuestion={rewardQuestion}
                    depth={depth + 1}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function QuestionRoutingWorkbench({ question }: { question: Question }) {
  const profile = question.task_profile;
  const explanations = question.match_explanations || [];

  if (!profile && explanations.length === 0) return null;

  return (
    <div className="mb-6 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
      {profile && (
        <section className="rounded-lg border border-gray-100 bg-white p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Task Profile</p>
              <h2 className="mt-1 text-base font-semibold text-gray-950">AI 任务画像</h2>
            </div>
            <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              {profile.answer_mode}
            </span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <ProfileSignal label="意图" value={profile.intent} />
            <ProfileSignal label="风险" value={profile.risk_level} />
            <ProfileSignal label="路由" value={profile.routing_mode === "smart_route" ? "智能路由" : "选角透明"} />
            <ProfileSignal label="输出" value={profile.expected_output} />
          </div>
          <div className="mt-4 space-y-3">
            <ChipGroup label="查询标签" values={profile.query_tags || []} />
            <ChipGroup label="领域" values={profile.domain_tags} />
            <ChipGroup label="能力" values={profile.capability_tags} />
          </div>
        </section>
      )}

      {explanations.length > 0 ? (
        <section className="rounded-lg border border-gray-100 bg-white p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Agent Casting</p>
              <h2 className="mt-1 text-base font-semibold text-gray-950">完整匹配解释</h2>
            </div>
            <span className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-500">
              {explanations.length} selected
            </span>
          </div>
          <div className="space-y-3">
            {explanations.map(agent => (
              <AgentMatchInspection key={agent.id} agent={agent} />
            ))}
          </div>
        </section>
      ) : profile ? (
        <section className="rounded-lg border border-gray-100 bg-white p-5">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Agent Casting</p>
          <h2 className="mt-1 text-base font-semibold text-gray-950">没有匹配到可派单 Agent</h2>
          <div className="mt-4 grid gap-2 text-sm text-gray-500">
            {["没有在线公开 Agent", "Agent 未完成 readiness 验证", "标签或相似领域没有命中", "Agent 配额已被阻塞"].map(reason => (
              <div key={reason} className="rounded-md bg-gray-50 px-3 py-2">{reason}</div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function AgentMatchInspection({ agent }: { agent: NonNullable<Question["match_explanations"]>[number] }) {
  const breakdown = agent.score_breakdown;
  const readinessState = agent.readiness?.state || "unknown";
  const evidence = [
    ["命中标签", agent.matched_tags],
    ["能力", agent.capability_hits],
    ["工具", agent.tool_hits || []],
    ["风格", agent.style_hits || []],
    ["学习命中", agent.learned_hits || []],
    ["避开", agent.avoid_tags || []],
  ] as const;

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-gray-950">{agent.name}</h3>
            <SignalPill label={agent.agent_type} />
            <SignalPill label={agent.status} />
            <SignalPill label={`ready: ${readinessState}`} />
            {agent.review_method && <SignalPill label={`review: ${agent.review_method}`} />}
          </div>
          <p className="mt-1 text-xs text-gray-500">
            {agent.request_id || "no request"} · answer {agent.answer_status || "unknown"} · quota {agent.quota_state}
          </p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-semibold text-primary">{agent.overall_score}</p>
          <p className="text-[11px] text-gray-400">overall</p>
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-5">
        <ScoreBox label="match" value={agent.match_score} />
        <ScoreBox label="repute" value={Number(agent.repute_score).toFixed(1)} />
        <ScoreBox label="repute part" value={breakdown?.repute_component ?? "-"} />
        <ScoreBox label="match part" value={breakdown?.match_component ?? "-"} />
        {!!breakdown?.subscription_boost && (
          <ScoreBox label="sub boost" value={`+${breakdown.subscription_boost}`} />
        )}
      </div>

      {breakdown && (
        <p className="mt-2 rounded-md bg-white px-3 py-2 font-mono text-[11px] text-gray-500">
          {breakdown.formula}
        </p>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <RouteSignal label="match_type" value={agent.match_type} />
        <RouteSignal label="quota_state" value={agent.quota_state} />
        <RouteSignal label="answers" value={String(agent.total_answers)} />
        <RouteSignal label="approval" value={`${Math.round(agent.approval_rate * 100)}%`} />
        <RouteSignal label="learned_samples" value={String(agent.learned_profile?.sample_count || 0)} />
        <RouteSignal label="owner_signal" value={String(agent.owner_supplement_summary?.total || 0)} />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {evidence.map(([label, values]) => (
          <EvidenceGroup key={label} label={label} values={values} />
        ))}
      </div>

      <OwnerExperienceEvidence context={agent.owner_experience_context} />

      <div className="mt-3 flex flex-wrap gap-2">
        {agent.reasons.map(reason => (
          <span key={reason} className="rounded-md bg-white px-2 py-1 text-xs text-gray-600">
            {reason}
          </span>
        ))}
      </div>
    </div>
  );
}

function OwnerExperienceEvidence({
  context,
}: {
  context: NonNullable<Question["match_explanations"]>[number]["owner_experience_context"];
}) {
  const groups = [
    ["主人纠错", context?.corrections || []],
    ["版本经验", context?.version_updates || []],
    ["风险提示", context?.risk_notes || []],
    ["高价值经验", context?.high_value_experiences || []],
  ] as const;
  if (!groups.some(([, values]) => values.length)) return null;

  return (
    <div className="mt-4 rounded-md border border-amber-100 bg-amber-50 p-3">
      <p className="mb-2 text-xs font-medium text-amber-800">主人经验上下文</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {groups.map(([label, values]) => values.length ? (
          <div key={label}>
            <p className="mb-1 text-[11px] text-amber-600">{label}</p>
            <div className="space-y-1">
              {values.map(value => (
                <p key={`${label}-${value}`} className="rounded bg-white/80 px-2 py-1 text-[11px] leading-relaxed text-amber-900">
                  {value}
                </p>
              ))}
            </div>
          </div>
        ) : null)}
      </div>
    </div>
  );
}

function SignalPill({ label }: { label: string }) {
  return <span className="rounded bg-white px-2 py-0.5 text-[11px] text-gray-500">{label}</span>;
}

function ScoreBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md bg-white p-3">
      <p className="text-[11px] uppercase text-gray-400">{label}</p>
      <p className="mt-1 text-sm font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function RouteSignal({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-white px-3 py-2">
      <p className="text-[11px] text-gray-400">{label}</p>
      <p className="mt-1 text-xs font-medium text-gray-700">{value}</p>
    </div>
  );
}

function EvidenceGroup({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <p className="mb-1 text-xs text-gray-400">{label}</p>
      {values.length ? (
        <div className="flex flex-wrap gap-1.5">
          {values.map(value => (
            <span key={value} className="rounded border border-gray-200 bg-white px-2 py-0.5 text-[11px] text-gray-600">
              {value}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-300">none</p>
      )}
    </div>
  );
}

function ProfileSignal({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-gray-50 p-3">
      <p className="text-xs text-gray-400">{label}</p>
      <p className="mt-1 text-sm font-medium text-gray-800">{value}</p>
    </div>
  );
}

function ChipGroup({ label, values }: { label: string; values: string[] }) {
  if (!values?.length) return null;
  return (
    <div>
      <p className="mb-2 text-xs text-gray-400">{label}</p>
      <div className="flex flex-wrap gap-2">
        {values.map(value => (
          <span key={value} className="rounded-full border border-primary/10 bg-primary/5 px-3 py-1 text-xs text-primary">
            {value}
          </span>
        ))}
      </div>
    </div>
  );
}
