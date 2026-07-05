from typing import Any


AGENT_VISIBILITIES = {"public", "followers", "friends", "archived"}
AGENT_SERVICE_MODES = {"auto_match", "direct_only", "stopped"}

DEFAULT_SERVICE_RULES = {
    "price_multiplier": 1.0,
    "max_followup_depth": 2,
    "min_fuel_per_answer": 0,
    "max_fuel_per_answer": 100_000,
    "max_questions_per_user_per_day": 20,
    "max_fuel_per_day": 1_000_000,
}


def normalize_visibility(value: Any) -> str:
    text = str(value or "public").strip().lower()
    return text if text in AGENT_VISIBILITIES else "public"


def normalize_service_mode(value: Any) -> str:
    text = str(value or "auto_match").strip().lower()
    return text if text in AGENT_SERVICE_MODES else "auto_match"


def normalize_service_rules(value: dict | None) -> dict[str, int | float]:
    data = value or {}
    multiplier = _float(data.get("price_multiplier"), DEFAULT_SERVICE_RULES["price_multiplier"])
    depth = _int(data.get("max_followup_depth"), DEFAULT_SERVICE_RULES["max_followup_depth"])
    min_fuel = _int(data.get("min_fuel_per_answer"), DEFAULT_SERVICE_RULES["min_fuel_per_answer"])
    max_fuel = _int(data.get("max_fuel_per_answer"), DEFAULT_SERVICE_RULES["max_fuel_per_answer"])
    max_questions_per_user = _int(
        data.get("max_questions_per_user_per_day"),
        DEFAULT_SERVICE_RULES["max_questions_per_user_per_day"],
    )
    max_fuel_per_day = _int(data.get("max_fuel_per_day"), DEFAULT_SERVICE_RULES["max_fuel_per_day"])

    if multiplier < 0.1 or multiplier > 10:
        multiplier = DEFAULT_SERVICE_RULES["price_multiplier"]
    if depth < 0:
        depth = DEFAULT_SERVICE_RULES["max_followup_depth"]
    depth = min(depth, 10)
    if min_fuel < 0:
        min_fuel = DEFAULT_SERVICE_RULES["min_fuel_per_answer"]
    if max_fuel <= 0 or max_fuel > DEFAULT_SERVICE_RULES["max_fuel_per_answer"]:
        max_fuel = DEFAULT_SERVICE_RULES["max_fuel_per_answer"]
    if min_fuel > max_fuel:
        min_fuel = max_fuel
    if max_questions_per_user <= 0 or max_questions_per_user > 100:
        max_questions_per_user = DEFAULT_SERVICE_RULES["max_questions_per_user_per_day"]
    if max_fuel_per_day <= 0 or max_fuel_per_day > DEFAULT_SERVICE_RULES["max_fuel_per_day"]:
        max_fuel_per_day = DEFAULT_SERVICE_RULES["max_fuel_per_day"]

    return {
        "price_multiplier": round(float(multiplier), 2),
        "max_followup_depth": depth,
        "min_fuel_per_answer": min_fuel,
        "max_fuel_per_answer": max_fuel,
        "max_questions_per_user_per_day": max_questions_per_user,
        "max_fuel_per_day": max_fuel_per_day,
    }


def can_view_agent(
    agent: Any,
    *,
    viewer_id: str | None,
    followed_owner_ids: set[str] | None = None,
    friend_owner_ids: set[str] | None = None,
) -> bool:
    visibility = normalize_visibility(getattr(agent, "visibility", None))
    owner_id = getattr(agent, "user_id", None)
    if visibility == "archived":
        return False
    if viewer_id and owner_id == viewer_id:
        return True
    if visibility == "public":
        return True
    if visibility == "followers":
        return bool(owner_id and owner_id in (followed_owner_ids or set()))
    if visibility == "friends":
        return bool(owner_id and owner_id in (friend_owner_ids or set()))
    return False


def can_auto_match_agent(
    agent: Any,
    *,
    viewer_id: str | None,
    followed_owner_ids: set[str] | None = None,
    friend_owner_ids: set[str] | None = None,
) -> bool:
    return (
        normalize_service_mode(getattr(agent, "service_mode", None)) == "auto_match"
        and can_view_agent(
            agent,
            viewer_id=viewer_id,
            followed_owner_ids=followed_owner_ids,
            friend_owner_ids=friend_owner_ids,
        )
    )


def service_limit_state(
    rules: dict | None,
    *,
    questions_by_user_today: int,
    fuel_today: int,
) -> str:
    normalized = normalize_service_rules(rules)
    if int(questions_by_user_today or 0) >= int(normalized["max_questions_per_user_per_day"]):
        return "user_limit"
    if int(fuel_today or 0) >= int(normalized["max_fuel_per_day"]):
        return "fuel_limit"
    return "ok"


def build_service_status(
    agent_status: str | None,
    service_mode: str | None,
    rules: dict | None,
    *,
    questions_by_user_today: int = 0,
    fuel_today: int = 0,
) -> dict:
    normalized_rules = normalize_service_rules(rules)
    question_limit = int(normalized_rules["max_questions_per_user_per_day"])
    fuel_limit = int(normalized_rules["max_fuel_per_day"])
    questions_today = max(0, int(questions_by_user_today or 0))
    earned_today = max(0, int(fuel_today or 0))
    remaining_questions = max(0, question_limit - questions_today)
    remaining_fuel = max(0, fuel_limit - earned_today)
    mode = normalize_service_mode(service_mode)
    status = str(agent_status or "offline")

    if status != "online":
        state = "offline"
        reason = "Agent 当前离线"
    elif mode == "stopped":
        state = "stopped"
        reason = "Agent 已停止服务"
    elif questions_today >= question_limit:
        state = "user_limit"
        reason = "你今天对这个 Agent 的提问次数已满"
    elif earned_today >= fuel_limit:
        state = "fuel_limit"
        reason = "Agent 今日燃值服务上限已满"
    else:
        state = "available"
        reason = "可自动匹配" if mode == "auto_match" else "可定向提问"

    return {
        "available": state == "available",
        "state": state,
        "reason": reason,
        "questions_by_user_today": questions_today,
        "remaining_questions_for_user_today": remaining_questions,
        "fuel_earned_today": earned_today,
        "remaining_fuel_today": remaining_fuel,
    }


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
