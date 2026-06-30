"""Review service — single source of truth for the auto/review decision.

This module consolidates two paths that used to drift apart in the prototype:
  - WS hub's `_handle_answer` (auto-approval when answer is uploaded)
  - REST router's manual approve/reject (operator decision via web UI)

Both call `approve_answer`/`reject_answer` here so fuel-earning, repute
adjustment, and notification creation happen in exactly one place.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models import Answer, Agent, Question, User
from services.learned_profile import update_learned_profile_from_approval
from services.notification import create_notification


def decide_review_method(
    *,
    quota_state: str,
    asker_trust_level: int,
    review_rules: dict | None,
    match_type: str,
) -> str:
    """Return "auto" or "review".

    Rules:
      - quota in "review_only" band → "review" (override)
      - asker trust ≥ auto_trust_level → "auto"
      - match_type == "exact" AND review_rules.auto_tag_match → "auto"
      - else → "review"
    """
    if quota_state == "review_only":
        return "review"
    rules = review_rules or {}
    if asker_trust_level >= int(rules.get("auto_trust_level", 2)):
        return "auto"
    if rules.get("auto_tag_match", True) and match_type == "exact":
        return "auto"
    return "review"


async def handle_uploaded_answer(agent_id: str, msg: dict):
    """Receive an `answer` message from a connector and store it.

    Outcome depends on the original answer row's `review_method` (set when the
    question was matched & pushed). If "auto" → approve immediately. Otherwise
    leave as `draft` for the owner to review.
    """
    request_id = msg.get("request_id")
    if not request_id:
        return
    success = msg.get("status") == "success"

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Answer).where(Answer.request_id == request_id, Answer.agent_id == agent_id)
        )
        answer = result.scalar_one_or_none()
        if not answer:
            print(f"[review] no matching answer row for request_id={request_id}, agent={agent_id}")
            return

        if answer.status in {"draft", "approved", "rejected", "expired"}:
            if msg.get("usage_correction"):
                await _apply_usage_correction(db, answer, msg)
                print(f"[review] usage corrected for request_id={request_id}, status={answer.status}")
                return
            print(f"[review] duplicate answer ignored for request_id={request_id}, status={answer.status}")
            return

        answer.content = msg.get("content", {}) or {}
        answer.model = msg.get("model", "") or ""
        answer.usage = msg.get("usage", {}) or {}
        answer.capability = msg.get("capability", {}) or {}

        if not success:
            answer.status = "rejected"
            answer.reviewed_at = datetime.utcnow()
            await db.commit()
            print(f"[review] {request_id} rejected (agent reported failure)")
            return

        answer.status = "draft"

        if answer.review_method == "auto":
            await _approve_inline(db, answer)
            print(f"[review] {request_id} auto-approved")
        else:
            # Notify the agent's owner that a draft is waiting
            agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
            agent = agent_result.scalar_one_or_none()
            if agent:
                await create_notification(
                    db, agent.user_id, "review_needed",
                    title=f"{agent.name} 有一份回答需审核",
                    ref_id=answer.id,
                )
            await db.commit()
            print(f"[review] {request_id} queued for manual review")


async def approve_answer_by_id(db: AsyncSession, answer: Answer) -> None:
    """Operator manually approves a draft answer."""
    await _approve_inline(db, answer)


async def reject_answer_by_id(db: AsyncSession, answer: Answer) -> None:
    answer.status = "rejected"
    answer.review_method = "review"
    answer.reviewed_at = datetime.utcnow()
    await db.commit()


async def _apply_usage_correction(db: AsyncSession, answer: Answer, msg: dict) -> None:
    """Accept late real token usage without treating it as a second answer."""
    new_usage = msg.get("usage", {}) or {}
    if not new_usage:
        return

    old_usage = answer.usage or {}
    old_tokens = int(old_usage.get("total_tokens") or 0)
    new_tokens = int(new_usage.get("total_tokens") or 0)
    answer.usage = new_usage
    if msg.get("model"):
        answer.model = msg.get("model", "") or answer.model
    if msg.get("capability"):
        answer.capability = msg.get("capability", {}) or answer.capability

    if answer.status == "approved":
        answer.fuel_earned = new_tokens
        delta = new_tokens - old_tokens
        if delta:
            agent_result = await db.execute(select(Agent).where(Agent.id == answer.agent_id))
            agent = agent_result.scalar_one_or_none()
            if agent:
                agent.fuel_earned = int(agent.fuel_earned or 0) + delta

    await db.commit()


# ─── Internal: shared approval logic ───

async def _approve_inline(db: AsyncSession, answer: Answer):
    """Mark approved, award fuel, update agent stats, notify asker.

    Single source of truth. Called from both auto and manual paths.
    """
    answer.status = "approved"
    answer.reviewed_at = datetime.utcnow()
    tokens = int((answer.usage or {}).get("total_tokens", 0))
    answer.fuel_earned = tokens

    # Update agent aggregates
    agent_result = await db.execute(select(Agent).where(Agent.id == answer.agent_id))
    agent = agent_result.scalar_one_or_none()
    if agent:
        agent.fuel_earned = int(agent.fuel_earned or 0) + tokens
        agent.total_answers = int(agent.total_answers or 0) + 1
        # Simple incremental approval-rate update (count of approvals / total_answers)
        # In practice total_answers also bumps on rejection; here we keep it simple.

    # Notify asker
    q_result = await db.execute(select(Question).where(Question.id == answer.question_id))
    question = q_result.scalar_one_or_none()
    if question:
        if agent:
            update_learned_profile_from_approval(agent, question, answer)
        await create_notification(
            db, question.asker_id, "answer_ready",
            title=f"你的问题「{question.title}」有了新回答",
            ref_id=question.id,
        )

    await db.commit()
