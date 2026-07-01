from datetime import datetime, timedelta
from operator import eq, ge
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.sql import operators
from sqlalchemy.sql.dml import Update

from routers import questions
from models import Agent, Answer, Question, User
from services import schema_migrations
from services.followups import (
    build_conversation_id,
    build_followup_payload,
    ensure_followup_targets,
)
from services.schema_migrations import FOLLOWUP_SCHEMA_SQL


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


def test_followup_schema_migration_adds_question_columns():
    sql = "\n".join(FOLLOWUP_SCHEMA_SQL)
    assert "ALTER TABLE questions ADD COLUMN IF NOT EXISTS root_question_id" in sql
    assert "ALTER TABLE questions ADD COLUMN IF NOT EXISTS parent_question_id" in sql
    assert "ALTER TABLE questions ADD COLUMN IF NOT EXISTS quoted_answer_id" in sql
    assert "ALTER TABLE questions ADD COLUMN IF NOT EXISTS turn_type" in sql
    assert "UPDATE questions SET turn_type='root' WHERE turn_type IS NULL" in sql
    assert "ALTER TABLE questions ALTER COLUMN turn_type SET NOT NULL" in sql


def test_followup_schema_migration_adds_answer_columns():
    sql = "\n".join(FOLLOWUP_SCHEMA_SQL)
    assert "ALTER TABLE answers ADD COLUMN IF NOT EXISTS conversation_id" in sql
    assert "ALTER TABLE answers ADD COLUMN IF NOT EXISTS parent_answer_id" in sql
    assert "ALTER TABLE answers ADD COLUMN IF NOT EXISTS turn_type" in sql
    assert "UPDATE answers SET turn_type='root' WHERE turn_type IS NULL" in sql
    assert "ALTER TABLE answers ALTER COLUMN turn_type SET NOT NULL" in sql


class FakeConnection:
    def __init__(self):
        self.executed = []

    async def execute(self, statement):
        self.executed.append(statement)


class FakeBeginContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeEngine:
    def __init__(self):
        self.connection = FakeConnection()

    def begin(self):
        return FakeBeginContext(self.connection)


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value


class FakeScalarListResult:
    def __init__(self, values):
        self.values = values

    def scalar_one_or_none(self):
        return self.values[0] if self.values else None

    def scalars(self):
        return self

    def all(self):
        return self.values


class FakeUpdateResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class FollowupRouteDB:
    def __init__(
        self,
        *,
        user=None,
        questions_by_id=None,
        answers_by_id=None,
        agents_by_id=None,
        balance_snapshot=None,
    ):
        self.user = user
        self.questions_by_id = questions_by_id or {}
        self.answers_by_id = answers_by_id or {}
        self.agents_by_id = agents_by_id or {}
        self.balance_snapshot = (
            int(user.fuel_balance or 0)
            if balance_snapshot is None and user is not None
            else balance_snapshot
        )
        self.added = []
        self.commits = 0
        self.flushed = 0
        self.answer_status_updates = []
        self.fuel_deductions = []
        self.fuel_refunds = []

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            return self._execute_update(stmt)

        entity = stmt.column_descriptions[0]["entity"]
        if entity is User:
            return FakeScalarResult(self.user if self._matches(self.user, stmt) else None)
        if entity is Question:
            values = [q for q in self.questions_by_id.values() if self._matches(q, stmt)]
            return FakeScalarResult(values[0] if values else None)
        if entity is Answer:
            values = [a for a in self.answers_by_id.values() if self._matches(a, stmt)]
            return FakeScalarListResult(values)
        if entity is Agent:
            values = [a for a in self.agents_by_id.values() if self._matches(a, stmt)]
            return FakeScalarListResult(values)
        raise AssertionError(f"unexpected statement: {stmt}")

    def add(self, obj):
        self.added.append(obj)
        if obj.__class__.__name__ == "Question":
            self.questions_by_id[getattr(obj, "id", None) or f"pending_q_{len(self.added)}"] = obj
        if obj.__class__.__name__ == "Answer":
            self.answers_by_id[getattr(obj, "id", None) or f"pending_ans_{len(self.added)}"] = obj

    async def flush(self):
        self.flushed += 1
        self._assign_pending_ids()

    async def commit(self):
        self._assign_pending_ids()
        self.commits += 1

    async def refresh(self, obj):
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.utcnow()

    def _assign_pending_ids(self):
        question_count = 0
        answer_count = 0
        for obj in self.added:
            if obj.__class__.__name__ == "Question":
                question_count += 1
                if getattr(obj, "id", None) is None:
                    obj.id = f"q_follow_{question_count}"
                self.questions_by_id[obj.id] = obj
            if obj.__class__.__name__ == "Answer":
                answer_count += 1
                if getattr(obj, "id", None) is None:
                    obj.id = f"ans_follow_{answer_count}"
                self.answers_by_id[obj.id] = obj

    def _execute_update(self, stmt):
        table_name = stmt.table.name
        if table_name == "answers":
            answer_id = self._where_value(stmt, "id")
            expected_status = self._where_value(stmt, "status")
            new_status = self._set_value(stmt, "status")
            answer = self.answers_by_id.get(answer_id)
            if answer and answer.status == expected_status:
                answer.status = new_status
                rowcount = 1
            else:
                rowcount = 0
            self.answer_status_updates.append({
                "answer_id": answer_id,
                "expected_status": expected_status,
                "new_status": new_status,
                "rowcount": rowcount,
            })
            return FakeUpdateResult(rowcount)

        if table_name == "users":
            user_id = self._where_value(stmt, "id")
            amount = self._fuel_amount_from_update(stmt)
            operator_name = next(iter(stmt._values.values())).operator.__name__
            if operator_name == "sub":
                if self.user and self.user.id == user_id and int(self.balance_snapshot or 0) >= amount:
                    self.balance_snapshot = int(self.balance_snapshot or 0) - amount
                    self.user.fuel_balance = int(self.user.fuel_balance or 0) - amount
                    rowcount = 1
                else:
                    rowcount = 0
                self.fuel_deductions.append({"user_id": user_id, "fuel_cost": amount, "rowcount": rowcount})
                return FakeUpdateResult(rowcount)
            if operator_name == "add":
                if self.user and self.user.id == user_id:
                    self.balance_snapshot = int(self.balance_snapshot or 0) + amount
                    self.user.fuel_balance = int(self.user.fuel_balance or 0) + amount
                rowcount = 1
                self.fuel_refunds.append({"user_id": user_id, "fuel_amount": amount})
                return FakeUpdateResult(rowcount)
            raise AssertionError(f"unexpected user update operator: {operator_name}")

        raise AssertionError(f"unexpected update: {stmt}")

    def _matches(self, obj, stmt):
        if obj is None:
            return False
        for criterion in stmt._where_criteria:
            field = criterion.left.name
            actual = getattr(obj, field)
            expected = criterion.right.value
            if criterion.operator is eq and actual != expected:
                return False
            if criterion.operator is operators.in_op and actual not in expected:
                return False
            if criterion.operator is ge and actual < expected:
                return False
        return True

    def _fuel_amount_from_update(self, stmt):
        value = next(iter(stmt._values.values()))
        return int(value.right.value)

    def _where_value(self, stmt, field_name):
        for criterion in stmt._where_criteria:
            if criterion.left.name == field_name:
                return criterion.right.value
        raise AssertionError(f"missing where value for {field_name}: {stmt}")

    def _set_value(self, stmt, field_name):
        for column, value in stmt._values.items():
            if column.name == field_name:
                return value.value
        raise AssertionError(f"missing set value for {field_name}: {stmt}")


def make_route_user(user_id="u_owner", balance=100_000):
    return SimpleNamespace(
        id=user_id,
        nickname="Tester",
        trust_level=3,
        fuel_balance=balance,
    )


def make_route_question(**overrides):
    data = {
        "id": "q_root",
        "asker_id": "u_owner",
        "title": "Root title",
        "body": "Root body",
        "tags": ["rust"],
        "deadline_at": datetime.utcnow() + timedelta(minutes=30),
        "max_responders": 2,
        "matched_agent_ids": ["a_ok", "a_fail"],
        "fuel_cost": 0,
        "status": "open",
        "root_question_id": None,
        "parent_question_id": None,
        "quoted_answer_id": None,
        "turn_type": "root",
        "created_at": datetime.utcnow(),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_route_answer(**overrides):
    data = {
        "id": "ans_quote",
        "question_id": "q_root",
        "agent_id": "a_ok",
        "request_id": "req_q_root_a_ok",
        "conversation_id": "conv_q_root_a_ok",
        "parent_answer_id": None,
        "turn_type": "root",
        "content": {"text": "Root answer"},
        "model": "",
        "usage": {},
        "capability": {},
        "status": "approved",
        "review_method": "auto",
        "fuel_earned": 0,
        "created_at": datetime.utcnow(),
        "reviewed_at": datetime.utcnow(),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_route_agent(agent_id):
    return SimpleNamespace(
        id=agent_id,
        review_rules={"auto_trust_level": 2, "auto_tag_match": True},
    )


@pytest.mark.asyncio
async def test_startup_schema_migrations_execute_all_sql_through_text_in_order(monkeypatch):
    wrapped_statements = []

    def fake_text(sql):
        wrapped_statement = ("text", sql)
        wrapped_statements.append(sql)
        return wrapped_statement

    engine = FakeEngine()
    monkeypatch.setattr(schema_migrations, "text", fake_text)

    await schema_migrations.run_startup_schema_migrations(engine)

    assert wrapped_statements == FOLLOWUP_SCHEMA_SQL
    assert engine.connection.executed == [("text", sql) for sql in FOLLOWUP_SCHEMA_SQL]


@pytest.mark.asyncio
async def test_create_followup_rejects_non_owner():
    user = make_route_user(user_id="u_other")
    root = make_route_question(asker_id="u_owner")
    db = FollowupRouteDB(user=user, questions_by_id={root.id: root})

    with pytest.raises(HTTPException) as err:
        await questions.create_followup(
            root.id,
            questions.CreateFollowUpReq(quoted_answer_id="ans_quote", agent_ids=["a_ok"], text="More?"),
            user_payload={"sub": user.id},
            db=db,
        )

    assert err.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("quoted_answer", [None, make_route_answer(status="draft")])
async def test_create_followup_rejects_missing_or_unapproved_quote(quoted_answer):
    user = make_route_user()
    root = make_route_question()
    answers = {} if quoted_answer is None else {quoted_answer.id: quoted_answer}
    db = FollowupRouteDB(user=user, questions_by_id={root.id: root}, answers_by_id=answers)

    with pytest.raises(HTTPException) as err:
        await questions.create_followup(
            root.id,
            questions.CreateFollowUpReq(quoted_answer_id="ans_quote", agent_ids=["a_ok"], text="More?"),
            user_payload={"sub": user.id},
            db=db,
        )

    assert err.value.status_code == 400


@pytest.mark.asyncio
async def test_create_followup_rejects_target_without_approved_root_answer():
    user = make_route_user()
    root = make_route_question()
    quoted = make_route_answer(agent_id="a_ok")
    db = FollowupRouteDB(
        user=user,
        questions_by_id={root.id: root},
        answers_by_id={quoted.id: quoted},
    )

    with pytest.raises(HTTPException) as err:
        await questions.create_followup(
            root.id,
            questions.CreateFollowUpReq(quoted_answer_id=quoted.id, agent_ids=["a_missing"], text="More?"),
            user_payload={"sub": user.id},
            db=db,
        )

    assert err.value.status_code == 400
    assert "没有已发布回答" in err.value.detail


@pytest.mark.asyncio
async def test_create_followup_partial_push_reserves_max_refunds_undelivered_and_persists_context(monkeypatch):
    user = make_route_user()
    root = make_route_question()
    quoted = make_route_answer(agent_id="a_ok")
    other_root_answer = make_route_answer(id="ans_other", agent_id="a_fail")
    db = FollowupRouteDB(
        user=user,
        questions_by_id={root.id: root},
        answers_by_id={quoted.id: quoted, other_root_answer.id: other_root_answer},
        agents_by_id={"a_ok": make_route_agent("a_ok"), "a_fail": make_route_agent("a_fail")},
    )
    incremented = []
    pushed_payloads = []

    async def fake_push_question(agent_id, payload):
        pushed_payloads.append((agent_id, payload))
        return agent_id == "a_ok"

    async def fake_increment_usage(db_arg, agent_id):
        incremented.append(agent_id)
        return len(incremented)

    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)
    monkeypatch.setattr(questions, "increment_usage", fake_increment_usage)

    res = await questions.create_followup(
        root.id,
        questions.CreateFollowUpReq(quoted_answer_id=quoted.id, agent_ids=["a_ok", "a_fail"], text="More?"),
        user_payload={"sub": user.id},
        db=db,
    )

    followup = next(q for q in db.added if q.__class__.__name__ == "Question")
    created_answers = [a for a in db.added if a.__class__.__name__ == "Answer"]
    assert followup.root_question_id == root.id
    assert followup.parent_question_id == root.id
    assert followup.quoted_answer_id == quoted.id
    assert followup.turn_type == "followup"
    assert followup.fuel_cost == questions.AVG_TOKENS_PER_ANSWER
    assert user.fuel_balance == 100_000 - questions.AVG_TOKENS_PER_ANSWER

    assert [(a.agent_id, a.conversation_id, a.parent_answer_id, a.turn_type) for a in created_answers] == [
        ("a_ok", "conv_q_root_a_ok", quoted.id, "followup"),
        ("a_fail", "conv_q_root_a_fail", quoted.id, "followup"),
    ]
    assert res["root_question_id"] == root.id
    assert res["quoted_answer_id"] == quoted.id
    assert res["pushed_count"] == 1
    assert res["fuel_cost"] == questions.AVG_TOKENS_PER_ANSWER
    assert res["requests"] == [
        {
            "agent_id": "a_ok",
            "request_id": "req_q_follow_1_a_ok",
            "conversation_id": "conv_q_root_a_ok",
            "status": "pushed",
        },
        {
            "agent_id": "a_fail",
            "request_id": "req_q_follow_1_a_fail",
            "conversation_id": "conv_q_root_a_fail",
            "status": "assigned",
        },
    ]
    assert incremented == ["a_ok"]
    assert db.fuel_deductions == [
        {"user_id": user.id, "fuel_cost": 2 * questions.AVG_TOKENS_PER_ANSWER, "rowcount": 1}
    ]
    assert db.fuel_refunds == [
        {"user_id": user.id, "fuel_amount": questions.AVG_TOKENS_PER_ANSWER}
    ]
    assert db.answer_status_updates == [
        {"answer_id": "ans_follow_1", "expected_status": "assigned", "new_status": "pushed", "rowcount": 1}
    ]
    assert [agent_id for agent_id, _payload in pushed_payloads] == ["a_ok", "a_fail"]


@pytest.mark.asyncio
async def test_create_followup_conditional_pushed_status_does_not_regress_processing(monkeypatch):
    user = make_route_user()
    root = make_route_question(matched_agent_ids=["a_ok"])
    quoted = make_route_answer(agent_id="a_ok")
    db = FollowupRouteDB(
        user=user,
        questions_by_id={root.id: root},
        answers_by_id={quoted.id: quoted},
        agents_by_id={"a_ok": make_route_agent("a_ok")},
    )

    async def fake_push_question(agent_id, payload):
        db.answers_by_id["ans_follow_1"].status = "processing"
        return True

    async def fake_increment_usage(db_arg, agent_id):
        return 1

    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)
    monkeypatch.setattr(questions, "increment_usage", fake_increment_usage)

    res = await questions.create_followup(
        root.id,
        questions.CreateFollowUpReq(quoted_answer_id=quoted.id, agent_ids=["a_ok"], text="More?"),
        user_payload={"sub": user.id},
        db=db,
    )

    followup_answer = db.answers_by_id["ans_follow_1"]
    assert res["requests"][0]["status"] == "pushed"
    assert followup_answer.status == "processing"
    assert db.answer_status_updates == [
        {"answer_id": "ans_follow_1", "expected_status": "assigned", "new_status": "pushed", "rowcount": 0}
    ]


@pytest.mark.asyncio
async def test_create_question_conditional_pushed_status_does_not_regress_processing(monkeypatch):
    user = make_route_user()
    agent = make_route_agent("a_ok")
    db = FollowupRouteDB(user=user, agents_by_id={agent.id: agent})

    async def fake_match_agents(db_arg, tags, max_responders, title="", body=""):
        return [(agent, 1.0, "exact", "ok")]

    async def fake_push_question(agent_id, payload):
        db.answers_by_id["ans_follow_1"].status = "processing"
        return True

    async def fake_increment_usage(db_arg, agent_id):
        return 1

    monkeypatch.setattr(questions, "match_agents", fake_match_agents)
    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)
    monkeypatch.setattr(questions, "increment_usage", fake_increment_usage)

    res = await questions.create_question(
        questions.CreateQuestionReq(title="Root", tags=["rust"], max_responders=1),
        user_payload={"sub": user.id},
        db=db,
    )

    root_answer = db.answers_by_id["ans_follow_1"]
    assert res["pushed_count"] == 1
    assert root_answer.status == "processing"
    assert db.answer_status_updates == [
        {"answer_id": "ans_follow_1", "expected_status": "assigned", "new_status": "pushed", "rowcount": 0}
    ]
