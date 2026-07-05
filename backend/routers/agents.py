"""Agent CRUD, connector token management, and review-queue endpoints.

Review-queue endpoints (approve/reject) check `agent.user_id == current_user`
to prevent users from approving each other's agents.
"""
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Agent, AgentSubscription, Connector, FriendRequest, Friendship, User, UserFollow, Answer, Question
from models.relationship import friendship_pair
from services.auth import decode_token, get_current_user, hash_token
from services.agent_readiness import get_agent_readiness, set_agent_readiness
from services.agent_service_rules import can_view_agent, normalize_service_mode, normalize_service_rules, normalize_visibility
from services.learned_profile import get_agent_health_summary, get_agent_learned_profile, get_owner_supplement_summary
from services.matching import normalize_capability_profile
from services.review import approve_answer_by_id, reject_answer_by_id
from services.notification import maybe_create_notification
from services.service_limits import agent_service_status

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


class LearnedProfileReviewReq(BaseModel):
    accept: dict[str, list[str]] = {}
    reject: dict[str, list[str]] = {}


# ═══════════════════════════════════════════════════
# Public endpoints
# ═══════════════════════════════════════════════════

def get_optional_user(request: Request) -> dict | None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = decode_token(auth[len("Bearer "):])
    if not payload or payload.get("type") != "access":
        return None
    return payload


@router.get("/agents")
async def list_agents(
    tag: str | None = None,
    q: str | None = None,
    sort: str = "repute",
    page: int = 1,
    size: int = 20,
    viewer: dict | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """List agents visible to the viewer (online + offline; status returned for UI)."""
    offset = (page - 1) * size

    base = select(Agent, User.nickname).join(User, Agent.user_id == User.id)
    if tag:
        base = base.where(Agent.tags.any(tag))

    order_map = {
        "repute": Agent.repute_score.desc(),
        "answers": Agent.total_answers.desc(),
        "latest": Agent.created_at.desc(),
    }
    base = base.order_by(order_map.get(sort, order_map["repute"]))

    result = await db.execute(base)
    rows = result.all()
    if viewer:
        followed_owner_ids, friend_owner_ids = await _relationship_owner_sets(db, viewer["sub"])
    else:
        followed_owner_ids, friend_owner_ids = set(), set()
    visible_rows = [
        (agent, nickname)
        for agent, nickname in rows
        if can_view_agent(
            agent,
            viewer_id=viewer["sub"] if viewer else None,
            followed_owner_ids=followed_owner_ids,
            friend_owner_ids=friend_owner_ids,
        )
    ]
    keyword = (q or "").strip().lower()
    if keyword:
        visible_rows = [
            (agent, nickname)
            for agent, nickname in visible_rows
            if keyword in _agent_search_text(agent, nickname)
        ]
    total = len(visible_rows)
    paged_rows = visible_rows[offset:offset + size]

    service_statuses = {
        agent.id: await agent_service_status(db, agent, viewer_id=viewer["sub"] if viewer else None)
        for agent, _ in paged_rows
    }

    return {
        "data": [
            _agent_to_dict(
                a,
                nickname,
                include_owner_id=True,
                service_status=service_statuses.get(a.id),
            )
            for a, nickname in paged_rows
        ],
        "pagination": {"page": page, "size": size, "total": total},
    }


def _agent_search_text(agent: Agent, owner_nickname: str | None = None) -> str:
    parts = [
        getattr(agent, "name", "") or "",
        getattr(agent, "description", "") or "",
        owner_nickname or "",
        " ".join(getattr(agent, "tags", None) or []),
    ]
    profile = getattr(agent, "review_rules", None) or {}
    capability = normalize_capability_profile(profile.get("capability_profile") or {})
    learned = get_agent_learned_profile(agent)
    for values in capability.values():
        parts.extend(values)
    for key in ("domain_tags", "capability_tags", "positive_tags"):
        parts.extend(learned.get(key) or [])
    return " ".join(parts).lower()


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
    service_status = await agent_service_status(db, agent, viewer_id=viewer["sub"] if viewer else None)
    return _agent_to_dict(
        agent,
        nickname,
        include_owner_id=True,
        full=True,
        relationship=relationship,
        service_status=service_status,
    )


@router.get("/users/{user_id}")
async def get_user_profile(
    user_id: str,
    viewer: dict | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    profile_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not profile_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    followed_owner_ids, friend_owner_ids = await _relationship_owner_sets(db, viewer["sub"]) if viewer else (set(), set())
    if not _can_view_user_profile(profile_user, viewer["sub"] if viewer else None, followed_owner_ids, friend_owner_ids):
        raise HTTPException(status_code=404, detail="用户不存在")

    relationship = await _user_relationship_context(db, viewer["sub"], profile_user.id) if viewer else None
    agent_rows = (await db.execute(
        select(Agent).where(Agent.user_id == user_id).order_by(Agent.created_at.desc())
    )).scalars().all()
    visible_agents = [
        agent for agent in agent_rows
        if can_view_agent(
            agent,
            viewer_id=viewer["sub"] if viewer else None,
            followed_owner_ids=followed_owner_ids,
            friend_owner_ids=friend_owner_ids,
        )
    ]

    return {
        "user": _public_user_profile(profile_user, relationship=relationship),
        "agents": [_agent_to_dict(agent, profile_user.nickname, include_owner_id=True) for agent in visible_agents],
    }


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


@router.get("/my/social")
async def my_social(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = user["sub"]
    incoming = (await db.execute(
        select(FriendRequest, User.nickname, User.repute_score)
        .join(User, FriendRequest.requester_id == User.id)
        .where(FriendRequest.recipient_id == user_id, FriendRequest.status == "pending")
        .order_by(FriendRequest.created_at.desc())
    )).all()
    outgoing = (await db.execute(
        select(FriendRequest, User.nickname, User.repute_score)
        .join(User, FriendRequest.recipient_id == User.id)
        .where(FriendRequest.requester_id == user_id, FriendRequest.status == "pending")
        .order_by(FriendRequest.created_at.desc())
    )).all()
    friend_rows = (await db.execute(
        select(
            Friendship,
            User.id,
            User.nickname,
            User.repute_score,
        )
        .join(
            User,
            User.id == case(
                (Friendship.user_low_id == user_id, Friendship.user_high_id),
                else_=Friendship.user_low_id,
            ),
        )
        .where((Friendship.user_low_id == user_id) | (Friendship.user_high_id == user_id))
        .order_by(Friendship.created_at.desc())
    )).all()
    following_rows = (await db.execute(
        select(UserFollow, User.nickname, User.repute_score)
        .join(User, UserFollow.followed_id == User.id)
        .where(UserFollow.follower_id == user_id)
        .order_by(UserFollow.created_at.desc())
    )).all()
    subscription_rows = (await db.execute(
        select(AgentSubscription, Agent, User.nickname)
        .join(Agent, AgentSubscription.agent_id == Agent.id)
        .join(User, Agent.user_id == User.id)
        .where(AgentSubscription.subscriber_id == user_id)
        .order_by(AgentSubscription.created_at.desc())
    )).all()

    return {
        "incoming_friend_requests": [
            _friend_request_to_dict(req, requester_id=req.requester_id, nickname=nickname, repute_score=repute)
            for req, nickname, repute in incoming
        ],
        "outgoing_friend_requests": [
            _friend_request_to_dict(req, requester_id=req.recipient_id, nickname=nickname, repute_score=repute)
            for req, nickname, repute in outgoing
        ],
        "friends": [
            {
                "id": friendship.id,
                "user": {"id": friend_id, "nickname": nickname, "repute_score": float(repute or 0)},
                "created_at": friendship.created_at.isoformat() if friendship.created_at else None,
            }
            for friendship, friend_id, nickname, repute in friend_rows
        ],
        "following_users": [
            {
                "id": follow.id,
                "user": {"id": follow.followed_id, "nickname": nickname, "repute_score": float(repute or 0)},
                "created_at": follow.created_at.isoformat() if follow.created_at else None,
            }
            for follow, nickname, repute in following_rows
        ],
        "agent_subscriptions": [
            {
                "id": subscription.id,
                "agent": _agent_to_dict(agent, owner_nickname),
                "created_at": subscription.created_at.isoformat() if subscription.created_at else None,
            }
            for subscription, agent, owner_nickname in subscription_rows
        ],
    }


@router.post("/my/agents", status_code=201)
async def create_agent(
    req: CreateAgentReq,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.agent_type not in ("openclaw", "hermes"):
        raise HTTPException(status_code=400, detail="agent_type 必须是 openclaw 或 hermes")
    owner = (await db.execute(select(User).where(User.id == user["sub"]))).scalar_one_or_none()
    default_visibility = getattr(owner, "default_agent_visibility", None) if owner else user.get("default_agent_visibility")
    default_service_mode = getattr(owner, "default_agent_service_mode", None) if owner else user.get("default_agent_service_mode")
    default_service_rules = getattr(owner, "default_agent_service_rules", None) if owner else user.get("default_agent_service_rules")
    requested_visibility = req.visibility if req.visibility != "public" else default_visibility or req.visibility
    visibility = normalize_visibility(requested_visibility if req.is_public else "archived")
    agent = Agent(
        user_id=user["sub"],
        name=req.name,
        agent_type=req.agent_type,
        tags=req.tags,
        description=req.description,
        is_public=visibility == "public",
        visibility=visibility,
        service_mode=normalize_service_mode(req.service_mode if req.service_mode != "auto_match" else default_service_mode or req.service_mode),
        service_rules=normalize_service_rules(req.service_rules or default_service_rules),
        review_rules=merge_capability_profile(None, req.capability_profile),
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return _agent_to_dict(agent, user.get("nickname", ""), include_owner_id=True, full=True)


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


@router.post("/my/agents/{agent_id}/learned-profile-review")
async def review_learned_profile_tags(
    agent_id: str,
    req: LearnedProfileReviewReq,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_owned_agent(db, agent_id, user["sub"])
    agent.review_rules = apply_learned_profile_review(agent.review_rules, req.accept, req.reject)
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
        if agent.user_id != user["sub"]:
            agent_name = getattr(agent, "name", None) or "Agent"
            await maybe_create_notification(
                db,
                agent.user_id,
                "agent_subscribed",
                "agent_subscribed",
                f"{agent_name} 有了新的订阅者",
                f"{user.get('nickname', '有人')} 订阅了你的 Agent",
                ref_id=agent.id,
            )
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
    await db.flush()
    await maybe_create_notification(
        db,
        target_user_id,
        "friend_request",
        "friend_request",
        "新的好友申请",
        f"{user.get('nickname', '有人')} 请求添加你为好友",
        ref_id=req.id,
    )
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
    await maybe_create_notification(
        db,
        req.requester_id,
        "friend_request",
        "friend_request_accepted",
        "好友申请已通过",
        f"{user.get('nickname', '对方')} 已通过你的好友申请",
        ref_id=req.id,
    )
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
    await maybe_create_notification(
        db,
        req.requester_id,
        "friend_request",
        "friend_request_rejected",
        "好友申请已拒绝",
        f"{user.get('nickname', '对方')} 已拒绝你的好友申请",
        ref_id=req.id,
    )
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
    service_status: dict | None = None,
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
        "learned_profile_review": build_learned_profile_review(agent.review_rules),
        "owner_supplement_summary": get_owner_supplement_summary(agent),
        "health_summary": get_agent_health_summary(agent),
        "readiness": get_agent_readiness(agent),
        "service_status": service_status,
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


LEARNED_REVIEW_FIELDS = ("domain_tags", "capability_tags", "tool_tags", "style_tags", "positive_tags", "negative_tags")


def build_learned_profile_review(review_rules: dict | None) -> dict:
    rules = dict(review_rules or {})
    learned = get_agent_learned_profile(rules)
    review = normalize_learned_profile_review(rules.get("learned_profile_review"))
    pending: dict[str, list[str]] = {}
    for field in LEARNED_REVIEW_FIELDS:
        reviewed = set(review["accepted"].get(field, [])) | set(review["rejected"].get(field, []))
        pending[field] = [value for value in learned.get(field, []) if value not in reviewed]
    return {**review, "pending": pending}


def apply_learned_profile_review(
    review_rules: dict | None,
    accept: dict[str, list[str]],
    reject: dict[str, list[str]],
) -> dict:
    rules = dict(review_rules or {})
    review = normalize_learned_profile_review(rules.get("learned_profile_review"))
    capability_profile = normalize_capability_profile(rules.get("capability_profile"))

    for field, values in (accept or {}).items():
        if field not in LEARNED_REVIEW_FIELDS:
            continue
        review["accepted"][field] = merge_unique(review["accepted"].get(field, []), values)
        review["rejected"][field] = [value for value in review["rejected"].get(field, []) if value not in set(values or [])]
        if field in capability_profile:
            capability_profile[field] = merge_unique(capability_profile.get(field, []), values)
    for field, values in (reject or {}).items():
        if field not in LEARNED_REVIEW_FIELDS:
            continue
        review["rejected"][field] = merge_unique(review["rejected"].get(field, []), values)
        review["accepted"][field] = [value for value in review["accepted"].get(field, []) if value not in set(values or [])]
        if field in capability_profile:
            capability_profile[field] = [value for value in capability_profile.get(field, []) if value not in set(values or [])]

    rules["learned_profile_review"] = review
    rules["capability_profile"] = capability_profile
    return rules


def normalize_learned_profile_review(value: dict | None) -> dict[str, dict[str, list[str]]]:
    raw = value if isinstance(value, dict) else {}
    return {
        "accepted": normalize_review_groups(raw.get("accepted")),
        "rejected": normalize_review_groups(raw.get("rejected")),
    }


def normalize_review_groups(value: dict | None) -> dict[str, list[str]]:
    raw = value if isinstance(value, dict) else {}
    return {field: merge_unique([], raw.get(field, [])) for field in LEARNED_REVIEW_FIELDS}


def merge_unique(current: list[str], values: list[str] | None) -> list[str]:
    seen = {str(item).lower() for item in current or []}
    out = list(current or [])
    for item in values or []:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _friend_request_to_dict(req: FriendRequest, requester_id: str, nickname: str, repute_score) -> dict:
    return {
        "id": req.id,
        "status": req.status,
        "user": {"id": requester_id, "nickname": nickname, "repute_score": float(repute_score or 0)},
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }


def _public_user_profile(user: User, relationship: dict | None = None) -> dict:
    out = {
        "id": user.id,
        "nickname": user.nickname,
        "avatar_url": getattr(user, "avatar_url", "") or "",
        "headline": getattr(user, "headline", "") or "",
        "bio": getattr(user, "bio", "") or "",
        "profile_tags": list(getattr(user, "profile_tags", None) or []),
        "experience_tags": list(getattr(user, "experience_tags", None) or []),
        "links": dict(getattr(user, "links", None) or {}),
        "profile_visibility": normalize_visibility(getattr(user, "profile_visibility", None)),
        "trust_level": int(getattr(user, "trust_level", 1) or 1),
        "fuel_balance": int(getattr(user, "fuel_balance", 0) or 0),
        "repute_score": float(getattr(user, "repute_score", 0) or 0),
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
    }
    if relationship is not None:
        out["relationship"] = relationship
    return out


def _can_view_user_profile(user: User, viewer_id: str | None, followed_owner_ids: set[str], friend_owner_ids: set[str]) -> bool:
    visibility = normalize_visibility(getattr(user, "profile_visibility", None))
    if viewer_id and viewer_id == user.id:
        return True
    if visibility == "archived":
        return False
    if visibility == "public":
        return True
    if visibility == "followers":
        return user.id in followed_owner_ids
    if visibility == "friends":
        return user.id in friend_owner_ids
    return False


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


async def _user_relationship_context(db: AsyncSession, viewer_id: str, owner_id: str) -> dict:
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
        "subscribed": False,
        "friendship_status": friendship_status,
        "friend_request_id": pending_request.id if pending_request else None,
    }
