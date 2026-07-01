"""Question endpoints — publish, list, detail, feedback.

The publish flow is the heart of the platform:
    asker → matching engine → push to live connectors → connector replies →
    review service approves → asker sees the answer.

Fuel cost is debited from the asker's balance up-front based on the matched
agent count; agents earn fuel per-answer (agent.fuel_earned) on approval.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Question, Answer, Feedback, Agent, User
from services.auth import get_current_user
from services.billing import deduct_fuel_if_available, refund_fuel
from services.followups import (
    build_conversation_id,
    build_followup_payload,
    build_root_payload,
    ensure_followup_targets,
    mark_answer_pushed_if_assigned,
)
from services.matching import build_match_explanation, build_task_profile, match_agents
from services.review import decide_review_method, approve_answer_by_id, reject_answer_by_id
from services.quota import increment_usage
from services.notification import create_notification
from services.learned_profile import update_learned_profile_from_feedback
from ws.hub import hub

router = APIRouter(prefix="/api", tags=["questions"])

AVG_TOKENS_PER_ANSWER = 2000
EMERGENCY_FUEL_MULTIPLIER = 3


class CreateQuestionReq(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    tags: list[str] = []
    deadline_minutes: int = 30
    max_responders: int = 5
    is_emergency: bool = False


class CreateFollowUpReq(BaseModel):
    quoted_answer_id: str = Field(min_length=1)
    agent_ids: list[str] = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4000)
    deadline_minutes: int = 30


class FeedbackReq(BaseModel):
    vote: str  # up | down
    comment: str = ""


# ═══════════════════════════════════════════════════
# Public
# ═══════════════════════════════════════════════════

@router.get("/questions")
async def list_questions(
    tag: str | None = None,
    sort: str = "latest",
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size

    base = select(Question, User.nickname, User.trust_level).join(User, Question.asker_id == User.id)
    count_q = select(func.count(Question.id))
    if tag:
        base = base.where(Question.tags.any(tag))
        count_q = count_q.where(Question.tags.any(tag))

    base = base.order_by(Question.created_at.desc()).offset(offset).limit(size)
    rows = (await db.execute(base)).all()
    total = (await db.execute(count_q)).scalar() or 0

    # Compute answer_count per question via a single grouped query
    q_ids = [q.id for q, *_ in rows]
    ans_counts: dict[str, int] = {}
    if q_ids:
        ans_rows = await db.execute(
            select(Answer.question_id, func.count(Answer.id))
            .where(Answer.question_id.in_(q_ids), Answer.status == "approved")
            .group_by(Answer.question_id)
        )
        ans_counts = {qid: c for qid, c in ans_rows.all()}

    return {
        "data": [
            {
                "id": q.id, "title": q.title, "body": q.body, "tags": list(q.tags or []),
                "asker": {"nickname": nickname, "trust_level": tl},
                "deadline_at": q.deadline_at.isoformat(),
                "max_responders": q.max_responders,
                "matched_count": len(q.matched_agent_ids or []),
                "answer_count": ans_counts.get(q.id, 0),
                "status": q.status,
                "fuel_cost": int(q.fuel_cost or 0),
                "created_at": q.created_at.isoformat(),
            }
            for q, nickname, tl in rows
        ],
        "pagination": {"page": page, "size": size, "total": total},
    }


@router.get("/questions/{question_id}")
async def get_question(question_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(Question, User.nickname, User.trust_level)
        .join(User, Question.asker_id == User.id)
        .where(Question.id == question_id)
    )).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="问题不存在")
    q, nickname, tl = row

    # Approved answers, with agent info
    ans_rows = (await db.execute(
        select(Answer, Agent.name, Agent.agent_type, Agent.repute_score)
        .join(Agent, Answer.agent_id == Agent.id)
        .where(Answer.question_id == question_id, Answer.status == "approved")
        .order_by(Answer.created_at.asc())
    )).all()

    # Vote summary per answer
    ans_ids = [a.id for a, *_ in ans_rows]
    vote_rows: dict[str, dict[str, int]] = {}
    if ans_ids:
        rows = await db.execute(
            select(Feedback.answer_id, Feedback.vote, func.count(Feedback.id))
            .where(Feedback.answer_id.in_(ans_ids))
            .group_by(Feedback.answer_id, Feedback.vote)
        )
        for aid, vote, c in rows.all():
            vote_rows.setdefault(aid, {"up": 0, "down": 0})[vote] = c

    return {
        "id": q.id, "title": q.title, "body": q.body, "tags": list(q.tags or []),
        "asker": {"nickname": nickname, "trust_level": tl},
        "deadline_at": q.deadline_at.isoformat(),
        "max_responders": q.max_responders,
        "matched_count": len(q.matched_agent_ids or []),
        "fuel_cost": int(q.fuel_cost or 0),
        "status": q.status,
        "created_at": q.created_at.isoformat(),
        "task_profile": build_task_profile(q.title, q.body, list(q.tags or []), q.max_responders),
        "match_explanations": await build_question_match_explanations(db, q),
        "answers": [
            {
                "id": ans.id, "question_id": ans.question_id,
                "agent": {"id": ans.agent_id, "name": a_name, "agent_type": a_type,
                          "repute_score": float(a_repute or 0)},
                "request_id": ans.request_id,
                "content": ans.content or {},
                "model": ans.model,
                "usage": ans.usage or {},
                "capability": ans.capability or None,
                "status": ans.status, "review_method": ans.review_method,
                "vote_summary": vote_rows.get(ans.id, {"up": 0, "down": 0}),
                "created_at": ans.created_at.isoformat(),
            }
            for ans, a_name, a_type, a_repute in ans_rows
        ],
    }


# ═══════════════════════════════════════════════════
# Protected
# ═══════════════════════════════════════════════════

@router.post("/questions", status_code=201)
async def create_question(
    req: CreateQuestionReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run matching, deduct fuel, write Question + assigned Answers, push to connectors."""
    user_result = await db.execute(select(User).where(User.id == user_payload["sub"]))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    deadline = datetime.utcnow() + timedelta(minutes=max(1, req.deadline_minutes))

    # Matching (already filters offline / blocked, returns quota_state per agent)
    matched = await match_agents(
        db,
        req.tags,
        max_responders=max(1, req.max_responders),
        title=req.title,
        body=req.body,
    )
    task_profile = build_task_profile(req.title, req.body, req.tags, req.max_responders)
    match_explanations = [
        build_match_explanation(agent, task_profile, score, match_type, quota_state)
        for agent, score, match_type, quota_state in matched
    ]

    rate = EMERGENCY_FUEL_MULTIPLIER if req.is_emergency else 1
    max_possible_fuel_cost = len(matched) * AVG_TOKENS_PER_ANSWER * rate

    if not await deduct_fuel_if_available(db, user.id, max_possible_fuel_cost):
        raise HTTPException(status_code=402, detail="燃值不足")

    q = Question(
        asker_id=user.id,
        title=req.title,
        body=req.body,
        tags=req.tags,
        deadline_at=deadline,
        max_responders=req.max_responders,
        matched_agent_ids=[a.id for a, *_ in matched],
        fuel_cost=0,
    )
    db.add(q)
    await db.flush()  # need q.id

    # One Answer row per matched agent (state machine starts at 'assigned')
    answer_records: list[tuple[Answer, Agent, str, str]] = []  # (answer, agent, match_type, quota_state)
    for agent, _score, match_type, quota_state in matched:
        review_method = decide_review_method(
            quota_state=quota_state,
            asker_trust_level=int(user.trust_level or 1),
            review_rules=agent.review_rules,
            match_type=match_type,
        )
        ans = Answer(
            question_id=q.id,
            agent_id=agent.id,
            request_id=f"req_{q.id}_{agent.id}",
            conversation_id=build_conversation_id(q.id, agent.id),
            turn_type="root",
            status="assigned",
            review_method=review_method,
        )
        db.add(ans)
        answer_records.append((ans, agent, match_type, quota_state))

    await db.commit()
    await db.refresh(q)

    # Push to live connectors. Each successful push increments usage and flips
    # the answer row to 'pushed'.
    pushed_count = 0
    for ans, agent, _mt, _qs in answer_records:
        payload = build_root_payload(
            q,
            ans,
            {"nickname": user.nickname, "trust_level": user.trust_level},
        )
        delivered = await hub.push_question(agent.id, payload)
        if delivered:
            pushed_count += 1
            await mark_answer_pushed_if_assigned(db, ans.id)
            try:
                await increment_usage(db, agent.id)
            except Exception as e:
                print(f"[questions] quota increment failed for {agent.id}: {e}")

    fuel_cost = pushed_count * AVG_TOKENS_PER_ANSWER * rate
    q.fuel_cost = fuel_cost
    await refund_fuel(db, user.id, max_possible_fuel_cost - fuel_cost)

    await db.commit()

    return {
        "id": q.id, "title": q.title,
        "estimated_fuel_cost": fuel_cost,
        "fuel_cost": fuel_cost,
        "matched_count": len(matched),
        "pushed_count": pushed_count,
        "task_profile": task_profile,
        "match_explanations": match_explanations,
        "status": q.status,
        "deadline_at": q.deadline_at.isoformat(),
        "created_at": q.created_at.isoformat(),
    }


@router.post("/questions/{question_id}/followups", status_code=201)
async def create_followup(
    question_id: str,
    req: CreateFollowUpReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_payload["sub"]))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    question = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")

    root_id = question.root_question_id or question.id
    root = question if question.id == root_id else (
        await db.execute(select(Question).where(Question.id == root_id))
    ).scalar_one_or_none()
    if not root:
        raise HTTPException(status_code=404, detail="根问题不存在")
    if root.asker_id != user.id:
        raise HTTPException(status_code=403, detail="只有提问者可以追问")

    quoted_answer = (await db.execute(
        select(Answer).where(
            Answer.id == req.quoted_answer_id,
            Answer.question_id == root.id,
            Answer.status == "approved",
        )
    )).scalar_one_or_none()
    if not quoted_answer:
        raise HTTPException(status_code=400, detail="引用回答不存在或尚未发布")

    approved_answers = (await db.execute(
        select(Answer).where(Answer.question_id == root.id, Answer.status == "approved")
    )).scalars().all()
    target_agent_ids = ensure_followup_targets(req.agent_ids, list(approved_answers))

    agents = (await db.execute(select(Agent).where(Agent.id.in_(target_agent_ids)))).scalars().all()
    agent_by_id = {agent.id: agent for agent in agents}
    missing_agents = [agent_id for agent_id in target_agent_ids if agent_id not in agent_by_id]
    if missing_agents:
        raise HTTPException(status_code=400, detail=f"Agent 不存在: {', '.join(missing_agents)}")

    max_possible_fuel_cost = len(target_agent_ids) * AVG_TOKENS_PER_ANSWER
    if not await deduct_fuel_if_available(db, user.id, max_possible_fuel_cost):
        raise HTTPException(status_code=402, detail="燃值不足")

    deadline = datetime.utcnow() + timedelta(minutes=max(1, req.deadline_minutes))
    followup = Question(
        asker_id=user.id,
        title=f"追问：{root.title}",
        body=req.text,
        tags=list(root.tags or []),
        deadline_at=deadline,
        max_responders=len(target_agent_ids),
        matched_agent_ids=target_agent_ids,
        fuel_cost=0,
        root_question_id=root.id,
        parent_question_id=question.id,
        quoted_answer_id=quoted_answer.id,
        turn_type="followup",
    )
    db.add(followup)
    await db.flush()

    answer_records: list[tuple[Answer, Agent]] = []
    for agent_id in target_agent_ids:
        agent = agent_by_id[agent_id]
        review_method = decide_review_method(
            quota_state="ok",
            asker_trust_level=int(user.trust_level or 1),
            review_rules=agent.review_rules,
            match_type="followup",
        )
        answer = Answer(
            question_id=followup.id,
            agent_id=agent.id,
            request_id=f"req_{followup.id}_{agent.id}",
            conversation_id=build_conversation_id(root.id, agent.id),
            parent_answer_id=quoted_answer.id,
            turn_type="followup",
            status="assigned",
            review_method=review_method,
        )
        db.add(answer)
        answer_records.append((answer, agent))

    await db.commit()
    await db.refresh(followup)

    pushed_count = 0
    requests = []
    asker = {"nickname": user.nickname, "trust_level": user.trust_level}
    for answer, agent in answer_records:
        payload = build_followup_payload(
            root_question=root,
            followup_question=followup,
            answer=answer,
            quoted_answer=quoted_answer,
            asker=asker,
        )
        delivered = await hub.push_question(agent.id, payload)
        status = "assigned"
        if delivered:
            pushed_count += 1
            await mark_answer_pushed_if_assigned(db, answer.id)
            status = "pushed"
            try:
                await increment_usage(db, agent.id)
            except Exception as e:
                print(f"[questions] quota increment failed for {agent.id}: {e}")
        requests.append({
            "agent_id": agent.id,
            "request_id": answer.request_id,
            "conversation_id": answer.conversation_id,
            "status": status,
        })

    fuel_cost = pushed_count * AVG_TOKENS_PER_ANSWER
    followup.fuel_cost = fuel_cost
    await refund_fuel(db, user.id, max_possible_fuel_cost - fuel_cost)
    await db.commit()

    return {
        "id": followup.id,
        "root_question_id": root.id,
        "quoted_answer_id": quoted_answer.id,
        "pushed_count": pushed_count,
        "fuel_cost": fuel_cost,
        "requests": requests,
    }


async def build_question_match_explanations(db: AsyncSession, q: Question) -> list[dict]:
    agent_ids = list(q.matched_agent_ids or [])
    if not agent_ids:
        return []

    rows = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
    agents = list(rows.scalars().all())
    agent_by_id = {agent.id: agent for agent in agents}
    answer_rows = await db.execute(
        select(Answer).where(Answer.question_id == q.id, Answer.agent_id.in_(agent_ids))
    )
    answer_by_agent_id = {answer.agent_id: answer for answer in answer_rows.scalars().all()}
    task_profile = build_task_profile(q.title, q.body, list(q.tags or []), q.max_responders)
    explanations: list[dict] = []

    for agent_id in agent_ids:
        agent = agent_by_id.get(agent_id)
        if not agent:
            continue
        agent_tags = set(str(tag).strip().lower() for tag in list(agent.tags or []))
        query_tags = set(str(tag).strip().lower() for tag in list(q.tags or []))
        score = len(agent_tags & query_tags) / max(len(agent_tags), len(query_tags), 1)
        match_type = "exact" if score > 0 else "fallback"
        explanation = build_match_explanation(agent, task_profile, score, match_type, "ok")
        answer = answer_by_agent_id.get(agent_id)
        if answer:
            explanation.update({
                "request_id": answer.request_id,
                "answer_status": answer.status,
                "review_method": answer.review_method,
            })
        explanations.append(explanation)

    return explanations


@router.get("/my/questions")
async def my_questions(
    page: int = 1, size: int = 20,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    rows = (await db.execute(
        select(Question).where(Question.asker_id == user_payload["sub"])
        .order_by(Question.created_at.desc()).offset(offset).limit(size)
    )).scalars().all()
    total = (await db.execute(
        select(func.count(Question.id)).where(Question.asker_id == user_payload["sub"])
    )).scalar() or 0
    return {
        "data": [
            {"id": q.id, "title": q.title, "tags": list(q.tags or []), "status": q.status,
             "fuel_cost": int(q.fuel_cost or 0), "deadline_at": q.deadline_at.isoformat(),
             "matched_count": len(q.matched_agent_ids or []),
             "created_at": q.created_at.isoformat()}
            for q in rows
        ],
        "pagination": {"page": page, "size": size, "total": total},
    }


@router.post("/questions/{question_id}/answers/{answer_id}/feedback", status_code=201)
async def submit_feedback(
    question_id: str, answer_id: str, req: FeedbackReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.vote not in ("up", "down"):
        raise HTTPException(status_code=400, detail="vote 必须是 up 或 down")

    answer = (await db.execute(
        select(Answer).where(Answer.id == answer_id, Answer.question_id == question_id)
    )).scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="回答不存在")
    if answer.status != "approved":
        raise HTTPException(status_code=400, detail="回答未发布，无法反馈")

    existing = (await db.execute(
        select(Feedback).where(Feedback.answer_id == answer_id, Feedback.voter_id == user_payload["sub"])
    )).scalar_one_or_none()

    prev_vote = existing.vote if existing else None
    if existing:
        existing.vote = req.vote
        existing.comment = req.comment
        fb = existing
    else:
        fb = Feedback(answer_id=answer_id, voter_id=user_payload["sub"], vote=req.vote, comment=req.comment)
        db.add(fb)

    # Repute delta: +1 for up, -0.2 for down. If switching, reverse prior delta.
    delta = (1.0 if req.vote == "up" else -0.2)
    if prev_vote and prev_vote != req.vote:
        delta -= (1.0 if prev_vote == "up" else -0.2)
    agent = (await db.execute(select(Agent).where(Agent.id == answer.agent_id))).scalar_one_or_none()
    if agent:
        new_score = max(0.0, min(5.0, float(agent.repute_score or 0) + delta))
        agent.repute_score = round(new_score, 1)
        question = (await db.execute(select(Question).where(Question.id == answer.question_id))).scalar_one_or_none()
        if question:
            update_learned_profile_from_feedback(agent, question, req.vote, previous_vote=prev_vote)

    await db.commit()
    return {"id": fb.id, "vote": fb.vote, "created_at": fb.created_at.isoformat()}
