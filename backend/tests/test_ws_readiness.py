from types import SimpleNamespace
import importlib

import pytest

from services.agent_readiness import get_agent_readiness
from ws.hub import Hub, WSClient, is_readiness_probe

hub_module = importlib.import_module("ws.hub")


class FakeWebSocket:
    def __init__(self, fail_send=False):
        self.sent = []
        self.fail_send = fail_send

    async def send_text(self, text):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append(text)


def make_node(node_id="rn_test", user_id="u_test"):
    return SimpleNamespace(
        id=node_id,
        user_id=user_id,
        runtime_type="hermes",
        name="Test runtime",
    )


def make_binding(agent_id="a_test", node_id="rn_test"):
    return SimpleNamespace(
        agent_id=agent_id,
        runtime_node_id=node_id,
        runtime_type="hermes",
        runtime_profile="wow-profile",
        runtime_workspace="",
        knowledge_scope="private",
        status="active",
    )


def test_is_readiness_probe_matches_probe_requests_only():
    assert is_readiness_probe({"request_id": "probe_a_test_123"})
    assert is_readiness_probe({"request_id": "req_q_1_a_1"}) is False


@pytest.mark.asyncio
async def test_push_readiness_probe_marks_checking_and_sends_hidden_question(monkeypatch):
    agent = SimpleNamespace(id="a_test", review_rules={})
    binding = make_binding()
    commits = []

    class ScalarResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            statement = str(stmt)
            if "agent_runtime_bindings" in statement:
                return ScalarResult(binding)
            return ScalarResult(agent)

        async def commit(self):
            commits.append(True)

    monkeypatch.setattr(hub_module, "AsyncSessionLocal", lambda: FakeSession())

    ws = FakeWebSocket()
    client = WSClient(ws, make_node())
    hub = Hub()
    hub.clients["rn_test"] = client
    hub.agent_to_node["a_test"] = "rn_test"

    delivered = await hub.push_readiness_probe("a_test")

    assert delivered is True
    assert get_agent_readiness(agent)["state"] == "checking"
    assert commits == [True]
    assert len(ws.sent) == 1
    assert '"type": "question"' in ws.sent[0]
    assert '"probe": true' in ws.sent[0]
    assert '"agent_id": "a_test"' in ws.sent[0]
    assert '"runtime_profile": "wow-profile"' in ws.sent[0]


@pytest.mark.asyncio
async def test_push_readiness_probe_marks_error_when_send_fails(monkeypatch):
    agent = SimpleNamespace(id="a_test", review_rules={})
    binding = make_binding()

    class ScalarResult:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            statement = str(stmt)
            if "agent_runtime_bindings" in statement:
                return ScalarResult(binding)
            return ScalarResult(agent)

        async def commit(self):
            pass

    monkeypatch.setattr(hub_module, "AsyncSessionLocal", lambda: FakeSession())

    client = WSClient(FakeWebSocket(fail_send=True), make_node())
    hub = Hub()
    hub.clients["rn_test"] = client
    hub.agent_to_node["a_test"] = "rn_test"

    delivered = await hub.push_readiness_probe("a_test")

    readiness = get_agent_readiness(agent)
    assert delivered is False
    assert readiness["state"] == "error"
    assert "发送检测消息失败" in readiness["error"]


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
    client = WSClient(FakeWebSocket(), make_node())

    await hub._dispatch(client, {
        "type": "answer",
        "request_id": "probe_a_test_123",
        "agent_id": "a_test",
        "status": "success",
        "content": {"text": "OK"},
    })

    assert get_agent_readiness(agent)["state"] == "ready"
    assert reviewed == []


@pytest.mark.asyncio
async def test_probe_answer_with_pairing_text_marks_pairing_required(monkeypatch):
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
    client = WSClient(FakeWebSocket(), make_node())

    await hub._dispatch(client, {
        "type": "answer",
        "request_id": "probe_a_test_123",
        "agent_id": "a_test",
        "status": "success",
        "content": {
            "text": "Hi~ I don't recognize you yet!\n\nHere's your pairing code: KJ5S6H25\n\n"
                    "Ask the bot owner to run: hermes pairing approve agentmint KJ5S6H25"
        },
    })

    readiness = get_agent_readiness(agent)
    assert readiness["state"] == "pairing_required"
    assert readiness["code"] == "KJ5S6H25"
    assert readiness["command"] == "hermes pairing approve agentmint KJ5S6H25"


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
    client = WSClient(FakeWebSocket(), make_node())

    await hub._dispatch(client, {
        "type": "pairing_required",
        "request_id": "probe_a_test_123",
        "agent_id": "a_test",
        "code": "KJ5S6H25",
        "command": "hermes pairing approve agentmint KJ5S6H25",
    })

    readiness = get_agent_readiness(agent)
    assert readiness["state"] == "pairing_required"
    assert readiness["code"] == "KJ5S6H25"
    assert readiness["command"] == "hermes pairing approve agentmint KJ5S6H25"
