"""WebSocket client — connection, auth, heartbeat, reconnect with backoff.

The client exposes an async iterator of incoming messages from the platform.
It owns the connection lifecycle:
  - exponential backoff: 0, 2, 4, 8, then 30s ×6, then circuit-break
  - replies to `ping` with `pong` automatically (and includes queue quota)
  - reconnects on disconnect; emits a `__reconnected__` synthetic message so
    the main loop can scan the SQLite queue for jobs to retry/resume
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .config import Config

log = logging.getLogger(__name__)

# Exponential then constant backoff: 0s, 2s, 4s, 8s, then 30s × 6, then circuit-break
BACKOFF_SCHEDULE = [0, 2, 4, 8, 30, 30, 30, 30, 30, 30]
MAX_ATTEMPTS = len(BACKOFF_SCHEDULE)  # 10


class CircuitBreakerOpen(Exception):
    """Raised when reconnect attempts have exceeded MAX_ATTEMPTS."""


class WSClient:
    """Reconnecting WebSocket client.

    Usage:
        async with WSClient(cfg) as client:
            async for msg in client.messages():
                ...
            await client.send({"type": "answer", ...})
    """

    def __init__(self, cfg: Config, quota_provider=None):
        self.cfg = cfg
        self.ws: websockets.WebSocketClientProtocol | None = None
        self._reconnect_attempts = 0
        self._closed = False
        self._send_lock = asyncio.Lock()
        # Optional callable returning current quota dict for pong replies
        self._quota_provider = quota_provider or (lambda: {"used": 0, "max": 50, "remaining_auto": 40, "remaining_review": 10})

    # ─── Lifecycle ───

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def close(self):
        self._closed = True
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass

    # ─── Connect + auth ───

    async def _connect_and_auth(self) -> websockets.WebSocketClientProtocol:
        """Connect once and run the auth handshake. Raises on failure."""
        log.info("connecting to %s", self.cfg.platform_url)
        ws = await websockets.connect(self.cfg.platform_url, open_timeout=10, ping_interval=None)
        try:
            await ws.send(json.dumps({
                "type": "auth",
                "connector_id": self.cfg.connector_id,
                "token": self.cfg.connector_token,
                "version": self.cfg.agent_version,
                "agent_type": self.cfg.agent_type,
                "agent_version": self.cfg.agent_version,
                "capabilities": ["chat"],
            }))
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(raw)
            if msg.get("type") != "auth_ok":
                reason = msg.get("reason") or msg.get("message") or "unknown"
                await ws.close()
                raise ConnectionRefusedError(f"auth_fail: {reason}")
            log.info("auth_ok as \"%s\" (heartbeat %dms)",
                     msg.get("connector_name"), msg.get("heartbeat_interval_ms"))
            return ws
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            raise

    # ─── Reconnect with backoff ───

    async def _connect_with_backoff(self) -> websockets.WebSocketClientProtocol:
        while not self._closed:
            try:
                ws = await self._connect_and_auth()
                self._reconnect_attempts = 0
                return ws
            except ConnectionRefusedError as e:
                # Authentication failure → no point retrying the same creds
                log.error("auth refused, giving up: %s", e)
                raise
            except (ConnectionClosed, WebSocketException, OSError, asyncio.TimeoutError) as e:
                if self._reconnect_attempts >= MAX_ATTEMPTS:
                    raise CircuitBreakerOpen(
                        f"unable to connect after {MAX_ATTEMPTS} attempts; last error: {e}"
                    )
                delay = BACKOFF_SCHEDULE[self._reconnect_attempts]
                self._reconnect_attempts += 1
                log.warning("connect failed (%s), retry %d/%d in %ds",
                            e, self._reconnect_attempts, MAX_ATTEMPTS, delay)
                await asyncio.sleep(delay)
        raise asyncio.CancelledError()

    # ─── Send ───

    async def send(self, msg: dict) -> bool:
        """Send a message. Returns False if the socket is currently down."""
        async with self._send_lock:
            if self.ws is None:
                return False
            try:
                await self.ws.send(json.dumps(msg, ensure_ascii=False))
                return True
            except (ConnectionClosed, WebSocketException) as e:
                log.warning("send failed: %s", e)
                return False

    # ─── Main message iterator with auto-reconnect ───

    async def messages(self) -> AsyncIterator[dict]:
        """Yield incoming platform messages.

        Yields a synthetic `{"type": "__reconnected__"}` after a successful
        reconnect so the caller can resume queued work.
        """
        first_connect = True
        while not self._closed:
            try:
                self.ws = await self._connect_with_backoff()
            except CircuitBreakerOpen as e:
                log.error(str(e))
                return
            except ConnectionRefusedError:
                # Permanent auth failure
                return

            if not first_connect:
                yield {"type": "__reconnected__"}
            first_connect = False

            try:
                async for raw in self.ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        log.warning("non-JSON message ignored")
                        continue

                    if msg.get("type") == "ping":
                        await self._reply_pong(msg)
                        continue  # don't surface ping to caller

                    yield msg
            except (ConnectionClosed, WebSocketException) as e:
                log.warning("connection lost: %s — will reconnect", e)
                self.ws = None
                continue

    async def _reply_pong(self, ping_msg: dict):
        try:
            quota = self._quota_provider()
        except Exception:
            quota = {}
        await self.send({
            "type": "pong",
            "ts": int(time.time() * 1000),
            "status": "idle",
            "quota": quota,
        })
