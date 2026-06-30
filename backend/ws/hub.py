"""WebSocket hub — single-process in-memory connector registry.

Responsibilities:
- Authenticate incoming connectors (`connector_id` + token plaintext → bcrypt
  verify against `connectors.token_hash`).
- Track live WebSocket clients by `connector_id` and `agent_id`.
- Heartbeat: send `ping` every 30s; mark agent offline if 90s without `pong`.
- Push questions to a specific agent (`push_question`) — called from REST.
- Receive `answer` messages and hand them to `services.review` for the
  auto/review decision (kept in one place to avoid drift).
"""
import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from typing import Any

from fastapi import WebSocket
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from models import Agent, Connector, Answer
from services.auth import verify_token_hash
from services.agent_readiness import set_agent_readiness

PROBE_REQUEST_PREFIX = "probe_"
PAIRING_CODE_RE = re.compile(r"pairing code:\s*([A-Z0-9-]+)", re.IGNORECASE)
PAIRING_COMMAND_RE = re.compile(r"(hermes\s+pairing\s+approve\s+agentmint\s+[A-Z0-9-]+)", re.IGNORECASE)


def is_readiness_probe(msg: dict) -> bool:
    return str(msg.get("request_id") or "").startswith(PROBE_REQUEST_PREFIX)


class WSClient:
    """In-memory record for a live connector connection."""

    def __init__(self, ws: WebSocket, connector_id: str, agent_id: str, user_id: str, agent_name: str):
        self.ws = ws
        self.connector_id = connector_id
        self.agent_id = agent_id
        self.user_id = user_id
        self.agent_name = agent_name
        self.last_pong = time.monotonic()
        self.quota_snapshot: dict[str, Any] = {}

    async def send(self, msg: dict) -> bool:
        try:
            await self.ws.send_text(json.dumps(msg, ensure_ascii=False))
            return True
        except Exception:
            return False


class Hub:
    """Singleton in-memory connector registry."""

    def __init__(self):
        self.clients: dict[str, WSClient] = {}        # connector_id → client
        self.agent_to_conn: dict[str, str] = {}       # agent_id → connector_id
        self._lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task | None = None

    # ─── Lifecycle ───

    def start_heartbeat(self):
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def mark_all_offline(self):
        """Reset DB presence after API process restart.

        Live connector state is in-memory, so a fresh process should consider
        every agent offline until its connector authenticates again.
        """
        async with AsyncSessionLocal() as db:
            await db.execute(update(Agent).where(Agent.status == "online").values(status="offline"))
            await db.commit()

    async def stop_heartbeat(self):
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    # ─── Connection handling ───

    async def handle(self, ws: WebSocket):
        """Drive one connector's lifecycle from accept → auth → message loop → cleanup."""
        await ws.accept()
        client: WSClient | None = None

        try:
            # Auth must be the first message and arrive within 5s.
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
                return  # _authenticate already closed the socket

            async with self._lock:
                # Evict prior connection for the same agent, if any.
                prev_conn_id = self.agent_to_conn.get(client.agent_id)
                if prev_conn_id and prev_conn_id in self.clients:
                    prev = self.clients.pop(prev_conn_id)
                    try:
                        await prev.ws.close(code=4003, reason="replaced")
                    except Exception:
                        pass
                self.clients[client.connector_id] = client
                self.agent_to_conn[client.agent_id] = client.connector_id

            await self.push_readiness_probe(client.agent_id)

            # Message loop
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._dispatch(client, msg)

        except Exception:
            # Including WebSocketDisconnect — fall through to cleanup
            pass
        finally:
            if client:
                await self._cleanup(client)

    async def _authenticate(self, ws: WebSocket, msg: dict) -> WSClient | None:
        connector_id = (msg.get("connector_id") or "").strip()
        token = (msg.get("token") or "").strip()
        if not connector_id or not token:
            await ws.send_text(json.dumps({"type": "auth_fail", "reason": "missing_credentials"}))
            await ws.close(code=4001)
            return None

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Connector, Agent).join(Agent, Connector.agent_id == Agent.id)
                .where(Connector.id == connector_id)
            )
            row = result.one_or_none()
            if not row:
                await ws.send_text(json.dumps({"type": "auth_fail", "reason": "invalid_connector"}))
                await ws.close(code=4001)
                return None

            conn, agent = row
            if not verify_token_hash(token, conn.token_hash):
                await ws.send_text(json.dumps({"type": "auth_fail", "reason": "invalid_token"}))
                await ws.close(code=4001)
                return None

            # Mark agent online
            agent.status = "online"
            agent.last_seen_at = datetime.utcnow()
            conn.connected_at = datetime.utcnow()
            await db.commit()

            await ws.send_text(json.dumps({
                "type": "auth_ok",
                "connector_name": agent.name,
                "heartbeat_interval_ms": settings.ws_heartbeat_interval_ms,
            }, ensure_ascii=False))

            print(f"[WS] connected: {agent.id} ({agent.name})")
            return WSClient(ws, connector_id, agent.id, agent.user_id, agent.name)

    async def _dispatch(self, client: WSClient, msg: dict):
        msg_type = msg.get("type")

        if msg_type == "pong":
            client.last_pong = time.monotonic()
            if msg.get("quota"):
                client.quota_snapshot = msg["quota"]

        elif msg_type == "ack":
            request_id = msg.get("request_id")
            if not request_id:
                return
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Answer)
                    .where(Answer.request_id == request_id, Answer.agent_id == client.agent_id)
                    .values(status="processing")
                )
                await db.commit()

        elif msg_type == "answer":
            if is_readiness_probe(msg):
                pairing = extract_pairing_required(msg)
                if pairing:
                    await self._set_readiness(
                        client.agent_id,
                        "pairing_required",
                        code=pairing["code"],
                        command=pairing["command"],
                    )
                    return
                state = "ready" if msg.get("status") == "success" else "error"
                await self._set_readiness(
                    client.agent_id,
                    state,
                    error=msg.get("error") if state == "error" else None,
                )
                return
            # Delegated to services.review (introduced in Stage 4) to keep auto
            # and manual approval paths convergent.
            from services.review import handle_uploaded_answer
            await handle_uploaded_answer(client.agent_id, msg)

        elif msg_type == "pairing_required":
            await self._set_readiness(
                client.agent_id,
                "pairing_required",
                code=msg.get("code"),
                command=msg.get("command"),
            )

        else:
            print(f"[WS] unknown msg type from {client.agent_id}: {msg_type}")

    async def _cleanup(self, client: WSClient):
        async with self._lock:
            self.clients.pop(client.connector_id, None)
            # Only remove the mapping if it still points to us.
            if self.agent_to_conn.get(client.agent_id) == client.connector_id:
                self.agent_to_conn.pop(client.agent_id, None)

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Agent)
                .where(Agent.id == client.agent_id)
                .values(status="offline", last_seen_at=datetime.utcnow())
            )
            await db.commit()
        print(f"[WS] disconnected: {client.agent_id}")

    async def disconnect_agent(self, agent_id: str, reason: str = "disconnected"):
        conn_id = self.agent_to_conn.get(agent_id)
        if not conn_id:
            return
        client = self.clients.get(conn_id)
        if not client:
            return
        try:
            await client.ws.close(code=4005, reason=reason)
        except Exception:
            pass
        await self._cleanup(client)

    # ─── Heartbeat ───

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

    # ─── Push to Connector (called from REST after matching) ───

    async def push_question(self, agent_id: str, payload: dict) -> bool:
        """Deliver a question to a connected agent. Returns True if delivered."""
        conn_id = self.agent_to_conn.get(agent_id)
        if not conn_id:
            return False
        client = self.clients.get(conn_id)
        if not client:
            return False
        return await client.send({"type": "question", **payload})

    async def push_readiness_probe(self, agent_id: str) -> bool:
        conn_id = self.agent_to_conn.get(agent_id)
        client = self.clients.get(conn_id) if conn_id else None
        if not client:
            await self._set_readiness(agent_id, "error", error="Agent 当前没有活动连接")
            return False

        request_id = f"{PROBE_REQUEST_PREFIX}{agent_id}_{int(time.time() * 1000)}"
        await self._set_readiness(agent_id, "checking")
        delivered = await client.send({"type": "question", **{
            "request_id": request_id,
            "title": "AgentMint pairing check",
            "body": "Reply OK. This is a hidden AgentMint readiness check.",
            "tags": ["agentmint_probe"],
            "asker": {"nickname": "AgentMint", "trust_level": 999},
            "auto_release": True,
            "deadline_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
            "probe": True,
        }})
        if not delivered:
            await self._set_readiness(agent_id, "error", error="发送检测消息失败")
        return delivered

    async def _set_readiness(
        self,
        agent_id: str,
        state: str,
        *,
        code: str | None = None,
        command: str | None = None,
        error: str | None = None,
    ):
        async with AsyncSessionLocal() as db:
            agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
            if not agent:
                return
            set_agent_readiness(agent, state, code=code, command=command, error=error)
            await db.commit()

    def is_online(self, agent_id: str) -> bool:
        return agent_id in self.agent_to_conn


# Module-level singleton — imported by REST routers and the WS endpoint.
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
