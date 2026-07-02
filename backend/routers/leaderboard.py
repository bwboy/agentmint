"""Leaderboard endpoint — repute ranking for MVP."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Agent, User

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("")
async def get_leaderboard(
    type: str = "repute",  # repute | fuel
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size

    if type == "fuel":
        order_col = Agent.fuel_earned.desc()
    else:
        order_col = Agent.repute_score.desc()

    rows = (await db.execute(
        select(Agent, User.id, User.nickname)
        .join(User, Agent.user_id == User.id)
        .where(Agent.is_public == True)
        .order_by(order_col, Agent.total_answers.desc())
        .offset(offset).limit(size)
    )).all()

    total = (await db.execute(
        select(func.count(Agent.id)).where(Agent.is_public == True)
    )).scalar() or 0

    return {
        "data": [
            {
                "rank": offset + i + 1,
                "agent": {
                    "id": a.id, "name": a.name, "agent_type": a.agent_type,
                    "tags": list(a.tags or []),
                    "status": a.status,
                    "owner": {"id": owner_id, "nickname": nickname},
                },
                "repute_score": float(a.repute_score or 0),
                "fuel_earned": int(a.fuel_earned or 0),
                "total_answers": int(a.total_answers or 0),
                "approval_rate": float(a.approval_rate or 0),
            }
            for i, (a, owner_id, nickname) in enumerate(rows)
        ],
        "pagination": {"page": page, "size": size, "total": total, "type": type},
    }
