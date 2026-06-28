from types import SimpleNamespace

import pytest

from services import review


class FakeExecuteResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, answer):
        self.answer = answer
        self.commits = 0
        self.executes = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        self.executes += 1
        return FakeExecuteResult(self.answer if self.executes == 1 else None)

    async def commit(self):
        self.commits += 1


def make_answer(status="approved"):
    return SimpleNamespace(
        id="ans_test",
        request_id="req_test",
        agent_id="a_test",
        question_id="q_test",
        content={"text": "first"},
        model="model-first",
        usage={"total_tokens": 10},
        capability={},
        status=status,
        review_method="auto",
        reviewed_at=None,
        fuel_earned=10,
    )


@pytest.mark.asyncio
async def test_duplicate_upload_does_not_overwrite_terminal_answer(monkeypatch):
    answer = make_answer(status="approved")
    session = FakeSession(answer)

    monkeypatch.setattr(review, "AsyncSessionLocal", lambda: session)

    await review.handle_uploaded_answer("a_test", {
        "type": "answer",
        "request_id": "req_test",
        "status": "success",
        "content": {"text": "second"},
        "model": "model-second",
        "usage": {"total_tokens": 99},
        "capability": {"tools": [{"name": "late"}]},
    })

    assert answer.content == {"text": "first"}
    assert answer.model == "model-first"
    assert answer.usage == {"total_tokens": 10}
    assert answer.status == "approved"
    assert session.commits == 0


@pytest.mark.asyncio
async def test_usage_correction_updates_terminal_answer_without_overwriting_content(monkeypatch):
    answer = make_answer(status="approved")
    agent = SimpleNamespace(id="a_test", fuel_earned=10)

    class CorrectionSession(FakeSession):
        async def execute(self, stmt):
            self.executes += 1
            if self.executes == 1:
                return FakeExecuteResult(answer)
            return FakeExecuteResult(agent)

    session = CorrectionSession(answer)
    monkeypatch.setattr(review, "AsyncSessionLocal", lambda: session)

    await review.handle_uploaded_answer("a_test", {
        "type": "answer",
        "request_id": "req_test",
        "status": "success",
        "usage_correction": True,
        "content": {"text": "second"},
        "model": "model-real",
        "usage": {
            "prompt_tokens": 70,
            "completion_tokens": 816,
            "total_tokens": 886,
        },
        "capability": {"engine": {"provider": "hermes", "model": "model-real"}},
    })

    assert answer.content == {"text": "first"}
    assert answer.model == "model-real"
    assert answer.usage == {
        "prompt_tokens": 70,
        "completion_tokens": 816,
        "total_tokens": 886,
    }
    assert answer.fuel_earned == 886
    assert agent.fuel_earned == 886
    assert answer.status == "approved"
    assert session.commits == 1
