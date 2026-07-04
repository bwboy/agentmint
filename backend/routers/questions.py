"""Question endpoints — publish, list, detail, feedback.

The publish flow is the heart of the platform:
    asker → matching engine → push to live connectors → connector replies →
    review service approves → asker sees the answer.

Fuel cost is debited from the asker's balance up-front based on the matched
agent count; agents earn fuel per-answer (agent.fuel_earned) on approval.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AnswerOwnerSupplement, Question, Answer, Feedback, Agent, User
from services.agent_service_rules import can_view_agent, normalize_service_mode, normalize_service_rules
from services.auth import decode_token, get_current_user
from services.billing import deduct_fuel_if_available, record_fuel_ledger, refund_fuel
from services.followups import (
    build_conversation_id,
    build_followup_payload,
    build_root_payload,
    ensure_followup_targets,
    mark_answer_pushed_if_assigned,
    serialize_answer,
    serialize_followup_thread,
)
from services.matching import build_match_explanation, build_task_profile, match_agents
from services.review import decide_review_method, approve_answer_by_id, reject_answer_by_id
from services.rewards import auto_award_due_rewards, award_reward_to_answer
from services.quota import check_quota, increment_usage
from services.notification import maybe_create_notification
from services.learned_profile import (
    normalize_owner_supplement_type,
    update_learned_profile_from_feedback,
    update_learned_profile_from_owner_supplement,
)
from ws.hub import hub

router = APIRouter(prefix="/api", tags=["questions"])

AVG_TOKENS_PER_ANSWER = 2000
DEFAULT_ESTIMATED_FUEL_PER_ANSWER = 900
DEFAULT_BASE_CAP_MULTIPLIER = 1.5
EMERGENCY_FUEL_MULTIPLIER = 3


class CreateQuestionReq(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = ""
    tags: list[str] = []
    deadline_minutes: int = 30
    max_responders: int = 5
    is_emergency: bool = False
    agent_ids: list[str] = []
    visibility: str = "public"
    estimated_fuel_per_answer: int | None = None
    reward_fuel: int = 0


class CreateFollowUpReq(BaseModel):
    quoted_answer_id: str = Field(min_length=1)
    agent_ids: list[str] = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4000)
    deadline_minutes: int = 30


class FeedbackReq(BaseModel):
    vote: str  # up | down
    comment: str = ""


class OwnerSupplementRequestReq(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class OwnerSupplementRespondReq(BaseModel):
    response: str = Field(min_length=1, max_length=4000)
    supplement_type: str = "experience"


class OwnerSupplementSelfReq(BaseModel):
    response: str = Field(min_length=1, max_length=4000)
    supplement_type: str = "experience"


class OwnerSupplementUpdateReq(BaseModel):
    response: str | None = Field(default=None, min_length=1, max_length=4000)
    supplement_type: str | None = None
    is_high_value: bool | None = None


class OwnerSupplementReactionReq(BaseModel):
    reaction: str = Field(pattern="^(like|neutral)$")
    accepted: bool = False


class AgentAnswerBatchMarkReq(BaseModel):
    answer_ids: list[str] = Field(min_length=1, max_length=100)
    mark: str = Field(pattern="^(excellent|needs_improvement|stale|none)$")


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

    base = (
        select(Question, User.nickname, User.trust_level)
        .join(User, Question.asker_id == User.id)
        .where(Question.root_question_id.is_(None), Question.visibility == "public")
    )
    count_q = select(func.count(Question.id)).where(Question.root_question_id.is_(None), Question.visibility == "public")
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
            question_public_payload(q, nickname, tl, answer_count=ans_counts.get(q.id, 0))
            for q, nickname, tl in rows
        ],
        "pagination": {"page": page, "size": size, "total": total},
    }


@router.get("/questions/fuel-estimate")
async def question_fuel_estimate(db: AsyncSession = Depends(get_db)):
    estimated = await estimate_answer_fuel_per_answer(db)
    return {
        "estimated_fuel_per_answer": estimated,
        "base_cap_multiplier": DEFAULT_BASE_CAP_MULTIPLIER,
        "preauthorized_fuel_per_answer": preauthorize_base_fuel_per_answer(estimated),
        "sample_window_days": 2,
    }


def get_optional_user(request: Request) -> dict | None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = decode_token(auth[len("Bearer "):])
    if not payload or payload.get("type") != "access":
        return None
    return payload


@router.get("/questions/{question_id}")
async def get_question(
    question_id: str,
    viewer: dict | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(
        select(Question, User.nickname, User.trust_level)
        .join(User, Question.asker_id == User.id)
        .where(Question.id == question_id)
    )).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="问题不存在")
    q, nickname, tl = row
    if q.root_question_id:
        root_row = (await db.execute(
            select(Question, User.nickname, User.trust_level)
            .join(User, Question.asker_id == User.id)
            .where(Question.id == q.root_question_id)
        )).one_or_none()
        if not root_row:
            raise HTTPException(status_code=404, detail="根问题不存在")
        q, nickname, tl = root_row

    if not await can_view_question(db, q, viewer):
        raise HTTPException(status_code=404, detail="问题不存在")

    await auto_award_due_rewards(db, q)

    # Approved answers, with agent info
    ans_rows = (await db.execute(
        select(Answer, Agent.name, Agent.agent_type, Agent.repute_score)
        .join(Agent, Answer.agent_id == Agent.id)
        .where(Answer.question_id == q.id, Answer.status == "approved")
        .order_by(Answer.created_at.asc())
    )).all()

    followups = (await db.execute(
        select(Question)
        .where(Question.root_question_id == q.id, Question.turn_type == "followup")
        .order_by(Question.created_at.asc())
    )).scalars().all()
    followup_ids = [item.id for item in followups]
    followup_answer_rows = []
    if followup_ids:
        followup_answer_rows = (await db.execute(
            select(Answer, Agent.name, Agent.agent_type, Agent.repute_score)
            .join(Agent, Answer.agent_id == Agent.id)
            .where(Answer.question_id.in_(followup_ids), Answer.status == "approved")
            .order_by(Answer.created_at.asc())
        )).all()

    # Vote summary per root and follow-up answer
    ans_ids = [a.id for a, *_ in ans_rows] + [a.id for a, *_ in followup_answer_rows]
    vote_rows: dict[str, dict[str, int]] = {}
    if ans_ids:
        rows = await db.execute(
            select(Feedback.answer_id, Feedback.vote, func.count(Feedback.id))
            .where(Feedback.answer_id.in_(ans_ids))
            .group_by(Feedback.answer_id, Feedback.vote)
        )
        for aid, vote, c in rows.all():
            vote_rows.setdefault(aid, {"up": 0, "down": 0})[vote] = c
    supplement_rows = []
    if ans_ids:
        supplement_rows = (await db.execute(
            select(AnswerOwnerSupplement)
            .where(AnswerOwnerSupplement.answer_id.in_(ans_ids))
            .order_by(AnswerOwnerSupplement.created_at.asc())
        )).scalars().all()
    supplements_by_answer = group_owner_supplements_by_answer(supplement_rows)

    rows_by_question: dict[str, list[tuple]] = {}
    for row in followup_answer_rows:
        answer = row[0]
        rows_by_question.setdefault(answer.question_id, []).append(row)
    followup_threads = [
        serialize_followup_thread(item, rows_by_question.get(item.id, []), vote_rows)
        for item in followups
    ]

    return {
        **question_public_payload(q, nickname, tl),
        "task_profile": build_task_profile(q.title, q.body, list(q.tags or []), q.max_responders),
        "match_explanations": await build_question_match_explanations(db, q),
        "answers": [
            {
                **serialize_answer(ans, a_name, a_type, a_repute, vote_rows.get(ans.id, {"up": 0, "down": 0})),
                "owner_supplements": supplements_by_answer.get(ans.id, []),
            }
            for ans, a_name, a_type, a_repute in ans_rows
        ],
        "followups": attach_owner_supplements_to_followups(followup_threads, supplements_by_answer),
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

    matched = await resolve_question_targets(db, req, user.id)
    task_profile = build_task_profile(req.title, req.body, req.tags, req.max_responders)
    match_explanations = [
        build_match_explanation(agent, task_profile, score, match_type, quota_state)
        for agent, score, match_type, quota_state in matched
    ]

    rate = EMERGENCY_FUEL_MULTIPLIER if req.is_emergency else 1
    estimated_fuel_per_answer = await estimate_answer_fuel_per_answer(db) * rate
    base_reserve_per_answer = preauthorize_base_fuel_per_answer(estimated_fuel_per_answer)
    base_reserve = len(matched) * base_reserve_per_answer
    reward_fuel = normalize_reward_fuel(req.reward_fuel)
    total_reserve = base_reserve + reward_fuel

    if not await deduct_fuel_if_available(db, user.id, total_reserve):
        raise HTTPException(status_code=402, detail="燃值不足")

    reward_status = "pending" if reward_fuel > 0 else "none"
    q = Question(
        asker_id=user.id,
        title=req.title,
        body=req.body,
        tags=req.tags,
        deadline_at=deadline,
        max_responders=req.max_responders,
        matched_agent_ids=[a.id for a, *_ in matched],
        fuel_cost=0,
        visibility=normalize_question_visibility(req.visibility),
        estimated_fuel_per_answer=estimated_fuel_per_answer,
        base_cap_multiplier=DEFAULT_BASE_CAP_MULTIPLIER,
        base_fuel_reserved=base_reserve,
        base_fuel_spent=0,
        reward_fuel=reward_fuel,
        reward_status=reward_status,
        reward_auto_award_after=None,
    )
    db.add(q)
    await db.flush()  # need q.id
    record_fuel_ledger(
        db,
        user_id=user.id,
        amount=base_reserve,
        direction="debit",
        event_type="base_reserved",
        question_id=q.id,
    )
    record_fuel_ledger(
        db,
        user_id=user.id,
        amount=reward_fuel,
        direction="debit",
        event_type="reward_reserved",
        question_id=q.id,
    )

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
    is_direct_question = bool(req.agent_ids)
    for ans, agent, _mt, _qs in answer_records:
        payload = build_root_payload(
            q,
            ans,
            {"nickname": user.nickname, "trust_level": user.trust_level},
            agent=agent,
        )
        delivered = await hub.push_question(agent.id, payload)
        if delivered:
            pushed_count += 1
            await mark_answer_pushed_if_assigned(db, ans.id)
            try:
                await increment_usage(db, agent.id)
            except Exception as e:
                print(f"[questions] quota increment failed for {agent.id}: {e}")
            agent_owner_id = getattr(agent, "user_id", None)
            if is_direct_question and agent_owner_id and agent_owner_id != user.id:
                await maybe_create_notification(
                    db,
                    agent_owner_id,
                    "direct_question",
                    "direct_question",
                    f"{getattr(agent, 'name', None) or 'Agent'} 收到一个定向问题",
                    f"{user.nickname} 提问：{q.title}",
                    ref_id=q.id,
                )

    fuel_cost = pushed_count * estimated_fuel_per_answer
    q.fuel_cost = fuel_cost
    refund_amount = (len(matched) - pushed_count) * base_reserve_per_answer
    await refund_fuel(db, user.id, refund_amount)
    record_fuel_ledger(
        db,
        user_id=user.id,
        amount=refund_amount,
        direction="credit",
        event_type="base_refunded",
        question_id=q.id,
    )

    await db.commit()

    return {
        "id": q.id, "title": q.title,
        "estimated_fuel_cost": fuel_cost,
        "fuel_cost": fuel_cost,
        "visibility": q.visibility,
        "estimated_fuel_per_answer": int(q.estimated_fuel_per_answer or 0),
        "base_fuel_reserved": int(q.base_fuel_reserved or 0),
        "base_fuel_spent": int(q.base_fuel_spent or 0),
        "reward_fuel": int(q.reward_fuel or 0),
        "reward_status": q.reward_status,
        "reward_answer_id": q.reward_answer_id,
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
            Answer.status == "approved",
        )
    )).scalar_one_or_none()
    if not quoted_answer:
        raise HTTPException(status_code=400, detail="引用回答不存在或尚未发布")

    quoted_question = (await db.execute(
        select(Question).where(Question.id == quoted_answer.question_id)
    )).scalar_one_or_none()
    if not quoted_question or (quoted_question.root_question_id or quoted_question.id) != root.id:
        raise HTTPException(status_code=400, detail="引用回答不属于当前问题")

    approved_answers = (await db.execute(
        select(Answer).where(Answer.question_id == root.id, Answer.status == "approved")
    )).scalars().all()
    target_agent_ids = ensure_followup_targets(req.agent_ids, list(approved_answers))

    agents = (await db.execute(select(Agent).where(Agent.id.in_(target_agent_ids)))).scalars().all()
    agent_by_id = {agent.id: agent for agent in agents}
    missing_agents = [agent_id for agent_id in target_agent_ids if agent_id not in agent_by_id]
    if missing_agents:
        raise HTTPException(status_code=400, detail=f"Agent 不存在: {', '.join(missing_agents)}")

    depth = await followup_depth(db, quoted_answer)
    too_deep = [
        agent.name or agent.id
        for agent in agents
        if depth > int(normalize_service_rules(getattr(agent, "service_rules", None))["max_followup_depth"])
    ]
    if too_deep:
        raise HTTPException(status_code=400, detail=f"超过 Agent 追问深度限制: {', '.join(too_deep)}")

    estimated_fuel_per_answer = int(getattr(root, "estimated_fuel_per_answer", None) or DEFAULT_ESTIMATED_FUEL_PER_ANSWER)
    base_reserve_per_answer = int(round(estimated_fuel_per_answer * float(getattr(root, "base_cap_multiplier", None) or DEFAULT_BASE_CAP_MULTIPLIER)))
    base_reserve = len(target_agent_ids) * base_reserve_per_answer
    if not await deduct_fuel_if_available(db, user.id, base_reserve):
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
        parent_question_id=quoted_question.id,
        quoted_answer_id=quoted_answer.id,
        turn_type="followup",
        visibility=normalize_question_visibility(getattr(root, "visibility", None)),
        estimated_fuel_per_answer=estimated_fuel_per_answer,
        base_cap_multiplier=float(getattr(root, "base_cap_multiplier", None) or DEFAULT_BASE_CAP_MULTIPLIER),
        base_fuel_reserved=base_reserve,
        base_fuel_spent=0,
        reward_fuel=0,
        reward_status="none",
    )
    db.add(followup)
    await db.flush()
    record_fuel_ledger(
        db,
        user_id=user.id,
        amount=base_reserve,
        direction="debit",
        event_type="base_reserved",
        question_id=followup.id,
    )

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
            agent=agent,
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
            agent_owner_id = getattr(agent, "user_id", None)
            if agent_owner_id and agent_owner_id != user.id:
                await maybe_create_notification(
                    db,
                    agent_owner_id,
                    "direct_question",
                    "direct_question",
                    f"{getattr(agent, 'name', None) or 'Agent'} 收到一个追问",
                    f"{user.nickname} 追问：{root.title}",
                    ref_id=root.id,
                )
        requests.append({
            "agent_id": agent.id,
            "request_id": answer.request_id,
            "conversation_id": answer.conversation_id,
            "status": status,
        })

    fuel_cost = pushed_count * estimated_fuel_per_answer
    followup.fuel_cost = fuel_cost
    refund_amount = (len(target_agent_ids) - pushed_count) * base_reserve_per_answer
    await refund_fuel(db, user.id, refund_amount)
    record_fuel_ledger(
        db,
        user_id=user.id,
        amount=refund_amount,
        direction="credit",
        event_type="base_refunded",
        question_id=followup.id,
    )
    await db.commit()

    return {
        "id": followup.id,
        "root_question_id": root.id,
        "quoted_answer_id": quoted_answer.id,
        "pushed_count": pushed_count,
        "fuel_cost": fuel_cost,
        "requests": requests,
    }


@router.post("/questions/{question_id}/answers/{answer_id}/reward")
async def award_answer_reward(
    question_id: str,
    answer_id: str,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = await award_reward_to_answer(db, question_id, answer_id, user_payload["sub"])
    return {
        "id": q.id,
        "reward_fuel": int(getattr(q, "reward_fuel", None) or 0),
        "reward_status": getattr(q, "reward_status", None) or "none",
        "reward_answer_id": getattr(q, "reward_answer_id", None),
        "reward_awarded_at": q.reward_awarded_at.isoformat() if getattr(q, "reward_awarded_at", None) else None,
    }


@router.post("/questions/{question_id}/answers/{answer_id}/owner-supplements", status_code=201)
async def request_owner_supplement(
    question_id: str,
    answer_id: str,
    req: OwnerSupplementRequestReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    question = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    root_question_id = getattr(question, "root_question_id", None) or question.id
    if getattr(question, "asker_id", None) != user_payload["sub"]:
        raise HTTPException(status_code=403, detail="只有提问者可以请求主人补充")

    answer = await get_approved_answer_in_thread(db, answer_id, root_question_id)
    if not answer:
        raise HTTPException(status_code=404, detail="回答不存在或尚未发布")

    agent = (await db.execute(select(Agent).where(Agent.id == answer.agent_id))).scalar_one_or_none()
    if not agent or not getattr(agent, "user_id", None):
        raise HTTPException(status_code=404, detail="Agent 不存在")

    supplement = AnswerOwnerSupplement(
        question_id=root_question_id,
        answer_id=answer.id,
        agent_id=agent.id,
        requester_id=user_payload["sub"],
        owner_id=agent.user_id,
        prompt=req.prompt.strip(),
        status="pending",
    )
    db.add(supplement)
    await db.flush()
    if agent.user_id != user_payload["sub"]:
        await maybe_create_notification(
            db,
            agent.user_id,
            "answer_feedback",
            "owner_supplement_requested",
            f"{getattr(agent, 'name', None) or 'Agent'} 有一条主人补充请求",
            f"{user_payload.get('nickname') or '提问者'} 请求你补充：{question.title}",
            ref_id=question.id,
        )
    await db.commit()
    return serialize_owner_supplement(supplement)


@router.get("/my/owner-supplements")
async def my_owner_supplements(
    status: str = "pending",
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(AnswerOwnerSupplement, Question.title, Agent.name)
        .join(Question, AnswerOwnerSupplement.question_id == Question.id)
        .join(Agent, AnswerOwnerSupplement.agent_id == Agent.id)
        .where(AnswerOwnerSupplement.owner_id == user_payload["sub"], AnswerOwnerSupplement.status == status)
        .order_by(AnswerOwnerSupplement.created_at.desc())
    )).all()
    return {
        "data": [
            {
                **serialize_owner_supplement(item),
                "question_title": question_title,
                "agent_name": agent_name,
            }
            for item, question_title, agent_name in rows
        ]
    }


@router.get("/my/agent-answers")
async def my_agent_answers(
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(Answer, Question, Agent)
        .join(Agent, Answer.agent_id == Agent.id)
        .join(Question, Answer.question_id == Question.id)
        .where(Agent.user_id == user_payload["sub"], Answer.status == "approved")
        .order_by(Answer.created_at.desc())
    )).all()

    answer_ids = [answer.id for answer, *_ in rows]
    supplements_by_answer: dict[str, list[dict]] = {}
    if answer_ids:
        supplement_rows = (await db.execute(
            select(AnswerOwnerSupplement)
            .where(AnswerOwnerSupplement.answer_id.in_(answer_ids))
            .order_by(AnswerOwnerSupplement.created_at.asc())
        )).scalars().all()
        supplements_by_answer = group_owner_supplements_by_answer(supplement_rows)

    return {
        "data": [
            serialize_my_agent_answer(answer, question, agent, supplements_by_answer.get(answer.id, []))
            for answer, question, agent in rows
        ]
    }


@router.post("/my/agent-answers/batch-mark")
async def batch_mark_my_agent_answers(
    req: AgentAnswerBatchMarkReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    answer_ids = list(dict.fromkeys(req.answer_ids))
    rows = (await db.execute(
        select(Answer, Agent)
        .join(Agent, Answer.agent_id == Agent.id)
        .where(Answer.id.in_(answer_ids))
    )).all()
    if len(rows) != len(answer_ids):
        raise HTTPException(status_code=404, detail="部分回答不存在")
    if any(agent.user_id != user_payload["sub"] for _, agent in rows):
        raise HTTPException(status_code=403, detail="只能标记自己 Agent 的回答")

    mark = None if req.mark == "none" else req.mark
    for answer, _agent in rows:
        answer.owner_quality_mark = mark
    await db.commit()
    return {"updated": len(rows), "mark": mark}


@router.post("/my/owner-supplements/{supplement_id}/respond")
async def respond_owner_supplement(
    supplement_id: str,
    req: OwnerSupplementRespondReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    supplement = (await db.execute(
        select(AnswerOwnerSupplement).where(AnswerOwnerSupplement.id == supplement_id)
    )).scalar_one_or_none()
    if not supplement:
        raise HTTPException(status_code=404, detail="补充请求不存在")
    if supplement.owner_id != user_payload["sub"]:
        raise HTTPException(status_code=403, detail="无权处理")
    if supplement.status != "pending":
        raise HTTPException(status_code=400, detail="补充请求已处理")

    supplement.response = req.response.strip()
    supplement.supplement_type = normalize_owner_supplement_type(req.supplement_type)
    supplement.status = "answered"
    supplement.responded_at = datetime.utcnow()
    question = (await db.execute(select(Question).where(Question.id == supplement.question_id))).scalar_one_or_none()
    agent = (await db.execute(select(Agent).where(Agent.id == supplement.agent_id))).scalar_one_or_none()
    if question and agent:
        update_learned_profile_from_owner_supplement(agent, question, supplement)
    await db.commit()
    return serialize_owner_supplement(supplement)


@router.put("/my/owner-supplements/{supplement_id}")
async def update_owner_supplement(
    supplement_id: str,
    req: OwnerSupplementUpdateReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    supplement = await get_owner_supplement_or_404(db, supplement_id)
    if supplement.owner_id != user_payload["sub"]:
        raise HTTPException(status_code=403, detail="无权处理")
    if supplement.status == "withdrawn":
        raise HTTPException(status_code=400, detail="补充已撤回")

    if req.response is not None:
        supplement.response = req.response.strip()
    if req.supplement_type is not None:
        supplement.supplement_type = normalize_owner_supplement_type(req.supplement_type)
    if req.is_high_value is not None:
        supplement.is_high_value = bool(req.is_high_value)
    supplement.edited_at = datetime.utcnow()
    await db.commit()
    return serialize_owner_supplement(supplement)


@router.post("/my/owner-supplements/{supplement_id}/withdraw")
async def withdraw_owner_supplement(
    supplement_id: str,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    supplement = await get_owner_supplement_or_404(db, supplement_id)
    if supplement.owner_id != user_payload["sub"]:
        raise HTTPException(status_code=403, detail="无权处理")
    supplement.status = "withdrawn"
    supplement.withdrawn_at = datetime.utcnow()
    await db.commit()
    return serialize_owner_supplement(supplement)


@router.post("/owner-supplements/{supplement_id}/reaction")
async def react_owner_supplement(
    supplement_id: str,
    req: OwnerSupplementReactionReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    supplement = await get_owner_supplement_or_404(db, supplement_id)
    question = (await db.execute(select(Question).where(Question.id == supplement.question_id))).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    if getattr(question, "asker_id", None) != user_payload["sub"]:
        raise HTTPException(status_code=403, detail="只有提问者可以评价主人补充")
    if supplement.status != "answered":
        raise HTTPException(status_code=400, detail="补充尚未发布")

    supplement.asker_reaction = req.reaction
    if req.accepted:
        supplement.accepted_at = datetime.utcnow()
        supplement.is_high_value = True
        agent = (await db.execute(select(Agent).where(Agent.id == supplement.agent_id))).scalar_one_or_none()
        if agent:
            update_learned_profile_from_owner_supplement(agent, question, supplement)
    if req.accepted and supplement.owner_id != user_payload["sub"]:
        await maybe_create_notification(
            db,
            supplement.owner_id,
            "answer_feedback",
            "owner_supplement_accepted",
            "你的主人补充被采纳",
            f"{user_payload.get('nickname') or '提问者'} 采纳了你的补充",
            ref_id=supplement.question_id,
        )
    await db.commit()
    return serialize_owner_supplement(supplement)


@router.post("/my/owner-supplements/remind-overdue")
async def remind_overdue_owner_supplements(
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=1)
    rows = (await db.execute(
        select(AnswerOwnerSupplement)
        .where(
            AnswerOwnerSupplement.owner_id == user_payload["sub"],
            AnswerOwnerSupplement.status == "pending",
            AnswerOwnerSupplement.reminded_at.is_(None),
            AnswerOwnerSupplement.created_at <= cutoff,
        )
    )).scalars().all()
    for supplement in rows:
        supplement.reminded_at = datetime.utcnow()
        await maybe_create_notification(
            db,
            supplement.owner_id,
            "answer_feedback",
            "owner_supplement_overdue",
            "你有补充请求待处理",
            "有提问者等待你补充 Agent 的回答",
            ref_id=supplement.question_id,
        )
    if rows:
        await db.commit()
    return {"reminded": len(rows)}


@router.post("/questions/{question_id}/answers/{answer_id}/owner-supplements/self", status_code=201)
async def create_owner_self_supplement(
    question_id: str,
    answer_id: str,
    req: OwnerSupplementSelfReq,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    question = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    root_question_id = getattr(question, "root_question_id", None) or question.id

    answer = await get_approved_answer_in_thread(db, answer_id, root_question_id)
    if not answer:
        raise HTTPException(status_code=404, detail="回答不存在或尚未发布")

    agent = (await db.execute(select(Agent).where(Agent.id == answer.agent_id))).scalar_one_or_none()
    if not agent or not getattr(agent, "user_id", None):
        raise HTTPException(status_code=404, detail="Agent 不存在")
    if agent.user_id != user_payload["sub"]:
        raise HTTPException(status_code=403, detail="只有 Agent 主人可以主动补充")

    supplement = AnswerOwnerSupplement(
        question_id=root_question_id,
        answer_id=answer.id,
        agent_id=agent.id,
        requester_id=user_payload["sub"],
        owner_id=agent.user_id,
        prompt="主人主动补充",
        response=req.response.strip(),
        supplement_type=normalize_owner_supplement_type(req.supplement_type),
        status="answered",
        responded_at=datetime.utcnow(),
    )
    db.add(supplement)
    await db.flush()
    update_learned_profile_from_owner_supplement(agent, question, supplement)
    asker_id = getattr(question, "asker_id", None)
    if asker_id and asker_id != user_payload["sub"]:
        await maybe_create_notification(
            db,
            asker_id,
            "answer_feedback",
            "owner_supplement_added",
            f"{getattr(agent, 'name', None) or 'Agent'} 的主人补充了回答",
            f"{user_payload.get('nickname') or 'Agent 主人'} 补充了：{question.title}",
            ref_id=root_question_id,
        )
    await db.commit()
    return serialize_owner_supplement(supplement)


async def get_approved_answer_in_thread(
    db: AsyncSession,
    answer_id: str,
    root_question_id: str,
) -> Answer | None:
    answer = (await db.execute(
        select(Answer).where(Answer.id == answer_id, Answer.status == "approved")
    )).scalar_one_or_none()
    if not answer:
        return None
    if answer.question_id == root_question_id:
        return answer
    answer_question = (await db.execute(
        select(Question).where(Question.id == answer.question_id)
    )).scalar_one_or_none()
    if answer_question and getattr(answer_question, "root_question_id", None) == root_question_id:
        return answer
    return None


async def get_owner_supplement_or_404(db: AsyncSession, supplement_id: str) -> AnswerOwnerSupplement:
    supplement = (await db.execute(
        select(AnswerOwnerSupplement).where(AnswerOwnerSupplement.id == supplement_id)
    )).scalar_one_or_none()
    if not supplement:
        raise HTTPException(status_code=404, detail="补充请求不存在")
    return supplement


async def resolve_question_targets(
    db: AsyncSession,
    req: CreateQuestionReq,
    viewer_id: str,
) -> list[tuple[Agent, float, str, str]]:
    requested_ids = [str(agent_id).strip() for agent_id in (req.agent_ids or []) if str(agent_id).strip()]
    if not requested_ids:
        return await match_agents(
            db,
            req.tags,
            max_responders=max(1, req.max_responders),
            title=req.title,
            body=req.body,
            viewer_id=viewer_id,
        )

    unique_ids = list(dict.fromkeys(requested_ids))
    rows = await db.execute(select(Agent).where(Agent.id.in_(unique_ids)))
    agents = list(rows.scalars().all())
    by_id = {agent.id: agent for agent in agents}
    missing = [agent_id for agent_id in unique_ids if agent_id not in by_id]
    if missing:
        raise HTTPException(status_code=400, detail=f"Agent 不存在: {', '.join(missing)}")

    from services.matching import _relationship_owner_sets
    followed_owner_ids, friend_owner_ids = await _relationship_owner_sets(db, viewer_id)

    task_profile = build_task_profile(req.title, req.body, req.tags, req.max_responders)
    out: list[tuple[Agent, float, str, str]] = []
    for agent_id in unique_ids:
        agent = by_id[agent_id]
        if getattr(agent, "status", None) != "online":
            raise HTTPException(status_code=400, detail=f"Agent 当前离线: {agent.name or agent.id}")
        if normalize_service_mode(getattr(agent, "service_mode", None)) == "stopped":
            raise HTTPException(status_code=400, detail=f"Agent 不提供服务: {agent.name or agent.id}")
        if not can_view_agent(
            agent,
            viewer_id=viewer_id,
            followed_owner_ids=followed_owner_ids,
            friend_owner_ids=friend_owner_ids,
        ):
            raise HTTPException(status_code=404, detail=f"Agent 不存在: {agent.id}")
        state, _ = await check_quota(db, agent.id, getattr(agent, "daily_quota_config", None))
        if state == "blocked":
            raise HTTPException(status_code=400, detail=f"Agent 今日服务次数已满: {agent.name or agent.id}")
        explanation = build_match_explanation(agent, task_profile, 1.0, "direct", state)
        score = (explanation.get("overall_score") or 100) / 100
        out.append((agent, score, "direct", state))
    return out[:max(1, req.max_responders)]


async def followup_depth(db: AsyncSession, quoted_answer: Answer) -> int:
    depth = 1
    question_id = quoted_answer.question_id
    while question_id:
        question = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
        if not question or not question.quoted_answer_id:
            return depth
        quoted_answer = (await db.execute(select(Answer).where(Answer.id == question.quoted_answer_id))).scalar_one_or_none()
        if not quoted_answer:
            return depth
        question_id = quoted_answer.question_id
        depth += 1
    return depth


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


def question_public_payload(q: Question, asker_nickname: str, asker_trust_level: int, answer_count: int | None = None) -> dict:
    out = {
        "id": q.id,
        "title": q.title,
        "body": q.body,
        "tags": list(q.tags or []),
        "root_question_id": getattr(q, "root_question_id", None),
        "turn_type": getattr(q, "turn_type", None) or "root",
        "asker": {"nickname": asker_nickname, "trust_level": asker_trust_level},
        "deadline_at": q.deadline_at.isoformat(),
        "max_responders": q.max_responders,
        "matched_count": len(q.matched_agent_ids or []),
        "fuel_cost": int(q.fuel_cost or 0),
        "status": q.status,
        "created_at": q.created_at.isoformat(),
        "visibility": normalize_question_visibility(getattr(q, "visibility", None)),
        "estimated_fuel_per_answer": int(getattr(q, "estimated_fuel_per_answer", None) or DEFAULT_ESTIMATED_FUEL_PER_ANSWER),
        "base_cap_multiplier": float(getattr(q, "base_cap_multiplier", None) or DEFAULT_BASE_CAP_MULTIPLIER),
        "base_fuel_reserved": int(getattr(q, "base_fuel_reserved", None) or 0),
        "base_fuel_spent": int(getattr(q, "base_fuel_spent", None) or 0),
        "reward_fuel": int(getattr(q, "reward_fuel", None) or 0),
        "reward_status": getattr(q, "reward_status", None) or "none",
        "reward_answer_id": getattr(q, "reward_answer_id", None),
        "reward_awarded_at": q.reward_awarded_at.isoformat() if getattr(q, "reward_awarded_at", None) else None,
        "reward_auto_award_after": q.reward_auto_award_after.isoformat() if getattr(q, "reward_auto_award_after", None) else None,
    }
    if answer_count is not None:
        out["answer_count"] = answer_count
    return out


def serialize_owner_supplement(item: AnswerOwnerSupplement) -> dict:
    return {
        "id": item.id,
        "question_id": getattr(item, "question_id", None),
        "answer_id": getattr(item, "answer_id", None),
        "agent_id": getattr(item, "agent_id", None),
        "requester_id": getattr(item, "requester_id", None),
        "owner_id": getattr(item, "owner_id", None),
        "prompt": getattr(item, "prompt", None) or "",
        "response": getattr(item, "response", None) or "",
        "supplement_type": normalize_owner_supplement_type(getattr(item, "supplement_type", None)),
        "status": getattr(item, "status", None) or "pending",
        "is_high_value": bool(getattr(item, "is_high_value", False)),
        "asker_reaction": getattr(item, "asker_reaction", None),
        "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
        "responded_at": item.responded_at.isoformat() if getattr(item, "responded_at", None) else None,
        "edited_at": item.edited_at.isoformat() if getattr(item, "edited_at", None) else None,
        "withdrawn_at": item.withdrawn_at.isoformat() if getattr(item, "withdrawn_at", None) else None,
        "accepted_at": item.accepted_at.isoformat() if getattr(item, "accepted_at", None) else None,
        "reminded_at": item.reminded_at.isoformat() if getattr(item, "reminded_at", None) else None,
    }


def group_owner_supplements_by_answer(items: list[AnswerOwnerSupplement]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        grouped.setdefault(item.answer_id, []).append(serialize_owner_supplement(item))
    return grouped


def serialize_my_agent_answer(answer: Answer, question: Question, agent: Agent, supplements: list[dict]) -> dict:
    pending_count = sum(1 for item in supplements if item.get("status") == "pending")
    answered_count = sum(1 for item in supplements if item.get("status") == "answered")
    return {
        "id": answer.id,
        "question_id": getattr(question, "root_question_id", None) or question.id,
        "answer_question_id": answer.question_id,
        "question_title": getattr(question, "title", None) or "",
        "agent_id": agent.id,
        "agent_name": getattr(agent, "name", None) or "",
        "content": getattr(answer, "content", None) or {},
        "model": getattr(answer, "model", None) or "",
        "usage": getattr(answer, "usage", None) or {},
        "turn_type": getattr(answer, "turn_type", None) or "root",
        "owner_quality_mark": getattr(answer, "owner_quality_mark", None),
        "created_at": answer.created_at.isoformat() if getattr(answer, "created_at", None) else None,
        "owner_supplements": supplements,
        "owner_supplement_pending_count": pending_count,
        "owner_supplement_answered_count": answered_count,
    }


def attach_owner_supplements_to_followups(
    followup_threads: list[dict],
    supplements_by_answer: dict[str, list[dict]],
) -> list[dict]:
    for thread in followup_threads:
        for answer in thread.get("answers") or []:
            answer["owner_supplements"] = supplements_by_answer.get(answer.get("id"), [])
    return followup_threads


def normalize_question_visibility(value: str | None) -> str:
    return value if value in {"public", "private"} else "public"


def normalize_estimated_fuel_per_answer(value: int | None) -> int:
    try:
        amount = int(value or DEFAULT_ESTIMATED_FUEL_PER_ANSWER)
    except (TypeError, ValueError):
        amount = DEFAULT_ESTIMATED_FUEL_PER_ANSWER
    return max(100, min(amount, 100_000))


async def estimate_answer_fuel_per_answer(db: AsyncSession) -> int:
    since = datetime.utcnow() - timedelta(days=2)
    result = await db.execute(
        select(func.avg(Answer.fuel_earned))
        .where(Answer.status == "approved", Answer.fuel_earned > 0, Answer.reviewed_at >= since)
    )
    try:
        average = result.scalar()
    except AttributeError:
        average = None
    return normalize_estimated_fuel_per_answer(average)


def preauthorize_base_fuel_per_answer(estimated_fuel_per_answer: int) -> int:
    return int(round(normalize_estimated_fuel_per_answer(estimated_fuel_per_answer) * DEFAULT_BASE_CAP_MULTIPLIER))


def normalize_reward_fuel(value: int | None) -> int:
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return max(0, min(amount, 1_000_000))


async def can_view_question(db: AsyncSession, q: Question, viewer: dict | None) -> bool:
    if normalize_question_visibility(getattr(q, "visibility", None)) == "public":
        return True
    viewer_id = viewer.get("sub") if viewer else None
    if not viewer_id:
        return False
    if viewer_id == getattr(q, "asker_id", None):
        return True

    agent_ids = list(getattr(q, "matched_agent_ids", None) or [])
    if not agent_ids:
        return False
    rows = await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))
    return any(getattr(agent, "user_id", None) == viewer_id for agent in rows.scalars().all())


@router.get("/my/questions")
async def my_questions(
    page: int = 1, size: int = 20,
    user_payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * size
    rows = (await db.execute(
        select(Question).where(
            Question.asker_id == user_payload["sub"],
            Question.root_question_id.is_(None),
        )
        .order_by(Question.created_at.desc()).offset(offset).limit(size)
    )).scalars().all()
    total = (await db.execute(
        select(func.count(Question.id)).where(
            Question.asker_id == user_payload["sub"],
            Question.root_question_id.is_(None),
        )
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
            agent_owner_id = getattr(agent, "user_id", None)
            if agent_owner_id and agent_owner_id != user_payload["sub"]:
                vote_text = "赞同" if req.vote == "up" else "指出问题"
                await maybe_create_notification(
                    db,
                    agent_owner_id,
                    "answer_feedback",
                    "answer_feedback",
                    f"{getattr(agent, 'name', None) or 'Agent'} 的回答收到了反馈",
                    f"有人对「{question.title}」中的回答{vote_text}",
                    ref_id=question.id,
                )

    await db.commit()
    return {"id": fb.id, "vote": fb.vote, "created_at": fb.created_at.isoformat()}
