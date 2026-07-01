from typing import Any

from fastapi import HTTPException


def build_conversation_id(root_question_id: str, agent_id: str) -> str:
    return f"conv_{root_question_id}_{agent_id}"


def answer_text(answer: Any) -> str:
    content = getattr(answer, "content", None) or {}
    if isinstance(content, dict):
        return str(content.get("text") or "")
    return ""


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


def build_root_payload(question: Any, answer: Any, asker: dict) -> dict:
    return {
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


def build_followup_payload(
    *,
    root_question: Any,
    followup_question: Any,
    answer: Any,
    quoted_answer: Any,
    asker: dict,
) -> dict:
    return {
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
