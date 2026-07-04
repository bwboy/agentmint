from typing import Any

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Answer
from services.learned_profile import build_owner_experience_context


def build_conversation_id(root_question_id: str, agent_id: str) -> str:
    return f"conv_{root_question_id}_{agent_id}"


async def mark_answer_pushed_if_assigned(db: AsyncSession, answer_id: str) -> bool:
    result = await db.execute(
        update(Answer)
        .where(Answer.id == answer_id, Answer.status == "assigned")
        .values(status="pushed")
    )
    rowcount = getattr(result, "rowcount", None)
    return rowcount is None or int(rowcount or 0) > 0


def answer_text(answer: Any) -> str:
    content = getattr(answer, "content", None) or {}
    if isinstance(content, dict):
        return str(content.get("text") or "")
    return ""


def serialize_answer(
    answer: Any,
    agent_name: str,
    agent_type: str,
    repute_score: float,
    vote_summary: dict | None = None,
) -> dict:
    fuel_earned = max(0, int(getattr(answer, "fuel_earned", None) or 0))
    return {
        "id": answer.id,
        "question_id": answer.question_id,
        "agent": {
            "id": answer.agent_id,
            "name": agent_name,
            "agent_type": agent_type,
            "repute_score": float(repute_score or 0),
        },
        "request_id": answer.request_id,
        "conversation_id": answer.conversation_id,
        "parent_answer_id": answer.parent_answer_id,
        "turn_type": answer.turn_type,
        "content": answer.content or {},
        "model": answer.model,
        "usage": answer.usage or {},
        "fuel_earned": fuel_earned,
        "settlement": {
            "base_fuel_charged": fuel_earned,
        },
        "capability": answer.capability or None,
        "status": answer.status,
        "review_method": answer.review_method,
        "vote_summary": vote_summary or {"up": 0, "down": 0},
        "created_at": answer.created_at.isoformat(),
    }


def serialize_followup_thread(followup: Any, answer_rows: list[tuple], vote_rows: dict[str, dict[str, int]]) -> dict:
    return {
        "id": followup.id,
        "root_question_id": followup.root_question_id,
        "quoted_answer_id": followup.quoted_answer_id,
        "text": followup.body,
        "deadline_at": followup.deadline_at.isoformat(),
        "created_at": followup.created_at.isoformat(),
        "answers": [
            serialize_answer(
                answer,
                agent_name,
                agent_type,
                repute_score,
                vote_rows.get(answer.id, {"up": 0, "down": 0}),
            )
            for answer, agent_name, agent_type, repute_score in answer_rows
        ],
    }


def ensure_followup_targets(agent_ids: list[str], approved_root_answers: list[Any]) -> list[str]:
    requested = [str(agent_id).strip() for agent_id in agent_ids if str(agent_id).strip()]
    deduped = list(dict.fromkeys(requested))
    if not deduped:
        raise HTTPException(status_code=400, detail="请选择至少一个已回答的 Agent")

    approved_by_agent = {
        answer.agent_id: answer
        for answer in approved_root_answers
        if answer.status == "approved"
    }
    missing = [agent_id for agent_id in deduped if agent_id not in approved_by_agent]
    if missing:
        raise HTTPException(status_code=400, detail=f"Agent 没有已发布回答，不能追问: {', '.join(missing)}")
    return deduped


def build_root_payload(question: Any, answer: Any, asker: dict, agent: Any | None = None) -> dict:
    payload = {
        "request_id": answer.request_id,
        "conversation_id": answer.conversation_id,
        "turn_type": "root",
        "context_mode": "root",
        "title": question.title,
        "body": question.body,
        "tags": list(question.tags or []),
        "asker": asker,
        "auto_release": answer.review_method == "auto",
        "deadline_at": question.deadline_at.isoformat(),
    }
    _attach_owner_experience_context(payload, agent)
    return payload


def build_followup_payload(
    *,
    root_question: Any,
    followup_question: Any,
    answer: Any,
    quoted_answer: Any,
    asker: dict,
    agent: Any | None = None,
) -> dict:
    payload = {
        "request_id": answer.request_id,
        "conversation_id": answer.conversation_id,
        "turn_type": "followup",
        "context_mode": "auto",
        "title": followup_question.title,
        "body": followup_question.body,
        "tags": list(followup_question.tags or []),
        "root_question": {
            "id": root_question.id,
            "title": root_question.title,
            "body": root_question.body,
            "tags": list(root_question.tags or []),
        },
        "quoted_answer": {
            "id": quoted_answer.id,
            "agent_id": quoted_answer.agent_id,
            "text": answer_text(quoted_answer),
        },
        "followup": {"text": followup_question.body},
        "asker": asker,
        "auto_release": answer.review_method == "auto",
        "deadline_at": followup_question.deadline_at.isoformat(),
    }
    _attach_owner_experience_context(payload, agent)
    return payload


def _attach_owner_experience_context(payload: dict, agent: Any | None) -> None:
    context = build_owner_experience_context(agent) if agent is not None else None
    if context and context.get("has_context"):
        payload["owner_experience_context"] = context
