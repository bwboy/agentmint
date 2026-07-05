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
MAX_CONTEXT_ITEMS = 8
OWNER_EXPERIENCE_CONTEXT_KEY = "owner_experience_context"
OWNER_EXPERIENCE_CONTEXT_FIELDS = (
    "corrections",
    "version_updates",
    "risk_notes",
    "high_value_experiences",
    "avoid_next_time",
)


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
    out[OWNER_EXPERIENCE_CONTEXT_KEY] = normalize_owner_experience_context(profile.get(OWNER_EXPERIENCE_CONTEXT_KEY))
    out["updated_at"] = profile.get("updated_at")
    return out


def get_agent_learned_profile(agent_or_rules: Any) -> dict[str, Any]:
    rules = agent_or_rules if isinstance(agent_or_rules, dict) else getattr(agent_or_rules, "review_rules", None)
    raw = (rules or {}).get(LEARNED_PROFILE_KEY) if isinstance(rules, dict) else {}
    return normalize_learned_profile(raw)


def owner_supplement_summary_from_profile(profile: dict | None) -> dict[str, Any]:
    normalized = normalize_learned_profile(profile)
    types = dict(normalized.get("owner_supplement_types") or {})
    return {
        "total": int(normalized.get("owner_supplement_count") or 0),
        "types": types,
        "has_signal": int(normalized.get("owner_supplement_count") or 0) > 0,
        "dominant_type": _dominant_type(types),
    }


def get_owner_supplement_summary(agent_or_rules: Any) -> dict[str, Any]:
    return owner_supplement_summary_from_profile(get_agent_learned_profile(agent_or_rules))


def agent_health_summary_from_profile(profile: dict | None) -> dict[str, Any]:
    normalized = normalize_learned_profile(profile)
    type_counts = dict(normalized.get("owner_supplement_types") or {})
    negative_feedback = int(normalized.get("negative_feedback") or 0)
    owner_corrections = int(type_counts.get("correction") or 0)
    owner_risk_notes = int(type_counts.get("risk_note") or 0)
    avoid_next_time = normalize_owner_experience_context(
        normalized.get(OWNER_EXPERIENCE_CONTEXT_KEY)
    ).get("avoid_next_time", [])
    risk_level = "healthy"
    if negative_feedback >= 2 or owner_corrections >= 2 or owner_risk_notes >= 2:
        risk_level = "high"
    elif negative_feedback > 0 or owner_corrections > 0 or owner_risk_notes > 0 or avoid_next_time:
        risk_level = "watch"
    return {
        "risk_level": risk_level,
        "negative_feedback": negative_feedback,
        "owner_corrections": owner_corrections,
        "owner_risk_notes": owner_risk_notes,
        "avoid_next_time_count": len(avoid_next_time),
        "needs_review": risk_level == "high",
    }


def get_agent_health_summary(agent_or_rules: Any) -> dict[str, Any]:
    return agent_health_summary_from_profile(get_agent_learned_profile(agent_or_rules))


def normalize_owner_experience_context(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    out = {
        field: _clean_list(raw.get(field))[:MAX_CONTEXT_ITEMS]
        for field in OWNER_EXPERIENCE_CONTEXT_FIELDS
    }
    out["has_context"] = any(out[field] for field in OWNER_EXPERIENCE_CONTEXT_FIELDS)
    return out


def build_owner_experience_context(agent_or_rules: Any) -> dict[str, Any]:
    profile = get_agent_learned_profile(agent_or_rules)
    return normalize_owner_experience_context(profile.get(OWNER_EXPERIENCE_CONTEXT_KEY))


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
    reasons: list[str] | None = None,
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
        _merge(profile, "negative_tags", feedback_reason_tags(reasons))

    profile["updated_at"] = datetime.utcnow().isoformat()
    rules[LEARNED_PROFILE_KEY] = profile
    agent.review_rules = rules
    return profile


FEEDBACK_REASON_TAGS = {
    "stale": "反馈:过期",
    "missed_point": "反馈:没答到点",
    "needs_sources": "反馈:需要来源",
    "owner_review": "反馈:建议主人修正",
}


def feedback_reason_tags(values: list[str] | None) -> list[str]:
    tags: list[str] = []
    for value in values or []:
        tag = FEEDBACK_REASON_TAGS.get(str(value or "").strip())
        if tag:
            tags.append(tag)
    return tags


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
    _merge_owner_experience_context(profile, supplement)
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


def _dominant_type(type_counts: dict[str, int]) -> str | None:
    if not type_counts:
        return None
    return sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


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


def _merge_owner_experience_context(profile: dict[str, Any], supplement: Any) -> None:
    response = str(getattr(supplement, "response", "") or "").strip()
    if not response:
        return
    supplement_type = normalize_owner_supplement_type(getattr(supplement, "supplement_type", None))
    context = normalize_owner_experience_context(profile.get(OWNER_EXPERIENCE_CONTEXT_KEY))
    field_by_type = {
        "experience": "high_value_experiences" if bool(getattr(supplement, "is_high_value", False)) else None,
        "correction": "corrections",
        "version_update": "version_updates",
        "risk_note": "risk_notes",
    }
    field = field_by_type.get(supplement_type)
    if field:
        context[field] = _clean_list([response] + list(context.get(field) or []))[:MAX_CONTEXT_ITEMS]
    if supplement_type in {"correction", "risk_note"}:
        context["avoid_next_time"] = _clean_list(
            [response] + list(context.get("avoid_next_time") or [])
        )[:MAX_CONTEXT_ITEMS]
    if bool(getattr(supplement, "is_high_value", False)):
        context["high_value_experiences"] = _clean_list(
            [response] + list(context.get("high_value_experiences") or [])
        )[:MAX_CONTEXT_ITEMS]
    context["has_context"] = any(context[name] for name in OWNER_EXPERIENCE_CONTEXT_FIELDS)
    profile[OWNER_EXPERIENCE_CONTEXT_KEY] = context


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
