import pytest

from services import schema_migrations
from services.schema_migrations import FOLLOWUP_SCHEMA_SQL


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
