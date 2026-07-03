"""Notification creation helpers."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Notification, User


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


async def get_user_for_notification(db: AsyncSession, user_id: str) -> User | None:
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def maybe_create_notification(
    db: AsyncSession,
    user_id: str,
    pref_key: str,
    notif_type: str,
    title: str,
    body: str = "",
    ref_id: str | None = None,
    *,
    target_user: User | None = None,
) -> Notification | None:
    target = target_user or await get_user_for_notification(db, user_id)
    prefs = getattr(target, "notification_prefs", None) if target else None
    if isinstance(prefs, dict) and prefs.get(pref_key) is False:
        return None
    return await create_notification(db, user_id, notif_type, title, body, ref_id)
