"""Long-running WebSocket client for the Arena platform.

Run inside the Hermes event loop as a background asyncio task spawned by
ArenaAdapter.connect(). The client owns:

  - auth handshake with the Arena platform
  - heartbeat: replies to platform `ping` with `pong`
  - reconnect: exponential backoff (0, 2, 4, 8, then capped at 30s) until stopped
  - inbound `question`s → handed to `on_question` callback
  - outbound `answer` / `ack` / `config_ack` via `send_*` helpers

The adapter, not the client, decides what to do with each question — typically
build a `MessageEvent` and call `self.handle_message(event)` to push it into
Hermes's gateway runner.
"""
import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

log = logging.getLogger(__name__)

BACKOFF_SCHEDULE = [0, 2, 4, 8, 30, 30, 30, 30, 30, 30]
SERVER_IDLE_TIMEOUT_SECONDS = 75
AGENTMINT_WS_CLIENT_VERSION = "2026-06-29.3"


class ArenaAuthError(Exception):
    """Connector credentials were rejected by Arena; retrying will not help."""


QuestionHandler = Callable[[dict], Awaitable[None]]
QuotaProvider = Callable[[], dict]


class ArenaWSClient:
    """Reconnecting Arena platform WebSocket client."""

    def __init__(
        self,
        platform_url: str,
        connector_id: str,
        connector_token: str,
        on_question: QuestionHandler,
        on_reconnected: Callable[[], Awaitable[None]] | None = None,
        quota_provider: QuotaProvider | None = None,
        agent_type: str = "hermes",
        agent_version: str = "0.1.0",
    ):
        self.platform_url = platform_url
        self.connector_id = connector_id
        self.connector_token = connector_token
        self.on_question = on_question
        self.on_reconnected = on_reconnected
        self.quota_provider = quota_provider or (lambda: {"used": 0, "max": 50, "remaining_auto": 40, "remaining_review": 10})
        self.agent_type = agent_type
        self.agent_version = agent_version

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._send_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._closed = asyncio.Event()
        self._connected = asyncio.Event()
        self._attempts = 0

    # ─── Lifecycle ───

    def start(self):
        if self._task is None or self._task.done():
            log.info(
                "agentmint ws client %s loaded from %s",
                AGENTMINT_WS_CLIENT_VERSION,
                __file__,
            )
            self._task = asyncio.create_task(self._run(), name="agentmint-ws-client")

    async def stop(self):
        self._closed.set()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, Exception):
                self._task.cancel()

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    # ─── Send helpers ───

    async def send(self, payload: dict) -> bool:
        async with self._send_lock:
            if self._ws is None:
                return False
            try:
                await self._ws.send(json.dumps(payload, ensure_ascii=False))
                return True
            except (ConnectionClosed, WebSocketException) as e:
                log.warning("ws send failed: %s", e)
                return False

    async def send_ack(self, request_id: str) -> bool:
        return await self.send({"type": "ack", "request_id": request_id})

    async def send_answer(self, request_id: str, *, text: str, model: str,
                          usage: dict, capability: dict | None = None,
                          duration_ms: int = 0,
                          usage_correction: bool = False) -> bool:
        payload = {
            "type": "answer",
            "request_id": request_id,
            "status": "success",
            "content": {"text": text, "attachments": []},
            "model": model,
            "usage": usage,
            "capability": capability or {},
            "duration_ms": duration_ms,
        }
        if usage_correction:
            payload["usage_correction"] = True
        return await self.send(payload)

    async def send_error(self, request_id: str, error: str, retryable: bool = False) -> bool:
        return await self.send({
            "type": "answer",
            "request_id": request_id,
            "status": "error",
            "error": error,
            "retryable": retryable,
        })

    # ─── Internal: connect + auth ───

    async def _connect_once(self) -> websockets.WebSocketClientProtocol:
        log.info("connecting to %s", self.platform_url)
        ws = await websockets.connect(self.platform_url, open_timeout=10, ping_interval=None)
        await ws.send(json.dumps({
            "type": "auth",
            "connector_id": self.connector_id,
            "token": self.connector_token,
            "version": self.agent_version,
            "agent_type": self.agent_type,
            "agent_version": self.agent_version,
            "capabilities": ["chat"],
        }))
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        msg = json.loads(raw)
        if msg.get("type") != "auth_ok":
            reason = msg.get("reason") or "unknown"
            await ws.close()
            raise ArenaAuthError(reason)
        log.info("auth_ok as \"%s\"", msg.get("connector_name"))
        return ws

    async def _connect_with_backoff(self) -> websockets.WebSocketClientProtocol | None:
        while not self._closed.is_set():
            try:
                ws = await self._connect_once()
                self._attempts = 0
                return ws
            except ArenaAuthError as e:
                log.error("auth refused, giving up: %s", e)
                return None
            except (ConnectionClosed, WebSocketException, OSError, asyncio.TimeoutError) as e:
                self._attempts += 1
                delay = BACKOFF_SCHEDULE[min(self._attempts - 1, len(BACKOFF_SCHEDULE) - 1)]
                log.warning("connect failed (%s), retry %d in %ds", e, self._attempts, delay)
                try:
                    await asyncio.wait_for(self._closed.wait(), timeout=delay)
                    return None  # stopped while waiting
                except asyncio.TimeoutError:
                    pass
        return None

    # ─── Main loop ───

    async def _run(self):
        first = True
        while not self._closed.is_set():
            ws = await self._connect_with_backoff()
            if ws is None:
                break
            self._ws = ws
            self._connected.set()

            if not first and self.on_reconnected is not None:
                try:
                    await self.on_reconnected()
                except Exception:
                    log.exception("on_reconnected callback raised")
            first = False

            try:
                while not self._closed.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=SERVER_IDLE_TIMEOUT_SECONDS)
                    except asyncio.TimeoutError:
                        log.warning("no server messages for %ss — reconnecting", SERVER_IDLE_TIMEOUT_SECONDS)
                        try:
                            await ws.close()
                        except Exception:
                            pass
                        break
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    await self._dispatch(msg)
            except (ConnectionClosed, WebSocketException) as e:
                log.warning("connection lost: %s — will reconnect", e)
            finally:
                self._connected.clear()
                self._ws = None

    async def _dispatch(self, msg: dict):
        mtype = msg.get("type")
        if mtype == "ping":
            await self.send({
                "type": "pong",
                "ts": int(time.time() * 1000),
                "status": "idle",
                "quota": self.quota_provider(),
            })
        elif mtype == "question":
            try:
                await self.on_question(msg)
            except Exception:
                log.exception("on_question handler raised for %s", msg.get("request_id"))
        elif mtype == "update_config":
            await self.send({
                "type": "config_ack",
                "applied_fields": list((msg.get("fields") or {}).keys()),
            })
        elif mtype == "auth_fail":
            log.error("auth_fail received mid-session: %s", msg.get("reason"))
            self._closed.set()
        else:
            log.debug("unhandled ws message: %s", mtype)
