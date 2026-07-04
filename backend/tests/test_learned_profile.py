from types import SimpleNamespace

from services.learned_profile import (
    build_owner_experience_context,
    get_agent_learned_profile,
    normalize_learned_profile,
    update_learned_profile_from_approval,
    update_learned_profile_from_feedback,
    update_learned_profile_from_owner_supplement,
)


def test_normalize_learned_profile_defaults_and_dedupes():
    profile = normalize_learned_profile({
        "domain_tags": ["AI", "ai", "", "系统设计"],
        "sample_count": "3",
        "positive_feedback": None,
    })

    assert profile["domain_tags"] == ["AI", "系统设计"]
    assert profile["capability_tags"] == []
    assert profile["positive_tags"] == []
    assert profile["sample_count"] == 3
    assert profile["positive_feedback"] == 0
    assert profile["negative_feedback"] == 0


def test_update_learned_profile_from_approval_uses_question_and_answer_signals():
    agent = SimpleNamespace(review_rules={})
    question = SimpleNamespace(
        title="wow硬核模式职业选择",
        body="给我三个选择和风险",
        tags=["魔兽世界"],
    )
    answer = SimpleNamespace(
        capability={
            "tools": [{"name": "知识库", "used": True}, {"name": "未使用", "used": False}],
            "style_tags": ["实战", "简洁"],
        }
    )

    profile = update_learned_profile_from_approval(agent, question, answer)

    assert profile["sample_count"] == 1
    assert "魔兽世界" in profile["domain_tags"]
    assert "游戏" in profile["domain_tags"]
    assert "风险审查" in profile["capability_tags"]
    assert profile["tool_tags"] == ["知识库"]
    assert profile["style_tags"] == ["实战", "简洁"]
    assert get_agent_learned_profile(agent) == profile


def test_update_learned_profile_from_feedback_tracks_vote_changes():
    agent = SimpleNamespace(review_rules={})
    question = SimpleNamespace(tags=["魔兽世界", "硬核模式"])

    first = update_learned_profile_from_feedback(agent, question, "up")
    assert first["positive_feedback"] == 1
    assert first["negative_feedback"] == 0
    assert first["positive_tags"] == ["魔兽世界", "硬核模式"]

    switched = update_learned_profile_from_feedback(agent, question, "down", previous_vote="up")
    assert switched["positive_feedback"] == 0
    assert switched["negative_feedback"] == 1
    assert switched["negative_tags"] == ["魔兽世界", "硬核模式"]


def test_update_learned_profile_from_owner_supplement_tracks_type_and_question_tags():
    agent = SimpleNamespace(review_rules={})
    question = SimpleNamespace(tags=["荒野大镖客2", "平台选择"])
    supplement = SimpleNamespace(supplement_type="correction", response="PC 画质更好，但主机体验更省心")

    profile = update_learned_profile_from_owner_supplement(agent, question, supplement)

    assert profile["owner_supplement_count"] == 1
    assert profile["owner_supplement_types"]["correction"] == 1
    assert profile["positive_tags"] == ["荒野大镖客2", "平台选择"]
    assert "主人纠错" in profile["style_tags"]


def test_owner_supplement_learning_keeps_actionable_context_by_type():
    agent = SimpleNamespace(review_rules={})
    question = SimpleNamespace(tags=["魔兽世界", "惩戒骑"])

    update_learned_profile_from_owner_supplement(
        agent,
        question,
        SimpleNamespace(
            supplement_type="correction",
            response="不要默认推荐玻璃大炮天赋，先判断硬核模式死亡风险。",
            is_high_value=True,
        ),
    )
    update_learned_profile_from_owner_supplement(
        agent,
        question,
        SimpleNamespace(
            supplement_type="version_update",
            response="12.07 后饰品优先级变化，先查新团本掉落。",
            is_high_value=False,
        ),
    )

    context = build_owner_experience_context(agent)

    assert context["has_context"] is True
    assert context["corrections"] == ["不要默认推荐玻璃大炮天赋，先判断硬核模式死亡风险。"]
    assert context["version_updates"] == ["12.07 后饰品优先级变化，先查新团本掉落。"]
    assert context["high_value_experiences"] == ["不要默认推荐玻璃大炮天赋，先判断硬核模式死亡风险。"]
    assert context["avoid_next_time"] == ["不要默认推荐玻璃大炮天赋，先判断硬核模式死亡风险。"]


def test_risk_notes_become_next_answer_constraints():
    agent = SimpleNamespace(review_rules={})
    question = SimpleNamespace(tags=["魔兽世界", "硬核模式"])

    update_learned_profile_from_owner_supplement(
        agent,
        question,
        SimpleNamespace(
            supplement_type="risk_note",
            response="硬核模式回答前必须提醒死亡不可逆，避免只按普通服输出推荐。",
            is_high_value=False,
        ),
    )

    context = build_owner_experience_context(agent)

    assert context["risk_notes"] == ["硬核模式回答前必须提醒死亡不可逆，避免只按普通服输出推荐。"]
    assert context["avoid_next_time"] == ["硬核模式回答前必须提醒死亡不可逆，避免只按普通服输出推荐。"]
