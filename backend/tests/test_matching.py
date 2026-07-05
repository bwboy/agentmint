"""Unit tests for the matching engine — covers the 4 design-doc scenarios."""
import pytest

from services.matching import (
    normalize_tags, exact_match_score, similarity_score, rank,
    build_task_profile, build_match_explanation, build_query_tags, TAG_GROUPS,
    filter_ready_agents, agent_matching_tags, filter_matchable_agents,
    rank_with_relationship_boost, rank_with_quality_adjustment,
)


def test_normalize_tags():
    assert normalize_tags(["Rust", " 系统编程 ", "", "  "]) == {"rust", "系统编程"}


def test_exact_match_scenario_1_perfect():
    """Asker tags {rust, 系统编程} vs Agent {rust, 系统编程, 编译器} → perfect Ochiai."""
    q = {"rust", "系统编程"}
    a = {"rust", "系统编程", "编译器"}
    s = exact_match_score(q, a)
    # |∩|=2, max(2,3)=3 → 0.667
    assert 0.66 <= s <= 0.67


def test_exact_match_scenario_2_partial():
    q = {"rust"}
    a = {"rust", "系统编程", "编译器"}
    s = exact_match_score(q, a)
    # |∩|=1, max(1,3)=3 → 0.333
    assert 0.33 <= s <= 0.34


def test_exact_match_scenario_3_no_overlap():
    q = {"rust"}
    a = {"法律"}
    assert exact_match_score(q, a) == 0.0


def test_similarity_scenario_4_fallback():
    """Asker 'WASM' vs Agent has 'rust' — both fall into 系统底层 group."""
    q = normalize_tags(["WASM"])
    a = normalize_tags(["rust", "性能优化"])
    s = similarity_score(q, a)
    assert s > 0  # both in 系统底层 group


def test_tag_groups_cover_design_doc():
    """The 9 predefined tag groups must each contain at least 1 tag."""
    assert len(TAG_GROUPS) >= 9
    for name, members in TAG_GROUPS.items():
        assert len(members) > 0, f"group {name} is empty"


def test_rank_balances_repute_and_match():
    """rank = 0.6 * (repute/5) + 0.4 * match_score — sanity check the weights."""
    # Perfect repute, no match
    assert rank(5.0, 0.0) == pytest.approx(0.6)
    # No repute, perfect match
    assert rank(0.0, 1.0) == pytest.approx(0.4)
    # Both perfect
    assert rank(5.0, 1.0) == pytest.approx(1.0)


def test_rank_with_relationship_boost_prioritizes_subscribed_agents():
    unsubscribed = rank_with_relationship_boost(4.0, 0.5, subscribed=False)
    subscribed = rank_with_relationship_boost(4.0, 0.5, subscribed=True)

    assert subscribed > unsubscribed
    assert subscribed <= 1.0


def test_rank_with_quality_adjustment_penalizes_risky_agents():
    healthy = type("AgentStub", (), {
        "id": "a_healthy",
        "repute_score": 4.0,
        "review_rules": {},
    })()
    risky = type("AgentStub", (), {
        "id": "a_risky",
        "repute_score": 4.0,
        "review_rules": {
            "learned_profile": {
                "negative_feedback": 3,
                "owner_supplement_types": {"correction": 2},
                "owner_experience_context": {"avoid_next_time": ["不要再给过期版本建议"]},
            }
        },
    })()

    assert rank_with_quality_adjustment(healthy, 0.7) == pytest.approx(0.76)
    assert rank_with_quality_adjustment(risky, 0.7) < rank_with_quality_adjustment(healthy, 0.7)


def test_build_task_profile_infers_domains_and_capabilities():
    profile = build_task_profile(
        title="重新设计 AI Agent 匹配系统",
        body="需要方案设计、系统架构和风险审查，输出 MVP 路线。",
        tags=["AI", "系统设计"],
        max_responders=3,
    )

    assert profile["intent"] == "方案设计"
    assert "AI/ML" in profile["domain_tags"]
    assert "架构" in profile["domain_tags"]
    assert "方案设计" in profile["capability_tags"]
    assert "系统架构" in profile["capability_tags"]
    assert "风险审查" in profile["capability_tags"]
    assert profile["answer_mode"] == "选角透明"
    assert profile["routing_mode"] == "transparent_casting"


def test_build_match_explanation_describes_agent_selection():
    class AgentStub:
        id = "a_test"
        name = "RouterSmith"
        agent_type = "hermes"
        tags = ["AI", "系统设计", "数据库"]
        description = "擅长 Agent routing 和系统架构"
        repute_score = 4.6
        total_answers = 42
        approval_rate = 0.88
        status = "online"

    profile = build_task_profile(
        title="设计 Agent 匹配系统",
        body="需要系统架构和风险审查",
        tags=["AI", "系统设计"],
        max_responders=3,
    )
    explanation = build_match_explanation(
        AgentStub(),
        task_profile=profile,
        match_score=0.67,
        match_type="exact",
        quota_state="ok",
    )

    assert explanation["id"] == "a_test"
    assert explanation["name"] == "RouterSmith"
    assert explanation["match_type"] == "exact"
    assert explanation["match_score"] == 67
    assert explanation["overall_score"] > 0
    assert "ai" in explanation["matched_tags"]
    assert "系统设计" in explanation["matched_tags"]
    assert explanation["quota_state"] == "ok"
    assert explanation["reasons"]


def test_build_match_explanation_displays_subscribed_priority():
    class AgentStub:
        id = "a_sub"
        name = "Subscribed Agent"
        agent_type = "hermes"
        tags = ["AI"]
        description = ""
        repute_score = 4.0
        total_answers = 8
        approval_rate = 0.75
        status = "online"

    profile = build_task_profile(
        title="AI 方案设计",
        body="",
        tags=["AI"],
        max_responders=3,
    )

    explanation = build_match_explanation(
        AgentStub(),
        task_profile=profile,
        match_score=0.5,
        match_type="subscribed_exact",
        quota_state="ok",
    )

    assert explanation["match_type"] == "subscribed_exact"
    assert explanation["score_breakdown"]["subscription_boost"] > 0
    assert any("订阅优先" in reason for reason in explanation["reasons"])


def test_build_match_explanation_uses_structured_capability_profile():
    class AgentStub:
        id = "a_profile"
        name = "Profiled Agent"
        agent_type = "hermes"
        tags = ["魔兽世界"]
        description = ""
        repute_score = 4.8
        total_answers = 12
        approval_rate = 0.9
        status = "online"
        review_rules = {
            "capability_profile": {
                "domain_tags": ["魔兽世界", "MMO"],
                "capability_tags": ["方案设计", "风险审查"],
                "tool_tags": ["知识库"],
                "style_tags": ["实战", "简洁"],
                "avoid_tags": ["插件开发"],
            }
        }

    profile = build_task_profile(
        title="wow硬核模式职业选择",
        body="给我三个选择和风险",
        tags=[],
        max_responders=3,
    )
    explanation = build_match_explanation(
        AgentStub(),
        task_profile=profile,
        match_score=1.0,
        match_type="exact",
        quota_state="ok",
    )

    assert "魔兽世界" in explanation["matched_tags"]
    assert "风险审查" in explanation["capability_hits"]
    assert "知识库" in explanation["tool_hits"]
    assert "实战" in explanation["style_hits"]
    assert "插件开发" in explanation["avoid_tags"]


def test_build_match_explanation_includes_score_breakdown_and_readiness():
    class AgentStub:
        id = "a_score"
        name = "Score Agent"
        agent_type = "hermes"
        tags = ["AI", "系统设计"]
        description = "擅长系统架构"
        repute_score = 4.0
        total_answers = 8
        approval_rate = 0.75
        status = "online"
        review_rules = {"agentmint_readiness": {"state": "ready", "checked_at": "2026-06-30T10:00:00"}}

    profile = build_task_profile(
        title="设计 Agent 匹配系统",
        body="需要系统架构",
        tags=["AI", "系统设计"],
        max_responders=3,
    )

    explanation = build_match_explanation(
        AgentStub(),
        task_profile=profile,
        match_score=0.5,
        match_type="exact",
        quota_state="ok",
    )

    assert explanation["readiness"]["state"] == "ready"
    assert explanation["score_breakdown"] == {
        "formula": "0.6 * (repute / 5.0) + 0.4 * match_score",
        "repute_weight": 0.6,
        "match_weight": 0.4,
        "repute_score": 4.0,
        "match_score": 50,
        "repute_component": 48,
        "match_component": 20,
        "subscription_boost": 0,
        "quality_penalty": 0,
        "overall_score": 68,
    }


def test_build_match_explanation_includes_learned_hits():
    class AgentStub:
        id = "a_learned"
        name = "Learned Agent"
        agent_type = "hermes"
        tags = []
        description = ""
        repute_score = 4.0
        total_answers = 8
        approval_rate = 0.75
        status = "online"
        review_rules = {
            "learned_profile": {
                "domain_tags": ["魔兽世界"],
                "capability_tags": ["风险审查"],
                "positive_tags": ["硬核模式"],
                "sample_count": 4,
            }
        }

    profile = build_task_profile(
        title="wow硬核模式职业选择",
        body="给我三个选择和风险",
        tags=[],
        max_responders=3,
    )

    explanation = build_match_explanation(
        AgentStub(),
        task_profile=profile,
        match_score=0.5,
        match_type="exact",
        quota_state="ok",
    )

    assert "魔兽世界" in explanation["learned_hits"]
    assert "风险审查" in explanation["learned_hits"]


def test_build_match_explanation_includes_owner_supplement_signal():
    class AgentStub:
        id = "a_owner_signal"
        name = "Owner Signal Agent"
        agent_type = "hermes"
        tags = []
        description = ""
        repute_score = 4.0
        total_answers = 8
        approval_rate = 0.75
        status = "online"
        review_rules = {
            "learned_profile": {
                "positive_tags": ["荒野大镖客2"],
                "owner_supplement_count": 3,
                "owner_supplement_types": {"correction": 2, "risk_note": 1},
                "owner_experience_context": {
                    "corrections": ["PC 画质更好，但主机体验更省心"],
                    "version_updates": ["新版本先看官方补丁说明"],
                    "risk_notes": ["注意存档迁移风险"],
                    "high_value_experiences": ["先确认玩家更看重画质还是省心"],
                },
            }
        }

    profile = build_task_profile(
        title="荒野大镖客2 平台选择",
        body="哪个平台更适合",
        tags=[],
        max_responders=3,
    )

    explanation = build_match_explanation(
        AgentStub(),
        task_profile=profile,
        match_score=0.5,
        match_type="exact",
        quota_state="ok",
    )

    assert explanation["owner_supplement_summary"]["total"] == 3
    assert explanation["owner_supplement_summary"]["types"]["correction"] == 2
    assert explanation["owner_experience_context"]["corrections"] == ["PC 画质更好，但主机体验更省心"]
    assert explanation["owner_experience_context"]["high_value_experiences"] == ["先确认玩家更看重画质还是省心"]
    assert any("主人经验" in reason for reason in explanation["reasons"])


def test_filter_matchable_agents_uses_visibility_relationships_and_service_mode():
    public = _agent_for_filter("a_public", "u_public", "public", "auto_match")
    follower = _agent_for_filter("a_follower", "u_followed", "followers", "auto_match")
    friend = _agent_for_filter("a_friend", "u_friend", "friends", "auto_match")
    direct = _agent_for_filter("a_direct", "u_public", "public", "direct_only")
    archived = _agent_for_filter("a_archived", "u_public", "archived", "stopped")

    visible = filter_matchable_agents(
        [public, follower, friend, direct, archived],
        viewer_id="u_me",
        followed_owner_ids={"u_followed"},
        friend_owner_ids={"u_friend"},
    )

    assert [agent.id for agent in visible] == ["a_public", "a_follower", "a_friend"]


def _agent_for_filter(agent_id: str, owner_id: str, visibility: str, service_mode: str):
    return type("AgentFilterStub", (), {
        "id": agent_id,
        "user_id": owner_id,
        "visibility": visibility,
        "service_mode": service_mode,
        "review_rules": {"agentmint_readiness": {"state": "ready"}},
    })()
    assert explanation["learned_profile"]["sample_count"] == 4
    assert "魔兽世界" in agent_matching_tags(AgentStub())


def test_build_query_tags_infers_wow_domain_from_title_when_tags_are_missing_or_wrong():
    assert "魔兽世界" in build_query_tags(
        title="wow硬核模式，最适合选择什么职业",
        body="毒狼，给我三个选择吧",
        tags=[],
    )
    assert "魔兽世界" in build_query_tags(
        title="wow硬核模式，最适合选择什么职业",
        body="",
        tags=["wo w"],
    )


def test_filter_ready_agents_keeps_only_readiness_ready():
    ready = type("AgentStub", (), {
        "id": "a_ready",
        "review_rules": {"agentmint_readiness": {"state": "ready"}},
    })()
    pairing = type("AgentStub", (), {
        "id": "a_pairing",
        "review_rules": {"agentmint_readiness": {"state": "pairing_required"}},
    })()
    missing = type("AgentStub", (), {
        "id": "a_missing",
        "review_rules": {},
    })()

    assert filter_ready_agents([ready, pairing, missing]) == [ready]


def test_filter_ready_agents_keeps_legacy_answering_agents_without_readiness_record():
    legacy = type("AgentStub", (), {
        "id": "a_legacy",
        "review_rules": {},
        "total_answers": 26,
    })()
    explicit_unverified = type("AgentStub", (), {
        "id": "a_new_token",
        "review_rules": {"agentmint_readiness": {"state": "unverified"}},
        "total_answers": 26,
    })()

    assert filter_ready_agents([legacy, explicit_unverified]) == [legacy]
