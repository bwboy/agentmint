"""Agent CRUD, connector token management, and review-queue endpoints.

Review-queue endpoints (approve/reject) check `agent.user_id == current_user`
to prevent users from approving each other's agents.
"""
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Agent, Connector, User, Answer, Question
from services.auth import get_current_user, hash_token
from services.review import approve_answer_by_id, reject_answer_by_id

router = APIRouter(prefix="/api", tags=["agents"])


class CreateAgentReq(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    agent_type: str  # openclaw | hermes
    tags: list[str] = []
    description: str = ""
    is_public: bool = True


class UpdateAgentReq(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    description: str | None = None
    is_public: bool | None = None
    daily_quota_config: dict | None = None
    review_rules: dict | None = None


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

    base = select(Agent, User.nickname).join(User, Agent.user_id == User.id).where(Agent.is_public == True)
    count_base = select(func.count(Agent.id)).where(Agent.is_public == True)
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


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Agent, User.nickname).join(User, Agent.user_id == User.id).where(Agent.id == agent_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    agent, nickname = row
    return _agent_to_dict(agent, nickname, include_owner_id=False, full=True)


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
    agent = Agent(
        user_id=user["sub"],
        name=req.name,
        agent_type=req.agent_type,
        tags=req.tags,
        description=req.description,
        is_public=req.is_public,
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
    if req.daily_quota_config is not None: agent.daily_quota_config = req.daily_quota_config
    if req.review_rules is not None: agent.review_rules = req.review_rules

    await db.commit()
    await db.refresh(agent)
    return _agent_to_dict(agent, user.get("nickname", ""), full=True)


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
    await db.commit()
    return Response(status_code=204)


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


def _agent_to_dict(agent: Agent, owner_nickname: str, include_owner_id: bool = False, full: bool = False) -> dict:
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
        "owner": {"nickname": owner_nickname},
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }
    if full:
        out["daily_quota_config"] = agent.daily_quota_config
        out["review_rules"] = agent.review_rules
        out["last_seen_at"] = agent.last_seen_at.isoformat() if agent.last_seen_at else None
    return out
