"""Authentication endpoints: SMS verification + JWT issuance."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import FuelLedgerEntry, User
from services.auth import (
    issue_code,
    verify_code,
    create_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from services.agent_service_rules import normalize_service_mode, normalize_service_rules, normalize_visibility

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SendCodeReq(BaseModel):
    phone: str = Field(min_length=8, max_length=20)


class VerifyCodeReq(BaseModel):
    phone: str
    code: str
    nickname: str = ""


class RefreshReq(BaseModel):
    refresh_token: str


class UpdateProfileReq(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    avatar_url: str | None = None
    headline: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=2000)
    profile_tags: list[str] | None = None
    experience_tags: list[str] | None = None
    links: dict | None = None
    profile_visibility: str | None = None
    default_agent_visibility: str | None = None
    default_agent_service_mode: str | None = None
    default_agent_service_rules: dict | None = None
    notification_prefs: dict | None = None


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
            **_user_profile_dict(user),
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
        **_user_profile_dict(user),
    }


@router.get("/my/profile")
async def my_profile(user_payload: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user = await _get_user(db, user_payload["sub"])
    return _private_user_profile(user)


@router.put("/my/profile")
async def update_my_profile(
    req: UpdateProfileReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user(db, user_payload["sub"])

    if req.nickname is not None:
        user.nickname = req.nickname.strip()
    if req.avatar_url is not None:
        user.avatar_url = _clean_url(req.avatar_url)
    if req.headline is not None:
        user.headline = (req.headline or "").strip()
    if req.bio is not None:
        user.bio = (req.bio or "").strip()
    if req.profile_tags is not None:
        user.profile_tags = _clean_list(req.profile_tags, limit=20)
    if req.experience_tags is not None:
        user.experience_tags = _clean_list(req.experience_tags, limit=20)
    if req.links is not None:
        user.links = _clean_links(req.links)
    if req.profile_visibility is not None:
        user.profile_visibility = normalize_visibility(req.profile_visibility)
    if req.default_agent_visibility is not None:
        user.default_agent_visibility = normalize_visibility(req.default_agent_visibility)
    if req.default_agent_service_mode is not None:
        user.default_agent_service_mode = normalize_service_mode(req.default_agent_service_mode)
    if req.default_agent_service_rules is not None:
        user.default_agent_service_rules = normalize_service_rules(req.default_agent_service_rules)
    if req.notification_prefs is not None:
        user.notification_prefs = _clean_notification_prefs(req.notification_prefs)

    await db.commit()
    await db.refresh(user)
    return _private_user_profile(user)


@router.get("/my/fuel-ledger")
async def my_fuel_ledger(
    page: int = 1,
    size: int = 50,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = max(1, int(page or 1))
    size = min(100, max(1, int(size or 50)))
    offset = (page - 1) * size
    user_id = user_payload["sub"]

    rows = (await db.execute(
        select(FuelLedgerEntry)
        .where(FuelLedgerEntry.user_id == user_id)
        .order_by(FuelLedgerEntry.created_at.desc())
        .offset(offset)
        .limit(size)
    )).scalars().all()
    total = (await db.execute(
        select(func.count(FuelLedgerEntry.id)).where(FuelLedgerEntry.user_id == user_id)
    )).scalar() or 0

    return {
        "data": [_fuel_ledger_to_dict(item) for item in rows],
        "pagination": {"page": page, "size": size, "total": total},
    }


@router.get("/my/fuel-summary")
async def my_fuel_summary(
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = user_payload["sub"]
    rows = (await db.execute(
        select(
            FuelLedgerEntry.direction,
            FuelLedgerEntry.event_type,
            FuelLedgerEntry.agent_id,
            func.coalesce(func.sum(FuelLedgerEntry.amount), 0),
        )
        .where(FuelLedgerEntry.user_id == user_id)
        .group_by(FuelLedgerEntry.direction, FuelLedgerEntry.event_type, FuelLedgerEntry.agent_id)
    )).all()
    return build_fuel_summary(rows)


def build_fuel_summary(rows: list[tuple]) -> dict:
    totals = {
        "income": 0,
        "spend": 0,
        "refund": 0,
        "reward_income": 0,
        "base_income": 0,
        "net": 0,
    }
    by_agent: dict[str, dict] = {}
    by_event: dict[str, int] = {}

    for direction, event_type, agent_id, amount in rows:
        amount = int(amount or 0)
        event_type = str(event_type or "")
        by_event[event_type] = by_event.get(event_type, 0) + amount
        is_refund = event_type.endswith("_refunded") or event_type in {"base_refunded", "reward_refunded"}
        if direction == "credit" and not is_refund:
            totals["income"] += amount
        elif direction == "debit":
            totals["spend"] += amount
        if is_refund:
            totals["refund"] += amount
        if event_type in {"reward_awarded", "reward_auto_awarded"}:
            totals["reward_income"] += amount
        if event_type in {"answer_base_earned", "usage_correction"}:
            totals["base_income"] += amount
        if agent_id and direction == "credit":
            item = by_agent.setdefault(str(agent_id), {
                "agent_id": str(agent_id),
                "income": 0,
                "base_income": 0,
                "reward_income": 0,
            })
            item["income"] += amount
            if event_type in {"reward_awarded", "reward_auto_awarded"}:
                item["reward_income"] += amount
            else:
                item["base_income"] += amount

    totals["net"] = totals["income"] - totals["spend"] + totals["refund"]
    agent_income = sorted(by_agent.values(), key=lambda item: item["income"], reverse=True)
    return {
        "totals": totals,
        "by_event": by_event,
        "agent_income": agent_income,
    }


def _mask_phone(phone: str) -> str:
    if len(phone) <= 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


async def _get_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


def _private_user_profile(user: User) -> dict:
    return {
        "id": user.id,
        "nickname": user.nickname,
        "phone": _mask_phone(user.phone),
        "trust_level": user.trust_level,
        "fuel_balance": user.fuel_balance,
        "repute_score": float(user.repute_score),
        **_user_profile_dict(user),
    }


def _fuel_ledger_to_dict(item: FuelLedgerEntry) -> dict:
    return {
        "id": item.id,
        "amount": int(item.amount or 0),
        "direction": item.direction,
        "event_type": item.event_type,
        "question_id": item.question_id,
        "answer_id": item.answer_id,
        "agent_id": item.agent_id,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _user_profile_dict(user: User) -> dict:
    return {
        "avatar_url": getattr(user, "avatar_url", "") or "",
        "headline": getattr(user, "headline", "") or "",
        "bio": getattr(user, "bio", "") or "",
        "profile_tags": list(getattr(user, "profile_tags", None) or []),
        "experience_tags": list(getattr(user, "experience_tags", None) or []),
        "links": dict(getattr(user, "links", None) or {}),
        "profile_visibility": normalize_visibility(getattr(user, "profile_visibility", None)),
        "default_agent_visibility": normalize_visibility(getattr(user, "default_agent_visibility", None)),
        "default_agent_service_mode": normalize_service_mode(getattr(user, "default_agent_service_mode", None)),
        "default_agent_service_rules": normalize_service_rules(getattr(user, "default_agent_service_rules", None)),
        "notification_prefs": _clean_notification_prefs(getattr(user, "notification_prefs", None) or {}),
    }


def _clean_list(values: list[str], limit: int = 20) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text[:40])
        if len(out) >= limit:
            break
    return out


def _clean_url(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text[:500]
    return ""


def _clean_links(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {}
    allowed = {"website", "github", "x", "bilibili", "youtube", "linkedin"}
    out = {}
    for key, url in value.items():
        key_text = str(key).strip().lower()
        clean = _clean_url(str(url))
        if key_text in allowed and clean:
            out[key_text] = clean
    return out


def _clean_notification_prefs(value: dict | None) -> dict:
    defaults = {
        "friend_request": True,
        "agent_subscribed": True,
        "direct_question": True,
        "answer_feedback": True,
    }
    if not isinstance(value, dict):
        return defaults
    return {key: bool(value.get(key, default)) for key, default in defaults.items()}
