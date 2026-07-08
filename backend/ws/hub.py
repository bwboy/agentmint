"""WebSocket hub for local Agent runtime nodes.

Runtime nodes are owner machines running Hermes, OpenClaw, or another mature
Agent runtime. A node authenticates once and may serve multiple AgentMint
Agents through runtime-specific spaces such as Hermes profiles or OpenClaw
workspaces.
"""
import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select, update

from config import settings
from database import AsyncSessionLocal
from models import Agent, AgentRuntimeBinding, Answer, RuntimeNode
from services.agent_readiness import set_agent_readiness
from services.auth import verify_token_hash

PROBE_REQUEST_PREFIX = "probe_"
PAIRING_CODE_RE = re.compile(r"pairing code:\s*([A-Z0-9-]+)", re.IGNORECASE)
PAIRING_COMMAND_RE = re.compile(r"(hermes\s+pairing\s+approve\s+agentmint\s+[A-Z0-9-]+)", re.IGNORECASE)


def is_readiness_probe(msg: dict) -> bool:
    return str(msg.get("request_id") or "").startswith(PROBE_REQUEST_PREFIX)


class WSClient:
    """In-memory record for a live runtime-node connection."""

    def __init__(self, ws: WebSocket, node: RuntimeNode):
        self.ws = ws
        self.runtime_node_id = node.id
        self.user_id = node.user_id
        self.runtime_type = node.runtime_type
        self.node_name = node.name
        self.last_pong = time.monotonic()
        self.quota_snapshot: dict[str, Any] = {}

    async def send(self, msg: dict) -> bool:
        try:
            await self.ws.send_text(json.dumps(msg, ensure_ascii=False))
            return True
        except Exception:
            return False


class Hub:
    """Singleton in-memory runtime-node registry."""

    def __init__(self):
        self.clients: dict[str, WSClient] = {}  # runtime_node_id -> client
        self.agent_to_node: dict[str, str] = {}  # agent_id -> runtime_node_id, cached for tests/status
        self._lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task | None = None

    def start_heartbeat(self):
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def mark_all_offline(self):
        """Reset DB presence after API process restart."""
        async with AsyncSessionLocal() as db:
            await db.execute(update(RuntimeNode).where(RuntimeNode.status == "online").values(status="offline"))
            await db.execute(update(Agent).where(Agent.status == "online").values(status="offline"))
            await db.commit()

    async def stop_heartbeat(self):
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def handle(self, ws: WebSocket):
        await ws.accept()
        client: WSClient | None = None
        try:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=5.0)
            except asyncio.TimeoutError:
                await ws.close(code=4001, reason="auth timeout")
                return

            msg = json.loads(raw)
            if msg.get("type") != "auth":
                await ws.send_text(json.dumps({"type": "auth_fail", "reason": "expected_auth"}))
                await ws.close(code=4002)
                return

            client = await self._authenticate(ws, msg)
            if not client:
                return

            async with self._lock:
                prev = self.clients.get(client.runtime_node_id)
                if prev:
                    try:
                        await prev.ws.close(code=4003, reason="replaced")
                    except Exception:
                        pass
                self.clients[client.runtime_node_id] = client
                await self._refresh_agent_node_cache(client.runtime_node_id)

            await self.push_readiness_probes_for_node(client.runtime_node_id)

            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._dispatch(client, msg)
        except Exception:
            pass
        finally:
            if client:
                await self._cleanup(client)

    async def _authenticate(self, ws: WebSocket, msg: dict) -> WSClient | None:
        node_id = (msg.get("runtime_node_id") or msg.get("node_id") or "").strip()
        token = (msg.get("token") or "").strip()
        if not node_id or not token:
            await ws.send_text(json.dumps({"type": "auth_fail", "reason": "missing_credentials"}))
            await ws.close(code=4001)
            return None

        async with AsyncSessionLocal() as db:
            node = (await db.execute(select(RuntimeNode).where(RuntimeNode.id == node_id))).scalar_one_or_none()
            if not node:
                await ws.send_text(json.dumps({"type": "auth_fail", "reason": "invalid_runtime_node"}))
                await ws.close(code=4001)
                return None
            if not verify_token_hash(token, node.token_hash):
                await ws.send_text(json.dumps({"type": "auth_fail", "reason": "invalid_token"}))
                await ws.close(code=4001)
                return None

            node.status = "online"
            node.connected_at = datetime.utcnow()
            node.last_seen_at = datetime.utcnow()
            node.runtime_type = str(msg.get("runtime_type") or node.runtime_type or "").strip() or node.runtime_type
            node.runtime_version = str(msg.get("runtime_version") or node.runtime_version or "")
            node.adapter_version = str(msg.get("adapter_version") or msg.get("agent_version") or node.adapter_version or "")
            capabilities = msg.get("capabilities")
            if isinstance(capabilities, dict):
                node.capabilities = capabilities
            await self._mark_bound_agents(db, node.id, "online")
            await db.commit()
            await db.refresh(node)

            await ws.send_text(json.dumps({
                "type": "auth_ok",
                "runtime_node_id": node.id,
                "runtime_node_name": node.name,
                "heartbeat_interval_ms": settings.ws_heartbeat_interval_ms,
            }, ensure_ascii=False))

            print(f"[WS] runtime node connected: {node.id} ({node.name})")
            return WSClient(ws, node)

    async def _dispatch(self, client: WSClient, msg: dict):
        msg_type = msg.get("type")
        if msg_type == "pong":
            client.last_pong = time.monotonic()
            if msg.get("quota"):
                client.quota_snapshot = msg["quota"]
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(RuntimeNode)
                    .where(RuntimeNode.id == client.runtime_node_id)
                    .values(last_seen_at=datetime.utcnow())
                )
                await db.commit()
            return

        agent_id = str(msg.get("agent_id") or "").strip()
        if msg_type == "ack":
            request_id = msg.get("request_id")
            if not request_id or not agent_id:
                return
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Answer)
                    .where(Answer.request_id == request_id, Answer.agent_id == agent_id)
                    .values(status="processing")
                )
                await db.commit()
            return

        if msg_type == "answer":
            if not agent_id:
                return
            if is_readiness_probe(msg):
                pairing = extract_pairing_required(msg)
                if pairing:
                    await self._set_readiness(agent_id, "pairing_required", code=pairing["code"], command=pairing["command"])
                    return
                state = "ready" if msg.get("status") == "success" else "error"
                await self._set_readiness(agent_id, state, error=msg.get("error") if state == "error" else None)
                return
            from services.review import handle_uploaded_answer
            await handle_uploaded_answer(agent_id, msg)
            return

        if msg_type == "pairing_required":
            if agent_id:
                await self._set_readiness(agent_id, "pairing_required", code=msg.get("code"), command=msg.get("command"))
            return

        print(f"[WS] unknown msg type from {client.runtime_node_id}: {msg_type}")

    async def _cleanup(self, client: WSClient):
        async with self._lock:
            if self.clients.get(client.runtime_node_id) is client:
                self.clients.pop(client.runtime_node_id, None)
            self.agent_to_node = {agent_id: node_id for agent_id, node_id in self.agent_to_node.items() if node_id != client.runtime_node_id}
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(RuntimeNode)
                .where(RuntimeNode.id == client.runtime_node_id)
                .values(status="offline", disconnected_at=datetime.utcnow(), last_seen_at=datetime.utcnow())
            )
            await self._mark_bound_agents(db, client.runtime_node_id, "offline")
            await db.commit()
        print(f"[WS] runtime node disconnected: {client.runtime_node_id}")

    async def disconnect_node(self, runtime_node_id: str, reason: str = "disconnected"):
        client = self.clients.get(runtime_node_id)
        if not client:
            return
        try:
            await client.ws.close(code=4005, reason=reason)
        except Exception:
            pass
        await self._cleanup(client)

    async def disconnect_agent(self, agent_id: str, reason: str = "disconnected"):
        async with self._lock:
            self.agent_to_node.pop(agent_id, None)
        await self._set_readiness(agent_id, "offline", error=reason)

    async def _heartbeat_loop(self):
        interval = settings.ws_heartbeat_interval_ms / 1000.0
        timeout = settings.ws_heartbeat_timeout_seconds
        while True:
            await asyncio.sleep(interval)
            now = time.monotonic()
            stale: list[WSClient] = []
            for client in list(self.clients.values()):
                if now - client.last_pong > timeout:
                    stale.append(client)
                    continue
                ok = await client.send({"type": "ping", "ts": int(time.time() * 1000), "pending_questions": 0})
                if not ok:
                    stale.append(client)
            for client in stale:
                try:
                    await client.ws.close(code=4004, reason="heartbeat timeout")
                except Exception:
                    pass
                await self._cleanup(client)

    async def push_question(self, agent_id: str, payload: dict) -> bool:
        async with AsyncSessionLocal() as db:
            binding = await self._binding_for_agent(db, agent_id)
        if not binding:
            await self._set_readiness(agent_id, "error", error="Agent 尚未绑定本地节点")
            return False
        client = self.clients.get(binding.runtime_node_id)
        if not client:
            await self._set_readiness(agent_id, "error", error="绑定的本地节点当前离线")
            return False
        routed = {
            "type": "question",
            **payload,
            "agent_id": agent_id,
            "runtime_node_id": binding.runtime_node_id,
            "runtime_type": binding.runtime_type,
            "runtime_profile": binding.runtime_profile or "",
            "runtime_workspace": binding.runtime_workspace or "",
            "knowledge_scope": binding.knowledge_scope or "private",
        }
        return await client.send(routed)

    async def push_readiness_probe(self, agent_id: str) -> bool:
        async with AsyncSessionLocal() as db:
            binding = await self._binding_for_agent(db, agent_id)
        if not binding:
            await self._set_readiness(agent_id, "error", error="Agent 尚未绑定本地节点")
            return False
        client = self.clients.get(binding.runtime_node_id)
        if not client:
            await self._set_readiness(agent_id, "error", error="绑定的本地节点当前离线")
            return False
        request_id = f"{PROBE_REQUEST_PREFIX}{agent_id}_{int(time.time() * 1000)}"
        await self._set_readiness(agent_id, "checking")
        delivered = await client.send({
            "type": "question",
            "request_id": request_id,
            "agent_id": agent_id,
            "runtime_node_id": binding.runtime_node_id,
            "runtime_type": binding.runtime_type,
            "runtime_profile": binding.runtime_profile or "",
            "runtime_workspace": binding.runtime_workspace or "",
            "knowledge_scope": binding.knowledge_scope or "private",
            "title": "AgentMint pairing check",
            "body": "Reply OK. This is a hidden AgentMint readiness check.",
            "tags": ["agentmint_probe"],
            "asker": {"nickname": "AgentMint", "trust_level": 999},
            "auto_release": True,
            "deadline_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
            "probe": True,
        })
        if not delivered:
            await self._set_readiness(agent_id, "error", error="发送检测消息失败")
        return delivered

    async def push_readiness_probes_for_node(self, runtime_node_id: str) -> None:
        async with AsyncSessionLocal() as db:
            rows = await self._agent_ids_for_runtime_node(db, runtime_node_id)
        for agent_id in rows:
            await self.push_readiness_probe(agent_id)

    async def _binding_for_agent(self, db, agent_id: str) -> AgentRuntimeBinding | None:
        return (await db.execute(
            select(AgentRuntimeBinding).where(
                AgentRuntimeBinding.agent_id == agent_id,
                AgentRuntimeBinding.status == "active",
            )
        )).scalar_one_or_none()

    async def _mark_bound_agents(self, db, runtime_node_id: str, status: str) -> None:
        agent_ids = await self._agent_ids_for_runtime_node(db, runtime_node_id)
        if agent_ids:
            await db.execute(
                update(Agent)
                .where(Agent.id.in_(agent_ids))
                .values(status=status, last_seen_at=datetime.utcnow())
            )

    async def _refresh_agent_node_cache(self, runtime_node_id: str) -> None:
        async with AsyncSessionLocal() as db:
            agent_ids = await self._agent_ids_for_runtime_node(db, runtime_node_id)
        for agent_id in agent_ids:
            self.agent_to_node[agent_id] = runtime_node_id

    async def _agent_ids_for_runtime_node(self, db, runtime_node_id: str) -> list[str]:
        binding_ids = (await db.execute(
            select(AgentRuntimeBinding.agent_id).where(
                AgentRuntimeBinding.runtime_node_id == runtime_node_id,
                AgentRuntimeBinding.status == "active",
            )
        )).scalars().all()
        owner_agent_id = (await db.execute(
            select(RuntimeNode.agent_id).where(RuntimeNode.id == runtime_node_id)
        )).scalar_one_or_none()
        ids: list[str] = []
        for agent_id in [owner_agent_id, *binding_ids]:
            if agent_id and agent_id not in ids:
                ids.append(agent_id)
        return ids

    async def _set_readiness(self, agent_id: str, state: str, *, code: str | None = None, command: str | None = None, error: str | None = None):
        async with AsyncSessionLocal() as db:
            agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
            if not agent:
                return
            set_agent_readiness(agent, state, code=code, command=command, error=error)
            await db.commit()

    def is_online(self, agent_id: str) -> bool:
        node_id = self.agent_to_node.get(agent_id)
        return bool(node_id and node_id in self.clients)


hub = Hub()


def extract_pairing_required(msg: dict) -> dict[str, str] | None:
    content = msg.get("content") or {}
    if isinstance(content, dict):
        text = str(content.get("text") or "")
    else:
        text = str(content or "")
    code_match = PAIRING_CODE_RE.search(text)
    command_match = PAIRING_COMMAND_RE.search(text)
    if not code_match and not command_match:
        return None
    code = code_match.group(1).strip() if code_match else command_match.group(1).split()[-1].strip()
    command = command_match.group(1).strip() if command_match else f"hermes pairing approve agentmint {code}"
    return {"code": code, "command": command}
