"""Authentication endpoints: SMS verification + JWT issuance."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from services.auth import (
    issue_code,
    verify_code,
    create_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SendCodeReq(BaseModel):
    phone: str = Field(min_length=8, max_length=20)


class VerifyCodeReq(BaseModel):
    phone: str
    code: str
    nickname: str = ""


class RefreshReq(BaseModel):
    refresh_token: str


@router.post("/send-code")
async def send_code(req: SendCodeReq):
    code = await issue_code(req.phone)
    # In dev / mock provider, log the code for convenience.
    print(f"[SMS] code for {req.phone}: {code}")
    return {"expires_in": 300}


@router.post("/verify-code")
async def verify_code_handler(req: VerifyCodeReq, db: AsyncSession = Depends(get_db)):
    if not await verify_code(req.phone, req.code):
        raise HTTPException(status_code=401, detail="验证码错误或已过期")

    result = await db.execute(select(User).where(User.phone == req.phone))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            phone=req.phone,
            nickname=req.nickname or f"用户{req.phone[-4:]}",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_token(user.id, user.nickname, user.trust_level)
    refresh = create_refresh_token(user.id)

    return {
        "token": token,
        "refresh_token": refresh,
        "user": {
            "id": user.id,
            "nickname": user.nickname,
            "phone": _mask_phone(req.phone),
            "trust_level": user.trust_level,
            "fuel_balance": user.fuel_balance,
            "repute_score": float(user.repute_score),
        },
    }


@router.post("/refresh")
async def refresh_token(req: RefreshReq, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="刷新令牌无效")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    return {
        "token": create_token(user.id, user.nickname, user.trust_level),
        "refresh_token": create_refresh_token(user.id),
    }


@router.get("/me")
async def me(user_payload: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from models import Agent
    result = await db.execute(select(User).where(User.id == user_payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    count_result = await db.execute(select(Agent).where(Agent.user_id == user.id))
    agent_count = len(count_result.scalars().all())

    return {
        "id": user.id,
        "nickname": user.nickname,
        "phone": _mask_phone(user.phone),
        "trust_level": user.trust_level,
        "fuel_balance": user.fuel_balance,
        "repute_score": float(user.repute_score),
        "agent_count": agent_count,
    }


def _mask_phone(phone: str) -> str:
    if len(phone) <= 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"
