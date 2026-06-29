from datetime import datetime
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
        for obj in self.added:
            if obj.__class__.__name__ == "Question" and getattr(obj, "id", None) is None:
                obj.id = "q_test"

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = "q_test"
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.utcnow()


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

    async def fake_match_agents(db_arg, tags, max_responders, title="", body=""):
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

    async def fake_match_agents(db_arg, tags, max_responders, title="", body=""):
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
