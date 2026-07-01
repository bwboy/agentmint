from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models import User


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
