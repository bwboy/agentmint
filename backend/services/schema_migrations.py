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
    "ALTER TABLE questions ALTER COLUMN turn_type SET NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_questions_root_question_id ON questions(root_question_id)",
    "CREATE INDEX IF NOT EXISTS idx_questions_quoted_answer_id ON questions(quoted_answer_id)",
    "ALTER TABLE answers ADD COLUMN IF NOT EXISTS conversation_id VARCHAR",
    "ALTER TABLE answers ADD COLUMN IF NOT EXISTS parent_answer_id VARCHAR",
    "ALTER TABLE answers ADD COLUMN IF NOT EXISTS turn_type VARCHAR",
    "UPDATE answers SET turn_type='root' WHERE turn_type IS NULL",
    "ALTER TABLE answers ALTER COLUMN turn_type SET DEFAULT 'root'",
    "ALTER TABLE answers ALTER COLUMN turn_type SET NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_answers_conversation_id ON answers(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_answers_parent_answer_id ON answers(parent_answer_id)",
]


async def run_startup_schema_migrations(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in FOLLOWUP_SCHEMA_SQL:
            await conn.execute(text(sql))
