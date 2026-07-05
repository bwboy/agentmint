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

    def scalar(self):
        return self.value


class FakeDB:
    def __init__(self, user, scalar_values=None):
        self.user = user
        self.scalar_values = list(scalar_values or [])
        self.added = []
        self.commits = 0
        self.flushed = 0
        self.refreshed = []
        self.fuel_deductions = []
        self.fuel_refunds = []

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            return self._execute_update(stmt)
        entity = stmt.column_descriptions[0].get("entity") if getattr(stmt, "column_descriptions", None) else None
        if getattr(entity, "__name__", None) == "User":
            return FakeScalarResult(self.user)
        if self.scalar_values:
            return FakeScalarResult(self.scalar_values.pop(0))
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
            if amount <= 0:
                return SimpleNamespace(rowcount=1)
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


def test_question_public_payload_includes_reward_settlement_fields():
    q = SimpleNamespace(
        id="q_test",
        title="Reward model",
        body="",
        tags=["AI"],
        visibility="private",
        deadline_at=datetime.utcnow(),
        max_responders=4,
        matched_agent_ids=["a1", "a2"],
        fuel_cost=0,
        status="open",
        created_at=datetime.utcnow(),
        estimated_fuel_per_answer=900,
        base_cap_multiplier=1.5,
        base_fuel_reserved=3600,
        base_fuel_spent=0,
        reward_fuel=500,
        reward_status="pending",
        reward_answer_id=None,
        reward_awarded_at=None,
        reward_auto_award_after=datetime.utcnow(),
    )

    out = questions.question_public_payload(q, "Tester", 3, answer_count=0)

    assert out["visibility"] == "private"
    assert out["estimated_fuel_per_answer"] == 900
    assert out["base_cap_multiplier"] == 1.5
    assert out["base_fuel_reserved"] == 3600
    assert out["base_fuel_spent"] == 0
    assert out["reward_fuel"] == 500
    assert out["reward_status"] == "pending"
    assert out["reward_answer_id"] is None


def test_my_agent_answer_serialization_includes_feedback_reason_summary():
    answer = SimpleNamespace(
        id="ans_test",
        question_id="q_test",
        content={"text": "回答内容"},
        model="gpt-test",
        usage={"total_tokens": 1200},
        turn_type="root",
        owner_quality_mark=None,
        created_at=datetime.utcnow(),
    )
    question = SimpleNamespace(id="q_test", root_question_id=None, title="需要主人关注的问题")
    agent = SimpleNamespace(id="a_test", name="测试 Agent")

    out = questions.serialize_my_agent_answer(
        answer,
        question,
        agent,
        supplements=[],
        vote_summary={"up": 0, "down": 2},
        feedback_reason_summary={"stale": 1, "owner_review": 2},
    )

    assert out["feedback_reason_summary"] == {"stale": 1, "owner_review": 2}
    assert out["quality_signals"]["feedback_reasons"] == {"stale": 1, "owner_review": 2}
    assert "feedback_reason_stale" in out["quality_signals"]["reasons"]
    assert "feedback_reason_owner_review" in out["quality_signals"]["reasons"]


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


class OneOrNoneResult:
    def __init__(self, value):
        self.value = value

    def one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_private_question_access_allows_asker_and_assigned_agent_owner():
    q = SimpleNamespace(
        id="q_private",
        asker_id="u_asker",
        visibility="private",
        matched_agent_ids=["a_owner"],
    )

    class AccessDB:
        def __init__(self, agent_owner_id=None):
            self.agent_owner_id = agent_owner_id
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            if self.calls == 1 and self.agent_owner_id:
                return FakeListResult([SimpleNamespace(id="a_owner", user_id=self.agent_owner_id)])
            return FakeListResult([])

    assert await questions.can_view_question(AccessDB(), q, {"sub": "u_asker"}) is True
    assert await questions.can_view_question(AccessDB(agent_owner_id="u_owner"), q, {"sub": "u_owner"}) is True
    assert await questions.can_view_question(AccessDB(agent_owner_id="u_owner"), q, {"sub": "u_other"}) is False


@pytest.mark.asyncio
async def test_public_question_access_allows_anonymous_viewer():
    q = SimpleNamespace(id="q_public", asker_id="u_asker", visibility="public", matched_agent_ids=[])

    assert await questions.can_view_question(FakeDB(make_user()), q, None) is True


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
async def test_estimate_answer_fuel_uses_recent_two_day_average_usage():
    class EstimateDB:
        async def execute(self, stmt):
            return SimpleNamespace(scalar=lambda: 1000)

    estimated = await questions.estimate_answer_fuel_per_answer(EstimateDB())

    assert estimated == 1000


@pytest.mark.asyncio
async def test_question_fuel_estimate_endpoint_returns_preauthorization_fields():
    class EstimateDB:
        async def execute(self, stmt):
            return SimpleNamespace(scalar=lambda: 1000)

    out = await questions.question_fuel_estimate(EstimateDB())

    assert out == {
        "estimated_fuel_per_answer": 1000,
        "base_cap_multiplier": 1.5,
        "preauthorized_fuel_per_answer": 1500,
        "sample_window_days": 2,
    }


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
        {"user_id": user.id, "fuel_cost": 1350, "rowcount": 1}
    ]
    assert db.fuel_refunds == [
        {"user_id": user.id, "fuel_amount": 1350}
    ]


@pytest.mark.asyncio
async def test_create_question_reserves_base_estimate_and_reward(monkeypatch):
    user = make_user()
    db = FakeDB(user, scalar_values=[1000])
    agents = [make_agent("a_one"), make_agent("a_two")]

    async def fake_resolve_question_targets(db_arg, req, viewer_id):
        return [(agents[0], 1.0, "direct", "ok"), (agents[1], 1.0, "direct", "ok")]

    async def fake_push_question(agent_id, payload):
        return False

    monkeypatch.setattr(questions, "resolve_question_targets", fake_resolve_question_targets)
    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)

    res = await questions.create_question(
        questions.CreateQuestionReq(
            title="Reward ask",
            max_responders=2,
            visibility="private",
            estimated_fuel_per_answer=99999,
            reward_fuel=500,
        ),
        user_payload={"sub": user.id},
        db=db,
    )

    created_question = next(item for item in db.added if item.__class__.__name__ == "Question")
    ledgers = [item for item in db.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert res["visibility"] == "private"
    assert res["estimated_fuel_per_answer"] == 1000
    assert res["base_fuel_reserved"] == 3000
    assert res["reward_fuel"] == 500
    assert res["reward_status"] == "pending"
    assert created_question.base_fuel_reserved == 3000
    assert created_question.reward_fuel == 500
    assert user.fuel_balance == 100_000 - 500
    assert db.fuel_deductions == [
        {"user_id": user.id, "fuel_cost": 3500, "rowcount": 1}
    ]
    assert db.fuel_refunds == [
        {"user_id": user.id, "fuel_amount": 3000}
    ]
    assert [(entry.direction, entry.event_type, entry.amount) for entry in ledgers] == [
        ("debit", "base_reserved", 3000),
        ("debit", "reward_reserved", 500),
        ("credit", "base_refunded", 3000),
    ]


@pytest.mark.asyncio
async def test_create_question_reserves_platform_estimate_with_authorization_multiplier(monkeypatch):
    user = make_user()
    db = FakeDB(user, scalar_values=[1000])
    agents = [make_agent("a_one"), make_agent("a_two"), make_agent("a_three")]

    async def fake_resolve_question_targets(db_arg, req, viewer_id):
        return [(agent, 1.0, "direct", "ok") for agent in agents]

    async def fake_push_question(agent_id, payload):
        return True

    async def fake_increment_usage(db_arg, agent_id):
        return 1

    monkeypatch.setattr(questions, "resolve_question_targets", fake_resolve_question_targets)
    monkeypatch.setattr(questions.hub, "push_question", fake_push_question)
    monkeypatch.setattr(questions, "increment_usage", fake_increment_usage)

    res = await questions.create_question(
        questions.CreateQuestionReq(
            title="Platform estimated ask",
            max_responders=3,
            estimated_fuel_per_answer=99999,
        ),
        user_payload={"sub": user.id},
        db=db,
    )

    created_question = next(item for item in db.added if item.__class__.__name__ == "Question")
    assert res["estimated_fuel_per_answer"] == 1000
    assert res["base_fuel_reserved"] == 4500
    assert res["fuel_cost"] == 3000
    assert created_question.base_cap_multiplier == 1.5
    assert created_question.base_fuel_reserved == 4500
    assert user.fuel_balance == 100_000 - 4500
    assert db.fuel_deductions == [
        {"user_id": user.id, "fuel_cost": 4500, "rowcount": 1}
    ]
    assert db.fuel_refunds == []


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
    assert res["fuel_cost"] == questions.DEFAULT_ESTIMATED_FUEL_PER_ANSWER
    assert res["estimated_fuel_cost"] == questions.DEFAULT_ESTIMATED_FUEL_PER_ANSWER
    assert user.fuel_balance == 100_000 - 1350
    assert incremented == ["a_ok"]
    assert [(agent_id, payload["conversation_id"], payload["turn_type"], payload["context_mode"])
            for agent_id, payload in pushed_payloads] == [
        ("a_ok", "conv_q_test_a_ok", "root", "root"),
        ("a_fail", "conv_q_test_a_fail", "root", "root"),
    ]
    assert db.fuel_deductions == [
        {"user_id": user.id, "fuel_cost": 2700, "rowcount": 1}
    ]
    assert db.fuel_refunds == [
        {"user_id": user.id, "fuel_amount": 1350}
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
    existing = SimpleNamespace(id="fb_test", vote="up", comment="", feedback_reasons=[], created_at=datetime.utcnow())
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


@pytest.mark.asyncio
async def test_submit_feedback_stores_structured_reasons_and_learning_signals():
    answer = SimpleNamespace(id="ans_test", question_id="q_test", agent_id="a_test", status="approved")
    agent = SimpleNamespace(id="a_test", user_id="u_test", repute_score=4.0, review_rules={})
    question = SimpleNamespace(id="q_test", title="真实问题", tags=["魔兽世界", "硬核模式"])

    class FeedbackDB:
        def __init__(self):
            self.calls = 0
            self.added = []
            self.commits = 0

        async def execute(self, stmt):
            self.calls += 1
            values = [answer, None, agent, question]
            return FeedbackResult(values[self.calls - 1])

        def add(self, obj):
            self.added.append(obj)
            obj.id = "fb_new"
            obj.created_at = datetime.utcnow()

        async def commit(self):
            self.commits += 1

    db = FeedbackDB()

    out = await questions.submit_feedback(
        "q_test",
        "ans_test",
        questions.FeedbackReq(
            vote="down",
            comment="版本过期且没有来源",
            reasons=["stale", "needs_sources", "owner_review"],
        ),
        user_payload={"sub": "u_test"},
        db=db,
    )

    feedback = db.added[0]
    learned = agent.review_rules["learned_profile"]
    assert out["reasons"] == ["stale", "needs_sources", "owner_review"]
    assert feedback.feedback_reasons == ["stale", "needs_sources", "owner_review"]
    assert "反馈:过期" in learned["negative_tags"]
    assert "反馈:需要来源" in learned["negative_tags"]
    assert "反馈:建议主人修正" in learned["negative_tags"]
