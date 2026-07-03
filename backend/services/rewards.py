from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Agent, Answer, Feedback, Question
from services.billing import credit_answer_owner, record_fuel_ledger, refund_fuel

AUTO_AWARD_DELAY_HOURS = 24


async def award_reward_to_answer(
    db: AsyncSession,
    question_id: str,
    answer_id: str,
    actor_user_id: str,
    *,
    event_type: str = "reward_awarded",
) -> Question:
    question = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    if getattr(question, "root_question_id", None):
        raise HTTPException(status_code=400, detail="只能给根问题回答分配奖励")
    if question.asker_id != actor_user_id:
        raise HTTPException(status_code=403, detail="只有提问者可以分配奖励")

    return await _award_reward_to_answer(db, question, answer_id, event_type=event_type)


async def auto_award_due_rewards(db: AsyncSession, question: Question) -> Question | None:
    if not _reward_is_pending(question):
        return None

    approved = (await db.execute(
        select(Answer, Agent.repute_score)
        .join(Agent, Answer.agent_id == Agent.id)
        .where(
            Answer.question_id == question.id,
            Answer.status == "approved",
            Answer.turn_type == "root",
        )
        .order_by(Answer.created_at.asc())
    )).all()
    if not approved:
        deadline_at = as_utc_naive(getattr(question, "deadline_at", None))
        if deadline_at and deadline_at < utcnow():
            return await refund_pending_reward(db, question)
        return None

    now = utcnow()
    if not getattr(question, "reward_auto_award_after", None):
        first_approved_at = min(
            (getattr(answer, "reviewed_at", None) or getattr(answer, "created_at", None) or now)
            for answer, _ in approved
        )
        question.reward_auto_award_after = first_approved_at + timedelta(hours=AUTO_AWARD_DELAY_HOURS)
        await db.commit()
        return None

    if as_utc_naive(question.reward_auto_award_after) > now:
        return None

    answer_ids = [answer.id for answer, _ in approved]
    votes_by_answer: dict[str, int] = {answer_id: 0 for answer_id in answer_ids}
    if answer_ids:
        vote_rows = await db.execute(
            select(Feedback.answer_id, Feedback.vote)
            .where(Feedback.answer_id.in_(answer_ids))
        )
        for answer_id, vote in vote_rows.all():
            if vote == "up":
                votes_by_answer[answer_id] = votes_by_answer.get(answer_id, 0) + 1

    def score(row: tuple[Answer, object]) -> tuple[float, datetime]:
        answer, repute = row
        created_at = as_utc_naive(getattr(answer, "created_at", None)) or now
        return (
            float(votes_by_answer.get(answer.id, 0) * 5) + float(repute or 0) * 2,
            created_at,
        )

    winner, _ = max(approved, key=lambda row: (score(row)[0], -score(row)[1].timestamp()))
    return await _award_reward_to_answer(db, question, winner.id, event_type="reward_auto_awarded")


async def mark_reward_auto_award_after_first_answer(
    db: AsyncSession,
    question_or_id: Question | str,
    answer: Answer,
) -> Question | None:
    if isinstance(question_or_id, str):
        question = (await db.execute(select(Question).where(Question.id == question_or_id))).scalar_one_or_none()
    else:
        question = question_or_id
    if not question or not _reward_is_pending(question):
        return question
    if getattr(question, "reward_auto_award_after", None):
        return question

    approved_at = as_utc_naive(getattr(answer, "reviewed_at", None) or getattr(answer, "created_at", None)) or utcnow()
    question.reward_auto_award_after = approved_at + timedelta(hours=AUTO_AWARD_DELAY_HOURS)
    return question


async def refund_pending_reward(db: AsyncSession, question: Question) -> Question:
    if not _reward_is_pending(question):
        return question
    reward_fuel = int(getattr(question, "reward_fuel", None) or 0)
    if await refund_fuel(db, question.asker_id, reward_fuel):
        record_fuel_ledger(
            db,
            user_id=question.asker_id,
            amount=reward_fuel,
            direction="credit",
            event_type="reward_refunded",
            question_id=question.id,
        )
        question.reward_status = "refunded"
        await db.commit()
    return question


async def _award_reward_to_answer(
    db: AsyncSession,
    question: Question,
    answer_id: str,
    *,
    event_type: str,
) -> Question:
    if not _reward_is_pending(question):
        raise HTTPException(status_code=400, detail="奖励已经分配或不可用")

    answer = (await db.execute(
        select(Answer).where(Answer.id == answer_id, Answer.question_id == question.id)
    )).scalar_one_or_none()
    if not answer:
        raise HTTPException(status_code=404, detail="回答不存在")
    if getattr(answer, "status", None) != "approved":
        raise HTTPException(status_code=400, detail="只能奖励已发布回答")
    if getattr(answer, "turn_type", None) != "root":
        raise HTTPException(status_code=400, detail="只能奖励根问题回答")

    agent = (await db.execute(select(Agent).where(Agent.id == answer.agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    reward_fuel = int(getattr(question, "reward_fuel", None) or 0)
    if not await credit_answer_owner(
        db,
        owner_id=agent.user_id,
        amount=reward_fuel,
        question_id=question.id,
        answer_id=answer.id,
        agent_id=agent.id,
        event_type=event_type,
    ):
        raise HTTPException(status_code=404, detail="Agent 主人不存在")

    agent.fuel_earned = int(getattr(agent, "fuel_earned", None) or 0) + reward_fuel
    question.reward_status = "auto_awarded" if event_type == "reward_auto_awarded" else "awarded"
    question.reward_answer_id = answer.id
    question.reward_awarded_at = utcnow()
    await db.commit()
    return question


def _reward_is_pending(question: Question) -> bool:
    return int(getattr(question, "reward_fuel", None) or 0) > 0 and getattr(question, "reward_status", None) == "pending"


def utcnow() -> datetime:
    return datetime.utcnow()


def as_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
