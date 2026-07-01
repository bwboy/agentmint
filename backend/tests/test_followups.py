from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
