from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

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


class RowcountResult:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount


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


def test_decide_review_method_forces_review_for_high_health_risk():
    assert review.decide_review_method(
        quota_state="ok",
        asker_trust_level=5,
        review_rules={"auto_trust_level": 2, "auto_tag_match": True},
        match_type="exact",
        health_summary={"risk_level": "high"},
    ) == "review"


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
            values = [agent, question, owner]
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
    assert ledger[0].event_type == "answer_base_earned"
    assert ledger[0].answer_id == "ans_test"
    assert ledger[0].question_id == "q_test"
    assert ledger[0].agent_id == "a_test"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_approve_inline_charges_extra_fuel_above_preauthorization(monkeypatch):
    answer = make_answer(status="draft")
    answer.usage = {"prompt_tokens": 1000, "completion_tokens": 1000}
    agent = SimpleNamespace(
        id="a_test",
        user_id="u_owner",
        fuel_earned=0,
        total_answers=0,
        review_rules={},
        service_rules={"min_fuel_per_answer": 0, "max_fuel_per_answer": 100000, "price_multiplier": 1.0},
    )
    question = SimpleNamespace(
        id="q_test",
        asker_id="u_asker",
        title="Capped settlement",
        body="",
        tags=[],
        max_responders=1,
        estimated_fuel_per_answer=900,
        base_cap_multiplier=1.5,
        base_fuel_spent=0,
    )
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)
    asker = SimpleNamespace(id="u_asker", fuel_balance=2_000)

    class ApprovalSession:
        def __init__(self):
            self.executes = 0
            self.commits = 0
            self.added = []

        async def execute(self, stmt):
            if isinstance(stmt, Update):
                value = next(iter(stmt._values.values()))
                amount = int(value.right.value)
                if value.operator.__name__ == "sub":
                    asker.fuel_balance -= amount
                    return RowcountResult(1)
                raise AssertionError(f"unexpected update: {stmt}")
            self.executes += 1
            values = [agent, question, owner]
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

    assert answer.fuel_earned == 3000
    assert agent.fuel_earned == 3000
    assert owner.fuel_balance == 3100
    assert asker.fuel_balance == 350
    assert question.base_fuel_spent == 3000
    ledger = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert [(entry.user_id, entry.direction, entry.event_type, entry.amount) for entry in ledger] == [
        ("u_asker", "debit", "base_extra_charged", 1650),
        ("u_owner", "credit", "answer_base_earned", 3000),
    ]


@pytest.mark.asyncio
async def test_approve_inline_refunds_unused_base_reserve_to_asker(monkeypatch):
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
    question = SimpleNamespace(
        id="q_test",
        asker_id="u_asker",
        title="Exact base settlement",
        body="",
        tags=[],
        max_responders=1,
        estimated_fuel_per_answer=900,
        base_cap_multiplier=1.5,
        base_fuel_spent=0,
    )
    asker = SimpleNamespace(id="u_asker", fuel_balance=98_600)
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)

    class ApprovalSession:
        def __init__(self):
            self.executes = 0
            self.commits = 0
            self.added = []

        async def execute(self, stmt):
            if isinstance(stmt, Update):
                value = next(iter(stmt._values.values()))
                amount = int(value.right.value)
                if value.operator.__name__ == "add":
                    asker.fuel_balance += amount
                    return RowcountResult(1)
                raise AssertionError(f"unexpected update: {stmt}")
            self.executes += 1
            values = [agent, question, owner]
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
    assert owner.fuel_balance == 150
    assert asker.fuel_balance == 99_900
    ledgers = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert [(entry.user_id, entry.direction, entry.event_type, entry.amount) for entry in ledgers] == [
        ("u_asker", "credit", "base_refunded", 1300),
        ("u_owner", "credit", "answer_base_earned", 50),
    ]


@pytest.mark.asyncio
async def test_approve_inline_uses_preauthorized_base_before_charging_extra(monkeypatch):
    answer = make_answer(status="draft")
    answer.usage = {"prompt_tokens": 450, "completion_tokens": 450}
    agent = SimpleNamespace(
        id="a_test",
        user_id="u_owner",
        fuel_earned=0,
        total_answers=0,
        review_rules={},
        service_rules={"min_fuel_per_answer": 0, "max_fuel_per_answer": 100000, "price_multiplier": 1.0},
    )
    question = SimpleNamespace(
        id="q_test",
        asker_id="u_asker",
        title="Over estimate settlement",
        body="",
        tags=[],
        max_responders=1,
        estimated_fuel_per_answer=900,
        base_cap_multiplier=1.5,
        base_fuel_spent=0,
    )
    asker = SimpleNamespace(id="u_asker", fuel_balance=2_000)
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)

    class ApprovalSession:
        def __init__(self):
            self.executes = 0
            self.commits = 0
            self.added = []

        async def execute(self, stmt):
            if isinstance(stmt, Update):
                value = next(iter(stmt._values.values()))
                amount = int(value.right.value)
                if value.operator.__name__ == "sub":
                    asker.fuel_balance -= amount
                    return RowcountResult(1)
                raise AssertionError(f"unexpected update: {stmt}")
            self.executes += 1
            values = [agent, question, owner]
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

    assert answer.fuel_earned == 1350
    assert agent.fuel_earned == 1350
    assert owner.fuel_balance == 1450
    assert asker.fuel_balance == 2_000
    assert question.base_fuel_spent == 1350
    ledgers = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert [(entry.user_id, entry.direction, entry.event_type, entry.amount) for entry in ledgers] == [
        ("u_owner", "credit", "answer_base_earned", 1350),
    ]


@pytest.mark.asyncio
async def test_approve_inline_accepts_actual_fuel_equal_to_preauthorized_base(monkeypatch):
    answer = make_answer(status="draft")
    answer.usage = {"prompt_tokens": 500, "completion_tokens": 500}
    agent = SimpleNamespace(
        id="a_test",
        user_id="u_owner",
        fuel_earned=0,
        total_answers=0,
        review_rules={},
        service_rules={"min_fuel_per_answer": 0, "max_fuel_per_answer": 100000, "price_multiplier": 1.0},
    )
    question = SimpleNamespace(
        id="q_test",
        asker_id="u_asker",
        title="Over authorization settlement",
        body="",
        tags=[],
        max_responders=1,
        estimated_fuel_per_answer=1000,
        base_cap_multiplier=1.5,
        base_fuel_spent=0,
    )
    asker = SimpleNamespace(id="u_asker", fuel_balance=2_000)
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)

    class ApprovalSession:
        def __init__(self):
            self.executes = 0
            self.commits = 0
            self.added = []

        async def execute(self, stmt):
            if isinstance(stmt, Update):
                value = next(iter(stmt._values.values()))
                amount = int(value.right.value)
                if value.operator.__name__ == "sub":
                    asker.fuel_balance -= amount
                    return RowcountResult(1)
                raise AssertionError(f"unexpected update: {stmt}")
            self.executes += 1
            values = [agent, question, owner]
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

    assert answer.fuel_earned == 1500
    assert agent.fuel_earned == 1500
    assert owner.fuel_balance == 1600
    assert asker.fuel_balance == 2_000
    assert question.base_fuel_spent == 1500
    ledgers = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert [(entry.user_id, entry.direction, entry.event_type, entry.amount) for entry in ledgers] == [
        ("u_owner", "credit", "answer_base_earned", 1500),
    ]


@pytest.mark.asyncio
async def test_approve_inline_charges_asker_when_actual_fuel_exceeds_preauthorization(monkeypatch):
    answer = make_answer(status="draft")
    answer.usage = {"prompt_tokens": 1000, "completion_tokens": 1000}
    agent = SimpleNamespace(
        id="a_test",
        user_id="u_owner",
        fuel_earned=0,
        total_answers=0,
        review_rules={},
        service_rules={"min_fuel_per_answer": 0, "max_fuel_per_answer": 100000, "price_multiplier": 1.0},
    )
    question = SimpleNamespace(
        id="q_test",
        asker_id="u_asker",
        title="Over authorization settlement",
        body="",
        tags=[],
        max_responders=1,
        estimated_fuel_per_answer=900,
        base_cap_multiplier=1.5,
        base_fuel_spent=0,
    )
    asker = SimpleNamespace(id="u_asker", fuel_balance=2_000)
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)

    class ApprovalSession:
        def __init__(self):
            self.executes = 0
            self.commits = 0
            self.added = []

        async def execute(self, stmt):
            if isinstance(stmt, Update):
                value = next(iter(stmt._values.values()))
                amount = int(value.right.value)
                if value.operator.__name__ == "sub":
                    asker.fuel_balance -= amount
                    return RowcountResult(1)
                raise AssertionError(f"unexpected update: {stmt}")
            self.executes += 1
            values = [agent, question, owner]
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

    assert answer.fuel_earned == 3000
    assert agent.fuel_earned == 3000
    assert owner.fuel_balance == 3100
    assert asker.fuel_balance == 350
    assert question.base_fuel_spent == 3000
    ledgers = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert [(entry.user_id, entry.direction, entry.event_type, entry.amount) for entry in ledgers] == [
        ("u_asker", "debit", "base_extra_charged", 1650),
        ("u_owner", "credit", "answer_base_earned", 3000),
    ]


@pytest.mark.asyncio
async def test_approve_inline_caps_owner_earning_at_preauthorized_fuel_when_extra_charge_fails(monkeypatch):
    answer = make_answer(status="draft")
    answer.usage = {"prompt_tokens": 1000, "completion_tokens": 1000}
    agent = SimpleNamespace(
        id="a_test",
        user_id="u_owner",
        fuel_earned=0,
        total_answers=0,
        review_rules={},
        service_rules={"min_fuel_per_answer": 0, "max_fuel_per_answer": 100000, "price_multiplier": 1.0},
    )
    question = SimpleNamespace(
        id="q_test",
        asker_id="u_asker",
        title="Insufficient balance settlement",
        body="",
        tags=[],
        max_responders=1,
        estimated_fuel_per_answer=900,
        base_cap_multiplier=1.5,
        base_fuel_spent=0,
    )
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)

    class ApprovalSession:
        def __init__(self):
            self.executes = 0
            self.commits = 0
            self.added = []

        async def execute(self, stmt):
            if isinstance(stmt, Update):
                value = next(iter(stmt._values.values()))
                if value.operator.__name__ == "sub":
                    return RowcountResult(0)
                raise AssertionError(f"unexpected update: {stmt}")
            self.executes += 1
            values = [agent, question, owner]
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

    assert answer.fuel_earned == 1350
    assert agent.fuel_earned == 1350
    assert owner.fuel_balance == 1450
    assert question.base_fuel_spent == 1350
    ledgers = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert [(entry.user_id, entry.direction, entry.event_type, entry.amount) for entry in ledgers] == [
        ("u_owner", "credit", "answer_base_earned", 1350),
    ]


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
async def test_final_upload_overwrites_runtime_only_answer(monkeypatch):
    answer = make_answer(status="approved")
    answer.content = {"text": "⏳ Working — 3 min — iteration 1/150, receiving stream response"}
    session = FakeSession(answer)

    monkeypatch.setattr(review, "AsyncSessionLocal", lambda: session)

    await review.handle_uploaded_answer("a_test", {
        "type": "answer",
        "request_id": "req_test",
        "status": "success",
        "content": {"text": "最终答案"},
        "model": "model-final",
        "usage": {"total_tokens": 99},
        "capability": {"tools": [{"name": "vision"}]},
    })

    assert answer.content == {"text": "最终答案"}
    assert answer.model == "model-final"
    assert answer.usage == {"total_tokens": 99}
    assert answer.status == "approved"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_final_upload_overwrites_waiting_for_stream_status(monkeypatch):
    answer = make_answer(status="approved")
    answer.content = {"text": "⌛ Working — 3 min — iteration 1/150, waiting for stream response (150s, no chunks yet)"}
    session = FakeSession(answer)

    monkeypatch.setattr(review, "AsyncSessionLocal", lambda: session)

    await review.handle_uploaded_answer("a_test", {
        "type": "answer",
        "request_id": "req_test",
        "status": "success",
        "content": {"text": "最终答案"},
        "model": "model-final",
        "usage": {"total_tokens": 99},
        "capability": {},
    })

    assert answer.content == {"text": "最终答案"}
    assert answer.status == "approved"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_usage_correction_updates_terminal_answer_without_overwriting_content(monkeypatch):
    answer = make_answer(status="approved")
    agent = SimpleNamespace(id="a_test", fuel_earned=10, service_rules={})
    question = SimpleNamespace(id="q_test", estimated_fuel_per_answer=5000, base_cap_multiplier=1.5, base_fuel_spent=10)

    class CorrectionSession(FakeSession):
        async def execute(self, stmt):
            self.executes += 1
            if self.executes == 1:
                return FakeExecuteResult(answer)
            if self.executes == 2:
                return FakeExecuteResult(agent)
            return FakeExecuteResult(question)

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
    assert question.base_fuel_spent == 1702
    assert answer.status == "approved"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_usage_correction_adjusts_owner_balance_and_records_delta(monkeypatch):
    answer = make_answer(status="approved")
    answer.fuel_earned = 10
    agent = SimpleNamespace(id="a_test", user_id="u_owner", fuel_earned=10, service_rules={})
    question = SimpleNamespace(id="q_test", estimated_fuel_per_answer=5000, base_cap_multiplier=1.5, base_fuel_spent=10)
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)

    class CorrectionSession(FakeSession):
        async def execute(self, stmt):
            self.executes += 1
            if self.executes == 1:
                return FakeExecuteResult(answer)
            if self.executes == 2:
                return FakeExecuteResult(agent)
            if self.executes == 3:
                return FakeExecuteResult(question)
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
    assert question.base_fuel_spent == 50
    assert owner.fuel_balance == 140
    ledger = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert len(ledger) == 1
    assert ledger[0].user_id == "u_owner"
    assert ledger[0].amount == 40
    assert ledger[0].direction == "credit"
    assert ledger[0].event_type == "usage_correction"
    assert ledger[0].answer_id == "ans_test"


@pytest.mark.asyncio
async def test_usage_correction_charges_asker_for_new_extra_above_preauthorization(monkeypatch):
    answer = make_answer(status="approved")
    answer.fuel_earned = 900
    agent = SimpleNamespace(id="a_test", user_id="u_owner", fuel_earned=900, service_rules={
        "min_fuel_per_answer": 0,
        "max_fuel_per_answer": 100000,
        "price_multiplier": 1.0,
    })
    question = SimpleNamespace(
        id="q_test",
        asker_id="u_asker",
        estimated_fuel_per_answer=900,
        base_cap_multiplier=1.5,
        base_fuel_spent=900,
    )
    asker = SimpleNamespace(id="u_asker", fuel_balance=2_000)
    owner = SimpleNamespace(id="u_owner", fuel_balance=100)

    class CorrectionSession(FakeSession):
        async def execute(self, stmt):
            if isinstance(stmt, Update):
                value = next(iter(stmt._values.values()))
                amount = int(value.right.value)
                if value.operator.__name__ == "sub":
                    asker.fuel_balance -= amount
                    return RowcountResult(1)
                raise AssertionError(f"unexpected update: {stmt}")
            self.executes += 1
            if self.executes == 1:
                return FakeExecuteResult(answer)
            if self.executes == 2:
                return FakeExecuteResult(agent)
            if self.executes == 3:
                return FakeExecuteResult(question)
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
            "prompt_tokens": 900,
            "completion_tokens": 900,
            "total_tokens": 1800,
        },
    })

    assert answer.fuel_earned == 2700
    assert agent.fuel_earned == 2700
    assert question.base_fuel_spent == 2700
    assert asker.fuel_balance == 650
    assert owner.fuel_balance == 1900
    ledger = [item for item in session.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert [(entry.user_id, entry.direction, entry.event_type, entry.amount) for entry in ledger] == [
        ("u_asker", "debit", "base_extra_charged", 1350),
        ("u_owner", "credit", "usage_correction", 1800),
    ]
