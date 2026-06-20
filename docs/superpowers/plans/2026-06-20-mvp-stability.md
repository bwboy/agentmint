# AgentMint MVP Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the MVP delivery path so billing, quota, and answer uploads follow the approved spec.

**Architecture:** Keep the change local to the existing FastAPI router and review service. The question endpoint still performs matching, row creation, synchronous WebSocket push, and response construction in one path; this plan only changes when fuel is deducted and when duplicate answer uploads are accepted.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, pytest, pytest-asyncio.

---

## File Map

- Modify `backend/routers/questions.py`: charge fuel from `pushed_count`, return final `fuel_cost`, keep zero-delivery questions open.
- Modify `backend/services/review.py`: ignore duplicate answer uploads after the first accepted result.
- Add `backend/tests/test_question_delivery.py`: focused route-level tests for actual-push billing and quota calls.
- Add `backend/tests/test_review_idempotency.py`: focused service tests for duplicate upload handling.

---

### Task 1: Add Question Delivery Billing Tests

**Files:**
- Create: `backend/tests/test_question_delivery.py`
- Modify later: `backend/routers/questions.py`

- [ ] **Step 1: Write failing tests for zero and partial delivery**

Create `backend/tests/test_question_delivery.py` with:

```python
from types import SimpleNamespace

import pytest

from routers import questions


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, user):
        self.user = user
        self.added = []
        self.commits = 0
        self.flushed = 0
        self.refreshed = []

    async def execute(self, stmt):
        return FakeScalarResult(self.user)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = "q_test"


def make_user(balance=100_000):
    return SimpleNamespace(
        id="u_test",
        nickname="Tester",
        trust_level=3,
        fuel_balance=balance,
    )


def make_agent(agent_id, review_rules=None):
    return SimpleNamespace(
        id=agent_id,
        review_rules=review_rules or {"auto_trust_level": 2, "auto_tag_match": True},
    )


@pytest.mark.asyncio
async def test_create_question_zero_push_charges_zero(monkeypatch):
    user = make_user()
    db = FakeDB(user)
    agent = make_agent("a_zero")

    async def fake_match_agents(db_arg, tags, max_responders):
        return [(agent, 1.0, "exact", "ok")]

    async def fake_push_question(agent_id, payload):
        return False

    async def fail_increment_usage(db_arg, agent_id):
        raise AssertionError("quota must not increment when push fails")

    monkeypatch.setattr(questions, "match_agents", fake_match_agents)
    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)
    monkeypatch.setattr(questions, "increment_usage", fail_increment_usage)

    res = await questions.create_question(
        questions.CreateQuestionReq(title="Zero push", tags=["rust"], max_responders=1),
        user_payload={"sub": user.id},
        db=db,
    )

    assert res["matched_count"] == 1
    assert res["pushed_count"] == 0
    assert res["fuel_cost"] == 0
    assert res["estimated_fuel_cost"] == 0
    assert user.fuel_balance == 100_000


@pytest.mark.asyncio
async def test_create_question_partial_push_charges_only_successes(monkeypatch):
    user = make_user()
    db = FakeDB(user)
    agents = [make_agent("a_ok"), make_agent("a_fail")]
    incremented = []

    async def fake_match_agents(db_arg, tags, max_responders):
        return [
            (agents[0], 1.0, "exact", "ok"),
            (agents[1], 1.0, "exact", "ok"),
        ]

    async def fake_push_question(agent_id, payload):
        return agent_id == "a_ok"

    async def fake_increment_usage(db_arg, agent_id):
        incremented.append(agent_id)
        return len(incremented)

    monkeypatch.setattr(questions, "match_agents", fake_match_agents)
    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)
    monkeypatch.setattr(questions, "increment_usage", fake_increment_usage)

    res = await questions.create_question(
        questions.CreateQuestionReq(title="Partial push", tags=["rust"], max_responders=2),
        user_payload={"sub": user.id},
        db=db,
    )

    assert res["matched_count"] == 2
    assert res["pushed_count"] == 1
    assert res["fuel_cost"] == questions.AVG_TOKENS_PER_ANSWER
    assert res["estimated_fuel_cost"] == questions.AVG_TOKENS_PER_ANSWER
    assert user.fuel_balance == 100_000 - questions.AVG_TOKENS_PER_ANSWER
    assert incremented == ["a_ok"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
backend/.venv/bin/pytest -q backend/tests/test_question_delivery.py
```

Expected: tests fail because `create_question()` charges by matched count and does not return `fuel_cost`.

---

### Task 2: Implement Actual-Push Billing

**Files:**
- Modify: `backend/routers/questions.py`
- Test: `backend/tests/test_question_delivery.py`

- [ ] **Step 1: Update balance precheck and defer final deduction**

In `backend/routers/questions.py`, inside `create_question()`, replace the current early `fuel_cost` calculation and immediate balance deduction with a maximum-cost precheck:

```python
rate = EMERGENCY_FUEL_MULTIPLIER if req.is_emergency else 1
max_possible_fuel_cost = len(matched) * AVG_TOKENS_PER_ANSWER * rate

if int(user.fuel_balance or 0) < max_possible_fuel_cost:
    raise HTTPException(status_code=402, detail="燃值不足")
```

Set the initial `Question.fuel_cost` to `0` when constructing `q`.

- [ ] **Step 2: Deduct final fuel after WebSocket push attempts**

After the push loop, compute and persist the final cost:

```python
fuel_cost = pushed_count * AVG_TOKENS_PER_ANSWER * rate
q.fuel_cost = fuel_cost
user.fuel_balance = int(user.fuel_balance or 0) - fuel_cost
```

Keep `pushed_count=0` valid, with `fuel_cost=0` and `q.status` unchanged.

- [ ] **Step 3: Return final fuel fields**

Update the response to include:

```python
"estimated_fuel_cost": fuel_cost,
"fuel_cost": fuel_cost,
```

- [ ] **Step 4: Run delivery tests**

Run:

```bash
backend/.venv/bin/pytest -q backend/tests/test_question_delivery.py
```

Expected: both tests pass.

---

### Task 3: Add Answer Upload Idempotency Tests

**Files:**
- Create: `backend/tests/test_review_idempotency.py`
- Modify later: `backend/services/review.py`

- [ ] **Step 1: Write failing duplicate-upload test**

Create `backend/tests/test_review_idempotency.py` with:

```python
from types import SimpleNamespace

import pytest

from services import review


class FakeExecuteResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, answer):
        self.answer = answer
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        return FakeExecuteResult(self.answer)

    async def commit(self):
        self.commits += 1


def make_answer(status="approved"):
    return SimpleNamespace(
        id="ans_test",
        request_id="req_test",
        agent_id="a_test",
        question_id="q_test",
        content={"text": "first"},
        model="model-first",
        usage={"total_tokens": 10},
        capability={},
        status=status,
        review_method="auto",
        reviewed_at=None,
        fuel_earned=10,
    )


@pytest.mark.asyncio
async def test_duplicate_upload_does_not_overwrite_terminal_answer(monkeypatch):
    answer = make_answer(status="approved")
    session = FakeSession(answer)

    monkeypatch.setattr(review, "AsyncSessionLocal", lambda: session)

    await review.handle_uploaded_answer("a_test", {
        "type": "answer",
        "request_id": "req_test",
        "status": "success",
        "content": {"text": "second"},
        "model": "model-second",
        "usage": {"total_tokens": 99},
        "capability": {"tools": [{"name": "late"}]},
    })

    assert answer.content == {"text": "first"}
    assert answer.model == "model-first"
    assert answer.usage == {"total_tokens": 10}
    assert answer.status == "approved"
    assert session.commits == 0
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
backend/.venv/bin/pytest -q backend/tests/test_review_idempotency.py
```

Expected: test fails because `handle_uploaded_answer()` currently overwrites content before checking status.

---

### Task 4: Implement Answer Upload Idempotency

**Files:**
- Modify: `backend/services/review.py`
- Test: `backend/tests/test_review_idempotency.py`

- [ ] **Step 1: Add immutable states guard**

In `backend/services/review.py`, inside `handle_uploaded_answer()` after loading `answer` and before mutating fields, add:

```python
if answer.status in {"draft", "approved", "rejected", "expired"}:
    print(f"[review] duplicate answer ignored for request_id={request_id}, status={answer.status}")
    return
```

- [ ] **Step 2: Run idempotency test**

Run:

```bash
backend/.venv/bin/pytest -q backend/tests/test_review_idempotency.py
```

Expected: test passes.

---

### Task 5: Run Full Verification

**Files:**
- Verify all modified files

- [ ] **Step 1: Run backend tests**

Run:

```bash
backend/.venv/bin/pytest -q backend/tests
```

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend build**

Run:

```bash
npm run build
```

Working directory: `web`

Expected: Next.js production build passes.

- [ ] **Step 3: Review git diff**

Run:

```bash
git diff -- backend/routers/questions.py backend/services/review.py backend/tests/test_question_delivery.py backend/tests/test_review_idempotency.py
```

Expected: diff only contains the approved MVP stability changes.

- [ ] **Step 4: Commit implementation**

Run:

```bash
git add backend/routers/questions.py backend/services/review.py backend/tests/test_question_delivery.py backend/tests/test_review_idempotency.py docs/superpowers/plans/2026-06-20-mvp-stability.md
git commit -m "Stabilize MVP delivery billing"
```
