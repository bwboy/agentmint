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

    def one_or_none(self):
        return self.value


class ListResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class RowResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


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
        self.flushes = 0

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

    async def flush(self):
        self.flushes += 1
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = "generated"

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = "generated"


class AgentDetailDB(RelationshipDB):
    def __init__(self, row, results=None):
        super().__init__(results=results)
        self.row = row
        self.first = True

    async def execute(self, stmt):
        if self.first:
            self.first = False
            return ScalarResult(self.row)
        return await super().execute(stmt)


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


class SubscribeDB(RelationshipDB):
    def __init__(self, agent, owner, existing_subscription=None):
        super().__init__()
        self.results = [
            ScalarResult(agent),
            RowResult([]),
            RowResult([]),
            ScalarResult(existing_subscription),
            ScalarResult(owner),
        ]


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
            "learned_profile": {
                "domain_tags": ["魔兽世界"],
                "sample_count": 2,
                "owner_supplement_count": 3,
                "owner_supplement_types": {"correction": 2, "risk_note": 1},
            },
        },
    )

    out = agents._agent_to_dict(agent, "owner")

    assert out["readiness"]["state"] == "ready"
    assert out["learned_profile"]["domain_tags"] == ["魔兽世界"]
    assert out["learned_profile"]["sample_count"] == 2
    assert out["owner_supplement_summary"]["total"] == 3
    assert out["owner_supplement_summary"]["types"]["correction"] == 2
    assert out["visibility"] == "followers"
    assert out["service_mode"] == "direct_only"
    assert out["service_rules"]["price_multiplier"] == 1.5
    assert out["service_rules"]["max_followup_depth"] == 3


def test_agent_to_dict_includes_learned_profile_review_state():
    agent = SimpleNamespace(
        id="a_review",
        name="Review Agent",
        agent_type="hermes",
        tags=[],
        description="",
        repute_score=0,
        fuel_earned=0,
        total_answers=0,
        approval_rate=0,
        status="online",
        is_public=True,
        visibility="public",
        service_mode="auto_match",
        service_rules={},
        created_at=None,
        review_rules={
            "learned_profile": {
                "domain_tags": ["魔兽世界", "硬核模式"],
                "capability_tags": ["风险审查"],
            },
            "learned_profile_review": {
                "accepted": {"domain_tags": ["魔兽世界"]},
                "rejected": {"domain_tags": ["硬核模式"]},
            },
        },
    )

    out = agents._agent_to_dict(agent, "owner")

    assert out["learned_profile_review"]["accepted"]["domain_tags"] == ["魔兽世界"]
    assert out["learned_profile_review"]["rejected"]["domain_tags"] == ["硬核模式"]
    assert out["learned_profile_review"]["pending"]["capability_tags"] == ["风险审查"]
    assert out["learned_profile_review"]["pending"]["domain_tags"] == []


@pytest.mark.asyncio
async def test_owner_can_accept_and_reject_learned_profile_tags():
    agent = SimpleNamespace(
        id="a_review",
        user_id="u_owner",
        name="Review Agent",
        agent_type="hermes",
        tags=[],
        description="",
        repute_score=0,
        fuel_earned=0,
        total_answers=0,
        approval_rate=0,
        status="online",
        is_public=True,
        visibility="public",
        service_mode="auto_match",
        service_rules={},
        daily_quota_config={},
        last_seen_at=None,
        created_at=None,
        review_rules={
            "capability_profile": {"domain_tags": [], "capability_tags": [], "tool_tags": [], "style_tags": [], "avoid_tags": []},
            "learned_profile": {"domain_tags": ["魔兽世界"], "capability_tags": ["风险审查"]},
        },
    )
    db = RefreshableDB(agent)

    out = await agents.review_learned_profile_tags(
        "a_review",
        agents.LearnedProfileReviewReq(
            accept={"domain_tags": ["魔兽世界"]},
            reject={"capability_tags": ["风险审查"]},
        ),
        user={"sub": "u_owner"},
        db=db,
    )

    assert out["capability_profile"]["domain_tags"] == ["魔兽世界"]
    assert out["learned_profile_review"]["accepted"]["domain_tags"] == ["魔兽世界"]
    assert out["learned_profile_review"]["rejected"]["capability_tags"] == ["风险审查"]
    assert db.commits == 1


def test_agent_to_dict_can_include_owner_id_and_relationships():
    agent = SimpleNamespace(
        id="a_public",
        user_id="u_owner",
        name="Public Agent",
        agent_type="hermes",
        tags=[],
        description="",
        repute_score=0,
        fuel_earned=0,
        total_answers=0,
        approval_rate=0,
        status="online",
        is_public=True,
        visibility="public",
        service_mode="auto_match",
        service_rules={},
        created_at=None,
        review_rules={},
    )

    out = agents._agent_to_dict(
        agent,
        "owner",
        include_owner_id=True,
        relationship={
            "is_owner": False,
            "following_owner": True,
            "subscribed": True,
            "friendship_status": "pending_outgoing",
            "friend_request_id": "freq_1",
        },
    )

    assert out["owner"]["id"] == "u_owner"
    assert out["relationship"]["following_owner"] is True
    assert out["relationship"]["subscribed"] is True
    assert out["relationship"]["friendship_status"] == "pending_outgoing"


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
async def test_subscribe_agent_notifies_agent_owner_when_enabled():
    agent = SimpleNamespace(id="a_public", user_id="u_owner", name="Owner Agent", visibility="public", service_mode="auto_match")
    owner = SimpleNamespace(id="u_owner", notification_prefs={"agent_subscribed": True})
    db = SubscribeDB(agent, owner)

    out = await agents.subscribe_agent(
        "a_public",
        user={"sub": "u_sub", "nickname": "Subscriber"},
        db=db,
    )

    notifications = [item for item in db.added if item.__class__.__name__ == "Notification"]
    assert out == {"subscribed": True, "agent_id": "a_public"}
    assert len(notifications) == 1
    assert notifications[0].user_id == "u_owner"
    assert notifications[0].type == "agent_subscribed"
    assert notifications[0].ref_id == "a_public"
    assert "Subscriber" in notifications[0].body
    assert db.commits == 1


@pytest.mark.asyncio
async def test_subscribe_agent_respects_owner_notification_pref():
    agent = SimpleNamespace(id="a_public", user_id="u_owner", name="Owner Agent", visibility="public", service_mode="auto_match")
    owner = SimpleNamespace(id="u_owner", notification_prefs={"agent_subscribed": False})
    db = SubscribeDB(agent, owner)

    await agents.subscribe_agent(
        "a_public",
        user={"sub": "u_sub", "nickname": "Subscriber"},
        db=db,
    )

    notifications = [item for item in db.added if item.__class__.__name__ == "Notification"]
    assert notifications == []
    assert db.commits == 1


@pytest.mark.asyncio
async def test_create_agent_uses_owner_default_service_settings_when_not_provided():
    db = RelationshipDB()

    out = await agents.create_agent(
        agents.CreateAgentReq(name="Defaulted Agent", agent_type="hermes"),
        user={
            "sub": "u_owner",
            "nickname": "owner",
            "default_agent_visibility": "followers",
            "default_agent_service_mode": "direct_only",
            "default_agent_service_rules": {"price_multiplier": 2.0, "max_followup_depth": 4},
        },
        db=db,
    )

    assert db.added[0].visibility == "followers"
    assert db.added[0].service_mode == "direct_only"
    assert db.added[0].service_rules["price_multiplier"] == 2.0
    assert out["visibility"] == "followers"


@pytest.mark.asyncio
async def test_get_agent_returns_relationship_context_for_logged_in_viewer():
    agent = SimpleNamespace(
        id="a_public",
        user_id="u_owner",
        name="Public Agent",
        agent_type="hermes",
        tags=[],
        description="",
        repute_score=0,
        fuel_earned=0,
        total_answers=0,
        approval_rate=0,
        status="online",
        is_public=True,
        visibility="public",
        service_mode="auto_match",
        service_rules={},
        created_at=None,
        daily_quota_config={},
        last_seen_at=None,
        review_rules={},
    )
    db = AgentDetailDB(
        (agent, "owner"),
        results=[
            ListResult([]),
            ListResult([]),
            ScalarResult(SimpleNamespace(id="follow_1")),
            ScalarResult(SimpleNamespace(id="sub_1")),
            ScalarResult(None),
            ScalarResult(SimpleNamespace(id="freq_1", requester_id="u_me", recipient_id="u_owner", status="pending")),
        ],
    )

    out = await agents.get_agent("a_public", viewer={"sub": "u_me"}, db=db)

    assert out["owner"]["id"] == "u_owner"
    assert out["relationship"]["following_owner"] is True
    assert out["relationship"]["subscribed"] is True
    assert out["relationship"]["friendship_status"] == "pending_outgoing"
    assert out["relationship"]["friend_request_id"] == "freq_1"


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
async def test_my_social_lists_relationship_collections():
    incoming = SimpleNamespace(id="freq_in", requester_id="u_other", recipient_id="u_me", status="pending", created_at=None)
    outgoing = SimpleNamespace(id="freq_out", requester_id="u_me", recipient_id="u_other", status="pending", created_at=None)
    friendship = SimpleNamespace(id="fr_1", user_low_id="u_friend", user_high_id="u_me", created_at=None)
    follow = SimpleNamespace(id="uf_1", followed_id="u_followed", created_at=None)
    subscription = SimpleNamespace(id="asub_1", agent_id="a_sub", created_at=None)
    followed_user = SimpleNamespace(id="u_followed", nickname="Followed", repute_score=3.5)
    friend_user = SimpleNamespace(id="u_friend", nickname="Friend", repute_score=4.0)
    requester = SimpleNamespace(id="u_other", nickname="Requester", repute_score=2.0)
    subscribed_agent = SimpleNamespace(
        id="a_sub",
        user_id="u_owner",
        name="Sub Agent",
        agent_type="hermes",
        tags=["AI"],
        description="",
        repute_score=4.2,
        fuel_earned=100,
        total_answers=5,
        approval_rate=0.8,
        status="online",
        is_public=True,
        visibility="public",
        service_mode="auto_match",
        service_rules={},
        created_at=None,
        review_rules={},
    )

    db = RelationshipDB(results=[
        RowResult([(incoming, requester.nickname, requester.repute_score)]),
        RowResult([(outgoing, requester.nickname, requester.repute_score)]),
        RowResult([(friendship, friend_user.id, friend_user.nickname, friend_user.repute_score)]),
        RowResult([(follow, followed_user.nickname, followed_user.repute_score)]),
        RowResult([(subscription, subscribed_agent, "owner")]),
    ])

    out = await agents.my_social(user={"sub": "u_me"}, db=db)

    assert out["incoming_friend_requests"][0]["id"] == "freq_in"
    assert out["outgoing_friend_requests"][0]["id"] == "freq_out"
    assert out["friends"][0]["user"]["id"] == "u_friend"
    assert out["following_users"][0]["user"]["nickname"] == "Followed"
    assert out["agent_subscriptions"][0]["agent"]["id"] == "a_sub"


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
