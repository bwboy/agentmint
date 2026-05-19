"""Daily quota service.

Counts per-agent question deliveries against `agent_daily_usage(agent_id, usage_date)`.
The counter increments when a question is *pushed* to the connector — receiving
the push consumes a slot regardless of whether the agent finally answers, to
prevent gaming via "go offline to skip work".

Three-state classification driven by `agent.daily_quota_config`:
  - "ok"          : auto path allowed (still subject to review_rules)
  - "review_only" : must go through manual review (auto_threshold ≤ used < max)
  - "blocked"     : matching engine filters this agent out
"""
from datetime import date
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import AgentDailyUsage


DEFAULT_QUOTA = {"max": 50, "auto_threshold": 40, "emergency_reserve": 3}


async def get_today_usage(db: AsyncSession, agent_id: str) -> int:
    today = date.today()
    result = await db.execute(
        select(AgentDailyUsage.used_count).where(
            AgentDailyUsage.agent_id == agent_id,
            AgentDailyUsage.usage_date == today,
        )
    )
    val = result.scalar_one_or_none()
    return int(val or 0)


async def increment_usage(db: AsyncSession, agent_id: str) -> int:
    """Atomic UPSERT — counter += 1. Returns new value."""
    today = date.today()
    stmt = pg_insert(AgentDailyUsage).values(
        agent_id=agent_id, usage_date=today, used_count=1
    ).on_conflict_do_update(
        index_elements=["agent_id", "usage_date"],
        set_={"used_count": AgentDailyUsage.used_count + 1},
    ).returning(AgentDailyUsage.used_count)
    result = await db.execute(stmt)
    new_val = result.scalar_one()
    await db.commit()
    return int(new_val)


def classify(used: int, quota_config: dict | None) -> str:
    cfg = {**DEFAULT_QUOTA, **(quota_config or {})}
    if used >= cfg["max"]:
        return "blocked"
    if used >= cfg["auto_threshold"]:
        return "review_only"
    return "ok"


async def check_quota(db: AsyncSession, agent_id: str, quota_config: dict | None) -> tuple[str, int]:
    """Return (state, used_count)."""
    used = await get_today_usage(db, agent_id)
    return classify(used, quota_config), used
