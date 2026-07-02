from types import SimpleNamespace

import pytest

from routers import auth


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class ListResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class ProfileDB:
    def __init__(self, user, agents=None):
        self.user = user
        self.agents = agents or []
        self.calls = 0
        self.commits = 0
        self.refreshes = 0

    async def execute(self, stmt):
        self.calls += 1
        if self.calls == 1:
            return ScalarResult(self.user)
        return ListResult(self.agents)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshes += 1


def make_user():
    return SimpleNamespace(
        id="u_profile",
        phone="13800138000",
        nickname="Gavin",
        trust_level=2,
        fuel_balance=50000,
        repute_score=4.2,
        avatar_url="",
        headline="AI Agent builder",
        bio="Building AgentMint",
        profile_tags=["AI", "产品"],
        experience_tags=["实战"],
        links={"github": "https://github.com/bwboy"},
        profile_visibility="public",
        default_agent_visibility="followers",
        default_agent_service_mode="direct_only",
        default_agent_service_rules={"price_multiplier": 1.5, "max_followup_depth": 3},
        notification_prefs={"friend_request": True},
    )


@pytest.mark.asyncio
async def test_me_includes_profile_settings_and_defaults():
    user = make_user()
    db = ProfileDB(user, agents=[SimpleNamespace(id="a1")])

    out = await auth.me(user_payload={"sub": user.id}, db=db)

    assert out["nickname"] == "Gavin"
    assert out["headline"] == "AI Agent builder"
    assert out["profile_tags"] == ["AI", "产品"]
    assert out["default_agent_visibility"] == "followers"
    assert out["default_agent_service_rules"]["price_multiplier"] == 1.5
    assert out["agent_count"] == 1


@pytest.mark.asyncio
async def test_update_my_profile_normalizes_profile_and_default_agent_settings():
    user = make_user()
    db = ProfileDB(user)

    out = await auth.update_my_profile(
        auth.UpdateProfileReq(
            nickname="New Gavin",
            headline="AI 设计",
            bio="新的简介",
            profile_tags=["AI", "AI", "产品"],
            experience_tags=["实战", "研究"],
            links={"github": "https://github.com/bwboy", "bad": "javascript:alert(1)"},
            profile_visibility="friends",
            default_agent_visibility="friends",
            default_agent_service_mode="auto_match",
            default_agent_service_rules={"price_multiplier": 2.0, "max_followup_depth": 4},
            notification_prefs={"friend_request": False, "agent_subscribed": True},
        ),
        user_payload={"sub": user.id},
        db=db,
    )

    assert user.nickname == "New Gavin"
    assert user.profile_tags == ["AI", "产品"]
    assert user.links == {"github": "https://github.com/bwboy"}
    assert user.profile_visibility == "friends"
    assert user.default_agent_visibility == "friends"
    assert user.default_agent_service_mode == "auto_match"
    assert user.default_agent_service_rules["max_followup_depth"] == 4
    assert out["notification_prefs"]["friend_request"] is False
    assert db.commits == 1
