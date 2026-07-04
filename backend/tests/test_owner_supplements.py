from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import questions


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class RowResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def scalars(self):
        return self


class SupplementDB:
    def __init__(self, values):
        self.values = list(values)
        self.added = []
        self.commits = 0
        self.flushed = 0

    async def execute(self, stmt):
        value = self.values.pop(0)
        if isinstance(value, list):
            return RowResult(value)
        return ScalarResult(value)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1
        for obj in self.added:
            if obj.__class__.__name__ == "AnswerOwnerSupplement" and getattr(obj, "id", None) is None:
                obj.id = "os_test"

    async def commit(self):
        self.commits += 1


def make_question(**overrides):
    data = {
        "id": "q_test",
        "asker_id": "u_asker",
        "title": "Question title",
        "body": "",
        "tags": [],
        "visibility": "public",
        "matched_agent_ids": ["a_test"],
        "deadline_at": datetime.utcnow(),
        "max_responders": 1,
        "fuel_cost": 0,
        "status": "open",
        "created_at": datetime.utcnow(),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_answer(**overrides):
    data = {
        "id": "ans_test",
        "question_id": "q_test",
        "agent_id": "a_test",
        "status": "approved",
        "turn_type": "root",
        "content": {"text": "Agent answer"},
        "created_at": datetime.utcnow(),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_agent(**overrides):
    data = {"id": "a_test", "name": "Agent", "user_id": "u_owner", "agent_type": "hermes"}
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_request_owner_supplement_creates_pending_item_and_notifies_owner(monkeypatch):
    question = make_question()
    answer = make_answer()
    agent = make_agent()
    db = SupplementDB([question, answer, agent])
    notifications = []

    async def fake_maybe_create_notification(*args, **kwargs):
        notifications.append((args, kwargs))

    monkeypatch.setattr(questions, "maybe_create_notification", fake_maybe_create_notification)

    out = await questions.request_owner_supplement(
        "q_test",
        "ans_test",
        questions.OwnerSupplementRequestReq(prompt="请主人补充真实经验"),
        user_payload={"sub": "u_asker", "nickname": "Asker"},
        db=db,
    )

    supplement = next(item for item in db.added if item.__class__.__name__ == "AnswerOwnerSupplement")
    assert out["id"] == "os_test"
    assert out["status"] == "pending"
    assert supplement.requester_id == "u_asker"
    assert supplement.owner_id == "u_owner"
    assert supplement.prompt == "请主人补充真实经验"
    assert db.commits == 1
    assert notifications[0][0][1] == "u_owner"
    assert notifications[0][0][3] == "owner_supplement_requested"
    assert notifications[0][1]["ref_id"] == "q_test"


@pytest.mark.asyncio
async def test_request_owner_supplement_rejects_non_asker():
    db = SupplementDB([make_question(asker_id="u_other"), make_answer(), make_agent()])

    with pytest.raises(HTTPException) as err:
        await questions.request_owner_supplement(
            "q_test",
            "ans_test",
            questions.OwnerSupplementRequestReq(prompt="请补充"),
            user_payload={"sub": "u_asker"},
            db=db,
        )

    assert err.value.status_code == 403


@pytest.mark.asyncio
async def test_request_owner_supplement_accepts_followup_answer_in_root_thread(monkeypatch):
    root = make_question(id="q_root")
    answer = make_answer(id="ans_follow", question_id="q_follow", turn_type="followup")
    followup = make_question(id="q_follow", root_question_id="q_root")
    agent = make_agent()
    db = SupplementDB([root, answer, followup, agent])

    async def fake_maybe_create_notification(*args, **kwargs):
        return None

    monkeypatch.setattr(questions, "maybe_create_notification", fake_maybe_create_notification)

    out = await questions.request_owner_supplement(
        "q_root",
        "ans_follow",
        questions.OwnerSupplementRequestReq(prompt="请补充追问里的经验"),
        user_payload={"sub": "u_asker", "nickname": "Asker"},
        db=db,
    )

    supplement = next(item for item in db.added if item.__class__.__name__ == "AnswerOwnerSupplement")
    assert out["answer_id"] == "ans_follow"
    assert supplement.question_id == "q_root"
    assert supplement.answer_id == "ans_follow"
    assert supplement.prompt == "请补充追问里的经验"


@pytest.mark.asyncio
async def test_owner_can_submit_supplement_response():
    question = make_question()
    agent = make_agent()
    supplement = SimpleNamespace(
        id="os_test",
        answer_id="ans_test",
        question_id="q_test",
        agent_id="a_test",
        owner_id="u_owner",
        status="pending",
        response="",
        supplement_type="experience",
        responded_at=None,
    )
    db = SupplementDB([supplement, question, agent])

    out = await questions.respond_owner_supplement(
        "os_test",
        questions.OwnerSupplementRespondReq(response="我的补充判断", supplement_type="risk_note"),
        user_payload={"sub": "u_owner"},
        db=db,
    )

    assert out["status"] == "answered"
    assert supplement.status == "answered"
    assert supplement.response == "我的补充判断"
    assert supplement.supplement_type == "risk_note"
    assert isinstance(supplement.responded_at, datetime)
    assert agent.review_rules["learned_profile"]["owner_supplement_count"] == 1
    assert agent.review_rules["learned_profile"]["owner_supplement_types"]["risk_note"] == 1
    assert db.commits == 1


@pytest.mark.asyncio
async def test_owner_can_add_self_supplement_and_notify_asker(monkeypatch):
    question = make_question()
    answer = make_answer()
    agent = make_agent()
    db = SupplementDB([question, answer, agent])
    notifications = []

    async def fake_maybe_create_notification(*args, **kwargs):
        notifications.append((args, kwargs))

    monkeypatch.setattr(questions, "maybe_create_notification", fake_maybe_create_notification)

    out = await questions.create_owner_self_supplement(
        "q_test",
        "ans_test",
        questions.OwnerSupplementSelfReq(response="主人主动补充：这里要注意版本差异", supplement_type="version_update"),
        user_payload={"sub": "u_owner", "nickname": "Owner"},
        db=db,
    )

    supplement = next(item for item in db.added if item.__class__.__name__ == "AnswerOwnerSupplement")
    assert out["status"] == "answered"
    assert out["prompt"] == "主人主动补充"
    assert supplement.requester_id == "u_owner"
    assert supplement.owner_id == "u_owner"
    assert supplement.supplement_type == "version_update"
    assert supplement.response == "主人主动补充：这里要注意版本差异"
    assert isinstance(supplement.responded_at, datetime)
    assert agent.review_rules["learned_profile"]["owner_supplement_count"] == 1
    assert agent.review_rules["learned_profile"]["owner_supplement_types"]["version_update"] == 1
    assert notifications[0][0][1] == "u_asker"
    assert notifications[0][0][3] == "owner_supplement_added"
    assert notifications[0][1]["ref_id"] == "q_test"


@pytest.mark.asyncio
async def test_my_agent_answers_lists_owner_answers_with_supplement_summary():
    answer = make_answer(id="ans_test")
    question = make_question(id="q_test", title="真实问题")
    agent = make_agent(id="a_test", name="Owner Agent")
    supplement = SimpleNamespace(
        id="os_test",
        question_id="q_test",
        answer_id="ans_test",
        agent_id="a_test",
        requester_id="u_asker",
        owner_id="u_owner",
        prompt="请补充",
        response="",
        status="pending",
        created_at=datetime(2026, 7, 4, 12, 0, 0),
        responded_at=None,
    )
    db = SupplementDB([
        [(answer, question, agent)],
        [supplement],
    ])

    out = await questions.my_agent_answers(user_payload={"sub": "u_owner"}, db=db)

    item = out["data"][0]
    assert item["id"] == "ans_test"
    assert item["question_title"] == "真实问题"
    assert item["agent_name"] == "Owner Agent"
    assert item["owner_supplement_pending_count"] == 1
    assert item["owner_supplement_answered_count"] == 0
    assert item["owner_supplements"][0]["prompt"] == "请补充"


@pytest.mark.asyncio
async def test_owner_can_edit_mark_high_value_and_withdraw_supplement():
    supplement = SimpleNamespace(
        id="os_test",
        question_id="q_test",
        answer_id="ans_test",
        agent_id="a_test",
        requester_id="u_owner",
        owner_id="u_owner",
        prompt="主人主动补充",
        response="旧内容",
        supplement_type="experience",
        status="answered",
        is_high_value=False,
        edited_at=None,
        withdrawn_at=None,
        responded_at=datetime.utcnow(),
    )
    db = SupplementDB([supplement, supplement])

    edited = await questions.update_owner_supplement(
        "os_test",
        questions.OwnerSupplementUpdateReq(
            response="新内容",
            supplement_type="correction",
            is_high_value=True,
        ),
        user_payload={"sub": "u_owner"},
        db=db,
    )

    assert edited["response"] == "新内容"
    assert edited["supplement_type"] == "correction"
    assert edited["is_high_value"] is True
    assert isinstance(supplement.edited_at, datetime)

    withdrawn = await questions.withdraw_owner_supplement(
        "os_test",
        user_payload={"sub": "u_owner"},
        db=db,
    )

    assert withdrawn["status"] == "withdrawn"
    assert supplement.status == "withdrawn"
    assert isinstance(supplement.withdrawn_at, datetime)
    assert db.commits == 2


@pytest.mark.asyncio
async def test_asker_can_react_and_accept_owner_supplement(monkeypatch):
    question = make_question()
    supplement = SimpleNamespace(
        id="os_test",
        question_id="q_test",
        answer_id="ans_test",
        agent_id="a_test",
        requester_id="u_owner",
        owner_id="u_owner",
        prompt="主人主动补充",
        response="主人补充",
        supplement_type="experience",
        status="answered",
        is_high_value=False,
        asker_reaction=None,
        accepted_at=None,
        created_at=datetime.utcnow(),
        responded_at=datetime.utcnow(),
    )
    db = SupplementDB([supplement, question])
    notifications = []

    async def fake_maybe_create_notification(*args, **kwargs):
        notifications.append((args, kwargs))

    monkeypatch.setattr(questions, "maybe_create_notification", fake_maybe_create_notification)

    out = await questions.react_owner_supplement(
        "os_test",
        questions.OwnerSupplementReactionReq(reaction="like", accepted=True),
        user_payload={"sub": "u_asker", "nickname": "Asker"},
        db=db,
    )

    assert out["asker_reaction"] == "like"
    assert out["accepted_at"] is not None
    assert supplement.is_high_value is True
    assert notifications[0][0][1] == "u_owner"
    assert notifications[0][0][3] == "owner_supplement_accepted"


@pytest.mark.asyncio
async def test_remind_overdue_owner_supplements_notifies_once(monkeypatch):
    old_pending = SimpleNamespace(
        id="os_old",
        question_id="q_test",
        answer_id="ans_test",
        agent_id="a_test",
        requester_id="u_asker",
        owner_id="u_owner",
        prompt="请补充",
        response="",
        supplement_type="experience",
        status="pending",
        created_at=datetime.utcnow() - timedelta(days=2),
        reminded_at=None,
    )
    db = SupplementDB([[old_pending]])
    notifications = []

    async def fake_maybe_create_notification(*args, **kwargs):
        notifications.append((args, kwargs))

    monkeypatch.setattr(questions, "maybe_create_notification", fake_maybe_create_notification)

    out = await questions.remind_overdue_owner_supplements(user_payload={"sub": "u_owner"}, db=db)

    assert out["reminded"] == 1
    assert isinstance(old_pending.reminded_at, datetime)
    assert notifications[0][0][1] == "u_owner"
    assert notifications[0][0][3] == "owner_supplement_overdue"
    assert db.commits == 1


def test_group_owner_supplements_by_answer_serializes_visible_fields():
    supplement = SimpleNamespace(
        id="os_test",
        answer_id="ans_test",
        requester_id="u_asker",
        owner_id="u_owner",
        prompt="请补充",
        response="主人补充",
        status="answered",
        created_at=datetime(2026, 7, 4, 12, 0, 0),
        responded_at=datetime(2026, 7, 4, 12, 5, 0),
    )

    grouped = questions.group_owner_supplements_by_answer([supplement])

    assert grouped["ans_test"][0]["prompt"] == "请补充"
    assert grouped["ans_test"][0]["response"] == "主人补充"
    assert grouped["ans_test"][0]["status"] == "answered"
