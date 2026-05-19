"""Notification endpoints — list + mark-read."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Notification
from services.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    unread: int = 0,
    page: int = 1,
    size: int = 20,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List notifications for the current user. Pass unread=1 for unread only."""
    offset = (page - 1) * size
    base = select(Notification).where(Notification.user_id == user["sub"])
    count_q = select(func.count(Notification.id)).where(Notification.user_id == user["sub"])
    if unread:
        base = base.where(Notification.read == False)
        count_q = count_q.where(Notification.read == False)
    base = base.order_by(Notification.created_at.desc()).offset(offset).limit(size)

    rows = (await db.execute(base)).scalars().all()
    total = (await db.execute(count_q)).scalar() or 0

    return {
        "data": [
            {
                "id": n.id, "type": n.type, "title": n.title, "body": n.body,
                "ref_id": n.ref_id, "read": n.read,
                "created_at": n.created_at.isoformat(),
            }
            for n in rows
        ],
        "pagination": {"page": page, "size": size, "total": total},
    }


@router.put("/read-all", status_code=204)
async def mark_all_read(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification).where(
            Notification.user_id == user["sub"], Notification.read == False
        ).values(read=True)
    )
    await db.commit()
    return Response(status_code=204)


@router.put("/{notif_id}/read", status_code=204)
async def mark_read(
    notif_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notif_id, Notification.user_id == user["sub"]
        )
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404)
    n.read = True
    await db.commit()
    return Response(status_code=204)
