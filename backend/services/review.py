"""Review service — single source of truth for the auto/review decision.

This module consolidates two paths that used to drift apart in the prototype:
  - WS hub's `_handle_answer` (auto-approval when answer is uploaded)
  - REST router's manual approve/reject (operator decision via web UI)

Both call `approve_answer`/`reject_answer` here so fuel-earning, repute
adjustment, and notification creation happen in exactly one place.
"""
from datetime import datetime
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models import Answer, Agent, Question, User
from services.billing import (
    calculate_answer_fuel,
    credit_answer_owner,
    deduct_fuel_if_available,
    record_fuel_ledger,
    refund_fuel,
)
from services.learned_profile import update_learned_profile_from_approval
from services.notification import create_notification
from services.rewards import mark_reward_auto_award_after_first_answer

RUNTIME_ONLY_PATTERNS = [
    re.compile(r"^\s*(?:[^\w\s]+\s*)?working\s+[-—]\s+.+\biteration\s+\d+/\d+\b.*\b(?:receiving|waiting\s+for)\s+stream\s+response\b", re.IGNORECASE),
    re.compile(r"^\s*(?:[^\w\s]+\s*)?(?:vision_analyze|image_analyze|browser_[a-z0-9_]*|terminal|tool_[a-z0-9_]*|execute_code)\s*:", re.IGNORECASE),
]


def decide_review_method(
    *,
    quota_state: str,
    asker_trust_level: int,
    review_rules: dict | None,
    match_type: str,
    health_summary: dict | None = None,
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
    if (health_summary or {}).get("risk_level") == "high":
        return "review"
    rules = review_rules or {}
    if asker_trust_level >= int(rules.get("auto_trust_level", 2)):
        return "auto"
    if rules.get("auto_tag_match", True) and match_type == "exact":
        return "auto"
    return "review"


async def handle_uploaded_answer(agent_id: str, msg: dict):
    """Receive an `answer` message from a runtime node and store it.

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

        runtime_only_upload = _is_runtime_only_message(msg)

        if answer.status in {"draft", "approved", "rejected", "expired"}:
            if msg.get("usage_correction"):
                await _apply_usage_correction(db, answer, msg)
                print(f"[review] usage corrected for request_id={request_id}, status={answer.status}")
                return
            if success and answer.status in {"draft", "approved"}:
                if _merge_terminal_success_upload(answer, msg, update_usage=not runtime_only_upload and answer.status != "approved"):
                    if answer.status == "approved":
                        answer.reviewed_at = datetime.utcnow()
                        if not runtime_only_upload and msg.get("usage"):
                            await _apply_usage_correction(db, answer, msg)
                        else:
                            await db.commit()
                    else:
                        await db.commit()
                    print(f"[review] answer part appended for request_id={request_id}, status={answer.status}")
                else:
                    print(f"[review] duplicate answer ignored for request_id={request_id}, status={answer.status}")
                return
            if success and _can_merge_upload(answer, msg):
                _merge_answer_upload(answer, msg, keep_status=runtime_only_upload)
                if answer.status == "approved" and not runtime_only_upload:
                    answer.reviewed_at = datetime.utcnow()
                await db.commit()
                print(f"[review] answer upload merged for request_id={request_id}, status={answer.status}")
                return
            print(f"[review] duplicate answer ignored for request_id={request_id}, status={answer.status}")
            return

        answer.content = _append_upload_to_content(getattr(answer, "content", None) or {}, msg.get("content", {}) or {})
        answer.model = msg.get("model", "") or getattr(answer, "model", "") or ""
        answer.usage = msg.get("usage", {}) or getattr(answer, "usage", {}) or {}
        answer.capability = msg.get("capability", {}) or getattr(answer, "capability", {}) or {}

        if not success:
            answer.status = "rejected"
            answer.reviewed_at = datetime.utcnow()
            await db.commit()
            print(f"[review] {request_id} rejected (agent reported failure)")
            return

        if runtime_only_upload:
            answer.status = "processing"
            await db.commit()
            print(f"[review] {request_id} runtime update merged")
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


def _is_runtime_only_answer(answer: Answer) -> bool:
    content = getattr(answer, "content", None) or {}
    text = str(content.get("text") if isinstance(content, dict) else content or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in RUNTIME_ONLY_PATTERNS)


def _is_runtime_only_message(msg: dict) -> bool:
    usage = msg.get("usage", {}) or {}
    if isinstance(usage, dict) and usage.get("runtime_update"):
        return True
    content = msg.get("content", {}) or {}
    text = str(content.get("text") if isinstance(content, dict) else content or "").strip()
    return bool(text) and any(pattern.search(text) for pattern in RUNTIME_ONLY_PATTERNS)


def _can_merge_upload(answer: Answer, msg: dict) -> bool:
    return _is_runtime_only_answer(answer) or _is_runtime_only_message(msg)


def _merge_answer_upload(answer: Answer, msg: dict, *, keep_status: bool = False) -> None:
    answer.content = _append_upload_to_content(getattr(answer, "content", None) or {}, msg.get("content", {}) or {})
    answer.model = msg.get("model", "") or getattr(answer, "model", "") or ""
    answer.usage = msg.get("usage", {}) or getattr(answer, "usage", {}) or {}
    answer.capability = msg.get("capability", {}) or getattr(answer, "capability", {}) or {}
    if not keep_status and answer.status == "processing":
        answer.status = "draft"


def _merge_terminal_success_upload(answer: Answer, msg: dict, *, update_usage: bool = True) -> bool:
    previous = {
        "content": getattr(answer, "content", None) or {},
        "model": getattr(answer, "model", "") or "",
        "usage": getattr(answer, "usage", None) or {},
        "capability": getattr(answer, "capability", None) or {},
    }
    next_content = _append_upload_to_content(previous["content"], msg.get("content", {}) or {})
    next_model = msg.get("model", "") or previous["model"]
    next_usage = (msg.get("usage", {}) or previous["usage"]) if update_usage else previous["usage"]
    next_capability = msg.get("capability", {}) or previous["capability"]
    if (
        next_content == previous["content"]
        and next_model == previous["model"]
        and next_usage == previous["usage"]
        and next_capability == previous["capability"]
    ):
        return False
    answer.content = next_content
    answer.model = next_model
    answer.usage = next_usage
    answer.capability = next_capability
    return True


def _append_upload_to_content(existing: dict, incoming: dict) -> dict:
    existing = existing if isinstance(existing, dict) else {}
    incoming = incoming if isinstance(incoming, dict) else {"text": str(incoming or "")}
    existing_text = str(existing.get("text") or "").strip()
    incoming_text = str(incoming.get("text") or "").strip()
    existing_runtime = _text_is_runtime_only(existing_text)
    incoming_runtime = _text_is_runtime_only(incoming_text)

    if not existing_text:
        text = incoming_text
    elif not incoming_text:
        text = existing_text
    elif existing_runtime and not incoming_runtime:
        text = "\n\n".join([existing_text, incoming_text])
    elif incoming_runtime:
        text = "\n\n".join([existing_text, incoming_text])
    else:
        text = incoming_text

    attachments = []
    for source in (existing, incoming):
        for item in source.get("attachments") or []:
            if isinstance(item, dict) and item not in attachments:
                attachments.append(item)

    parts = _append_content_part(_content_parts(existing), {
        "text": incoming_text,
        "attachments": _content_attachments(incoming),
        "runtime_update": incoming_runtime,
    })
    if parts:
        text = _answer_text_from_parts(parts)
    out = {**existing, **incoming, "text": text}
    if attachments:
        out["attachments"] = attachments[:10]
    if parts:
        out["parts"] = parts
    return out


def _answer_text_from_parts(parts: list[dict]) -> str:
    final_texts = [
        str(part.get("text") or "").strip()
        for part in parts
        if not part.get("runtime_update") and str(part.get("text") or "").strip()
    ]
    if final_texts:
        return "\n\n".join(final_texts)
    return "\n\n".join(
        str(part.get("text") or "").strip()
        for part in parts
        if str(part.get("text") or "").strip()
    )


def _content_attachments(content: dict) -> list[dict]:
    attachments = content.get("attachments") if isinstance(content, dict) else []
    return [item for item in (attachments or []) if isinstance(item, dict)]


def _content_parts(content: dict) -> list[dict]:
    if not isinstance(content, dict):
        return []
    raw_parts = content.get("parts")
    if isinstance(raw_parts, list):
        parts = []
        for item in raw_parts:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            attachments = _content_attachments(item)
            if not text and not attachments:
                continue
            parts.append({
                "text": text,
                "attachments": attachments,
                "runtime_update": bool(item.get("runtime_update")),
            })
        if parts:
            return parts
    text = str(content.get("text") or "").strip()
    attachments = _content_attachments(content)
    if not text and not attachments:
        return []
    return [{
        "text": text,
        "attachments": attachments,
        "runtime_update": _text_is_runtime_only(text),
    }]


def _append_content_part(parts: list[dict], incoming: dict) -> list[dict]:
    text = str(incoming.get("text") or "").strip()
    attachments = _content_attachments(incoming)
    if not text and not attachments:
        return parts
    part = {
        "text": text,
        "attachments": attachments,
        "runtime_update": bool(incoming.get("runtime_update")),
    }
    if parts:
        last = parts[-1]
        if (
            str(last.get("text") or "").strip() == part["text"]
            and _content_attachments(last) == part["attachments"]
            and bool(last.get("runtime_update")) == part["runtime_update"]
        ):
            return parts
    return [*parts, part]


def _text_is_runtime_only(text: str) -> bool:
    value = str(text or "").strip()
    return bool(value) and any(pattern.search(value) for pattern in RUNTIME_ONLY_PATTERNS)


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

    answer.usage = new_usage
    if msg.get("model"):
        answer.model = msg.get("model", "") or answer.model
    if msg.get("capability"):
        answer.capability = msg.get("capability", {}) or answer.capability

    if answer.status == "approved":
        agent_result = await db.execute(select(Agent).where(Agent.id == answer.agent_id))
        agent = agent_result.scalar_one_or_none()
        question_result = await db.execute(select(Question).where(Question.id == answer.question_id))
        question = question_result.scalar_one_or_none()
        if agent:
            new_fuel = calculate_answer_fuel(new_usage, agent)
            delta = new_fuel - int(answer.fuel_earned or 0)
            answer.fuel_earned = new_fuel
            paid_delta = delta
            if question and delta > 0:
                previous_fuel = int(answer.fuel_earned or 0) - delta
                paid_delta = await charge_usage_correction_extra(db, question, answer, previous_fuel, new_fuel)
            if paid_delta:
                answer.fuel_earned = int(answer.fuel_earned or 0) + paid_delta - delta
                if question:
                    question.base_fuel_spent = max(0, int(getattr(question, "base_fuel_spent", None) or 0) + paid_delta)
                agent.fuel_earned = int(agent.fuel_earned or 0) + paid_delta
                if paid_delta > 0 and getattr(agent, "user_id", None):
                    await credit_answer_owner(
                        db,
                        owner_id=agent.user_id,
                        amount=paid_delta,
                        question_id=answer.question_id,
                        answer_id=answer.id,
                        agent_id=agent.id,
                        event_type="usage_correction",
                    )
            elif delta:
                answer.fuel_earned = int(answer.fuel_earned or 0) - delta

    await db.commit()


# ─── Internal: shared approval logic ───

async def _approve_inline(db: AsyncSession, answer: Answer):
    """Mark approved, award fuel, update agent stats, notify asker.

    Single source of truth. Called from both auto and manual paths.
    """
    answer.status = "approved"
    answer.reviewed_at = datetime.utcnow()

    # Update agent aggregates
    agent_result = await db.execute(select(Agent).where(Agent.id == answer.agent_id))
    agent = agent_result.scalar_one_or_none()
    q_result = await db.execute(select(Question).where(Question.id == answer.question_id))
    question = q_result.scalar_one_or_none()
    calculated_fuel = (
        calculate_answer_fuel(answer.usage or {}, agent)
        if agent else int((answer.usage or {}).get("total_tokens", 0))
    )
    fuel = await settle_initial_base_fuel(db, question, answer, calculated_fuel)
    answer.fuel_earned = fuel
    if agent:
        agent.fuel_earned = int(agent.fuel_earned or 0) + fuel
        agent.total_answers = int(agent.total_answers or 0) + 1
        if question:
            question.base_fuel_spent = int(getattr(question, "base_fuel_spent", None) or 0) + fuel
        if getattr(agent, "user_id", None):
            await credit_answer_owner(
                db,
                owner_id=agent.user_id,
                amount=fuel,
                question_id=answer.question_id,
                answer_id=answer.id,
                agent_id=agent.id,
                event_type="answer_base_earned",
            )
        # Simple incremental approval-rate update (count of approvals / total_answers)
        # In practice total_answers also bumps on rejection; here we keep it simple.

    if question:
        await mark_reward_auto_award_after_first_answer(db, question, answer)
        if agent:
            update_learned_profile_from_approval(agent, question, answer)
        await create_notification(
            db, question.asker_id, "answer_ready",
            title=f"你的问题「{question.title}」有了新回答",
            ref_id=question.id,
        )

    await db.commit()


async def settle_initial_base_fuel(db: AsyncSession, question: Question | None, answer: Answer, fuel: int) -> int:
    if not question or not hasattr(question, "estimated_fuel_per_answer"):
        return int(fuel or 0)

    reserved = reserved_base_fuel_per_answer(question)
    fuel = int(fuel or 0)
    if fuel < reserved:
        await refund_unused_base_reserve(db, question, answer, fuel)
        return fuel

    extra_amount = fuel - reserved
    if extra_amount <= 0:
        return fuel
    if not getattr(question, "asker_id", None):
        return fuel

    if await deduct_fuel_if_available(db, question.asker_id, extra_amount):
        record_fuel_ledger(
            db,
            user_id=question.asker_id,
            amount=extra_amount,
            direction="debit",
            event_type="base_extra_charged",
            question_id=question.id,
            answer_id=answer.id,
            agent_id=answer.agent_id,
        )
        return fuel

    return reserved


async def charge_usage_correction_extra(
    db: AsyncSession,
    question: Question,
    answer: Answer,
    previous_fuel: int,
    new_fuel: int,
) -> int:
    previous_fuel = int(previous_fuel or 0)
    new_fuel = int(new_fuel or 0)
    delta = new_fuel - previous_fuel
    if delta <= 0:
        return delta
    if not hasattr(question, "estimated_fuel_per_answer") or not getattr(question, "asker_id", None):
        return delta

    reserved = reserved_base_fuel_per_answer(question)
    previous_extra = max(0, previous_fuel - reserved)
    new_extra = max(0, new_fuel - reserved)
    charge_amount = new_extra - previous_extra
    if charge_amount <= 0:
        return delta

    if await deduct_fuel_if_available(db, question.asker_id, charge_amount):
        record_fuel_ledger(
            db,
            user_id=question.asker_id,
            amount=charge_amount,
            direction="debit",
            event_type="base_extra_charged",
            question_id=question.id,
            answer_id=answer.id,
            agent_id=answer.agent_id,
        )
        return delta
    return delta - charge_amount


async def refund_unused_base_reserve(db: AsyncSession, question: Question, answer: Answer, fuel: int) -> None:
    reserved = reserved_base_fuel_per_answer(question)
    refund_amount = reserved - int(fuel or 0)
    if refund_amount <= 0:
        return
    if await refund_fuel(db, question.asker_id, refund_amount):
        record_fuel_ledger(
            db,
            user_id=question.asker_id,
            amount=refund_amount,
            direction="credit",
            event_type="base_refunded",
            question_id=question.id,
            answer_id=answer.id,
            agent_id=answer.agent_id,
        )


def question_base_cap(question: Question | None) -> int | None:
    if not question:
        return None
    estimated = int(getattr(question, "estimated_fuel_per_answer", None) or 0)
    if estimated <= 0:
        return None
    try:
        multiplier = float(getattr(question, "base_cap_multiplier", None) or 1.5)
    except (TypeError, ValueError):
        multiplier = 1.5
    return int(round(estimated * multiplier))


def reserved_base_fuel_per_answer(question: Question) -> int:
    cap = question_base_cap(question)
    if cap is not None:
        return cap
    return int(getattr(question, "estimated_fuel_per_answer", None) or 0)
