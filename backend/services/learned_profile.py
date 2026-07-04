"""System-learned Agent capability profile stored inside Agent.review_rules."""
from __future__ import annotations

from datetime import datetime
from typing import Any

LEARNED_PROFILE_KEY = "learned_profile"
LIST_FIELDS = (
    "domain_tags",
    "capability_tags",
    "tool_tags",
    "style_tags",
    "positive_tags",
    "negative_tags",
)
MAX_LIST_ITEMS = 16


def normalize_learned_profile(profile: dict | None) -> dict[str, Any]:
    profile = profile or {}
    out: dict[str, Any] = {
        field: _clean_list(profile.get(field))
        for field in LIST_FIELDS
    }
    out["sample_count"] = _safe_int(profile.get("sample_count"))
    out["positive_feedback"] = _safe_int(profile.get("positive_feedback"))
    out["negative_feedback"] = _safe_int(profile.get("negative_feedback"))
    out["owner_supplement_count"] = _safe_int(profile.get("owner_supplement_count"))
    out["owner_supplement_types"] = _clean_type_counts(profile.get("owner_supplement_types"))
    out["updated_at"] = profile.get("updated_at")
    return out


def get_agent_learned_profile(agent_or_rules: Any) -> dict[str, Any]:
    rules = agent_or_rules if isinstance(agent_or_rules, dict) else getattr(agent_or_rules, "review_rules", None)
    raw = (rules or {}).get(LEARNED_PROFILE_KEY) if isinstance(rules, dict) else {}
    return normalize_learned_profile(raw)


def update_learned_profile_from_approval(agent: Any, question: Any, answer: Any) -> dict[str, Any]:
    from services.matching import build_task_profile

    rules = dict(getattr(agent, "review_rules", None) or {})
    profile = normalize_learned_profile(rules.get(LEARNED_PROFILE_KEY))
    task_profile = build_task_profile(
        getattr(question, "title", "") or "",
        getattr(question, "body", "") or "",
        list(getattr(question, "tags", None) or []),
        getattr(question, "max_responders", 3) or 3,
    )
    capability = getattr(answer, "capability", None) or {}

    _merge(profile, "domain_tags", list(getattr(question, "tags", None) or []))
    _merge(profile, "domain_tags", task_profile.get("domain_tags") or [])
    _merge(profile, "capability_tags", task_profile.get("capability_tags") or [])
    _merge(profile, "tool_tags", _used_tool_names(capability))
    _merge(profile, "style_tags", capability.get("style_tags") or capability.get("styles") or [])
    profile["sample_count"] = int(profile["sample_count"]) + 1
    profile["updated_at"] = datetime.utcnow().isoformat()

    rules[LEARNED_PROFILE_KEY] = profile
    agent.review_rules = rules
    return profile


def update_learned_profile_from_feedback(
    agent: Any,
    question: Any,
    vote: str,
    *,
    previous_vote: str | None = None,
) -> dict[str, Any]:
    rules = dict(getattr(agent, "review_rules", None) or {})
    profile = normalize_learned_profile(rules.get(LEARNED_PROFILE_KEY))
    tags = list(getattr(question, "tags", None) or [])

    if previous_vote == "up":
        profile["positive_feedback"] = max(0, int(profile["positive_feedback"]) - 1)
    elif previous_vote == "down":
        profile["negative_feedback"] = max(0, int(profile["negative_feedback"]) - 1)

    if vote == "up":
        profile["positive_feedback"] = int(profile["positive_feedback"]) + 1
        _merge(profile, "positive_tags", tags)
    elif vote == "down":
        profile["negative_feedback"] = int(profile["negative_feedback"]) + 1
        _merge(profile, "negative_tags", tags)

    profile["updated_at"] = datetime.utcnow().isoformat()
    rules[LEARNED_PROFILE_KEY] = profile
    agent.review_rules = rules
    return profile


def update_learned_profile_from_owner_supplement(agent: Any, question: Any, supplement: Any) -> dict[str, Any]:
    rules = dict(getattr(agent, "review_rules", None) or {})
    profile = normalize_learned_profile(rules.get(LEARNED_PROFILE_KEY))
    supplement_type = normalize_owner_supplement_type(getattr(supplement, "supplement_type", None))
    type_counts = dict(profile.get("owner_supplement_types") or {})

    profile["owner_supplement_count"] = int(profile["owner_supplement_count"]) + 1
    type_counts[supplement_type] = int(type_counts.get(supplement_type, 0)) + 1
    profile["owner_supplement_types"] = type_counts
    _merge(profile, "positive_tags", list(getattr(question, "tags", None) or []))
    style_tag = OWNER_SUPPLEMENT_STYLE_TAGS.get(supplement_type)
    if style_tag:
        _merge(profile, "style_tags", [style_tag])
    profile["updated_at"] = datetime.utcnow().isoformat()

    rules[LEARNED_PROFILE_KEY] = profile
    agent.review_rules = rules
    return profile


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


OWNER_SUPPLEMENT_TYPES = {"experience", "correction", "version_update", "risk_note"}
OWNER_SUPPLEMENT_STYLE_TAGS = {
    "experience": "主人经验",
    "correction": "主人纠错",
    "version_update": "版本更新",
    "risk_note": "风险提醒",
}


def normalize_owner_supplement_type(value: Any) -> str:
    text = str(value or "").strip()
    return text if text in OWNER_SUPPLEMENT_TYPES else "experience"


def _clean_type_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for key, count in value.items():
        normalized = normalize_owner_supplement_type(key)
        out[normalized] = out.get(normalized, 0) + _safe_int(count)
    return out


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
        if len(out) >= MAX_LIST_ITEMS:
            break
    return out


def _merge(profile: dict[str, Any], field: str, values: list[str]) -> None:
    profile[field] = _clean_list(list(profile.get(field) or []) + list(values or []))


def _used_tool_names(capability: dict) -> list[str]:
    tools = capability.get("tools")
    if not isinstance(tools, list):
        return []
    names: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("used") is False:
            continue
        name = str(tool.get("name") or "").strip()
        if name:
            names.append(name)
    return names
