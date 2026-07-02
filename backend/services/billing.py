from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from services.agent_service_rules import normalize_service_rules

INPUT_TOKEN_FUEL_PRICE = 1
OUTPUT_TOKEN_FUEL_PRICE = 2


async def deduct_fuel_if_available(db: AsyncSession, user_id: str, fuel_cost: int) -> bool:
    if fuel_cost <= 0:
        return True

    result = await db.execute(
        update(User)
        .where(User.id == user_id, User.fuel_balance >= fuel_cost)
        .values(fuel_balance=User.fuel_balance - fuel_cost)
    )
    rowcount = getattr(result, "rowcount", None)
    return rowcount is None or int(rowcount or 0) > 0


async def refund_fuel(db: AsyncSession, user_id: str, fuel_amount: int) -> bool:
    if fuel_amount <= 0:
        return True

    result = await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(fuel_balance=User.fuel_balance + fuel_amount)
    )
    rowcount = getattr(result, "rowcount", None)
    return rowcount is None or int(rowcount or 0) > 0


def calculate_answer_fuel(usage: dict | None, agent) -> int:
    usage = usage or {}
    prompt_tokens = _int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    completion_tokens = _int(usage.get("completion_tokens") or usage.get("output_tokens"))
    if not prompt_tokens and not completion_tokens:
        prompt_tokens = _int(usage.get("total_tokens"))

    rules = normalize_service_rules(getattr(agent, "service_rules", None))
    base = prompt_tokens * INPUT_TOKEN_FUEL_PRICE + completion_tokens * OUTPUT_TOKEN_FUEL_PRICE
    priced = int(round(base * float(rules["price_multiplier"])))
    return max(
        int(rules["min_fuel_per_answer"]),
        min(priced, int(rules["max_fuel_per_answer"])),
    )


def _int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
