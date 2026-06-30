# Learned Agent Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only system learned Agent profile generated from approved answers and feedback, then expose it in matching explanations and Agent management.

**Architecture:** Store learned profile data in `Agent.review_rules["learned_profile"]` to avoid schema migration. Add a focused backend service for normalization and incremental updates, call it from review approval and feedback submission, and extend matching/API/frontend display paths to consume the profile.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest, Next.js App Router, TypeScript, Tailwind CSS.

---

### Task 1: Learned Profile Service

**Files:**
- Create: `backend/services/learned_profile.py`
- Test: `backend/tests/test_learned_profile.py`

- [ ] **Step 1: Create tests**

Create tests for:

- default normalized learned profile
- approval update with question tags and task profile
- feedback update with up/down and previous vote reversal

- [ ] **Step 2: Implement service**

Implement:

- `LEARNED_PROFILE_KEY = "learned_profile"`
- `normalize_learned_profile(profile)`
- `get_agent_learned_profile(agent_or_rules)`
- `update_learned_profile_from_approval(agent, question, answer)`
- `update_learned_profile_from_feedback(agent, question, vote, previous_vote=None)`

List fields: `domain_tags`, `capability_tags`, `tool_tags`, `style_tags`, `positive_tags`, `negative_tags`.

Counters: `sample_count`, `positive_feedback`, `negative_feedback`.

- [ ] **Step 3: Run tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_learned_profile.py -q
```

- [ ] **Step 4: Commit**

Run:

```bash
git add backend/services/learned_profile.py backend/tests/test_learned_profile.py
git commit -m "Add learned agent profile service"
```

### Task 2: Wire Learning Into Review And Feedback

**Files:**
- Modify: `backend/services/review.py`
- Modify: `backend/routers/questions.py`
- Test: `backend/tests/test_review_idempotency.py`
- Test: `backend/tests/test_question_delivery.py`

- [ ] **Step 1: Approval learning**

In `_approve_inline()`, after loading `agent` and `question`, call:

```python
update_learned_profile_from_approval(agent, question, answer)
```

Keep it before `await db.commit()`.

- [ ] **Step 2: Feedback learning**

In `submit_feedback()`, after loading `agent`, call:

```python
update_learned_profile_from_feedback(agent, question, req.vote, previous_vote=prev_vote)
```

Load the question from `answer.question_id`.

- [ ] **Step 3: Add tests**

Add tests proving:

- auto/manual approval writes `learned_profile`.
- upvote increments positive tags.
- switching up to down decrements positive and increments negative.

- [ ] **Step 4: Run tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_review_idempotency.py backend/tests/test_question_delivery.py -q
```

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/services/review.py backend/routers/questions.py backend/tests/test_review_idempotency.py backend/tests/test_question_delivery.py
git commit -m "Learn profiles from approvals and feedback"
```

### Task 3: Matching And API Exposure

**Files:**
- Modify: `backend/services/matching.py`
- Modify: `backend/routers/agents.py`
- Test: `backend/tests/test_matching.py`
- Test: `backend/tests/test_agent_management.py`

- [ ] **Step 1: Matching uses learned tags**

Update matching candidate scoring so exact and similarity matching use:

```python
agent tags + explicit profile domain tags + learned profile domain tags + learned positive tags
```

- [ ] **Step 2: Explanation exposes learned hits**

`build_match_explanation()` returns:

- `learned_profile`
- `learned_hits`

Learned hits include overlaps between query/domain/capability signals and learned domain/capability/positive tags.

- [ ] **Step 3: Agent API exposes learned profile**

`_agent_to_dict()` returns:

```python
"learned_profile": get_agent_learned_profile(agent)
```

- [ ] **Step 4: Run tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_matching.py backend/tests/test_agent_management.py -q
```

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/services/matching.py backend/routers/agents.py backend/tests/test_matching.py backend/tests/test_agent_management.py
git commit -m "Use learned profiles in matching explanations"
```

### Task 4: Frontend Display

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/components/agent/MyAgentsPanel.tsx`
- Modify: `web/app/questions/[id]/page.tsx`

- [ ] **Step 1: Add types**

Add `AgentLearnedProfile` and wire:

- `Agent.learned_profile?: AgentLearnedProfile`
- `MatchExplanation.learned_profile?: AgentLearnedProfile`
- `MatchExplanation.learned_hits?: string[]`

- [ ] **Step 2: Agent management display**

Render learned profile below manual `CapabilityProfileView` with title `系统学习`.

- [ ] **Step 3: Question match display**

Add learned evidence group to `AgentMatchInspection`:

```tsx
["学习命中", agent.learned_hits || []]
```

Optionally show sample count in route signals.

- [ ] **Step 4: Build**

Run:

```bash
npm --prefix web run build
```

- [ ] **Step 5: Commit**

Run:

```bash
git add web/lib/types.ts web/components/agent/MyAgentsPanel.tsx web/app/questions/[id]/page.tsx
git commit -m "Show learned agent profiles"
```

### Task 5: Final Verification And Push

**Files:**
- Verify only.

- [ ] **Step 1: Backend tests**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

- [ ] **Step 2: Frontend build**

Run:

```bash
npm --prefix web run build
```

- [ ] **Step 3: Whitespace and status**

Run:

```bash
git diff --check
git status --short --branch
```

- [ ] **Step 4: Push**

Run:

```bash
git push
```

- [ ] **Step 5: Deployment note**

Tell the user:

```bash
git pull
docker compose up -d --build
```
