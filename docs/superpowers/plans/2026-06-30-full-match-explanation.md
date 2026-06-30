# Full Match Explanation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public full algorithm inspection panel on question detail pages without changing Agent matching behavior.

**Architecture:** Keep matching behavior in `backend/services/matching.py`, and extend its existing explanation formatter with explicit score and readiness metadata. Enrich question detail API explanations with answer routing metadata, then render a denser Clean AI Workbench style inspection panel in the existing Next.js question detail page.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest, Next.js App Router, TypeScript, Tailwind CSS.

---

### Task 1: Backend Explanation Metadata

**Files:**
- Modify: `backend/services/matching.py`
- Test: `backend/tests/test_matching.py`

- [ ] **Step 1: Add failing test for score breakdown and readiness**

Append this test to `backend/tests/test_matching.py`:

```python
def test_build_match_explanation_includes_score_breakdown_and_readiness():
    class AgentStub:
        id = "a_score"
        name = "Score Agent"
        agent_type = "hermes"
        tags = ["AI", "系统设计"]
        description = "擅长系统架构"
        repute_score = 4.0
        total_answers = 8
        approval_rate = 0.75
        status = "online"
        review_rules = {"agentmint_readiness": {"state": "ready", "checked_at": "2026-06-30T10:00:00"}}

    profile = build_task_profile(
        title="设计 Agent 匹配系统",
        body="需要系统架构",
        tags=["AI", "系统设计"],
        max_responders=3,
    )

    explanation = build_match_explanation(
        AgentStub(),
        task_profile=profile,
        match_score=0.5,
        match_type="exact",
        quota_state="ok",
    )

    assert explanation["readiness"]["state"] == "ready"
    assert explanation["score_breakdown"] == {
        "formula": "0.6 * (repute / 5.0) + 0.4 * match_score",
        "repute_weight": 0.6,
        "match_weight": 0.4,
        "repute_score": 4.0,
        "match_score": 50,
        "repute_component": 48,
        "match_component": 20,
        "overall_score": 68,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_matching.py::test_build_match_explanation_includes_score_breakdown_and_readiness -q
```

Expected: fail with missing `readiness` or `score_breakdown`.

- [ ] **Step 3: Implement metadata in `build_match_explanation()`**

In `backend/services/matching.py`, import is already available:

```python
from services.agent_readiness import get_agent_readiness
```

Inside `build_match_explanation()`, after `repute` is calculated, add:

```python
    readiness = get_agent_readiness(agent)
    repute_component = round(ALPHA * (repute / 5.0) * 100)
    match_component = round(BETA * match_score * 100)
```

Then add these keys to the returned dict:

```python
        "readiness": readiness,
        "score_breakdown": {
            "formula": "0.6 * (repute / 5.0) + 0.4 * match_score",
            "repute_weight": ALPHA,
            "match_weight": BETA,
            "repute_score": repute,
            "match_score": round(match_score * 100),
            "repute_component": repute_component,
            "match_component": match_component,
            "overall_score": overall,
        },
```

- [ ] **Step 4: Run matching tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_matching.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit backend formatter change**

Run:

```bash
git add backend/services/matching.py backend/tests/test_matching.py
git commit -m "Expose match score breakdown"
```

### Task 2: Question Detail API Routing Metadata

**Files:**
- Modify: `backend/routers/questions.py`
- Test: `backend/tests/test_question_delivery.py`

- [ ] **Step 1: Add focused test for explanation enrichment**

Append this test to `backend/tests/test_question_delivery.py`:

```python
@pytest.mark.asyncio
async def test_build_question_match_explanations_includes_answer_routing_metadata(monkeypatch):
    from types import SimpleNamespace
    from routers.questions import build_question_match_explanations

    q = SimpleNamespace(
        id="q_test",
        title="AI 系统设计",
        body="需要架构建议",
        tags=["AI", "系统设计"],
        max_responders=1,
        matched_agent_ids=["a_test"],
    )
    agent = SimpleNamespace(
        id="a_test",
        name="RouterSmith",
        agent_type="hermes",
        tags=["AI", "系统设计"],
        description="擅长系统架构",
        repute_score=4.5,
        total_answers=10,
        approval_rate=0.8,
        status="online",
        review_rules={"agentmint_readiness": {"state": "ready"}},
    )
    answer = SimpleNamespace(
        agent_id="a_test",
        request_id="req_q_test_a_test",
        status="pushed",
        review_method="auto",
    )

    class Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class DB:
        async def execute(self, stmt):
            text = str(stmt)
            if "answers" in text:
                return Result([answer])
            return Result([agent])

    explanations = await build_question_match_explanations(DB(), q)

    assert explanations[0]["request_id"] == "req_q_test_a_test"
    assert explanations[0]["answer_status"] == "pushed"
    assert explanations[0]["review_method"] == "auto"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_question_delivery.py::test_build_question_match_explanations_includes_answer_routing_metadata -q
```

Expected: fail with missing `request_id`, `answer_status`, or `review_method`.

- [ ] **Step 3: Enrich `build_question_match_explanations()`**

In `backend/routers/questions.py`, inside `build_question_match_explanations()`, after loading agents, load answer rows:

```python
    answer_rows = await db.execute(
        select(Answer).where(Answer.question_id == q.id, Answer.agent_id.in_(agent_ids))
    )
    answer_by_agent_id = {answer.agent_id: answer for answer in answer_rows.scalars().all()}
```

Then replace:

```python
        explanations.append(build_match_explanation(agent, task_profile, score, match_type, "ok"))
```

with:

```python
        explanation = build_match_explanation(agent, task_profile, score, match_type, "ok")
        answer = answer_by_agent_id.get(agent_id)
        if answer:
            explanation.update({
                "request_id": answer.request_id,
                "answer_status": answer.status,
                "review_method": answer.review_method,
            })
        explanations.append(explanation)
```

- [ ] **Step 4: Run backend tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit API enrichment**

Run:

```bash
git add backend/routers/questions.py backend/tests/test_question_delivery.py
git commit -m "Add routing metadata to match explanations"
```

### Task 3: Frontend Types And Full Inspection UI

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/app/questions/[id]/page.tsx`

- [ ] **Step 1: Extend TypeScript types**

In `web/lib/types.ts`, add this interface:

```ts
export interface MatchScoreBreakdown {
  formula: string;
  repute_weight: number;
  match_weight: number;
  repute_score: number;
  match_score: number;
  repute_component: number;
  match_component: number;
  overall_score: number;
}
```

Then add these optional fields to `MatchExplanation`:

```ts
  readiness?: AgentReadiness;
  score_breakdown?: MatchScoreBreakdown;
  request_id?: string;
  answer_status?: string;
  review_method?: string;
```

- [ ] **Step 2: Replace compact Agent Casting cards**

In `web/app/questions/[id]/page.tsx`, keep `QuestionRoutingWorkbench()` but update the Agent side to render:

```tsx
<AgentMatchInspection key={agent.id} agent={agent} />
```

Add helper components below `ChipGroup()`:

```tsx
function AgentMatchInspection({ agent }: { agent: NonNullable<Question["match_explanations"]>[number] }) {
  const breakdown = agent.score_breakdown;
  const readinessState = agent.readiness?.state || "unknown";
  const evidence = [
    ["命中标签", agent.matched_tags],
    ["能力", agent.capability_hits],
    ["工具", agent.tool_hits || []],
    ["风格", agent.style_hits || []],
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

      <div className="mt-4 grid gap-2 sm:grid-cols-4">
        <ScoreBox label="match" value={agent.match_score} />
        <ScoreBox label="repute" value={Number(agent.repute_score).toFixed(1)} />
        <ScoreBox label="repute part" value={breakdown?.repute_component ?? "-"} />
        <ScoreBox label="match part" value={breakdown?.match_component ?? "-"} />
      </div>

      {breakdown && (
        <p className="mt-2 rounded-md bg-white px-3 py-2 font-mono text-[11px] text-gray-500">
          {breakdown.formula}
        </p>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {evidence.map(([label, values]) => (
          <EvidenceGroup key={label} label={label} values={values} />
        ))}
      </div>

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
```

- [ ] **Step 3: Add no-match diagnostic UI**

In `QuestionRoutingWorkbench()`, if `profile` exists and `explanations.length === 0`, render this section in place of the Agent list:

```tsx
<section className="rounded-lg border border-gray-100 bg-white p-5">
  <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Agent Casting</p>
  <h2 className="mt-1 text-base font-semibold text-gray-950">没有匹配到可派单 Agent</h2>
  <div className="mt-4 grid gap-2 text-sm text-gray-500">
    {["没有在线公开 Agent", "Agent 未完成 readiness 验证", "标签或相似领域没有命中", "Agent 配额已被阻塞"].map(reason => (
      <div key={reason} className="rounded-md bg-gray-50 px-3 py-2">{reason}</div>
    ))}
  </div>
</section>
```

- [ ] **Step 4: Build frontend**

Run:

```bash
npm --prefix web run build
```

Expected: build completes successfully.

- [ ] **Step 5: Commit frontend UI**

Run:

```bash
git add web/lib/types.ts web/app/questions/[id]/page.tsx
git commit -m "Show full match explanation panel"
```

### Task 4: Final Verification And Push

**Files:**
- Verify only.

- [ ] **Step 1: Run backend tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm --prefix web run build
```

Expected: build completes successfully.

- [ ] **Step 3: Check whitespace and status**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors; branch may be ahead of origin by new commits.

- [ ] **Step 4: Push**

Run:

```bash
git push
```

Expected: remote `main` updates successfully.

- [ ] **Step 5: Provide deployment commands**

Tell the user to run on the container server:

```bash
git pull
docker compose up -d --build
```

