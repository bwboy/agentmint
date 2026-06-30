from types import SimpleNamespace

from services.agent_readiness import (
    READINESS_KEY,
    default_readiness,
    get_agent_readiness,
    set_agent_readiness,
)


def test_default_readiness_is_unverified():
    readiness = default_readiness()

    assert readiness["state"] == "unverified"
    assert readiness["code"] is None
    assert readiness["command"] is None


def test_set_agent_readiness_preserves_existing_review_rules():
    agent = SimpleNamespace(review_rules={"auto_trust_level": 3, "capability_profile": {"domain_tags": ["AI"]}})

    readiness = set_agent_readiness(
        agent,
        "pairing_required",
        code="KJ5S6H25",
        command="hermes pairing approve agentmint KJ5S6H25",
    )

    assert agent.review_rules["auto_trust_level"] == 3
    assert agent.review_rules["capability_profile"] == {"domain_tags": ["AI"]}
    assert agent.review_rules[READINESS_KEY] == readiness
    assert readiness["state"] == "pairing_required"
    assert readiness["code"] == "KJ5S6H25"
    assert readiness["command"] == "hermes pairing approve agentmint KJ5S6H25"


def test_get_agent_readiness_normalizes_missing_or_unknown_state():
    assert get_agent_readiness(SimpleNamespace(review_rules=None))["state"] == "unverified"
    assert get_agent_readiness(SimpleNamespace(review_rules={READINESS_KEY: {"state": "bogus"}}))["state"] == "unverified"
