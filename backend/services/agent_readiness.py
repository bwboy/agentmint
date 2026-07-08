"""AgentMint runtime readiness state stored inside Agent.review_rules."""
from __future__ import annotations

from datetime import datetime
from typing import Any

READINESS_KEY = "agentmint_readiness"
READINESS_STATES = {"unverified", "checking", "pairing_required", "ready", "error"}


def default_readiness() -> dict[str, Any]:
    return {
        "state": "unverified",
        "code": None,
        "command": None,
        "error": None,
        "checked_at": None,
    }


def get_agent_readiness(agent_or_rules: Any) -> dict[str, Any]:
    rules = agent_or_rules if isinstance(agent_or_rules, dict) else getattr(agent_or_rules, "review_rules", None)
    raw = (rules or {}).get(READINESS_KEY) if isinstance(rules, dict) else None
    if not isinstance(raw, dict):
        if not isinstance(agent_or_rules, dict) and int(getattr(agent_or_rules, "total_answers", 0) or 0) > 0:
            return {
                **default_readiness(),
                "state": "ready",
                "source": "legacy_answers",
            }
        return default_readiness()

    readiness = {**default_readiness(), **raw}
    if readiness.get("state") not in READINESS_STATES:
        readiness["state"] = "unverified"
    return readiness


def set_agent_readiness(
    agent: Any,
    state: str,
    *,
    code: str | None = None,
    command: str | None = None,
    error: str | None = None,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    if state not in READINESS_STATES:
        raise ValueError(f"unknown readiness state: {state}")

    readiness = {
        "state": state,
        "code": code,
        "command": command,
        "error": error,
        "checked_at": (checked_at or datetime.utcnow()).isoformat(),
    }
    rules = dict(getattr(agent, "review_rules", None) or {})
    rules[READINESS_KEY] = readiness
    agent.review_rules = rules
    return readiness
