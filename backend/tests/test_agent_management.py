from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import agents


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class ListResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class RefreshableDB:
    def __init__(self, agent):
        self.agent = agent
        self.commits = 0
        self.refreshes = 0

    async def execute(self, stmt):
        return ScalarResult(self.agent)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshes += 1


class RelationshipDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.deleted = []
        self.commits = 0

    async def execute(self, stmt):
        if self.results:
            return self.results.pop(0)
        return ScalarResult(None)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = "generated"


class FakeDB:
    def __init__(self, agent, answer_count=0, connectors=None):
        self.results = [
            ScalarResult(agent),
            ScalarResult(answer_count),
            ListResult(connectors or []),
        ]
        self.deleted = []
        self.commits = 0

    async def execute(self, stmt):
        return self.results.pop(0)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_delete_agent_removes_owned_agent_without_answers():
    agent = SimpleNamespace(id="a_delete", user_id="u_owner")
    connector = SimpleNamespace(id="conn_delete")
    db = FakeDB(agent, answer_count=0, connectors=[connector])

    res = await agents.delete_agent(
        "a_delete",
        user={"sub": "u_owner"},
        db=db,
    )

    assert res.status_code == 204
    assert db.deleted == [connector, agent]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_delete_agent_rejects_agents_with_answer_history():
    agent = SimpleNamespace(id="a_history", user_id="u_owner")
    db = FakeDB(agent, answer_count=2)

    with pytest.raises(HTTPException) as exc_info:
        await agents.delete_agent(
            "a_history",
            user={"sub": "u_owner"},
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert "已有回答" in exc_info.value.detail
    assert db.deleted == []
    assert db.commits == 0


def test_agent_to_dict_includes_readiness():
    agent = SimpleNamespace(
        id="a_ready",
        name="Ready Agent",
        agent_type="hermes",
        tags=[],
        description="",
        repute_score=0,
        fuel_earned=0,
        total_answers=0,
        approval_rate=0,
        status="online",
        is_public=True,
        visibility="followers",
        service_mode="direct_only",
        service_rules={"price_multiplier": 1.5, "max_followup_depth": 3},
        created_at=None,
        review_rules={
            "agentmint_readiness": {"state": "ready"},
            "learned_profile": {"domain_tags": ["魔兽世界"], "sample_count": 2},
        },
    )

    out = agents._agent_to_dict(agent, "owner")

    assert out["readiness"]["state"] == "ready"
    assert out["learned_profile"]["domain_tags"] == ["魔兽世界"]
    assert out["learned_profile"]["sample_count"] == 2
    assert out["visibility"] == "followers"
    assert out["service_mode"] == "direct_only"
    assert out["service_rules"]["price_multiplier"] == 1.5
    assert out["service_rules"]["max_followup_depth"] == 3


@pytest.mark.asyncio
async def test_create_agent_maps_legacy_non_public_to_archived():
    db = RelationshipDB()

    out = await agents.create_agent(
        agents.CreateAgentReq(name="Hidden", agent_type="hermes", is_public=False),
        user={"sub": "u_owner", "nickname": "owner"},
        db=db,
    )

    assert db.added[0].visibility == "archived"
    assert out["visibility"] == "archived"


@pytest.mark.asyncio
async def test_create_agent_visibility_controls_legacy_is_public():
    db = RelationshipDB()

    out = await agents.create_agent(
        agents.CreateAgentReq(name="Follower Agent", agent_type="hermes", visibility="followers"),
        user={"sub": "u_owner", "nickname": "owner"},
        db=db,
    )

    assert db.added[0].is_public is False
    assert out["is_public"] is False
    assert out["visibility"] == "followers"


@pytest.mark.asyncio
async def test_follow_user_creates_one_way_follow():
    target = SimpleNamespace(id="u_target")
    db = RelationshipDB(results=[ScalarResult(target), ScalarResult(None)])

    out = await agents.follow_user("u_target", user={"sub": "u_me"}, db=db)

    assert out == {"following": True, "user_id": "u_target"}
    assert db.added[0].follower_id == "u_me"
    assert db.added[0].followed_id == "u_target"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_subscribe_agent_creates_subscription():
    agent = SimpleNamespace(id="a_target", user_id="u_owner", visibility="public")
    db = RelationshipDB(results=[ScalarResult(agent), ListResult([]), ListResult([]), ScalarResult(None)])

    out = await agents.subscribe_agent("a_target", user={"sub": "u_me"}, db=db)

    assert out == {"subscribed": True, "agent_id": "a_target"}
    assert db.added[0].subscriber_id == "u_me"
    assert db.added[0].agent_id == "a_target"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_subscribe_agent_rejects_invisible_agent():
    agent = SimpleNamespace(id="a_hidden", user_id="u_owner", visibility="followers")
    db = RelationshipDB(results=[ScalarResult(agent), ListResult([]), ListResult([])])

    with pytest.raises(HTTPException) as exc_info:
        await agents.subscribe_agent("a_hidden", user={"sub": "u_me"}, db=db)

    assert exc_info.value.status_code == 404
    assert db.added == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_create_friend_request_creates_pending_request():
    target = SimpleNamespace(id="u_target")
    db = RelationshipDB(results=[ScalarResult(target), ScalarResult(None), ScalarResult(None)])

    out = await agents.create_friend_request("u_target", user={"sub": "u_me"}, db=db)

    assert out["status"] == "pending"
    assert db.added[0].requester_id == "u_me"
    assert db.added[0].recipient_id == "u_target"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_readiness_check_marks_offline_agent_error():
    agent = SimpleNamespace(id="a_offline", user_id="u_owner", status="offline", review_rules={})
    db = RefreshableDB(agent)

    out = await agents.readiness_check(
        "a_offline",
        user={"sub": "u_owner"},
        db=db,
    )

    assert out["delivered"] is False
    assert out["readiness"]["state"] == "error"
    assert "离线" in out["readiness"]["error"]
    assert db.commits == 1
