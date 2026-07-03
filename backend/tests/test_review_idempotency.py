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
async def test_approve_inline_updates_agent_learned_profile(monkeypatch):
    answer = make_answer(status="draft")
    answer.capability = {"tools": [{"name": "知识库", "used": True}], "style_tags": ["实战"]}
    agent = SimpleNamespace(id="a_test", fuel_earned=0, total_answers=0, review_rules={})
    question = SimpleNamespace(
        id="q_test",
        asker_id="u_asker",
        title="wow硬核模式职业选择",
        body="给我三个选择和风险",
        tags=["魔兽世界"],
        max_responders=3,
    )

    class ApprovalSession:
        def __init__(self):
            self.executes = 0
            self.commits = 0

        async def execute(self, stmt):
            self.executes += 1
            return FakeExecuteResult(agent if self.executes == 1 else question)

        async def commit(self):
            self.commits += 1

    async def fake_create_notification(*args, **kwargs):
        return None

    session = ApprovalSession()
    monkeypatch.setattr(review, "create_notification", fake_create_notification)

    await review._approve_inline(session, answer)

    learned = agent.review_rules["learned_profile"]
    assert answer.status == "approved"
    assert learned["sample_count"] == 1
    assert "魔兽世界" in learned["domain_tags"]
    assert "风险审查" in learned["capability_tags"]
    assert "知识库" in learned["tool_tags"]
    assert session.commits == 1


@pytest.mark.asyncio
async def test_approve_inline_credits_owner_balance_and_records_ledger(monkeypatch):
    answer = make_answer(status="draft")
    answer.usage = {"prompt_tokens": 10, "completion_tokens": 20}
    agent = SimpleNamespace(
        id="a_test",
        user_id="u_owner",
        fuel_earned=0,
        total_answers=0,
        review_rules={},
        service_rules={},
    )
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)
    question = SimpleNamespace(
        id="q_test",
        asker_id="u_asker",
        title="Token economy",
        body="",
        tags=[],
        max_responders=1,
    )

    class ApprovalSession:
        def __init__(self):
            self.executes = 0
            self.commits = 0
            self.added = []

        async def execute(self, stmt):
            self.executes += 1
            values = [agent, owner, question]
            return FakeExecuteResult(values[self.executes - 1])

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.commits += 1

    async def fake_create_notification(*args, **kwargs):
        return None

    session = ApprovalSession()
    monkeypatch.setattr(review, "create_notification", fake_create_notification)

    await review._approve_inline(session, answer)

    assert answer.fuel_earned == 50
    assert agent.fuel_earned == 50
    assert owner.fuel_balance == 150
    ledger = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert len(ledger) == 1
    assert ledger[0].user_id == "u_owner"
    assert ledger[0].amount == 50
    assert ledger[0].direction == "credit"
    assert ledger[0].event_type == "answer_earned"
    assert ledger[0].answer_id == "ans_test"
    assert ledger[0].question_id == "q_test"
    assert ledger[0].agent_id == "a_test"
    assert session.commits == 1


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
    agent = SimpleNamespace(id="a_test", fuel_earned=10, service_rules={})

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
    assert answer.fuel_earned == 1702
    assert agent.fuel_earned == 1702
    assert answer.status == "approved"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_usage_correction_adjusts_owner_balance_and_records_delta(monkeypatch):
    answer = make_answer(status="approved")
    answer.fuel_earned = 10
    agent = SimpleNamespace(id="a_test", user_id="u_owner", fuel_earned=10, service_rules={})
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)

    class CorrectionSession(FakeSession):
        async def execute(self, stmt):
            self.executes += 1
            if self.executes == 1:
                return FakeExecuteResult(answer)
            if self.executes == 2:
                return FakeExecuteResult(agent)
            return FakeExecuteResult(owner)

        def add(self, obj):
            self.added = getattr(self, "added", [])
            self.added.append(obj)

    session = CorrectionSession(answer)
    monkeypatch.setattr(review, "AsyncSessionLocal", lambda: session)

    await review.handle_uploaded_answer("a_test", {
        "type": "answer",
        "request_id": "req_test",
        "status": "success",
        "usage_correction": True,
        "model": "model-real",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    })

    assert answer.fuel_earned == 50
    assert agent.fuel_earned == 50
    assert owner.fuel_balance == 140
    ledger = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert len(ledger) == 1
    assert ledger[0].user_id == "u_owner"
    assert ledger[0].amount == 40
    assert ledger[0].direction == "credit"
    assert ledger[0].event_type == "usage_correction"
    assert ledger[0].answer_id == "ans_test"
