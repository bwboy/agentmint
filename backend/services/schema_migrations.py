"""Small idempotent schema migrations for container deployments without Alembic."""
from sqlalchemy.ext.asyncio import AsyncEngine


FOLLOWUP_SCHEMA_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS headline VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_tags VARCHAR[]",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS experience_tags VARCHAR[]",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS links JSONB",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_visibility VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_agent_visibility VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_agent_service_mode VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_agent_service_rules JSONB",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_prefs JSONB",
    "UPDATE users SET avatar_url='' WHERE avatar_url IS NULL",
    "UPDATE users SET headline='' WHERE headline IS NULL",
    "UPDATE users SET bio='' WHERE bio IS NULL",
    "UPDATE users SET profile_tags='{}' WHERE profile_tags IS NULL",
    "UPDATE users SET experience_tags='{}' WHERE experience_tags IS NULL",
    "UPDATE users SET links='{}'::jsonb WHERE links IS NULL",
    "UPDATE users SET profile_visibility='public' WHERE profile_visibility IS NULL",
    "UPDATE users SET default_agent_visibility='public' WHERE default_agent_visibility IS NULL",
    "UPDATE users SET default_agent_service_mode='auto_match' WHERE default_agent_service_mode IS NULL",
    """UPDATE users SET default_agent_service_rules='{"price_multiplier":1.0,"max_followup_depth":2,"min_fuel_per_answer":0,"max_fuel_per_answer":100000}'::jsonb WHERE default_agent_service_rules IS NULL""",
    """UPDATE users SET notification_prefs='{"friend_request":true,"agent_subscribed":true,"direct_question":true,"answer_feedback":true}'::jsonb WHERE notification_prefs IS NULL""",
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
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS visibility VARCHAR",
    "UPDATE agents SET visibility=CASE WHEN is_public THEN 'public' ELSE 'archived' END WHERE visibility IS NULL",
    "ALTER TABLE agents ALTER COLUMN visibility SET DEFAULT 'public'",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS service_mode VARCHAR",
    "UPDATE agents SET service_mode='auto_match' WHERE service_mode IS NULL",
    "ALTER TABLE agents ALTER COLUMN service_mode SET DEFAULT 'auto_match'",
    "ALTER TABLE agents ADD COLUMN IF NOT EXISTS service_rules JSONB",
    """UPDATE agents SET service_rules='{"price_multiplier":1.0,"max_followup_depth":2,"min_fuel_per_answer":0,"max_fuel_per_answer":100000}'::jsonb WHERE service_rules IS NULL""",
    "CREATE INDEX IF NOT EXISTS idx_agents_visibility ON agents(visibility)",
    "CREATE INDEX IF NOT EXISTS idx_agents_service_mode ON agents(service_mode)",
    """
    CREATE TABLE IF NOT EXISTS user_follows (
        id VARCHAR PRIMARY KEY,
        follower_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        followed_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (follower_id, followed_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_follows_follower_id ON user_follows(follower_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_follows_followed_id ON user_follows(followed_id)",
    """
    CREATE TABLE IF NOT EXISTS agent_subscriptions (
        id VARCHAR PRIMARY KEY,
        subscriber_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        agent_id VARCHAR NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (subscriber_id, agent_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_agent_subscriptions_subscriber_id ON agent_subscriptions(subscriber_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_subscriptions_agent_id ON agent_subscriptions(agent_id)",
    """
    CREATE TABLE IF NOT EXISTS friendships (
        id VARCHAR PRIMARY KEY,
        user_low_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        user_high_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (user_low_id, user_high_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_friendships_user_low_id ON friendships(user_low_id)",
    "CREATE INDEX IF NOT EXISTS idx_friendships_user_high_id ON friendships(user_high_id)",
    """
    CREATE TABLE IF NOT EXISTS friend_requests (
        id VARCHAR PRIMARY KEY,
        requester_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        recipient_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        status VARCHAR DEFAULT 'pending',
        created_at TIMESTAMPTZ DEFAULT now(),
        responded_at TIMESTAMPTZ,
        UNIQUE (requester_id, recipient_id, status)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_friend_requests_recipient_id ON friend_requests(recipient_id)",
    "CREATE INDEX IF NOT EXISTS idx_friend_requests_requester_id ON friend_requests(requester_id)",
]


async def run_startup_schema_migrations(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in FOLLOWUP_SCHEMA_SQL:
            await conn.exec_driver_sql(sql)
