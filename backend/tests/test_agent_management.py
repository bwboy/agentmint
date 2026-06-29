from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import agents


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class ListResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class FakeDB:
    def __init__(self, agent, answer_count=0, connectors=None):
        self.results = [
            ScalarResult(agent),
            ScalarResult(answer_count),
            ListResult(connectors or []),
        ]
        self.deleted = []
        self.commits = 0

    async def execute(self, stmt):
        return self.results.pop(0)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_delete_agent_removes_owned_agent_without_answers():
    agent = SimpleNamespace(id="a_delete", user_id="u_owner")
    connector = SimpleNamespace(id="conn_delete")
    db = FakeDB(agent, answer_count=0, connectors=[connector])

    res = await agents.delete_agent(
        "a_delete",
        user={"sub": "u_owner"},
        db=db,
    )

    assert res.status_code == 204
    assert db.deleted == [connector, agent]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_delete_agent_rejects_agents_with_answer_history():
    agent = SimpleNamespace(id="a_history", user_id="u_owner")
    db = FakeDB(agent, answer_count=2)

    with pytest.raises(HTTPException) as exc_info:
        await agents.delete_agent(
            "a_history",
            user={"sub": "u_owner"},
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert "已有回答" in exc_info.value.detail
    assert db.deleted == []
    assert db.commits == 0
