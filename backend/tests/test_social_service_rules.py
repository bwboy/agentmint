from types import SimpleNamespace

from services.agent_service_rules import (
    DEFAULT_SERVICE_RULES,
    normalize_service_rules,
    normalize_service_mode,
    normalize_visibility,
    can_view_agent,
    can_auto_match_agent,
)
from services.billing import calculate_answer_fuel
import pytest

from services.schema_migrations import FOLLOWUP_SCHEMA_SQL, run_startup_schema_migrations


class FakeMigrationConnection:
    def __init__(self):
        self.executed_sql = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def exec_driver_sql(self, sql):
        self.executed_sql.append(sql)


class FakeMigrationEngine:
    def __init__(self):
        self.connection = FakeMigrationConnection()

    def begin(self):
        return self.connection


def test_social_schema_migration_adds_relationship_tables_and_agent_service_columns():
    sql = "\n".join(FOLLOWUP_SCHEMA_SQL)

    assert "ALTER TABLE agents ADD COLUMN IF NOT EXISTS visibility VARCHAR" in sql
    assert "ALTER TABLE agents ADD COLUMN IF NOT EXISTS service_mode VARCHAR" in sql
    assert "ALTER TABLE agents ADD COLUMN IF NOT EXISTS service_rules JSONB" in sql
    assert "CREATE TABLE IF NOT EXISTS user_follows" in sql
    assert "CREATE TABLE IF NOT EXISTS agent_subscriptions" in sql
    assert "CREATE TABLE IF NOT EXISTS friendships" in sql
    assert "CREATE TABLE IF NOT EXISTS friend_requests" in sql


@pytest.mark.asyncio
async def test_schema_migrations_execute_raw_sql_so_json_literals_are_not_bound_params():
    engine = FakeMigrationEngine()

    await run_startup_schema_migrations(engine)

    assert any('{"price_multiplier":1.0' in sql for sql in engine.connection.executed_sql)


def test_normalize_agent_service_rules_defaults_and_bounds():
    out = normalize_service_rules({
        "price_multiplier": "2.5",
        "max_followup_depth": 12,
        "min_fuel_per_answer": -5,
        "max_fuel_per_answer": 25_000_000,
    })

    assert out["price_multiplier"] == 2.5
    assert out["max_followup_depth"] == 10
    assert out["min_fuel_per_answer"] == DEFAULT_SERVICE_RULES["min_fuel_per_answer"]
    assert out["max_fuel_per_answer"] == DEFAULT_SERVICE_RULES["max_fuel_per_answer"]


def test_visibility_and_service_mode_normalization():
    assert normalize_visibility("followers") == "followers"
    assert normalize_visibility("private") == "public"
    assert normalize_service_mode("direct_only") == "direct_only"
    assert normalize_service_mode("disabled") == "auto_match"


def test_agent_visibility_access_for_public_follower_friend_and_archived():
    public_agent = SimpleNamespace(user_id="u_owner", visibility="public", service_mode="auto_match")
    follower_agent = SimpleNamespace(user_id="u_owner", visibility="followers", service_mode="auto_match")
    friend_agent = SimpleNamespace(user_id="u_owner", visibility="friends", service_mode="auto_match")
    archived_agent = SimpleNamespace(user_id="u_owner", visibility="archived", service_mode="stopped")

    assert can_view_agent(public_agent, viewer_id="u_any", followed_owner_ids=set(), friend_owner_ids=set())
    assert not can_view_agent(follower_agent, viewer_id="u_any", followed_owner_ids=set(), friend_owner_ids=set())
    assert can_view_agent(follower_agent, viewer_id="u_any", followed_owner_ids={"u_owner"}, friend_owner_ids=set())
    assert not can_view_agent(friend_agent, viewer_id="u_any", followed_owner_ids={"u_owner"}, friend_owner_ids=set())
    assert can_view_agent(friend_agent, viewer_id="u_any", followed_owner_ids=set(), friend_owner_ids={"u_owner"})
    assert not can_view_agent(archived_agent, viewer_id="u_owner", followed_owner_ids=set(), friend_owner_ids=set())


def test_direct_only_agents_are_viewable_but_not_auto_matchable():
    agent = SimpleNamespace(user_id="u_owner", visibility="public", service_mode="direct_only")

    assert can_view_agent(agent, viewer_id="u_any", followed_owner_ids=set(), friend_owner_ids=set())
    assert not can_auto_match_agent(agent, viewer_id="u_any", followed_owner_ids=set(), friend_owner_ids=set())


def test_calculate_answer_fuel_uses_prompt_and_completion_tokens_with_multiplier_and_caps():
    agent = SimpleNamespace(service_rules={
        "price_multiplier": 2.0,
        "min_fuel_per_answer": 100,
        "max_fuel_per_answer": 2000,
    })

    assert calculate_answer_fuel({"prompt_tokens": 100, "completion_tokens": 200}, agent) == 1000
    assert calculate_answer_fuel({"prompt_tokens": 1, "completion_tokens": 1}, agent) == 100

    agent.service_rules["max_fuel_per_answer"] = 1000
    assert calculate_answer_fuel({"prompt_tokens": 1000, "completion_tokens": 1000}, agent) == 1000
