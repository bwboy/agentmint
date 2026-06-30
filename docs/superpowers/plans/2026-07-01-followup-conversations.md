# Follow-up Conversations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build owner-only follow-up questions that can quote an approved answer, route the same follow-up to one or more Agents that already answered the root question, and use Hermes conversation memory when warm.

**Architecture:** Store follow-ups as normal `questions` rows linked to a root question and quoted answer, with one `answers` row per target Agent. Use `conversation_id = conv_{root_question_id}_{agent_id}` as the Hermes chat/session id while keeping `request_id` as the AgentMint upload id. The backend always sends structured quote context; the Hermes plugin chooses a short warm prompt or a quoted cold prompt.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, pytest, Next.js App Router, React client components, Hermes platform plugin, SQLite local queue.

---

## File Structure

- Modify `backend/models/question.py`: add follow-up linkage columns.
- Modify `backend/models/answer.py`: add conversation and parent-answer columns.
- Create `backend/services/schema_migrations.py`: idempotent startup column migration for existing container Postgres databases.
- Modify `backend/main.py`: run schema migration before WebSocket heartbeat startup.
- Create `backend/services/followups.py`: validation, response serialization, and WebSocket payload helpers.
- Modify `backend/routers/questions.py`: root feed filtering, root detail follow-up threads, `POST /api/questions/{question_id}/followups`, root question `conversation_id`.
- Create `backend/tests/test_followups.py`: backend unit tests for validation, creation, charging, and detail threading.
- Modify `connector/hermes-plugin/queue.py`: expose chat/conversation lookups needed for warm/cold state.
- Modify `connector/hermes-plugin/adapter.py`: split `conversation_id` from `request_id`, serialize one active turn per conversation, warm/cold follow-up prompt building.
- Modify `connector/hermes-plugin/ws_client.py`: bump `AGENTMINT_WS_CLIENT_VERSION`.
- Modify `connector/hermes-plugin/test_adapter_usage.py`: plugin unit tests for conversation routing and prompt strategy.
- Modify `docs/api-spec.md` and `docs/ws-protocol.md`: keep final implemented payload shape documented.
- Modify `web/lib/types.ts`: add follow-up fields and response types.
- Create `web/components/question/FollowUpComposer.tsx`: client-side follow-up form and multi-Agent selector.
- Modify `web/components/question/QuestionAnswerPoller.logic.ts`: include follow-up pending answers in polling signature.
- Modify `web/components/question/QuestionAnswerPoller.tsx`: poll against root plus follow-up answer counts.
- Modify `web/app/questions/[id]/page.tsx`: render follow-up controls and compact answer threads.

## Implementation Notes

- Existing deployments have PostgreSQL tables already created, and the app currently has no Alembic flow. This feature must include an idempotent startup migration; changing SQLAlchemy models alone will not add columns in the user's container database.
- Existing public feeds must show root questions only. Follow-up rows are internal turns and appear only inside root question detail.
- Existing answer upload protocol remains unchanged. The backend identifies the answer row by `request_id`.
- First release keeps follow-ups owner-only. Public viewers can read approved follow-up threads returned in root detail but cannot create them.

---

### Task 1: Backend Schema and Startup Migration

**Files:**
- Modify: `backend/models/question.py`
- Modify: `backend/models/answer.py`
- Create: `backend/services/schema_migrations.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_followups.py`

- [ ] **Step 1: Write failing migration tests**

Add these tests to `backend/tests/test_followups.py`:

```python
from services.schema_migrations import FOLLOWUP_SCHEMA_SQL


def test_followup_schema_migration_adds_question_columns():
    sql = "\n".join(FOLLOWUP_SCHEMA_SQL)
    assert "ALTER TABLE questions ADD COLUMN IF NOT EXISTS root_question_id" in sql
    assert "ALTER TABLE questions ADD COLUMN IF NOT EXISTS parent_question_id" in sql
    assert "ALTER TABLE questions ADD COLUMN IF NOT EXISTS quoted_answer_id" in sql
    assert "ALTER TABLE questions ADD COLUMN IF NOT EXISTS turn_type" in sql
    assert "UPDATE questions SET turn_type='root' WHERE turn_type IS NULL" in sql


def test_followup_schema_migration_adds_answer_columns():
    sql = "\n".join(FOLLOWUP_SCHEMA_SQL)
    assert "ALTER TABLE answers ADD COLUMN IF NOT EXISTS conversation_id" in sql
    assert "ALTER TABLE answers ADD COLUMN IF NOT EXISTS parent_answer_id" in sql
    assert "ALTER TABLE answers ADD COLUMN IF NOT EXISTS turn_type" in sql
    assert "UPDATE answers SET turn_type='root' WHERE turn_type IS NULL" in sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_followups.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'services.schema_migrations'`.

- [ ] **Step 3: Add model columns**

In `backend/models/question.py`, add these mapped columns after `status`:

```python
    root_question_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_question_id: Mapped[str | None] = mapped_column(String, nullable=True)
    quoted_answer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_type: Mapped[str] = mapped_column(String, default="root")  # root | followup
```

In `backend/models/answer.py`, add these mapped columns after `request_id`:

```python
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_answer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_type: Mapped[str] = mapped_column(String, default="root")  # root | followup
```

- [ ] **Step 4: Create startup migration helper**

Create `backend/services/schema_migrations.py`:

```python
"""Small idempotent schema migrations for container deployments without Alembic."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


FOLLOWUP_SCHEMA_SQL = [
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS root_question_id VARCHAR",
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS parent_question_id VARCHAR",
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS quoted_answer_id VARCHAR",
    "ALTER TABLE questions ADD COLUMN IF NOT EXISTS turn_type VARCHAR",
    "UPDATE questions SET turn_type='root' WHERE turn_type IS NULL",
    "ALTER TABLE questions ALTER COLUMN turn_type SET DEFAULT 'root'",
    "CREATE INDEX IF NOT EXISTS idx_questions_root_question_id ON questions(root_question_id)",
    "CREATE INDEX IF NOT EXISTS idx_questions_quoted_answer_id ON questions(quoted_answer_id)",
    "ALTER TABLE answers ADD COLUMN IF NOT EXISTS conversation_id VARCHAR",
    "ALTER TABLE answers ADD COLUMN IF NOT EXISTS parent_answer_id VARCHAR",
    "ALTER TABLE answers ADD COLUMN IF NOT EXISTS turn_type VARCHAR",
    "UPDATE answers SET turn_type='root' WHERE turn_type IS NULL",
    "ALTER TABLE answers ALTER COLUMN turn_type SET DEFAULT 'root'",
    "CREATE INDEX IF NOT EXISTS idx_answers_conversation_id ON answers(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_answers_parent_answer_id ON answers(parent_answer_id)",
]


async def run_startup_schema_migrations(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in FOLLOWUP_SCHEMA_SQL:
            await conn.execute(text(sql))
```

- [ ] **Step 5: Run migration in app startup**

Modify `backend/main.py` imports:

```python
from database import engine
from services.schema_migrations import run_startup_schema_migrations
```

Modify `lifespan()` before `await hub.mark_all_offline()`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup_schema_migrations(engine)
    await hub.mark_all_offline()
```

- [ ] **Step 6: Verify schema tests pass**

Run: `pytest backend/tests/test_followups.py -q`

Expected: PASS for the two migration tests.

- [ ] **Step 7: Commit**

```bash
git add backend/models/question.py backend/models/answer.py backend/services/schema_migrations.py backend/main.py backend/tests/test_followups.py
git commit -m "Add follow-up schema migration"
```

---

### Task 2: Backend Follow-up Service and API

**Files:**
- Create: `backend/services/followups.py`
- Modify: `backend/routers/questions.py`
- Test: `backend/tests/test_followups.py`

- [ ] **Step 1: Write service tests for validation and creation**

Append to `backend/tests/test_followups.py`:

```python
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.followups import (
    build_conversation_id,
    build_followup_payload,
    ensure_followup_targets,
)


def test_build_conversation_id_is_stable_per_root_and_agent():
    assert build_conversation_id("q_root", "a_1") == "conv_q_root_a_1"


def test_build_followup_payload_contains_quote_context():
    root = SimpleNamespace(id="q_root", title="Root title", body="Root body", tags=["wow"], deadline_at=datetime.utcnow())
    followup = SimpleNamespace(id="q_fu", title="追问：Root title", body="More?", tags=["wow"], deadline_at=datetime.utcnow() + timedelta(minutes=30))
    answer = SimpleNamespace(
        id="ans_1",
        agent_id="a_1",
        request_id="req_q_fu_a_1",
        conversation_id="conv_q_root_a_1",
        review_method="auto",
    )
    quoted = SimpleNamespace(id="ans_root", agent_id="a_1", content={"text": "Original answer"})
    payload = build_followup_payload(
        root_question=root,
        followup_question=followup,
        answer=answer,
        quoted_answer=quoted,
        asker={"nickname": "Gavin", "trust_level": 3},
    )
    assert payload["request_id"] == "req_q_fu_a_1"
    assert payload["conversation_id"] == "conv_q_root_a_1"
    assert payload["turn_type"] == "followup"
    assert payload["context_mode"] == "auto"
    assert payload["root_question"]["id"] == "q_root"
    assert payload["quoted_answer"]["text"] == "Original answer"
    assert payload["body"] == "More?"


def test_ensure_followup_targets_rejects_agent_without_root_answer():
    approved = [
        SimpleNamespace(agent_id="a_1", id="ans_1", status="approved"),
    ]
    with pytest.raises(HTTPException) as err:
        ensure_followup_targets(["a_1", "a_2"], approved)
    assert err.value.status_code == 400
    assert "没有已发布回答" in err.value.detail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_followups.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing functions in `services.followups`.

- [ ] **Step 3: Implement `backend/services/followups.py`**

Create `backend/services/followups.py`:

```python
from datetime import datetime
from typing import Any

from fastapi import HTTPException


def build_conversation_id(root_question_id: str, agent_id: str) -> str:
    return f"conv_{root_question_id}_{agent_id}"


def answer_text(answer: Any) -> str:
    content = getattr(answer, "content", None) or {}
    if isinstance(content, dict):
        return str(content.get("text") or "")
    return ""


def ensure_followup_targets(agent_ids: list[str], approved_root_answers: list[Any]) -> list[str]:
    requested = [str(agent_id).strip() for agent_id in agent_ids if str(agent_id).strip()]
    deduped = list(dict.fromkeys(requested))
    if not deduped:
        raise HTTPException(status_code=400, detail="请选择至少一个已回答的 Agent")

    approved_by_agent = {answer.agent_id: answer for answer in approved_root_answers if answer.status == "approved"}
    missing = [agent_id for agent_id in deduped if agent_id not in approved_by_agent]
    if missing:
        raise HTTPException(status_code=400, detail=f"Agent 没有已发布回答，不能追问: {', '.join(missing)}")
    return deduped


def build_root_payload(question: Any, answer: Any, asker: dict) -> dict:
    return {
        "request_id": answer.request_id,
        "conversation_id": answer.conversation_id,
        "turn_type": "root",
        "context_mode": "root",
        "title": question.title,
        "body": question.body,
        "tags": list(question.tags or []),
        "asker": asker,
        "auto_release": answer.review_method == "auto",
        "deadline_at": question.deadline_at.isoformat(),
    }


def build_followup_payload(
    *,
    root_question: Any,
    followup_question: Any,
    answer: Any,
    quoted_answer: Any,
    asker: dict,
) -> dict:
    return {
        "request_id": answer.request_id,
        "conversation_id": answer.conversation_id,
        "turn_type": "followup",
        "context_mode": "auto",
        "title": followup_question.title,
        "body": followup_question.body,
        "tags": list(followup_question.tags or []),
        "root_question": {
            "id": root_question.id,
            "title": root_question.title,
            "body": root_question.body,
            "tags": list(root_question.tags or []),
        },
        "quoted_answer": {
            "id": quoted_answer.id,
            "agent_id": quoted_answer.agent_id,
            "text": answer_text(quoted_answer),
        },
        "followup": {"text": followup_question.body},
        "asker": asker,
        "auto_release": answer.review_method == "auto",
        "deadline_at": followup_question.deadline_at.isoformat(),
    }
```

- [ ] **Step 4: Add request model and root payload helper imports**

In `backend/routers/questions.py`, extend imports:

```python
from services.followups import (
    build_conversation_id,
    build_followup_payload,
    build_root_payload,
    ensure_followup_targets,
)
```

Add request model near `CreateQuestionReq`:

```python
class CreateFollowUpReq(BaseModel):
    quoted_answer_id: str = Field(min_length=1)
    agent_ids: list[str] = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4000)
    deadline_minutes: int = 30
```

- [ ] **Step 5: Store conversation ids for root questions**

In `create_question()`, when creating `Answer`, set:

```python
            conversation_id=build_conversation_id(q.id, agent.id),
            turn_type="root",
```

Replace the root question push payload block with:

```python
        payload = build_root_payload(
            q,
            ans,
            {"nickname": user.nickname, "trust_level": user.trust_level},
        )
```

- [ ] **Step 6: Add follow-up endpoint**

Add this endpoint before `build_question_match_explanations()` in `backend/routers/questions.py`:

```python
@router.post("/questions/{question_id}/followups", status_code=201)
async def create_followup(
    question_id: str,
    req: CreateFollowUpReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_payload["sub"]))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    question = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")

    root_id = question.root_question_id or question.id
    root = question if question.id == root_id else (
        await db.execute(select(Question).where(Question.id == root_id))
    ).scalar_one_or_none()
    if not root:
        raise HTTPException(status_code=404, detail="根问题不存在")
    if root.asker_id != user.id:
        raise HTTPException(status_code=403, detail="只有提问者可以追问")

    quoted_answer = (await db.execute(
        select(Answer).where(
            Answer.id == req.quoted_answer_id,
            Answer.question_id == root.id,
            Answer.status == "approved",
        )
    )).scalar_one_or_none()
    if not quoted_answer:
        raise HTTPException(status_code=400, detail="引用回答不存在或尚未发布")

    approved_answers = (await db.execute(
        select(Answer).where(Answer.question_id == root.id, Answer.status == "approved")
    )).scalars().all()
    target_agent_ids = ensure_followup_targets(req.agent_ids, list(approved_answers))

    agents = (await db.execute(select(Agent).where(Agent.id.in_(target_agent_ids)))).scalars().all()
    agent_by_id = {agent.id: agent for agent in agents}
    missing_agents = [agent_id for agent_id in target_agent_ids if agent_id not in agent_by_id]
    if missing_agents:
        raise HTTPException(status_code=400, detail=f"Agent 不存在: {', '.join(missing_agents)}")

    max_possible_fuel_cost = len(target_agent_ids) * AVG_TOKENS_PER_ANSWER
    if int(user.fuel_balance or 0) < max_possible_fuel_cost:
        raise HTTPException(status_code=402, detail="燃值不足")

    deadline = datetime.utcnow() + timedelta(minutes=max(1, req.deadline_minutes))
    followup = Question(
        asker_id=user.id,
        title=f"追问：{root.title}",
        body=req.text,
        tags=list(root.tags or []),
        deadline_at=deadline,
        max_responders=len(target_agent_ids),
        matched_agent_ids=target_agent_ids,
        fuel_cost=0,
        root_question_id=root.id,
        parent_question_id=question.id,
        quoted_answer_id=quoted_answer.id,
        turn_type="followup",
    )
    db.add(followup)
    await db.flush()

    answer_records: list[tuple[Answer, Agent]] = []
    for agent_id in target_agent_ids:
        agent = agent_by_id[agent_id]
        review_method = decide_review_method(
            quota_state="ok",
            asker_trust_level=int(user.trust_level or 1),
            review_rules=agent.review_rules,
            match_type="followup",
        )
        answer = Answer(
            question_id=followup.id,
            agent_id=agent.id,
            request_id=f"req_{followup.id}_{agent.id}",
            conversation_id=build_conversation_id(root.id, agent.id),
            parent_answer_id=quoted_answer.id,
            turn_type="followup",
            status="assigned",
            review_method=review_method,
        )
        db.add(answer)
        answer_records.append((answer, agent))

    await db.commit()
    await db.refresh(followup)

    pushed_count = 0
    requests = []
    asker = {"nickname": user.nickname, "trust_level": user.trust_level}
    for answer, agent in answer_records:
        payload = build_followup_payload(
            root_question=root,
            followup_question=followup,
            answer=answer,
            quoted_answer=quoted_answer,
            asker=asker,
        )
        delivered = await hub.push_question(agent.id, payload)
        status = "assigned"
        if delivered:
            pushed_count += 1
            answer.status = "pushed"
            status = "pushed"
            try:
                await increment_usage(db, agent.id)
            except Exception as e:
                print(f"[questions] quota increment failed for {agent.id}: {e}")
        requests.append({
            "agent_id": agent.id,
            "request_id": answer.request_id,
            "conversation_id": answer.conversation_id,
            "status": status,
        })

    fuel_cost = pushed_count * AVG_TOKENS_PER_ANSWER
    followup.fuel_cost = fuel_cost
    user.fuel_balance = int(user.fuel_balance or 0) - fuel_cost
    await db.commit()

    return {
        "id": followup.id,
        "root_question_id": root.id,
        "quoted_answer_id": quoted_answer.id,
        "pushed_count": pushed_count,
        "fuel_cost": fuel_cost,
        "requests": requests,
    }
```

- [ ] **Step 7: Run backend tests for creation path**

Run: `pytest backend/tests/test_question_delivery.py backend/tests/test_followups.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/routers/questions.py backend/services/followups.py backend/tests/test_followups.py
git commit -m "Add follow-up question API"
```

---

### Task 3: Backend Detail Response and Feed Filtering

**Files:**
- Modify: `backend/routers/questions.py`
- Modify: `web/lib/types.ts`
- Test: `backend/tests/test_followups.py`

- [ ] **Step 1: Add tests for root-only feeds and follow-up detail shape**

Append focused unit tests to `backend/tests/test_followups.py`:

```python
from services.followups import serialize_followup_thread


def test_serialize_followup_thread_groups_approved_answers():
    followup = SimpleNamespace(
        id="q_fu",
        root_question_id="q_root",
        quoted_answer_id="ans_root",
        body="More?",
        created_at=datetime(2026, 7, 1, 12, 0, 0),
    )
    answer = SimpleNamespace(
        id="ans_fu",
        question_id="q_fu",
        agent_id="a_1",
        request_id="req_q_fu_a_1",
        conversation_id="conv_q_root_a_1",
        parent_answer_id="ans_root",
        content={"text": "Follow-up answer"},
        model="hermes",
        usage={},
        capability={},
        status="approved",
        review_method="auto",
        created_at=datetime(2026, 7, 1, 12, 1, 0),
    )
    out = serialize_followup_thread(
        followup,
        [(answer, "Mac上的爱马仕", "hermes", 4.8)],
        {},
    )
    assert out["id"] == "q_fu"
    assert out["quoted_answer_id"] == "ans_root"
    assert out["text"] == "More?"
    assert out["answers"][0]["conversation_id"] == "conv_q_root_a_1"
    assert out["answers"][0]["parent_answer_id"] == "ans_root"
```

- [ ] **Step 2: Implement serializer**

Add to `backend/services/followups.py`:

```python
def serialize_answer(answer: Any, agent_name: str, agent_type: str, repute_score: float, vote_summary: dict | None = None) -> dict:
    return {
        "id": answer.id,
        "question_id": answer.question_id,
        "agent": {
            "id": answer.agent_id,
            "name": agent_name,
            "agent_type": agent_type,
            "repute_score": float(repute_score or 0),
        },
        "request_id": answer.request_id,
        "conversation_id": answer.conversation_id,
        "parent_answer_id": answer.parent_answer_id,
        "turn_type": answer.turn_type,
        "content": answer.content or {},
        "model": answer.model,
        "usage": answer.usage or {},
        "capability": answer.capability or None,
        "status": answer.status,
        "review_method": answer.review_method,
        "vote_summary": vote_summary or {"up": 0, "down": 0},
        "created_at": answer.created_at.isoformat(),
    }


def serialize_followup_thread(followup: Any, answer_rows: list[tuple], vote_rows: dict[str, dict[str, int]]) -> dict:
    return {
        "id": followup.id,
        "root_question_id": followup.root_question_id,
        "quoted_answer_id": followup.quoted_answer_id,
        "text": followup.body,
        "created_at": followup.created_at.isoformat(),
        "answers": [
            serialize_answer(answer, agent_name, agent_type, repute_score, vote_rows.get(answer.id, {"up": 0, "down": 0}))
            for answer, agent_name, agent_type, repute_score in answer_rows
        ],
    }
```

- [ ] **Step 3: Filter public and owner question lists to root questions**

In `list_questions()`, after the base queries are created, add:

```python
    base = base.where(Question.root_question_id.is_(None))
    count_q = count_q.where(Question.root_question_id.is_(None))
```

In `my_questions()`, add the same filter:

```python
        select(Question).where(Question.asker_id == user_payload["sub"], Question.root_question_id.is_(None))
```

and:

```python
        select(func.count(Question.id)).where(Question.asker_id == user_payload["sub"], Question.root_question_id.is_(None))
```

- [ ] **Step 4: Return root detail with follow-up threads**

In `get_question()`, normalize follow-up ids to root:

```python
    if q.root_question_id:
        root_row = (await db.execute(
            select(Question, User.nickname, User.trust_level)
            .join(User, Question.asker_id == User.id)
            .where(Question.id == q.root_question_id)
        )).one_or_none()
        if not root_row:
            raise HTTPException(status_code=404, detail="根问题不存在")
        q, nickname, tl = root_row
```

Replace answer serialization with `serialize_answer(...)` from `services.followups`.

Before returning, query follow-ups:

```python
    followups = (await db.execute(
        select(Question)
        .where(Question.root_question_id == q.id, Question.turn_type == "followup")
        .order_by(Question.created_at.asc())
    )).scalars().all()
    followup_ids = [item.id for item in followups]
    followup_threads = []
    if followup_ids:
        followup_answer_rows = (await db.execute(
            select(Answer, Agent.name, Agent.agent_type, Agent.repute_score)
            .join(Agent, Answer.agent_id == Agent.id)
            .where(Answer.question_id.in_(followup_ids), Answer.status == "approved")
            .order_by(Answer.created_at.asc())
        )).all()
        rows_by_question: dict[str, list[tuple]] = {}
        for row in followup_answer_rows:
            answer = row[0]
            rows_by_question.setdefault(answer.question_id, []).append(row)
        followup_threads = [
            serialize_followup_thread(item, rows_by_question.get(item.id, []), vote_rows)
            for item in followups
        ]
```

Add `"followups": followup_threads` to the returned dict.

- [ ] **Step 5: Extend frontend types**

In `web/lib/types.ts`, add to `Question`:

```typescript
  root_question_id?: string | null;
  turn_type?: "root" | "followup";
  followups?: FollowUpThread[];
```

Add after `Question`:

```typescript
export interface FollowUpThread {
  id: string;
  root_question_id: string;
  quoted_answer_id: string;
  text: string;
  created_at: string;
  answers: Answer[];
}
```

Add to `Answer`:

```typescript
  conversation_id?: string | null;
  parent_answer_id?: string | null;
  turn_type?: "root" | "followup";
```

- [ ] **Step 6: Run backend tests**

Run: `pytest backend/tests/test_followups.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/routers/questions.py backend/services/followups.py backend/tests/test_followups.py web/lib/types.ts
git commit -m "Return follow-up threads in question detail"
```

---

### Task 4: Hermes Plugin Conversation Routing

**Files:**
- Modify: `connector/hermes-plugin/queue.py`
- Modify: `connector/hermes-plugin/adapter.py`
- Modify: `connector/hermes-plugin/ws_client.py`
- Test: `connector/hermes-plugin/test_adapter_usage.py`

- [ ] **Step 1: Add plugin tests**

Append to `connector/hermes-plugin/test_adapter_usage.py`:

```python
    def test_on_question_uses_conversation_id_as_chat_id(self):
        adapter_mod = self.adapter

        class FakeQueue:
            def upsert_pending(self, request_id, chat_id, question):
                self.request_id = request_id
                self.chat_id = chat_id
                self.question = question
                return True

        class FakeClient:
            def __init__(self):
                self.acked = []

            async def send_ack(self, request_id):
                self.acked.append(request_id)
                return True

        class TestAdapter(adapter_mod.ArenaAdapter):
            def __init__(self):
                self._queue = FakeQueue()
                self._client = FakeClient()
                self._job_started_at = {}
                self._prompt_text_by_request = {}
                self._active_request_by_chat = {}
                self._warm_conversations = set()
                self._conversation_locks = {}
                self.events = []

            def build_source(self, **kwargs):
                return SimpleNamespace(**kwargs)

            async def handle_message(self, event):
                self.events.append(event)

        async def run_case():
            adapter = TestAdapter()
            original_message_event = adapter_mod.MessageEvent
            original_message_type = adapter_mod.MessageType
            adapter_mod.MessageEvent = lambda **kwargs: SimpleNamespace(**kwargs)
            adapter_mod.MessageType = SimpleNamespace(TEXT="text")
            try:
                await adapter._on_question({
                    "request_id": "req_fu",
                    "conversation_id": "conv_q_root_a_1",
                    "turn_type": "followup",
                    "title": "追问：Root",
                    "body": "More?",
                    "tags": ["wow"],
                    "asker": {"nickname": "Gavin", "trust_level": 3},
                    "root_question": {"id": "q_root", "title": "Root", "body": "Body", "tags": ["wow"]},
                    "quoted_answer": {"id": "ans_root", "agent_id": "a_1", "text": "Original"},
                })
                return adapter
            finally:
                adapter_mod.MessageEvent = original_message_event
                adapter_mod.MessageType = original_message_type

        adapter = asyncio.run(run_case())
        self.assertEqual(adapter._queue.chat_id, "conv_q_root_a_1")
        self.assertEqual(adapter.events[0].source.chat_id, "conv_q_root_a_1")
        self.assertIn("Original", adapter.events[0].text)

    def test_format_followup_prompt_warm_omits_quote_context(self):
        prompt = self.adapter._format_followup_prompt(
            "More?",
            root_question={"title": "Root", "body": "Body", "tags": ["wow"]},
            quoted_answer={"text": "Original answer"},
            include_context=False,
        )
        self.assertIn("More?", prompt)
        self.assertNotIn("Original answer", prompt)

    def test_format_followup_prompt_cold_includes_quote_context(self):
        prompt = self.adapter._format_followup_prompt(
            "More?",
            root_question={"title": "Root", "body": "Body", "tags": ["wow"]},
            quoted_answer={"text": "Original answer"},
            include_context=True,
        )
        self.assertIn("Root", prompt)
        self.assertIn("Original answer", prompt)
        self.assertIn("More?", prompt)
```

- [ ] **Step 2: Run plugin tests to verify they fail**

Run: `python -m pytest connector/hermes-plugin/test_adapter_usage.py -q`

Expected: FAIL because `_format_followup_prompt` is missing and `_on_question()` still uses `request_id` as chat id.

- [ ] **Step 3: Initialize conversation state**

In `ArenaAdapter.__init__()`, add:

```python
        self._active_request_by_chat: dict[str, str] = {}
        self._warm_conversations: set[str] = set()
        self._conversation_locks: dict[str, asyncio.Lock] = {}
```

- [ ] **Step 4: Add prompt helper**

Add near `_format_prompt()` helpers in `connector/hermes-plugin/adapter.py`:

```python
def _format_followup_prompt(
    followup_text: str,
    *,
    root_question: dict | None,
    quoted_answer: dict | None,
    include_context: bool,
) -> str:
    followup_text = (followup_text or "").strip()
    if not include_context:
        return f"{followup_text}\n\n{AGENTMINT_PROMPT_SAFETY_GUIDANCE}".strip()

    root_question = root_question or {}
    quoted_answer = quoted_answer or {}
    tags = root_question.get("tags") or []
    tag_text = ", ".join(str(tag) for tag in tags) if tags else "无"
    return f"""
AgentMint 追问。当前 Hermes 会话可能刚启动，因此请用下面引用恢复上下文。

原问题：
标题：{root_question.get("title") or ""}
正文：{root_question.get("body") or ""}
标签：{tag_text}

被引用的上一条回答：
{quoted_answer.get("text") or ""}

用户追问：
{followup_text}

{AGENTMINT_PROMPT_SAFETY_GUIDANCE}
""".strip()
```

- [ ] **Step 5: Route inbound questions by conversation id**

In `_on_question()`, compute:

```python
        conversation_id = str(msg.get("conversation_id") or request_id)
        turn_type = str(msg.get("turn_type") or "root")
```

Store `conversation_id`, `turn_type`, `root_question`, and `quoted_answer` in `question_record`.

Change queue insert:

```python
        is_new = self._queue.upsert_pending(request_id, chat_id=conversation_id, question=question_record)
```

Build prompt:

```python
        if turn_type == "followup":
            include_context = conversation_id not in self._warm_conversations
            user_text = _format_followup_prompt(
                body,
                root_question=msg.get("root_question"),
                quoted_answer=msg.get("quoted_answer"),
                include_context=include_context,
            )
        else:
            user_text = _format_prompt(title, body, tags, asker_nick)
```

Set active request and Hermes source:

```python
        self._active_request_by_chat[conversation_id] = request_id
        source = self.build_source(
            chat_id=conversation_id,
            chat_name=f"Arena问题: {title[:40]}",
            chat_type="dm",
            user_id="agentmint-platform",
            user_name="AgentMint",
        )
```

- [ ] **Step 6: Serialize same-conversation turns**

At the dispatch point in `_on_question()`:

```python
        lock = self._conversation_locks.setdefault(conversation_id, asyncio.Lock())
        async with lock:
            self._active_request_by_chat[conversation_id] = request_id
            try:
                await self.handle_message(event)
            finally:
                self._active_request_by_chat.pop(conversation_id, None)
```

- [ ] **Step 7: Resolve outbound sends from conversation id to request id**

At the start of `send()`:

```python
        conversation_id = str(chat_id)
        request_id = self._active_request_by_chat.get(conversation_id, conversation_id)
```

When recursively finalizing streaming sends, use:

```python
                    chat_id=conversation_id,
```

In `edit_message()`, resolve the same way:

```python
        conversation_id = str(chat_id)
        request_id = self._active_request_by_chat.get(conversation_id, conversation_id)
```

- [ ] **Step 8: Mark conversations warm after successful upload**

In `_upload_answer()`, after `ok` from `self._client.send_answer(...)`, load the job and mark warm:

```python
        job = self._queue.by_request_id(request_id)
        if ok:
            if job and job.get("chat_id"):
                self._warm_conversations.add(str(job["chat_id"]))
```

- [ ] **Step 9: Replay reconnect jobs with stored conversation fields**

In `_on_reconnected()`, build `fake_msg` from saved question:

```python
                fake_msg = {
                    **q,
                    "request_id": job["request_id"],
                    "conversation_id": q.get("conversation_id") or job["chat_id"],
                }
```

- [ ] **Step 10: Bump plugin version**

In `connector/hermes-plugin/ws_client.py`, set:

```python
AGENTMINT_WS_CLIENT_VERSION = "2026-07-01.1"
```

- [ ] **Step 11: Run plugin tests**

Run: `python -m pytest connector/hermes-plugin/test_adapter_usage.py -q`

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add connector/hermes-plugin/adapter.py connector/hermes-plugin/queue.py connector/hermes-plugin/ws_client.py connector/hermes-plugin/test_adapter_usage.py
git commit -m "Use Hermes conversations for follow-ups"
```

---

### Task 5: Frontend Follow-up Composer and Threads

**Files:**
- Create: `web/components/question/FollowUpComposer.tsx`
- Modify: `web/app/questions/[id]/page.tsx`
- Modify: `web/components/question/QuestionAnswerPoller.logic.ts`
- Modify: `web/components/question/QuestionAnswerPoller.tsx`
- Modify: `web/lib/types.ts`

- [ ] **Step 1: Extend polling logic tests or pure helpers**

If `web/components/question/QuestionAnswerPoller.logic.test.ts` exists, add:

```typescript
import { answerUsageSignature } from "./QuestionAnswerPoller.logic";

it("includes follow-up answers in usage signature", () => {
  const signature = answerUsageSignature([
    { id: "ans_root", usage: { total_tokens: 10 }, status: "approved" } as any,
    { id: "ans_fu", usage: { total_tokens: 20 }, status: "approved" } as any,
  ]);
  expect(signature).toContain("ans_root");
  expect(signature).toContain("ans_fu");
});
```

If there is no frontend test runner configured, continue with build verification in Step 7.

- [ ] **Step 2: Create client composer**

Create `web/components/question/FollowUpComposer.tsx`:

```typescript
"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Answer } from "@/lib/types";

export function FollowUpComposer({
  questionId,
  quotedAnswer,
  approvedAnswers,
}: {
  questionId: string;
  quotedAnswer: Answer;
  approvedAnswers: Answer[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [selected, setSelected] = useState<string[]>([quotedAnswer.agent.id]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const agents = useMemo(() => {
    const byId = new Map<string, Answer>();
    for (const answer of approvedAnswers) byId.set(answer.agent.id, answer);
    return Array.from(byId.values());
  }, [approvedAnswers]);

  function toggleAgent(agentId: string) {
    setSelected((current) => {
      if (current.includes(agentId)) return current.filter((id) => id !== agentId);
      return [...current, agentId];
    });
  }

  async function submit() {
    setError("");
    const token = getToken();
    if (!token) {
      setError("请先登录后再追问");
      return;
    }
    if (!text.trim()) {
      setError("请输入追问内容");
      return;
    }
    if (selected.length === 0) {
      setError("请选择至少一个 Agent");
      return;
    }
    setSubmitting(true);
    try {
      await api(`/api/questions/${questionId}/followups`, {
        method: "POST",
        token,
        json: {
          quoted_answer_id: quotedAnswer.id,
          agent_ids: selected,
          text: text.trim(),
          deadline_minutes: 30,
        },
      });
      setText("");
      setOpen(false);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "追问提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50" onClick={() => setOpen(true)}>
        追问
      </button>
    );
  }

  return (
    <div className="mt-4 border-l-2 border-slate-300 pl-4">
      <div className="mb-3 flex flex-wrap gap-2">
        {agents.map((answer) => {
          const active = selected.includes(answer.agent.id);
          return (
            <button
              key={answer.agent.id}
              type="button"
              onClick={() => toggleAgent(answer.agent.id)}
              className={`rounded-full border px-3 py-1 text-xs ${active ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-700"}`}
            >
              {answer.agent.name}
            </button>
          );
        })}
      </div>
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={3}
        className="w-full rounded border border-slate-300 p-3 text-sm outline-none focus:border-slate-900"
        placeholder="继续追问这个回答..."
      />
      {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={submitting}
          className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {submitting ? "提交中" : "发送追问"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded border border-slate-300 px-4 py-2 text-sm">
          取消
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Render composer and follow-up threads**

In `web/app/questions/[id]/page.tsx`, import:

```typescript
import { FollowUpComposer } from "@/components/question/FollowUpComposer";
```

Inside each approved root answer card, render:

```tsx
<FollowUpComposer questionId={question.id} quotedAnswer={answer} approvedAnswers={answers} />
```

Below the answer content, render follow-up threads for that quoted answer:

```tsx
{(question.followups || [])
  .filter((thread) => thread.quoted_answer_id === answer.id)
  .map((thread) => (
    <div key={thread.id} className="mt-4 border-l-2 border-slate-200 pl-4">
      <div className="mb-2 text-sm font-medium text-slate-700">追问：{thread.text}</div>
      <div className="space-y-3">
        {thread.answers.map((followupAnswer) => (
          <div key={followupAnswer.id} className="rounded border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 text-xs text-slate-500">{followupAnswer.agent.name}</div>
            <div className="prose prose-sm max-w-none">{followupAnswer.content?.text}</div>
          </div>
        ))}
      </div>
    </div>
  ))}
```

- [ ] **Step 4: Include follow-up answers in polling**

In `QuestionAnswerPoller.tsx`, after fetching `latest`, compute:

```typescript
        const latestFollowupAnswers = (latest.followups || []).flatMap((thread) => thread.answers || []);
        const latestAnswers = [...(latest.answers || []), ...latestFollowupAnswers];
        const latestAnswerCount = latestAnswers.length || latest.answer_count || 0;
        const latestUsageSignature = answerUsageSignature(latestAnswers);
```

In `page.tsx`, pass current root plus follow-up answers to the signature:

```tsx
currentUsageSignature={answerUsageSignature([
  ...answers,
  ...(question.followups || []).flatMap((thread) => thread.answers || []),
])}
```

- [ ] **Step 5: Ensure text fits and actions are usable on mobile**

Use full-width textarea, wrapping chips, and normal button text. Keep the form inline under the answer instead of a modal so the quoted context remains visible.

- [ ] **Step 6: Run frontend build**

Run: `npm --prefix web run build`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/components/question/FollowUpComposer.tsx web/app/questions/[id]/page.tsx web/components/question/QuestionAnswerPoller.logic.ts web/components/question/QuestionAnswerPoller.tsx web/lib/types.ts
git commit -m "Add follow-up composer UI"
```

---

### Task 6: Documentation, Full Verification, and Push

**Files:**
- Modify: `docs/api-spec.md`
- Modify: `docs/ws-protocol.md`

- [ ] **Step 1: Update API docs**

In `docs/api-spec.md`, document:

~~~markdown
### POST /api/questions/{question_id}/followups

Creates an owner-only follow-up turn under a root question.

Request:

```json
{
  "quoted_answer_id": "ans_xxx",
  "agent_ids": ["a_1", "a_2"],
  "text": "如果我是新手怎么选？",
  "deadline_minutes": 30
}
```

Response:

```json
{
  "id": "q_followup",
  "root_question_id": "q_root",
  "quoted_answer_id": "ans_root",
  "pushed_count": 2,
  "fuel_cost": 4000,
  "requests": [
    {
      "agent_id": "a_1",
      "request_id": "req_q_followup_a_1",
      "conversation_id": "conv_q_root_a_1",
      "status": "pushed"
    }
  ]
}
```
~~~

- [ ] **Step 2: Update WebSocket docs**

In `docs/ws-protocol.md`, document question payload additions:

```json
{
  "type": "question",
  "request_id": "req_q_followup_a_1",
  "conversation_id": "conv_q_root_a_1",
  "turn_type": "followup",
  "context_mode": "auto",
  "root_question": {
    "id": "q_root",
    "title": "原问题",
    "body": "原问题正文",
    "tags": ["wow"]
  },
  "quoted_answer": {
    "id": "ans_root",
    "agent_id": "a_1",
    "text": "被引用的回答"
  }
}
```

State that `request_id` remains the upload id and `conversation_id` is the Hermes chat/session id.

- [ ] **Step 3: Run full verification**

Run:

```bash
pytest backend/tests/test_question_delivery.py backend/tests/test_followups.py -q
python -m pytest connector/hermes-plugin/test_adapter_usage.py -q
npm --prefix web run build
```

Expected: all commands PASS.

- [ ] **Step 4: Inspect git diff**

Run:

```bash
git diff --stat
git status --short
```

Expected: only follow-up conversation files and docs are changed.

- [ ] **Step 5: Commit docs and final fixes**

```bash
git add docs/api-spec.md docs/ws-protocol.md
git commit -m "Document follow-up conversations"
```

- [ ] **Step 6: Push for container deployment**

```bash
git push
```

Expected: push succeeds. The user can run `git pull` on the deployment machine, then restart containers so `run_startup_schema_migrations()` adds the new columns automatically.

---

## Self-Review

- Spec coverage: The plan covers owner-only follow-ups, multi-Agent target selection limited to approved root answer Agents, stable per-root-agent Hermes `conversation_id`, `request_id` upload idempotency, warm/cold quote prompts, root-only feeds, follow-up threads in detail, existing polling, plugin version bump, docs, and container-safe schema migration.
- Placeholder scan: The plan avoids undefined future work and includes exact files, functions, commands, request/response shapes, and code snippets for every implementation step.
- Type consistency: Backend fields use `root_question_id`, `parent_question_id`, `quoted_answer_id`, `turn_type`, `conversation_id`, and `parent_answer_id`; frontend types and WebSocket payloads use the same names; plugin maps `conversation_id` to Hermes `chat_id` and `request_id` to answer upload.
