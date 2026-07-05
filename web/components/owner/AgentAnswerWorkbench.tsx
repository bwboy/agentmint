"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { AnswerOwnerSupplement, FeedbackReason, MyAgentAnswerItem, OwnerSupplementType } from "@/lib/types";
import { buildAgentHealthSummaries, type AgentHealthSummary } from "@/components/owner/AgentAnswerWorkbench.logic";

type FilterMode = "all" | "requested" | "answered" | "unanswered";
type QualityMark = "excellent" | "needs_improvement" | "stale" | "none";

export function AgentAnswerWorkbench() {
  const router = useRouter();
  const [items, setItems] = useState<MyAgentAnswerItem[] | null>(null);
  const [filter, setFilter] = useState<FilterMode>("all");
  const [agentFilter, setAgentFilter] = useState("all");
  const [supplementTypeFilter, setSupplementTypeFilter] = useState<"all" | OwnerSupplementType>("all");
  const [query, setQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [draftTypes, setDraftTypes] = useState<Record<string, OwnerSupplementType>>({});
  const [highValueDrafts, setHighValueDrafts] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    refresh();
    remindOverdue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      const res = await api<{ data: MyAgentAnswerItem[] }>("/api/my/agent-answers", { token });
      setItems(res.data || []);
      setErr(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setErr(e instanceof ApiError ? e.message : "加载回答工作台失败");
    }
  }

  async function remindOverdue() {
    const token = getToken();
    if (!token) return;
    try {
      await api("/api/my/owner-supplements/remind-overdue", { method: "POST", token });
    } catch {
      // Non-critical; the workbench should still load.
    }
  }

  const visibleItems = useMemo(() => {
    const all = items || [];
    const keyword = query.trim().toLowerCase();
    return all.filter(item => {
      if (filter === "requested" && item.owner_supplement_pending_count === 0) return false;
      if (filter === "answered" && item.owner_supplement_answered_count === 0) return false;
      if (filter === "unanswered" && item.owner_supplements.length > 0) return false;
      if (agentFilter !== "all" && item.agent_id !== agentFilter) return false;
      if (supplementTypeFilter !== "all" && !item.owner_supplements.some(s => s.supplement_type === supplementTypeFilter)) return false;
      if (keyword) {
        const haystack = `${item.question_title} ${item.agent_name} ${item.content?.text || ""}`.toLowerCase();
        if (!haystack.includes(keyword)) return false;
      }
      return true;
    });
  }, [agentFilter, filter, items, query, supplementTypeFilter]);

  const agentOptions = useMemo(() => {
    const byId = new Map<string, string>();
    for (const item of items || []) byId.set(item.agent_id, item.agent_name);
    return Array.from(byId.entries()).map(([id, name]) => ({ id, name }));
  }, [items]);

  const trend = useMemo(() => {
    const all = items || [];
    return {
      total: all.length,
      pending: all.reduce((sum, item) => sum + item.owner_supplement_pending_count, 0),
      supplemented: all.filter(item => item.owner_supplement_answered_count > 0).length,
      excellent: all.filter(item => item.owner_quality_mark === "excellent").length,
      needsImprovement: all.filter(item => item.owner_quality_mark === "needs_improvement").length,
      stale: all.filter(item => item.owner_quality_mark === "stale").length,
    };
  }, [items]);

  const agentHealth = useMemo(() => buildAgentHealthSummaries(items || []), [items]);

  async function respondToRequest(answer: MyAgentAnswerItem, supplement: AnswerOwnerSupplement) {
    const response = (drafts[supplement.id] || "").trim();
    if (!response) {
      setErr("请输入补充内容");
      return;
    }
    await submitSupplement(`/api/my/owner-supplements/${supplement.id}/respond`, supplement.id, response);
  }

  async function addSelfSupplement(answer: MyAgentAnswerItem) {
    const key = selfDraftKey(answer.id);
    const response = (drafts[key] || "").trim();
    if (!response) {
      setErr("请输入主动补充内容");
      return;
    }
    await submitSupplement(
      `/api/questions/${answer.question_id}/answers/${answer.id}/owner-supplements/self`,
      key,
      response,
    );
  }

  async function submitSupplement(path: string, draftKey: string, response: string) {
    const token = getToken();
    if (!token) return;
    const supplementType = draftTypes[draftKey] || "experience";
    setBusy(draftKey);
    setErr(null);
    try {
      await api(path, {
        method: "POST",
        token,
        json: { response, supplement_type: supplementType },
      });
      setDrafts(current => {
        const next = { ...current };
        delete next[draftKey];
        return next;
      });
      setDraftTypes(current => {
        const next = { ...current };
        delete next[draftKey];
        return next;
      });
      await refresh();
      router.refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "提交失败");
    } finally {
      setBusy(null);
    }
  }

  async function batchMark(mark: QualityMark) {
    const token = getToken();
    if (!token || selectedIds.length === 0) return;
    setBusy(`batch:${mark}`);
    setErr(null);
    try {
      await api("/api/my/agent-answers/batch-mark", {
        method: "POST",
        token,
        json: { answer_ids: selectedIds, mark },
      });
      setSelectedIds([]);
      await refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "批量标记失败");
    } finally {
      setBusy(null);
    }
  }

  function toggleSelected(answerId: string) {
    setSelectedIds(current => (
      current.includes(answerId)
        ? current.filter(id => id !== answerId)
        : [...current, answerId]
    ));
  }

  if (items === null) return <p className="text-sm text-gray-400">加载中...</p>;

  const pendingCount = items.reduce((sum, item) => sum + item.owner_supplement_pending_count, 0);

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-red-100 bg-red-50 p-3 text-xs text-red-500">{err}</div>}

      <div className="space-y-3 rounded-xl border border-gray-100 bg-white p-4">
        <div className="grid gap-2 sm:grid-cols-6">
          <TrendBox label="回答" value={trend.total} />
          <TrendBox label="待补充" value={trend.pending} />
          <TrendBox label="已补充" value={trend.supplemented} />
          <TrendBox label="优秀" value={trend.excellent} />
          <TrendBox label="需改进" value={trend.needsImprovement} />
          <TrendBox label="失效" value={trend.stale} />
        </div>
        {agentHealth.length > 0 && (
          <AgentHealthStrip
            summaries={agentHealth}
            activeAgentId={agentFilter}
            onSelect={setAgentFilter}
          />
        )}
        <div className="flex flex-wrap items-center gap-2">
          <FilterButton active={filter === "all"} onClick={() => setFilter("all")}>全部回答</FilterButton>
          <FilterButton active={filter === "requested"} onClick={() => setFilter("requested")}>待补充 {pendingCount}</FilterButton>
          <FilterButton active={filter === "answered"} onClick={() => setFilter("answered")}>已补充</FilterButton>
          <FilterButton active={filter === "unanswered"} onClick={() => setFilter("unanswered")}>未补充</FilterButton>
          <select
            value={agentFilter}
            onChange={event => setAgentFilter(event.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600"
          >
            <option value="all">全部 Agent</option>
            {agentOptions.map(agent => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
          </select>
          <select
            value={supplementTypeFilter}
            onChange={event => setSupplementTypeFilter(event.target.value as "all" | OwnerSupplementType)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600"
          >
            <option value="all">全部补充类型</option>
            <option value="experience">经验补充</option>
            <option value="correction">纠错</option>
            <option value="version_update">版本更新</option>
            <option value="risk_note">风险提醒</option>
          </select>
          <input
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="搜索问题、回答、Agent"
            className="min-w-52 flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm outline-none transition focus:border-primary"
          />
        </div>
        {selectedIds.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg bg-gray-50 p-2 text-xs">
            <span className="text-gray-500">已选 {selectedIds.length} 条</span>
            <button onClick={() => batchMark("excellent")} className="rounded bg-white px-2 py-1 text-emerald-600 ring-1 ring-gray-100">标优秀</button>
            <button onClick={() => batchMark("needs_improvement")} className="rounded bg-white px-2 py-1 text-amber-600 ring-1 ring-gray-100">标需改进</button>
            <button onClick={() => batchMark("stale")} className="rounded bg-white px-2 py-1 text-red-500 ring-1 ring-gray-100">标失效</button>
            <button onClick={() => batchMark("none")} className="rounded bg-white px-2 py-1 text-gray-500 ring-1 ring-gray-100">清除标记</button>
          </div>
        )}
      </div>

      {visibleItems.length === 0 ? (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-400">
          当前没有符合条件的 Agent 回答。
        </div>
      ) : (
        visibleItems.map(answer => (
          <AnswerCard
            key={answer.id}
            answer={answer}
            drafts={drafts}
            draftTypes={draftTypes}
            highValueDrafts={highValueDrafts}
            busy={busy}
            selected={selectedIds.includes(answer.id)}
            onToggleSelected={() => toggleSelected(answer.id)}
            onDraftChange={(key, value) => setDrafts(current => ({ ...current, [key]: value }))}
            onDraftTypeChange={(key, value) => setDraftTypes(current => ({ ...current, [key]: value }))}
            onHighValueChange={(key, value) => setHighValueDrafts(current => ({ ...current, [key]: value }))}
            onRespond={respondToRequest}
            onSelfSupplement={addSelfSupplement}
            onSetError={setErr}
            onRefresh={refresh}
          />
        ))
      )}
    </div>
  );
}

function AnswerCard({
  answer,
  drafts,
  draftTypes,
  highValueDrafts,
  busy,
  selected,
  onToggleSelected,
  onDraftChange,
  onDraftTypeChange,
  onHighValueChange,
  onRespond,
  onSelfSupplement,
  onSetError,
  onRefresh,
}: {
  answer: MyAgentAnswerItem;
  drafts: Record<string, string>;
  draftTypes: Record<string, OwnerSupplementType>;
  highValueDrafts: Record<string, boolean>;
  busy: string | null;
  selected: boolean;
  onToggleSelected: () => void;
  onDraftChange: (key: string, value: string) => void;
  onDraftTypeChange: (key: string, value: OwnerSupplementType) => void;
  onHighValueChange: (key: string, value: boolean) => void;
  onRespond: (answer: MyAgentAnswerItem, supplement: AnswerOwnerSupplement) => void;
  onSelfSupplement: (answer: MyAgentAnswerItem) => void;
  onSetError: (value: string | null) => void;
  onRefresh: () => Promise<void>;
}) {
  const pending = answer.owner_supplements.filter(item => item.status === "pending");
  const answered = answer.owner_supplements.filter(item => item.status === "answered");
  const selfKey = selfDraftKey(answer.id);
  const [expanded, setExpanded] = useState(false);
  const [activeReplyId, setActiveReplyId] = useState<string | null>(pending[0]?.id || null);
  const [selfComposerOpen, setSelfComposerOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const answerText = answer.content?.text || "无文本回答";

  async function updateSupplement(item: AnswerOwnerSupplement) {
    const token = getToken();
    if (!token) return;
    const draft = (drafts[item.id] ?? item.response).trim();
    if (!draft) {
      onSetError("请输入补充内容");
      return;
    }
    onSetError(null);
    try {
      await api(`/api/my/owner-supplements/${item.id}`, {
        method: "PUT",
        token,
        json: {
          response: draft,
          supplement_type: draftTypes[item.id] || item.supplement_type,
          is_high_value: highValueDrafts[item.id] ?? item.is_high_value,
        },
      });
      setEditingId(null);
      await onRefresh();
    } catch (e) {
      onSetError(e instanceof ApiError ? e.message : "保存失败");
    }
  }

  async function withdrawSupplement(item: AnswerOwnerSupplement) {
    const token = getToken();
    if (!token) return;
    if (!confirm("撤回这条主人补充？")) return;
    onSetError(null);
    try {
      await api(`/api/my/owner-supplements/${item.id}/withdraw`, { method: "POST", token });
      await onRefresh();
    } catch (e) {
      onSetError(e instanceof ApiError ? e.message : "撤回失败");
    }
  }

  return (
    <section className="rounded-xl border border-gray-100 bg-white p-5 transition hover:border-gray-200">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
            <input type="checkbox" checked={selected} onChange={onToggleSelected} className="h-3.5 w-3.5" />
            <span>{answer.agent_name}</span>
            <span>{answer.turn_type === "followup" ? "追问回答" : "首轮回答"}</span>
            {answer.created_at && <span>{formatDate(answer.created_at)}</span>}
            <span>Token {answer.usage?.total_tokens ?? 0}</span>
            {!!answer.vote_summary?.down && <span className="rounded bg-red-50 px-2 py-0.5 text-red-600">负反馈 {answer.vote_summary.down}</span>}
            {!!answer.quality_signals?.pending_owner_requests && <span className="rounded bg-amber-50 px-2 py-0.5 text-amber-700">待补充 {answer.quality_signals.pending_owner_requests}</span>}
            {!!answer.quality_signals?.owner_corrections && <span className="rounded bg-amber-50 px-2 py-0.5 text-amber-700">纠错 {answer.quality_signals.owner_corrections}</span>}
            {!!answer.quality_signals?.owner_risk_notes && <span className="rounded bg-red-50 px-2 py-0.5 text-red-600">风险 {answer.quality_signals.owner_risk_notes}</span>}
            {feedbackReasonBadges(answer.feedback_reason_summary).map(item => (
              <span key={item.reason} className="rounded bg-red-50 px-2 py-0.5 text-red-600">
                {item.label} {item.count}
              </span>
            ))}
            {answer.owner_quality_mark && <span className={`rounded px-2 py-0.5 ${qualityMarkClass(answer.owner_quality_mark)}`}>{qualityMarkLabel(answer.owner_quality_mark)}</span>}
          </div>
          <Link href={`/questions/${answer.question_id}`} className="mt-1 block font-medium text-gray-950 hover:text-primary">
            {answer.question_title}
          </Link>
        </div>
        {pending.length > 0 && (
          <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
            {pending.length} 条补充请求
          </span>
        )}
      </div>

      <p className={`mt-4 whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-sm text-gray-700 ${expanded ? "" : "line-clamp-3"}`}>
        {answerText}
      </p>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setExpanded(current => !current)}
          className="rounded-lg bg-gray-100 px-3 py-1.5 text-sm text-gray-600 hover:text-primary"
        >
          {expanded ? "收起内容" : "展开全部"}
        </button>
        <div className="flex flex-wrap gap-2">
          {pending.length > 0 && (
            <button
              type="button"
              onClick={() => {
                setExpanded(true);
                setSelfComposerOpen(false);
                setActiveReplyId(activeReplyId || pending[0].id);
              }}
              className="rounded-lg bg-primary px-3 py-1.5 text-sm text-white hover:bg-primary-dark"
            >
              回复请求
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setExpanded(true);
              setActiveReplyId(null);
              setSelfComposerOpen(true);
            }}
            className="rounded-lg bg-gray-950 px-3 py-1.5 text-sm text-white hover:bg-gray-800"
          >
            主动补充
          </button>
        </div>
      </div>

      {expanded && pending.length > 0 && (
        <div className="mt-4 space-y-3 rounded-lg border border-amber-100 bg-amber-50/70 p-3">
          <p className="text-xs font-medium text-amber-700">提问者希望你补充</p>
          {pending.map(item => (
            <div key={item.id} className="rounded-lg bg-white p-3 ring-1 ring-amber-100">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-sm text-gray-700">{item.prompt}</p>
                <button
                  type="button"
                  onClick={() => {
                    setSelfComposerOpen(false);
                    setActiveReplyId(activeReplyId === item.id ? null : item.id);
                  }}
                  className="rounded-lg bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100"
                >
                  {activeReplyId === item.id ? "收起回复" : "回答"}
                </button>
              </div>
              {activeReplyId === item.id && (
                <>
                  <textarea
                    value={drafts[item.id] || ""}
                    onChange={event => onDraftChange(item.id, event.target.value)}
                    rows={3}
                    className="mt-3 w-full resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none transition focus:border-primary"
                    placeholder="补充你的真实经验、判断依据或注意事项..."
                  />
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <SupplementTypeSelect
                      value={draftTypes[item.id] || "experience"}
                      onChange={value => onDraftTypeChange(item.id, value)}
                    />
                    <button
                      type="button"
                      onClick={() => onRespond(answer, item)}
                      disabled={busy === item.id}
                      className="rounded-lg bg-primary px-3 py-1.5 text-sm text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {busy === item.id ? "提交中..." : "提交回答"}
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {expanded && answered.length > 0 && (
        <div className="mt-4 space-y-2 rounded-lg border border-emerald-100 bg-emerald-50/60 p-3">
          <p className="text-xs font-medium text-emerald-700">已发布的主人补充</p>
          {answered.map(item => (
            <div key={item.id} className="rounded-lg bg-white p-3 text-sm text-gray-700 ring-1 ring-emerald-100">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-gray-400">
                <span className="rounded bg-emerald-50 px-2 py-0.5 text-emerald-700">{supplementTypeLabel(item.supplement_type)}</span>
                {item.is_high_value && <span className="rounded bg-orange-50 px-2 py-0.5 text-orange-700">高价值</span>}
                {item.accepted_at && <span className="rounded bg-emerald-50 px-2 py-0.5 text-emerald-700">已采纳</span>}
                {item.prompt !== "主人主动补充" && <span>问：{item.prompt}</span>}
              </div>
              {editingId === item.id ? (
                <div className="space-y-2">
                  <textarea
                    value={drafts[item.id] ?? item.response}
                    onChange={event => onDraftChange(item.id, event.target.value)}
                    rows={3}
                    className="w-full resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none transition focus:border-primary"
                  />
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <SupplementTypeSelect
                        value={draftTypes[item.id] || item.supplement_type}
                        onChange={value => onDraftTypeChange(item.id, value)}
                      />
                      <label className="flex items-center gap-1.5 text-xs text-gray-500">
                        <input
                          type="checkbox"
                          checked={highValueDrafts[item.id] ?? item.is_high_value}
                          onChange={event => onHighValueChange(item.id, event.target.checked)}
                        />
                        高价值经验
                      </label>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setEditingId(null)}
                        className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700"
                      >
                        取消
                      </button>
                      <button
                        type="button"
                        onClick={() => updateSupplement(item)}
                        className="rounded-lg bg-gray-950 px-3 py-1.5 text-xs text-white hover:bg-gray-800"
                      >
                        保存
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  <p className="whitespace-pre-wrap">{item.response}</p>
                  <div className="mt-2 flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        onDraftChange(item.id, item.response);
                        onDraftTypeChange(item.id, item.supplement_type);
                        onHighValueChange(item.id, item.is_high_value);
                        setEditingId(item.id);
                      }}
                      className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs text-gray-500 hover:text-primary"
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => withdrawSupplement(item)}
                      className="rounded-lg bg-red-50 px-3 py-1.5 text-xs text-red-500 hover:bg-red-100"
                    >
                      撤回
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {expanded && selfComposerOpen && (
      <div className="mt-4 rounded-lg border border-gray-100 bg-gray-50 p-3">
        <p className="mb-2 text-xs font-medium text-gray-500">主动补充这个回答</p>
        <textarea
          value={drafts[selfKey] || ""}
          onChange={event => onDraftChange(selfKey, event.target.value)}
          rows={3}
          className="w-full resize-y rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-primary"
          placeholder="主动追加你的经验、纠错或提醒，提问者会收到通知。"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <Link href={`/questions/${answer.question_id}`} className="text-xs text-gray-400 hover:text-primary">
            查看问题详情
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <SupplementTypeSelect
              value={draftTypes[selfKey] || "experience"}
              onChange={value => onDraftTypeChange(selfKey, value)}
            />
            <button
              type="button"
              onClick={() => onSelfSupplement(answer)}
              disabled={busy === selfKey}
              className="rounded-lg bg-gray-950 px-3 py-1.5 text-sm text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === selfKey ? "提交中..." : "发布主动补充"}
            </button>
          </div>
        </div>
      </div>
      )}
    </section>
  );
}

function SupplementTypeSelect({
  value,
  onChange,
}: {
  value: OwnerSupplementType;
  onChange: (value: OwnerSupplementType) => void;
}) {
  return (
    <select
      value={value}
      onChange={event => onChange(event.target.value as OwnerSupplementType)}
      className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-600 outline-none transition focus:border-primary"
    >
      <option value="experience">经验补充</option>
      <option value="correction">纠错</option>
      <option value="version_update">版本更新</option>
      <option value="risk_note">风险提醒</option>
    </select>
  );
}

function supplementTypeLabel(value: OwnerSupplementType) {
  return {
    experience: "经验补充",
    correction: "纠错",
    version_update: "版本更新",
    risk_note: "风险提醒",
  }[value] || "经验补充";
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg px-3 py-1.5 text-sm transition ${
        active ? "bg-gray-950 text-white" : "bg-gray-100 text-gray-500 hover:text-primary"
      }`}
    >
      {children}
    </button>
  );
}

function TrendBox({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-gray-50 px-3 py-2">
      <p className="text-[11px] text-gray-400">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function AgentHealthStrip({
  summaries,
  activeAgentId,
  onSelect,
}: {
  summaries: AgentHealthSummary[];
  activeAgentId: string;
  onSelect: (agentId: string) => void;
}) {
  return (
    <div className="space-y-2 rounded-lg border border-gray-100 bg-gray-50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium text-gray-500">Agent 健康</p>
        {activeAgentId !== "all" && (
          <button
            type="button"
            onClick={() => onSelect("all")}
            className="rounded bg-white px-2 py-1 text-[11px] text-gray-500 hover:text-primary"
          >
            查看全部
          </button>
        )}
      </div>
      <div className="grid gap-2 lg:grid-cols-3">
        {summaries.map(summary => (
          <button
            key={summary.agentId}
            type="button"
            onClick={() => onSelect(summary.agentId)}
            className={`rounded-lg border bg-white p-3 text-left transition hover:border-primary ${
              activeAgentId === summary.agentId ? "border-primary ring-1 ring-primary/20" : "border-gray-100"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-gray-950">{summary.agentName}</p>
                <p className="mt-1 text-[11px] text-gray-400">{summary.totalAnswers} 回答 · {summary.attentionAnswers} 需关注</p>
              </div>
              <span className={`rounded px-2 py-1 text-[11px] ${healthRiskClass(summary.riskLevel)}`}>
                {healthRiskLabel(summary.riskLevel)}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-1 text-center text-[11px]">
              <HealthSignal label="负反馈" value={summary.negativeFeedback} />
              <HealthSignal label="纠错" value={summary.ownerCorrections} />
              <HealthSignal label="风险" value={summary.ownerRiskNotes} />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function HealthSignal({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded bg-gray-50 px-2 py-1">
      <p className="text-gray-400">{label}</p>
      <p className="font-semibold text-gray-800">{value}</p>
    </div>
  );
}

function selfDraftKey(answerId: string) {
  return `self:${answerId}`;
}

function healthRiskLabel(value: AgentHealthSummary["riskLevel"]) {
  return {
    healthy: "健康",
    watch: "观察",
    high: "高风险",
  }[value];
}

function healthRiskClass(value: AgentHealthSummary["riskLevel"]) {
  return {
    healthy: "bg-emerald-50 text-emerald-700",
    watch: "bg-amber-50 text-amber-700",
    high: "bg-red-50 text-red-600",
  }[value];
}

function qualityMarkLabel(value: NonNullable<MyAgentAnswerItem["owner_quality_mark"]>) {
  return {
    excellent: "优秀",
    needs_improvement: "需改进",
    stale: "失效",
  }[value] || value;
}

function qualityMarkClass(value: NonNullable<MyAgentAnswerItem["owner_quality_mark"]>) {
  return {
    excellent: "bg-emerald-50 text-emerald-700",
    needs_improvement: "bg-amber-50 text-amber-700",
    stale: "bg-red-50 text-red-600",
  }[value] || "bg-gray-100 text-gray-500";
}

function feedbackReasonBadges(summary?: Partial<Record<FeedbackReason, number>>) {
  const rows: Array<{ reason: FeedbackReason; label: string; count: number }> = [];
  for (const reason of feedbackReasonOrder) {
    const count = Number(summary?.[reason] || 0);
    if (count > 0) rows.push({ reason, label: feedbackReasonLabel(reason), count });
  }
  return rows;
}

const feedbackReasonOrder: FeedbackReason[] = ["owner_review", "stale", "missed_point", "needs_sources"];

function feedbackReasonLabel(reason: FeedbackReason) {
  if (reason === "stale") return "过期";
  if (reason === "missed_point") return "没答到点";
  if (reason === "needs_sources") return "需要来源";
  return "建议修正";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
