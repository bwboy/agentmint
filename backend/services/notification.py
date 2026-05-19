"""Notification creation helpers."""
from sqlalchemy.ext.asyncio import AsyncSession

from models import Notification


async def create_notification(
    db: AsyncSession,
    user_id: str,
    notif_type: str,
    title: str,
    body: str = "",
    ref_id: str | None = None,
) -> Notification:
    n = Notification(
        user_id=user_id,
        type=notif_type,
        title=title,
        body=body,
        ref_id=ref_id,
    )
    db.add(n)
    return n
