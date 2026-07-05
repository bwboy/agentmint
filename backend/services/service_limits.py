from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Answer, Question
from services.agent_service_rules import build_service_status, service_limit_state


def day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def questions_by_user_for_agent_today(
    db: AsyncSession,
    *,
    agent_id: str,
    user_id: str,
    since: datetime | None = None,
) -> int:
    since = since or day_start()
    result = await db.execute(
        select(func.count(func.distinct(Question.id)))
        .join(Answer, Answer.question_id == Question.id)
        .where(
            Question.asker_id == user_id,
            Question.created_at >= since,
            Answer.agent_id == agent_id,
        )
    )
    return int(result.scalar() or 0)


async def fuel_earned_by_agent_today(
    db: AsyncSession,
    *,
    agent_id: str,
    since: datetime | None = None,
) -> int:
    since = since or day_start()
    result = await db.execute(
        select(func.coalesce(func.sum(Answer.fuel_earned), 0)).where(
            Answer.agent_id == agent_id,
            Answer.status == "approved",
            Answer.fuel_earned > 0,
            Answer.reviewed_at >= since,
        )
    )
    return int(result.scalar() or 0)


async def agent_service_limit_state(
    db: AsyncSession,
    agent,
    *,
    viewer_id: str | None,
    since: datetime | None = None,
) -> str:
    since = since or day_start()
    questions_today = 0
    if viewer_id:
        questions_today = await questions_by_user_for_agent_today(
            db,
            agent_id=agent.id,
            user_id=viewer_id,
            since=since,
        )
    fuel_today = await fuel_earned_by_agent_today(db, agent_id=agent.id, since=since)
    return service_limit_state(
        getattr(agent, "service_rules", None),
        questions_by_user_today=questions_today,
        fuel_today=fuel_today,
    )


async def agent_service_status(
    db: AsyncSession,
    agent,
    *,
    viewer_id: str | None,
    since: datetime | None = None,
) -> dict:
    since = since or day_start()
    questions_today = 0
    if viewer_id:
        questions_today = await questions_by_user_for_agent_today(
            db,
            agent_id=agent.id,
            user_id=viewer_id,
            since=since,
        )
    fuel_today = await fuel_earned_by_agent_today(db, agent_id=agent.id, since=since)
    return build_service_status(
        getattr(agent, "status", None),
        getattr(agent, "service_mode", None),
        getattr(agent, "service_rules", None),
        questions_by_user_today=questions_today,
        fuel_today=fuel_today,
    )
