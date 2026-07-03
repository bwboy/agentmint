from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services import rewards


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class RowcountResult:
    rowcount = 1


class RewardDB:
    def __init__(self, values):
        self.values = list(values)
        self.added = []
        self.commits = 0

    async def execute(self, stmt):
        if not self.values:
            return Result(None)
        return Result(self.values.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def make_question(**patch):
    data = dict(
        id="q_reward",
        asker_id="u_asker",
        reward_fuel=500,
        reward_status="pending",
        reward_answer_id=None,
        reward_awarded_at=None,
        root_question_id=None,
    )
    data.update(patch)
    return SimpleNamespace(**data)


def make_answer(**patch):
    data = dict(
        id="ans_reward",
        question_id="q_reward",
        agent_id="a_reward",
        status="approved",
        turn_type="root",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        reviewed_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    data.update(patch)
    return SimpleNamespace(**data)


def make_agent(**patch):
    data = dict(id="a_reward", user_id="u_owner", fuel_earned=100)
    data.update(patch)
    return SimpleNamespace(**data)


class RowsResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


@pytest.mark.asyncio
async def test_award_reward_credits_owner_and_records_ledger():
    question = make_question()
    answer = make_answer()
    agent = make_agent()
    owner = SimpleNamespace(id="u_owner", fuel_balance=1000)
    db = RewardDB([question, answer, agent, owner])

    out = await rewards.award_reward_to_answer(db, "q_reward", "ans_reward", "u_asker")

    ledger = [item for item in db.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert out is question
    assert question.reward_status == "awarded"
    assert question.reward_answer_id == "ans_reward"
    assert isinstance(question.reward_awarded_at, datetime)
    assert agent.fuel_earned == 600
    assert owner.fuel_balance == 1500
    assert len(ledger) == 1
    assert ledger[0].user_id == "u_owner"
    assert ledger[0].amount == 500
    assert ledger[0].direction == "credit"
    assert ledger[0].event_type == "reward_awarded"
    assert ledger[0].question_id == "q_reward"
    assert ledger[0].answer_id == "ans_reward"
    assert ledger[0].agent_id == "a_reward"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_award_reward_rejects_non_asker():
    db = RewardDB([make_question()])

    with pytest.raises(HTTPException) as err:
        await rewards.award_reward_to_answer(db, "q_reward", "ans_reward", "u_other")

    assert err.value.status_code == 403


@pytest.mark.asyncio
async def test_award_reward_rejects_followup_answer():
    db = RewardDB([make_question(), make_answer(turn_type="followup")])

    with pytest.raises(HTTPException) as err:
        await rewards.award_reward_to_answer(db, "q_reward", "ans_reward", "u_asker")

    assert err.value.status_code == 400
    assert "根问题回答" in err.value.detail


@pytest.mark.asyncio
async def test_award_reward_rejects_double_award():
    db = RewardDB([make_question(reward_status="awarded", reward_answer_id="ans_old")])

    with pytest.raises(HTTPException) as err:
        await rewards.award_reward_to_answer(db, "q_reward", "ans_reward", "u_asker")

    assert err.value.status_code == 400
    assert "已经分配" in err.value.detail


@pytest.mark.asyncio
async def test_auto_award_due_rewards_selects_highest_score():
    question = make_question(
        reward_auto_award_after=datetime.utcnow() - timedelta(minutes=1),
    )
    low = make_answer(id="ans_low", agent_id="a_low")
    high = make_answer(id="ans_high", agent_id="a_high", created_at=datetime(2026, 1, 1, 12, 5, 0))
    agent_high = make_agent(id="a_high", user_id="u_high", fuel_earned=0)
    owner = SimpleNamespace(id="u_high", fuel_balance=100)

    class AutoDB(RewardDB):
        def __init__(self):
            super().__init__([high, agent_high, owner])
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            if self.calls == 1:
                return RowsResult([(low, 1.0), (high, 1.0)])
            if self.calls == 2:
                return RowsResult([("ans_high", "up"), ("ans_high", "up")])
            return Result(self.values.pop(0))

    db = AutoDB()

    out = await rewards.auto_award_due_rewards(db, question)

    assert out is question
    assert question.reward_status == "auto_awarded"
    assert question.reward_answer_id == "ans_high"
    assert agent_high.fuel_earned == 500
    assert owner.fuel_balance == 600


@pytest.mark.asyncio
async def test_auto_award_due_rewards_chooses_earliest_on_tie():
    question = make_question(
        reward_auto_award_after=datetime.utcnow() - timedelta(minutes=1),
    )
    first = make_answer(id="ans_first", agent_id="a_first", created_at=datetime(2026, 1, 1, 12, 0, 0))
    later = make_answer(id="ans_later", agent_id="a_later", created_at=datetime(2026, 1, 1, 12, 10, 0))
    agent_first = make_agent(id="a_first", user_id="u_first", fuel_earned=0)
    owner = SimpleNamespace(id="u_first", fuel_balance=100)

    class AutoDB(RewardDB):
        def __init__(self):
            super().__init__([first, agent_first, owner])
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            if self.calls == 1:
                return RowsResult([(first, 2.0), (later, 2.0)])
            if self.calls == 2:
                return RowsResult([])
            return Result(self.values.pop(0))

    db = AutoDB()

    await rewards.auto_award_due_rewards(db, question)

    assert question.reward_status == "auto_awarded"
    assert question.reward_answer_id == "ans_first"


@pytest.mark.asyncio
async def test_mark_reward_auto_award_after_sets_deadline_from_first_approved_answer():
    question = make_question(reward_auto_award_after=None)
    db = RewardDB([question])

    await rewards.mark_reward_auto_award_after_first_answer(db, "q_reward", make_answer())

    assert question.reward_auto_award_after == datetime(2026, 1, 2, 12, 0, 0)
    assert db.commits == 0


@pytest.mark.asyncio
async def test_auto_award_due_rewards_refunds_expired_question_without_approved_answers():
    question = make_question(
        deadline_at=datetime.utcnow() - timedelta(minutes=1),
        reward_auto_award_after=None,
    )
    asker = SimpleNamespace(id="u_asker", fuel_balance=100)

    class RefundDB(RewardDB):
        def __init__(self):
            super().__init__([asker])
            self.calls = 0

        async def execute(self, stmt):
            self.calls += 1
            if self.calls == 1:
                return RowsResult([])
            if self.calls == 2:
                return RowcountResult()
            return Result(self.values.pop(0))

    db = RefundDB()

    out = await rewards.auto_award_due_rewards(db, question)

    ledger = [item for item in db.added if item.__class__.__name__ == "FuelLedgerEntry"]
    assert out is question
    assert question.reward_status == "refunded"
    assert ledger[0].event_type == "reward_refunded"
    assert ledger[0].direction == "credit"
    assert ledger[0].amount == 500
    assert db.commits == 1
