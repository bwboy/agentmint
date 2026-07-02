"""Agent CRUD, connector token management, and review-queue endpoints.

Review-queue endpoints (approve/reject) check `agent.user_id == current_user`
to prevent users from approving each other's agents.
"""
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Agent, AgentSubscription, Connector, FriendRequest, Friendship, User, UserFollow, Answer, Question
from models.relationship import friendship_pair
from services.auth import decode_token, get_current_user, hash_token
from services.agent_readiness import get_agent_readiness, set_agent_readiness
from services.agent_service_rules import can_view_agent, normalize_service_mode, normalize_service_rules, normalize_visibility
from services.learned_profile import get_agent_learned_profile
from services.matching import normalize_capability_profile
from services.review import approve_answer_by_id, reject_answer_by_id

router = APIRouter(prefix="/api", tags=["agents"])


class CreateAgentReq(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    agent_type: str  # openclaw | hermes
    tags: list[str] = []
    description: str = ""
    is_public: bool = True
    capability_profile: dict | None = None
    visibility: str = "public"
    service_mode: str = "auto_match"
    service_rules: dict | None = None


class UpdateAgentReq(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    description: str | None = None
    is_public: bool | None = None
    daily_quota_config: dict | None = None
    review_rules: dict | None = None
    capability_profile: dict | None = None
    visibility: str | None = None
    service_mode: str | None = None
    service_rules: dict | None = None


# ═══════════════════════════════════════════════════
# Public endpoints
# ═══════════════════════════════════════════════════

@router.get("/agents")
async def list_agents(
    tag: str | None = None,
    sort: str = "repute",
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all public agents (online + offline; status returned for UI)."""
    offset = (page - 1) * size

    base = select(Agent, User.nickname).join(User, Agent.user_id == User.id).where(Agent.visibility == "public")
    count_base = select(func.count(Agent.id)).where(Agent.visibility == "public")
    if tag:
        base = base.where(Agent.tags.any(tag))
        count_base = count_base.where(Agent.tags.any(tag))

    order_map = {
        "repute": Agent.repute_score.desc(),
        "answers": Agent.total_answers.desc(),
        "latest": Agent.created_at.desc(),
    }
    base = base.order_by(order_map.get(sort, order_map["repute"])).offset(offset).limit(size)

    result = await db.execute(base)
    rows = result.all()
    total = (await db.execute(count_base)).scalar() or 0

    return {
        "data": [_agent_to_dict(a, nickname) for a, nickname in rows],
        "pagination": {"page": page, "size": size, "total": total},
    }


def get_optional_user(request: Request) -> dict | None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = decode_token(auth[len("Bearer "):])
    if not payload or payload.get("type") != "access":
        return None
    return payload


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    viewer: dict | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent, User.nickname)
        .join(User, Agent.user_id == User.id)
        .where(Agent.id == agent_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    agent, nickname = row
    if viewer:
        followed_owner_ids, friend_owner_ids = await _relationship_owner_sets(db, viewer["sub"])
    else:
        followed_owner_ids, friend_owner_ids = set(), set()
    if not can_view_agent(
        agent,
        viewer_id=viewer["sub"] if viewer else None,
        followed_owner_ids=followed_owner_ids,
        friend_owner_ids=friend_owner_ids,
    ):
        raise HTTPException(status_code=404, detail="Agent 不存在")
    relationship = await _relationship_context(db, viewer["sub"], agent) if viewer else None
    return _agent_to_dict(agent, nickname, include_owner_id=True, full=True, relationship=relationship)


# ═══════════════════════════════════════════════════
# Protected: my agents
# ═══════════════════════════════════════════════════

@router.get("/my/agents")
async def my_agents(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Agent).where(Agent.user_id == user["sub"]).order_by(Agent.created_at.desc())
    )
    agents = result.scalars().all()
    return {"data": [_agent_to_dict(a, user.get("nickname", ""), full=True) for a in agents]}


@router.post("/my/agents", status_code=201)
async def create_agent(
    req: CreateAgentReq,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.agent_type not in ("openclaw", "hermes"):
        raise HTTPException(status_code=400, detail="agent_type 必须是 openclaw 或 hermes")
    visibility = normalize_visibility(req.visibility if req.is_public else "archived")
    agent = Agent(
        user_id=user["sub"],
        name=req.name,
        agent_type=req.agent_type,
        tags=req.tags,
        description=req.description,
        is_public=visibility == "public",
        visibility=visibility,
        service_mode=normalize_service_mode(req.service_mode),
        service_rules=normalize_service_rules(req.service_rules),
        review_rules=merge_capability_profile(None, req.capability_profile),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _agent_to_dict(agent, user.get("nickname", ""), full=True)


@router.put("/my/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    req: UpdateAgentReq,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(db, agent_id, user["sub"])

    if req.name is not None: agent.name = req.name
    if req.tags is not None: agent.tags = req.tags
    if req.description is not None: agent.description = req.description
    if req.is_public is not None: agent.is_public = req.is_public
    if req.visibility is not None:
        agent.visibility = normalize_visibility(req.visibility)
        agent.is_public = agent.visibility == "public"
    if req.service_mode is not None: agent.service_mode = normalize_service_mode(req.service_mode)
    if req.service_rules is not None: agent.service_rules = normalize_service_rules(req.service_rules)
    if req.daily_quota_config is not None: agent.daily_quota_config = req.daily_quota_config
    if req.review_rules is not None: agent.review_rules = req.review_rules
    if req.capability_profile is not None:
        agent.review_rules = merge_capability_profile(agent.review_rules, req.capability_profile)

    await db.commit()
    await db.refresh(agent)
    return _agent_to_dict(agent, user.get("nickname", ""), full=True)


@router.post("/users/{target_user_id}/follow")
async def follow_user(
    target_user_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if target_user_id == user["sub"]:
        raise HTTPException(status_code=400, detail="不能关注自己")
    target = (await db.execute(select(User).where(User.id == target_user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    existing = (await db.execute(
        select(UserFollow).where(UserFollow.follower_id == user["sub"], UserFollow.followed_id == target_user_id)
    )).scalar_one_or_none()
    if not existing:
        db.add(UserFollow(follower_id=user["sub"], followed_id=target_user_id))
        await db.commit()
    return {"following": True, "user_id": target_user_id}


@router.delete("/users/{target_user_id}/follow", status_code=204)
async def unfollow_user(
    target_user_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(UserFollow).where(UserFollow.follower_id == user["sub"], UserFollow.followed_id == target_user_id)
    )).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()
    return Response(status_code=204)


@router.post("/agents/{agent_id}/subscribe")
async def subscribe_agent(
    agent_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    followed_owner_ids, friend_owner_ids = await _relationship_owner_sets(db, user["sub"])
    if not can_view_agent(
        agent,
        viewer_id=user["sub"],
        followed_owner_ids=followed_owner_ids,
        friend_owner_ids=friend_owner_ids,
    ):
        raise HTTPException(status_code=404, detail="Agent 不存在")
    existing = (await db.execute(
        select(AgentSubscription).where(
            AgentSubscription.subscriber_id == user["sub"],
            AgentSubscription.agent_id == agent_id,
        )
    )).scalar_one_or_none()
    if not existing:
        db.add(AgentSubscription(subscriber_id=user["sub"], agent_id=agent_id))
        await db.commit()
    return {"subscribed": True, "agent_id": agent_id}


@router.delete("/agents/{agent_id}/subscribe", status_code=204)
async def unsubscribe_agent(
    agent_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(AgentSubscription).where(
            AgentSubscription.subscriber_id == user["sub"],
            AgentSubscription.agent_id == agent_id,
        )
    )).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()
    return Response(status_code=204)


@router.post("/users/{target_user_id}/friend-requests", status_code=201)
async def create_friend_request(
    target_user_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if target_user_id == user["sub"]:
        raise HTTPException(status_code=400, detail="不能添加自己为好友")
    target = (await db.execute(select(User).where(User.id == target_user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    low, high = friendship_pair(user["sub"], target_user_id)
    existing_friend = (await db.execute(
        select(Friendship).where(Friendship.user_low_id == low, Friendship.user_high_id == high)
    )).scalar_one_or_none()
    if existing_friend:
        return {"status": "accepted", "friend_id": target_user_id}

    existing = (await db.execute(
        select(FriendRequest).where(
            FriendRequest.requester_id == user["sub"],
            FriendRequest.recipient_id == target_user_id,
            FriendRequest.status == "pending",
        )
    )).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "status": existing.status, "recipient_id": target_user_id}

    req = FriendRequest(requester_id=user["sub"], recipient_id=target_user_id)
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return {"id": req.id, "status": req.status or "pending", "recipient_id": target_user_id}


@router.post("/friend-requests/{request_id}/accept")
async def accept_friend_request(
    request_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = (await db.execute(select(FriendRequest).where(FriendRequest.id == request_id))).scalar_one_or_none()
    if not req or req.recipient_id != user["sub"] or req.status != "pending":
        raise HTTPException(status_code=404, detail="好友请求不存在")
    low, high = friendship_pair(req.requester_id, req.recipient_id)
    existing = (await db.execute(
        select(Friendship).where(Friendship.user_low_id == low, Friendship.user_high_id == high)
    )).scalar_one_or_none()
    if not existing:
        db.add(Friendship(user_low_id=low, user_high_id=high))
    req.status = "accepted"
    req.responded_at = datetime.utcnow()
    await db.commit()
    return {"status": "accepted", "friend_id": req.requester_id}


@router.post("/friend-requests/{request_id}/reject")
async def reject_friend_request(
    request_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = (await db.execute(select(FriendRequest).where(FriendRequest.id == request_id))).scalar_one_or_none()
    if not req or req.recipient_id != user["sub"] or req.status != "pending":
        raise HTTPException(status_code=404, detail="好友请求不存在")
    req.status = "rejected"
    req.responded_at = datetime.utcnow()
    await db.commit()
    return {"status": "rejected", "request_id": request_id}


@router.delete("/my/agents/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(db, agent_id, user["sub"])

    answer_count = (await db.execute(
        select(func.count(Answer.id)).where(Answer.agent_id == agent_id)
    )).scalar() or 0
    if answer_count:
        raise HTTPException(
            status_code=409,
            detail="已有回答历史的 Agent 暂不能删除，请先设为不公开或撤销 Connector。",
        )

    old = await db.execute(select(Connector).where(Connector.agent_id == agent_id))
    for c in old.scalars().all():
        await db.delete(c)

    try:
        from ws.hub import hub
        await hub.disconnect_agent(agent_id, reason="deleted")
    except Exception:
        pass

    await db.delete(agent)
    await db.commit()
    return Response(status_code=204)


@router.post("/my/agents/{agent_id}/connector", status_code=201)
async def create_connector(
    agent_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a one-time-revealed connector token. The plaintext is returned
    here and never again — only its bcrypt hash is stored.
    """
    agent = await _get_owned_agent(db, agent_id, user["sub"])

    # Revoke existing connectors for this agent
    old = await db.execute(select(Connector).where(Connector.agent_id == agent_id))
    for c in old.scalars().all():
        await db.delete(c)

    plain_token = "conn_sk_" + secrets.token_urlsafe(24)
    conn = Connector(agent_id=agent_id, token_hash=hash_token(plain_token))
    db.add(conn)
    set_agent_readiness(agent, "unverified")
    await db.commit()
    await db.refresh(conn)

    return {
        "connector_id": conn.id,
        "token": plain_token,           # only shown once
        "created_at": conn.created_at.isoformat(),
    }


@router.delete("/my/agents/{agent_id}/connector", status_code=204)
async def revoke_connector(
    agent_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(db, agent_id, user["sub"])
    old = await db.execute(select(Connector).where(Connector.agent_id == agent_id))
    for c in old.scalars().all():
        await db.delete(c)
    agent.status = "offline"
    set_agent_readiness(agent, "unverified")
    await db.commit()
    return Response(status_code=204)


@router.post("/my/agents/{agent_id}/readiness-check")
async def readiness_check(
    agent_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(db, agent_id, user["sub"])
    if agent.status != "online":
        readiness = set_agent_readiness(agent, "error", error="Agent 当前离线，无法检测")
        await db.commit()
        return {"readiness": readiness, "delivered": False}

    try:
        from ws.hub import hub
        delivered = await hub.push_readiness_probe(agent_id)
    except Exception:
        delivered = False

    await db.refresh(agent)
    return {"readiness": get_agent_readiness(agent), "delivered": delivered}


@router.put("/my/agents/{agent_id}/quota")
async def update_quota(
    agent_id: str,
    config: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(db, agent_id, user["sub"])
    # Sanitise: only allow known keys
    allowed = {"max", "auto_threshold", "emergency_reserve"}
    sanitized = {k: int(v) for k, v in config.items() if k in allowed}
    if sanitized:
        agent.daily_quota_config = {**(agent.daily_quota_config or {}), **sanitized}
    await db.commit()
    return {"quota": agent.daily_quota_config}


# ═══════════════════════════════════════════════════
# Review queue (manual approval path)
# ═══════════════════════════════════════════════════

@router.get("/my/agents/{agent_id}/review-queue")
async def review_queue(
    agent_id: str,
    status: str = "draft",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_agent(db, agent_id, user["sub"])
    from models import Question
    rows = (await db.execute(
        select(Answer, Question.title, Question.body, Question.tags,
               Question.deadline_at, User.nickname, User.trust_level)
        .join(Question, Answer.question_id == Question.id)
        .join(User, Question.asker_id == User.id)
        .where(Answer.agent_id == agent_id, Answer.status == status)
        .order_by(Answer.created_at.desc())
    )).all()

    return {
        "data": [
            {
                "request_id": ans.request_id,
                "answer_id": ans.id,
                "question": {"title": q_title, "body": q_body, "tags": list(q_tags or [])},
                "asker": {"nickname": asker_name, "trust_level": asker_tl},
                "content": ans.content or {},
                "model": ans.model,
                "usage": ans.usage or {},
                "capability": ans.capability or {},
                "created_at": ans.created_at.isoformat(),
                "deadline_at": q_deadline.isoformat() if q_deadline else None,
            }
            for ans, q_title, q_body, q_tags, q_deadline, asker_name, asker_tl in rows
        ],
    }


@router.post("/my/agents/{agent_id}/review-queue/{request_id}/approve", status_code=204)
async def approve_review_item(
    agent_id: str, request_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_agent(db, agent_id, user["sub"])
    answer = (await db.execute(
        select(Answer).where(
            Answer.request_id == request_id,
            Answer.agent_id == agent_id,
            Answer.status == "draft",
        )
    )).scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="待审核回答不存在或已处理")
    await approve_answer_by_id(db, answer)
    return Response(status_code=204)


@router.post("/my/agents/{agent_id}/review-queue/{request_id}/reject", status_code=204)
async def reject_review_item(
    agent_id: str, request_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_agent(db, agent_id, user["sub"])
    answer = (await db.execute(
        select(Answer).where(
            Answer.request_id == request_id,
            Answer.agent_id == agent_id,
            Answer.status == "draft",
        )
    )).scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="待审核回答不存在或已处理")
    await reject_answer_by_id(db, answer)
    return Response(status_code=204)


# ═══════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════

async def _get_owned_agent(db: AsyncSession, agent_id: str, user_id: str) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    if agent.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权操作")
    return agent


def _agent_to_dict(
    agent: Agent,
    owner_nickname: str,
    include_owner_id: bool = False,
    full: bool = False,
    relationship: dict | None = None,
) -> dict:
    out = {
        "id": agent.id,
        "name": agent.name,
        "agent_type": agent.agent_type,
        "tags": list(agent.tags or []),
        "description": agent.description,
        "repute_score": float(agent.repute_score or 0),
        "fuel_earned": int(agent.fuel_earned or 0),
        "total_answers": int(agent.total_answers or 0),
        "approval_rate": float(agent.approval_rate or 0),
        "status": agent.status,
        "is_public": agent.is_public,
        "visibility": normalize_visibility(getattr(agent, "visibility", None)),
        "service_mode": normalize_service_mode(getattr(agent, "service_mode", None)),
        "service_rules": normalize_service_rules(getattr(agent, "service_rules", None)),
        "owner": {"nickname": owner_nickname},
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "capability_profile": normalize_capability_profile((agent.review_rules or {}).get("capability_profile")),
        "learned_profile": get_agent_learned_profile(agent),
        "readiness": get_agent_readiness(agent),
    }
    if full:
        out["daily_quota_config"] = agent.daily_quota_config
        out["review_rules"] = agent.review_rules
        out["last_seen_at"] = agent.last_seen_at.isoformat() if agent.last_seen_at else None
    if include_owner_id:
        out["owner"]["id"] = agent.user_id
    if relationship is not None:
        out["relationship"] = relationship
    return out


def merge_capability_profile(review_rules: dict | None, capability_profile: dict | None) -> dict:
    rules = dict(review_rules or {"auto_trust_level": 2, "auto_tag_match": True})
    if "auto_trust_level" not in rules:
        rules["auto_trust_level"] = 2
    if "auto_tag_match" not in rules:
        rules["auto_tag_match"] = True
    rules["capability_profile"] = normalize_capability_profile(capability_profile)
    return rules


async def _relationship_owner_sets(db: AsyncSession, user_id: str) -> tuple[set[str], set[str]]:
    followed_rows = await db.execute(select(UserFollow.followed_id).where(UserFollow.follower_id == user_id))
    followed_owner_ids = set(followed_rows.scalars().all())
    friend_rows = await db.execute(
        select(Friendship).where(
            (Friendship.user_low_id == user_id) | (Friendship.user_high_id == user_id)
        )
    )
    friend_owner_ids: set[str] = set()
    for item in friend_rows.scalars().all():
        friend_owner_ids.add(item.user_high_id if item.user_low_id == user_id else item.user_low_id)
    return followed_owner_ids, friend_owner_ids


async def _relationship_context(db: AsyncSession, viewer_id: str, agent: Agent) -> dict:
    owner_id = agent.user_id
    if viewer_id == owner_id:
        return {
            "is_owner": True,
            "following_owner": False,
            "subscribed": False,
            "friendship_status": "self",
            "friend_request_id": None,
        }

    following = (await db.execute(
        select(UserFollow).where(UserFollow.follower_id == viewer_id, UserFollow.followed_id == owner_id)
    )).scalar_one_or_none()
    subscription = (await db.execute(
        select(AgentSubscription).where(
            AgentSubscription.subscriber_id == viewer_id,
            AgentSubscription.agent_id == agent.id,
        )
    )).scalar_one_or_none()
    low, high = friendship_pair(viewer_id, owner_id)
    friendship = (await db.execute(
        select(Friendship).where(Friendship.user_low_id == low, Friendship.user_high_id == high)
    )).scalar_one_or_none()
    pending_request = None
    friendship_status = "none"
    if friendship:
        friendship_status = "accepted"
    else:
        pending_request = (await db.execute(
            select(FriendRequest).where(
                ((FriendRequest.requester_id == viewer_id) & (FriendRequest.recipient_id == owner_id))
                | ((FriendRequest.requester_id == owner_id) & (FriendRequest.recipient_id == viewer_id)),
                FriendRequest.status == "pending",
            )
        )).scalar_one_or_none()
        if pending_request:
            friendship_status = "pending_outgoing" if pending_request.requester_id == viewer_id else "pending_incoming"

    return {
        "is_owner": False,
        "following_owner": bool(following),
        "subscribed": bool(subscription),
        "friendship_status": friendship_status,
        "friend_request_id": pending_request.id if pending_request else None,
    }
