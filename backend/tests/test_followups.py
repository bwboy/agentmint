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
