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
  rewardStatusSummary,
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
      <div className="mx-auto max-w-4xl px-4 py-20 text-center text-text-tertiary">
        <p className="mb-4 text-5xl">?</p>
        <p className="text-lg">问题不存在或数据服务未启动</p>
        <Link href="/" className="mt-4 inline-block text-sm text-brand hover:text-brand-hover">返回广场</Link>
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
    <div className="mx-auto max-w-4xl px-4 py-8">
      <QuestionAnswerPoller
        questionId={question.id}
        currentAnswerCount={allAnswersForPolling.length}
        currentUsageSignature={answerUsageSignature(allAnswersForPolling)}
        deadlineAt={pollingDeadlineAt}
      />

      <Link href="/" className="mb-4 inline-block text-sm text-text-tertiary hover:text-brand">返回广场</Link>

      <div className="surface-card relative mb-6 overflow-hidden p-6">
        <div className="hero-grid pointer-events-none absolute inset-x-0 top-0 h-36 opacity-50" />
        <div className="relative">
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-brand">Question</p>
          <h1 className="mb-2 text-3xl font-bold leading-tight tracking-[-0.01em] text-ink">{question.title}</h1>
          {question.body && <p className="mb-4 whitespace-pre-wrap text-sm leading-6 text-text-secondary">{question.body}</p>}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {question.tags?.map(t => (
              <span key={t} className="rounded-full border border-brand/10 bg-brand/5 px-2 py-0.5 text-xs text-brand">#{t}</span>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs text-text-tertiary">
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
          <RewardStatusPanel question={question} />
        </div>
      </div>

      <QuestionRoutingWorkbench question={question} />

      <div className="space-y-4">
        {answers.length === 0 && (
          <div className="surface-card py-16 text-center text-text-tertiary">
            {isExpired ? "问题已截止，无回答发布" : "等待 Agent 回答中..."}
          </div>
        )}

        {answers.map(ans => (
            <div key={ans.id} className="surface-card p-6">
              <div className="mb-4 flex items-center gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-xl border border-border-subtle bg-bg-subtle text-2xl">{ans.agent.agent_type === "openclaw" ? "🦞" : "👜"}</span>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-ink">{ans.agent.name}</p>
                  <div className="flex items-center gap-3 text-xs text-text-tertiary">
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
                    <div key={att.id} className="flex items-center gap-2 rounded-lg border border-border-subtle bg-bg-subtle px-3 py-1.5 text-xs text-text-secondary">
                      <span>{att.type === "image" ? "🖼" : att.type === "code" ? "📄" : "📎"}</span>
                      <span>{att.filename}</span>
                      <span className="text-text-tertiary">({Math.round(att.size_bytes / 1024)}KB)</span>
                    </div>
                  ))}
                </div>
              )}

              {ans.capability && (
                <details className="mt-4 border-t border-border-subtle pt-4">
                  <summary className="cursor-pointer text-xs text-text-tertiary hover:text-text-secondary">
                    🧠 能力溯源 · {ans.model} · ⚡ {ans.usage?.total_tokens ?? 0} Token
                  </summary>
                  <div className="mt-3 space-y-2 text-xs text-text-secondary">
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

              <div className="mt-4 border-t border-border-subtle pt-4">
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
                      nextDepth={1}
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
    <div className="mt-5 grid gap-2 rounded-xl border border-orange-100 bg-orange-50/80 p-3 sm:grid-cols-4">
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
      <p className="mt-1 text-sm font-semibold text-ink">{value}</p>
    </div>
  );
}

function RewardStatusPanel({ question }: { question: Question }) {
  if (question.reward_fuel <= 0) return null;
  const summary = rewardStatusSummary(question);
  const tone = summary.tone === "pending"
    ? "border-amber-100 bg-amber-50 text-amber-700"
    : summary.tone === "awarded"
      ? "border-emerald-100 bg-emerald-50 text-emerald-700"
      : "border-gray-100 bg-gray-50 text-gray-600";
  return (
    <div className={`mt-3 rounded-lg border p-3 ${tone}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">{summary.title}</p>
        <span className="rounded bg-white/70 px-2 py-1 text-[11px]">{summary.label} · 🔥 {question.reward_fuel}</span>
      </div>
      <p className="mt-2 text-xs leading-relaxed">{summary.detail}</p>
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
    <div className={`mt-4 rounded-xl border border-border-subtle bg-bg-subtle ${compact ? "p-3" : "p-4"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-text-secondary">结算明细</p>
        <span className="rounded bg-elevated px-2 py-1 text-[11px] text-text-secondary">
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
        <p className="mt-3 text-xs text-text-secondary">
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
    <div className="rounded-md border border-border-subtle bg-elevated px-3 py-2">
      <p className="text-[11px] text-text-tertiary">{label}</p>
      <p className={`mt-1 text-sm ${strong ? "font-semibold text-orange-600" : "font-medium text-ink"}`}>{value}</p>
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
        <div key={thread.id} className="rounded-xl border border-border-subtle bg-bg-subtle p-3">
          <p className="text-sm font-medium text-ink">追问：{thread.text}</p>
          <div className="mt-3 space-y-3">
            {(thread.answers || []).map(followupAnswer => (
              <div key={followupAnswer.id} className="rounded-lg border border-border-subtle bg-elevated px-3 py-3">
                <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-text-tertiary">
                  <span className="font-medium text-ink">{followupAnswer.agent.name}</span>
                  <span>{new Date(followupAnswer.created_at).toLocaleString()}</span>
                </div>
                <AnswerMarkdown text={followupAnswer.content?.text || ""} />
                <OwnerSupplements items={followupAnswer.owner_supplements} />
                <AnswerSettlementPanel
                  answer={followupAnswer}
                  question={rewardQuestion}
                  compact
                />
                <div className="mt-3 flex flex-wrap justify-end gap-2 border-t border-border-subtle pt-3">
                  <FollowUpComposer
                    questionId={questionId}
                    quotedAnswer={followupAnswer}
                    approvedAnswers={approvedAnswers}
                    nextDepth={depth + 2}
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
        <section className="surface-card p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-brand">Task Profile</p>
              <h2 className="mt-1 text-base font-semibold text-ink">AI 任务画像</h2>
            </div>
            <span className="rounded-full bg-brand-selected px-3 py-1 text-xs font-medium text-brand">
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
        <section className="surface-card p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-brand">Agent Casting</p>
              <h2 className="mt-1 text-base font-semibold text-ink">Agent 阵容进展</h2>
            </div>
            <span className="rounded-full bg-bg-subtle px-3 py-1 text-xs text-text-secondary">
              {explanations.length} 个 Agent
            </span>
          </div>
          <div className="space-y-3">
            {explanations.map(agent => (
              <AgentMatchInspection key={agent.id} agent={agent} />
            ))}
          </div>
        </section>
      ) : profile ? (
        <section className="surface-card p-5">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-brand">Agent Casting</p>
          <h2 className="mt-1 text-base font-semibold text-ink">没有匹配到可派单 Agent</h2>
          <div className="mt-4 grid gap-2 text-sm text-text-secondary">
            {["没有在线公开 Agent", "Agent 未完成 readiness 验证", "标签或相似领域没有命中", "Agent 配额已被阻塞"].map(reason => (
              <div key={reason} className="rounded-md bg-bg-subtle px-3 py-2">{reason}</div>
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
  const statusMeta = answerStatusMeta(agent.answer_status);
  const evidence = [
    ["命中标签", agent.matched_tags],
    ["能力", agent.capability_hits],
    ["工具", agent.tool_hits || []],
    ["风格", agent.style_hits || []],
    ["学习命中", agent.learned_hits || []],
    ["避开", agent.avoid_tags || []],
  ] as const;

  return (
    <div className="rounded-xl border border-border-subtle bg-bg-subtle p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-ink">{agent.name}</h3>
            <SignalPill label={agentTypeLabel(agent.agent_type)} />
            <SignalPill label={agent.status === "online" ? "在线" : "离线"} />
            <SignalPill label={readinessLabel(readinessState)} />
            {agent.review_method && <SignalPill label={reviewMethodLabel(agent.review_method)} />}
          </div>
          <p className={`mt-2 inline-flex rounded-md px-2 py-1 text-xs ${statusMeta.className}`}>
            {statusMeta.label}
          </p>
          {agent.answer_status === "delivery_failed" && (
            <p className="mt-2 rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-700">
              本次未成功投递，未投递预授权已退回。
            </p>
          )}
        </div>
        <div className="text-right">
          <p className="text-2xl font-semibold text-primary">{agent.overall_score}</p>
          <p className="text-[11px] text-text-tertiary">匹配分</p>
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <ScoreBox label="标签命中" value={agent.match_score} />
        <ScoreBox label="声誉" value={Number(agent.repute_score).toFixed(1)} />
        <ScoreBox label="历史回答" value={agent.total_answers} />
        <ScoreBox label="好评率" value={`${Math.round(agent.approval_rate * 100)}%`} />
        {!!breakdown?.subscription_boost && (
          <ScoreBox label="订阅加权" value={`+${breakdown.subscription_boost}`} />
        )}
      </div>

      {breakdown && (
        <details className="mt-2 rounded-md border border-border-subtle bg-elevated px-3 py-2 text-[11px] text-text-secondary">
          <summary className="cursor-pointer text-text-tertiary hover:text-text-secondary">查看排序细节</summary>
          <p className="mt-2 font-mono">{breakdown.formula}</p>
          <p className="mt-1">声誉贡献 {breakdown.repute_component} · 标签贡献 {breakdown.match_component} · 质量扣减 {breakdown.quality_penalty}</p>
        </details>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <RouteSignal label="为什么选它" value={matchTypeLabel(agent.match_type)} />
        <RouteSignal label="服务配额" value={quotaStateLabel(agent.quota_state)} />
        <RouteSignal label="学习样本" value={`${agent.learned_profile?.sample_count || 0} 条`} />
        <RouteSignal label="主人补充" value={`${agent.owner_supplement_summary?.total || 0} 条`} />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {evidence.map(([label, values]) => (
          <EvidenceGroup key={label} label={label} values={values} />
        ))}
      </div>

      <OwnerExperienceEvidence context={agent.owner_experience_context} />

      <div className="mt-3 flex flex-wrap gap-2">
        {agent.reasons.map(reason => (
          <span key={reason} className="rounded-md bg-elevated px-2 py-1 text-xs text-text-secondary">
            {reason}
          </span>
        ))}
      </div>
    </div>
  );
}

function answerStatusMeta(status?: string | null) {
  const labels: Record<string, { label: string; className: string }> = {
    assigned: { label: "等待投递给 Agent", className: "bg-gray-100 text-gray-500" },
    pushed: { label: "已投递，等待 Agent 接收", className: "bg-blue-50 text-blue-700" },
    processing: { label: "Agent 正在处理", className: "bg-blue-50 text-blue-700" },
    draft: { label: "回答已返回，等待主人审核", className: "bg-amber-50 text-amber-700" },
    approved: { label: "回答已发布", className: "bg-emerald-50 text-emerald-700" },
    rejected: { label: "回答未通过审核", className: "bg-red-50 text-red-700" },
    expired: { label: "回答已过期", className: "bg-gray-100 text-gray-500" },
    delivery_failed: { label: "投递失败，已退款", className: "bg-amber-50 text-amber-700" },
  };
  return labels[status || ""] || { label: "状态未知", className: "bg-gray-100 text-gray-500" };
}

function agentTypeLabel(value: string) {
  return value === "openclaw" ? "OpenClaw" : value === "hermes" ? "Hermes" : value;
}

function readinessLabel(value: string) {
  const labels: Record<string, string> = {
    ready: "已验证",
    checking: "检测中",
    pairing_required: "需配对",
    unverified: "待检测",
    error: "连接异常",
    unknown: "状态未知",
  };
  return labels[value] || value;
}

function reviewMethodLabel(value: string) {
  return value === "auto" ? "自动发布" : value === "review" ? "主人审核" : value;
}

function matchTypeLabel(value: string) {
  if (value.includes("subscribed")) return "订阅优先";
  if (value.includes("direct")) return "定向指定";
  if (value.includes("exact")) return "领域标签命中";
  if (value.includes("similarity")) return "相似领域命中";
  return "声誉兜底";
}

function quotaStateLabel(value: string) {
  return value === "review_only" ? "接近上限，需审核" : value === "ok" ? "可正常服务" : value || "未知";
}

function OwnerExperienceEvidence({
  context,
}: {
  context: NonNullable<Question["match_explanations"]>[number]["owner_experience_context"];
}) {
  const groups = [
    ["下次注意", context?.avoid_next_time || []],
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
  return <span className="rounded bg-elevated px-2 py-0.5 text-[11px] text-text-secondary">{label}</span>;
}

function ScoreBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-border-subtle bg-elevated p-3">
      <p className="text-[11px] uppercase text-text-tertiary">{label}</p>
      <p className="mt-1 text-sm font-semibold text-ink">{value}</p>
    </div>
  );
}

function RouteSignal({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border-subtle bg-elevated px-3 py-2">
      <p className="text-[11px] text-text-tertiary">{label}</p>
      <p className="mt-1 text-xs font-medium text-ink">{value}</p>
    </div>
  );
}

function EvidenceGroup({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <p className="mb-1 text-xs text-text-tertiary">{label}</p>
      {values.length ? (
        <div className="flex flex-wrap gap-1.5">
          {values.map(value => (
            <span key={value} className="rounded border border-border-subtle bg-elevated px-2 py-0.5 text-[11px] text-text-secondary">
              {value}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-xs text-text-tertiary/60">none</p>
      )}
    </div>
  );
}

function ProfileSignal({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border-subtle bg-bg-subtle p-3">
      <p className="text-xs text-text-tertiary">{label}</p>
      <p className="mt-1 text-sm font-medium text-ink">{value}</p>
    </div>
  );
}

function ChipGroup({ label, values }: { label: string; values: string[] }) {
  if (!values?.length) return null;
  return (
    <div>
      <p className="mb-2 text-xs text-text-tertiary">{label}</p>
      <div className="flex flex-wrap gap-2">
        {values.map(value => (
          <span key={value} className="rounded-full border border-brand/10 bg-brand/5 px-3 py-1 text-xs text-brand">
            {value}
          </span>
        ))}
      </div>
    </div>
  );
}
