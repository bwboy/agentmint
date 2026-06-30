from types import SimpleNamespace
import importlib

import pytest

from services.agent_readiness import get_agent_readiness
from ws.hub import Hub, WSClient, is_readiness_probe

hub_module = importlib.import_module("ws.hub")


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(text)


def test_is_readiness_probe_matches_probe_requests_only():
    assert is_readiness_probe({"request_id": "probe_a_test_123"})
    assert is_readiness_probe({"request_id": "req_q_1_a_1"}) is False


@pytest.mark.asyncio
async def test_push_readiness_probe_marks_checking_and_sends_hidden_question(monkeypatch):
    agent = SimpleNamespace(id="a_test", review_rules={})
    commits = []

    class ScalarResult:
        def scalar_one_or_none(self):
            return agent

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            return ScalarResult()

        async def commit(self):
            commits.append(True)

    monkeypatch.setattr(hub_module, "AsyncSessionLocal", lambda: FakeSession())

    ws = FakeWebSocket()
    client = WSClient(ws, "conn_test", "a_test", "u_test", "Agent")
    hub = Hub()
    hub.clients["conn_test"] = client
    hub.agent_to_conn["a_test"] = "conn_test"

    delivered = await hub.push_readiness_probe("a_test")

    assert delivered is True
    assert get_agent_readiness(agent)["state"] == "checking"
    assert commits == [True]
    assert len(ws.sent) == 1
    assert '"type": "question"' in ws.sent[0]
    assert '"probe": true' in ws.sent[0]


@pytest.mark.asyncio
async def test_probe_answer_marks_agent_ready_without_review(monkeypatch):
    agent = SimpleNamespace(id="a_test", review_rules={})
    reviewed = []

    class ScalarResult:
        def scalar_one_or_none(self):
            return agent

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            return ScalarResult()

        async def commit(self):
            pass

    async def fake_review(agent_id, msg):
        reviewed.append((agent_id, msg))

    monkeypatch.setattr(hub_module, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("services.review.handle_uploaded_answer", fake_review)

    hub = Hub()
    client = WSClient(FakeWebSocket(), "conn_test", "a_test", "u_test", "Agent")

    await hub._dispatch(client, {
        "type": "answer",
        "request_id": "probe_a_test_123",
        "status": "success",
        "content": {"text": "OK"},
    })

    assert get_agent_readiness(agent)["state"] == "ready"
    assert reviewed == []


@pytest.mark.asyncio
async def test_pairing_required_marks_agent_with_command(monkeypatch):
    agent = SimpleNamespace(id="a_test", review_rules={})

    class ScalarResult:
        def scalar_one_or_none(self):
            return agent

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            return ScalarResult()

        async def commit(self):
            pass

    monkeypatch.setattr(hub_module, "AsyncSessionLocal", lambda: FakeSession())

    hub = Hub()
    client = WSClient(FakeWebSocket(), "conn_test", "a_test", "u_test", "Agent")

    await hub._dispatch(client, {
        "type": "pairing_required",
        "request_id": "probe_a_test_123",
        "code": "KJ5S6H25",
        "command": "hermes pairing approve agentmint KJ5S6H25",
    })

    readiness = get_agent_readiness(agent)
    assert readiness["state"] == "pairing_required"
    assert readiness["code"] == "KJ5S6H25"
    assert readiness["command"] == "hermes pairing approve agentmint KJ5S6H25"
