from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

from routers import questions
from services import billing


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, user):
        self.user = user
        self.added = []
        self.commits = 0
        self.flushed = 0
        self.refreshed = []
        self.fuel_deductions = []
        self.fuel_refunds = []

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            return self._execute_update(stmt)
        return FakeScalarResult(self.user)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1
        for obj in self.added:
            if obj.__class__.__name__ == "Question" and getattr(obj, "id", None) is None:
                obj.id = "q_test"

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = "q_test"
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.utcnow()

    def _execute_update(self, stmt):
        if stmt.table.name == "answers":
            return SimpleNamespace(rowcount=0)

        user_id = self._where_value(stmt, "id")
        value = next(iter(stmt._values.values()))
        amount = int(value.right.value)
        if value.operator.__name__ == "sub":
            rowcount = 0
            if self.user.id == user_id and int(self.user.fuel_balance or 0) >= amount:
                self.user.fuel_balance = int(self.user.fuel_balance or 0) - amount
                rowcount = 1
            self.fuel_deductions.append({"user_id": user_id, "fuel_cost": amount, "rowcount": rowcount})
            return SimpleNamespace(rowcount=rowcount)
        if value.operator.__name__ == "add":
            if self.user.id == user_id:
                self.user.fuel_balance = int(self.user.fuel_balance or 0) + amount
            self.fuel_refunds.append({"user_id": user_id, "fuel_amount": amount})
            return SimpleNamespace(rowcount=1)
        raise AssertionError(f"unexpected update: {stmt}")

    def _where_value(self, stmt, field_name):
        for criterion in stmt._where_criteria:
            if criterion.left.name == field_name:
                return criterion.right.value
        raise AssertionError(f"missing where value for {field_name}: {stmt}")


def make_user(balance=100_000):
    return SimpleNamespace(
        id="u_test",
        nickname="Tester",
        trust_level=3,
        fuel_balance=balance,
    )


def make_agent(agent_id, review_rules=None, user_id="u_owner", name=None):
    return SimpleNamespace(
        id=agent_id,
        name=name or agent_id,
        user_id=user_id,
        review_rules=review_rules or {"auto_trust_level": 2, "auto_tag_match": True},
    )


def make_direct_agent(agent_id, service_mode="direct_only", visibility="public", status="online"):
    return SimpleNamespace(
        id=agent_id,
        name=agent_id,
        user_id="u_owner",
        status=status,
        visibility=visibility,
        service_mode=service_mode,
        daily_quota_config={"max": 50, "auto_threshold": 40},
        service_rules={},
        review_rules={"auto_trust_level": 2, "auto_tag_match": True},
        tags=["AI"],
        description="",
        repute_score=4.0,
        total_answers=3,
        approval_rate=1.0,
    )


class FakeListResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class DirectTargetDB:
    def __init__(self, agents):
        self.calls = 0
        self.agents = agents

    async def execute(self, stmt):
        self.calls += 1
        if self.calls == 1:
            return FakeListResult(self.agents)
        return FakeListResult([])


class FeedbackResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_resolve_question_targets_allows_direct_only_agents_when_explicit(monkeypatch):
    agent = make_direct_agent("a_direct", service_mode="direct_only")
    db = DirectTargetDB([agent])

    async def fake_check_quota(db_arg, agent_id, quota_config):
        return "ok", 0

    monkeypatch.setattr(questions, "check_quota", fake_check_quota)

    matched = await questions.resolve_question_targets(
        db,
        questions.CreateQuestionReq(title="Ask", agent_ids=["a_direct"], max_responders=1),
        viewer_id="u_viewer",
    )

    assert matched[0][0] is agent
    assert matched[0][2] == "direct"
    assert matched[0][3] == "ok"


@pytest.mark.asyncio
async def test_resolve_question_targets_rejects_stopped_agents(monkeypatch):
    agent = make_direct_agent("a_stopped", service_mode="stopped")
    db = DirectTargetDB([agent])

    async def fake_check_quota(db_arg, agent_id, quota_config):
        return "ok", 0

    monkeypatch.setattr(questions, "check_quota", fake_check_quota)

    with pytest.raises(Exception) as exc_info:
        await questions.resolve_question_targets(
            db,
            questions.CreateQuestionReq(title="Ask", agent_ids=["a_stopped"], max_responders=1),
            viewer_id="u_viewer",
        )

    assert "不提供服务" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_question_zero_push_reserves_then_refunds_all(monkeypatch):
    user = make_user()
    db = FakeDB(user)
    agent = make_agent("a_zero")

    async def fake_match_agents(db_arg, tags, max_responders, title="", body="", viewer_id=None):
        return [(agent, 1.0, "exact", "ok")]

    async def fake_push_question(agent_id, payload):
        return False

    async def fail_increment_usage(db_arg, agent_id):
        raise AssertionError("quota must not increment when push fails")

    monkeypatch.setattr(questions, "match_agents", fake_match_agents)
    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)
    monkeypatch.setattr(questions, "increment_usage", fail_increment_usage)

    res = await questions.create_question(
        questions.CreateQuestionReq(title="Zero push", tags=["rust"], max_responders=1),
        user_payload={"sub": user.id},
        db=db,
    )

    assert res["matched_count"] == 1
    assert res["pushed_count"] == 0
    assert res["fuel_cost"] == 0
    assert res["estimated_fuel_cost"] == 0
    assert user.fuel_balance == 100_000
    assert db.fuel_deductions == [
        {"user_id": user.id, "fuel_cost": questions.AVG_TOKENS_PER_ANSWER, "rowcount": 1}
    ]
    assert db.fuel_refunds == [
        {"user_id": user.id, "fuel_amount": questions.AVG_TOKENS_PER_ANSWER}
    ]


@pytest.mark.asyncio
async def test_create_question_partial_push_reserves_max_and_refunds_undelivered(monkeypatch):
    user = make_user()
    db = FakeDB(user)
    agents = [make_agent("a_ok"), make_agent("a_fail")]
    incremented = []
    pushed_payloads = []

    async def fake_match_agents(db_arg, tags, max_responders, title="", body="", viewer_id=None):
        return [
            (agents[0], 1.0, "exact", "ok"),
            (agents[1], 1.0, "exact", "ok"),
        ]

    async def fake_push_question(agent_id, payload):
        pushed_payloads.append((agent_id, payload))
        return agent_id == "a_ok"

    async def fake_increment_usage(db_arg, agent_id):
        incremented.append(agent_id)
        return len(incremented)

    monkeypatch.setattr(questions, "match_agents", fake_match_agents)
    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)
    monkeypatch.setattr(questions, "increment_usage", fake_increment_usage)

    res = await questions.create_question(
        questions.CreateQuestionReq(title="Partial push", tags=["rust"], max_responders=2),
        user_payload={"sub": user.id},
        db=db,
    )

    assert res["matched_count"] == 2
    assert res["pushed_count"] == 1
    assert res["fuel_cost"] == questions.AVG_TOKENS_PER_ANSWER
    assert res["estimated_fuel_cost"] == questions.AVG_TOKENS_PER_ANSWER
    assert user.fuel_balance == 100_000 - questions.AVG_TOKENS_PER_ANSWER
    assert incremented == ["a_ok"]
    assert [(agent_id, payload["conversation_id"], payload["turn_type"], payload["context_mode"])
            for agent_id, payload in pushed_payloads] == [
        ("a_ok", "conv_q_test_a_ok", "root", "root"),
        ("a_fail", "conv_q_test_a_fail", "root", "root"),
    ]
    assert db.fuel_deductions == [
        {"user_id": user.id, "fuel_cost": 2 * questions.AVG_TOKENS_PER_ANSWER, "rowcount": 1}
    ]
    assert db.fuel_refunds == [
        {"user_id": user.id, "fuel_amount": questions.AVG_TOKENS_PER_ANSWER}
    ]


@pytest.mark.asyncio
async def test_create_direct_question_notifies_owner_for_successful_delivery(monkeypatch):
    user = make_user()
    db = FakeDB(user)
    agent = make_agent("a_direct", user_id="u_owner", name="Direct Agent")
    owner = SimpleNamespace(id="u_owner", notification_prefs={"direct_question": True})

    async def fake_resolve_question_targets(db_arg, req, viewer_id):
        return [(agent, 1.0, "direct", "ok")]

    async def fake_push_question(agent_id, payload):
        return True

    async def fake_increment_usage(db_arg, agent_id):
        return 1

    async def fake_maybe_create_notification(db_arg, user_id, pref_key, notif_type, title, body="", ref_id=None):
        assert user_id == "u_owner"
        assert pref_key == "direct_question"
        assert notif_type == "direct_question"
        assert ref_id == "q_test"
        db_arg.add(SimpleNamespace(user_id=user_id, type=notif_type, title=title, body=body, ref_id=ref_id))

    monkeypatch.setattr(questions, "resolve_question_targets", fake_resolve_question_targets)
    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)
    monkeypatch.setattr(questions, "increment_usage", fake_increment_usage)
    monkeypatch.setattr(questions, "get_user_for_notification", lambda db_arg, user_id: owner, raising=False)
    monkeypatch.setattr(questions, "maybe_create_notification", fake_maybe_create_notification, raising=False)

    res = await questions.create_question(
        questions.CreateQuestionReq(title="Direct ask", agent_ids=["a_direct"], max_responders=1),
        user_payload={"sub": user.id},
        db=db,
    )

    assert res["pushed_count"] == 1
    notifications = [item for item in db.added if getattr(item, "type", None) == "direct_question"]
    assert len(notifications) == 1
    assert "Direct ask" in notifications[0].body


@pytest.mark.asyncio
async def test_billing_deduct_zero_is_noop():
    user = make_user()
    db = FakeDB(user)

    assert await billing.deduct_fuel_if_available(db, user.id, 0) is True

    assert user.fuel_balance == 100_000
    assert db.fuel_deductions == []


def test_record_fuel_ledger_skips_zero_amounts():
    db = SimpleNamespace(added=[], add=lambda obj: db.added.append(obj))

    entry = billing.record_fuel_ledger(
        db,
        user_id="u_test",
        amount=0,
        direction="debit",
        event_type="question_reserved",
    )

    assert entry is None
    assert db.added == []


def test_record_fuel_ledger_records_context():
    db = SimpleNamespace(added=[], add=lambda obj: db.added.append(obj))

    entry = billing.record_fuel_ledger(
        db,
        user_id="u_test",
        amount=2000,
        direction="debit",
        event_type="question_reserved",
        question_id="q_test",
        answer_id="ans_test",
        agent_id="a_test",
    )

    assert entry is db.added[0]
    assert entry.user_id == "u_test"
    assert entry.amount == 2000
    assert entry.direction == "debit"
    assert entry.event_type == "question_reserved"
    assert entry.question_id == "q_test"
    assert entry.answer_id == "ans_test"
    assert entry.agent_id == "a_test"


@pytest.mark.asyncio
async def test_billing_refund_zero_is_noop():
    user = make_user()
    db = FakeDB(user)

    await billing.refund_fuel(db, user.id, 0)

    assert user.fuel_balance == 100_000
    assert db.fuel_refunds == []


@pytest.mark.asyncio
async def test_build_question_match_explanations_includes_answer_routing_metadata():
    q = SimpleNamespace(
        id="q_test",
        title="AI 系统设计",
        body="需要架构建议",
        tags=["AI", "系统设计"],
        max_responders=1,
        matched_agent_ids=["a_test"],
    )
    agent = SimpleNamespace(
        id="a_test",
        name="RouterSmith",
        agent_type="hermes",
        tags=["AI", "系统设计"],
        description="擅长系统架构",
        repute_score=4.5,
        total_answers=10,
        approval_rate=0.8,
        status="online",
        review_rules={"agentmint_readiness": {"state": "ready"}},
    )
    answer = SimpleNamespace(
        agent_id="a_test",
        request_id="req_q_test_a_test",
        status="pushed",
        review_method="auto",
    )

    class ExplanationDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            return FakeListResult([agent] if self.calls == 1 else [answer])

    explanations = await questions.build_question_match_explanations(ExplanationDB(), q)

    assert explanations[0]["request_id"] == "req_q_test_a_test"
    assert explanations[0]["answer_status"] == "pushed"
    assert explanations[0]["review_method"] == "auto"


@pytest.mark.asyncio
async def test_submit_feedback_updates_agent_learned_profile():
    answer = SimpleNamespace(id="ans_test", question_id="q_test", agent_id="a_test", status="approved")
    existing = SimpleNamespace(id="fb_test", vote="up", comment="", created_at=datetime.utcnow())
    agent = SimpleNamespace(id="a_test", repute_score=4.0, review_rules={
        "learned_profile": {"positive_feedback": 1, "positive_tags": ["魔兽世界"]}
    })
    question = SimpleNamespace(id="q_test", tags=["魔兽世界", "硬核模式"])

    class FeedbackDB:
        def __init__(self):
            self.calls = 0
            self.commits = 0

        async def execute(self, stmt):
            self.calls += 1
            values = [answer, existing, agent, question]
            return FeedbackResult(values[self.calls - 1])

        async def commit(self):
            self.commits += 1

    db = FeedbackDB()

    out = await questions.submit_feedback(
        "q_test",
        "ans_test",
        questions.FeedbackReq(vote="down", comment="不准确"),
        user_payload={"sub": "u_test"},
        db=db,
    )

    learned = agent.review_rules["learned_profile"]
    assert out["vote"] == "down"
    assert learned["positive_feedback"] == 0
    assert learned["negative_feedback"] == 1
    assert learned["negative_tags"] == ["魔兽世界", "硬核模式"]
    assert db.commits == 1
