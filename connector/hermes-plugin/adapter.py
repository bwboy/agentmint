"""Arena platform adapter for Hermes Agent.

Treats the AgentMint Q&A platform as a Hermes "platform" — analogous to
Telegram or IRC. Incoming questions flow:

    Arena (WebSocket)                    Hermes Gateway Runner
          │                                       │
          │  ─── question ───────────►  ArenaAdapter._on_question
          │                                       │
          │                          self.handle_message(MessageEvent)
          │                                       │
          │                              Hermes agent loop generates reply
          │                                       │
          │  ◄────────── upload answer  ArenaAdapter.send(chat_id, content)

The platform uses `request_id` as both the wire-level idempotency key *and*
the chat session identifier (each question = its own one-shot DM).

Tested against the Arena backend's `/ws` endpoint (see
agentmint/backend/ws/hub.py for the protocol).
"""
import asyncio
import logging
import math
import os
import time
from pathlib import Path
from typing import Any

# Hermes imports — only present when the plugin is loaded by Hermes itself.
# Wrapped in try/except so unit tests / IDE checks don't choke when Hermes
# isn't installed in the active environment.
try:
    from gateway.platforms.base import (
        BasePlatformAdapter,
        SendResult,
        MessageEvent,
        MessageType,
    )
    from gateway.config import Platform, PlatformConfig
    _HERMES_AVAILABLE = True
except ImportError:  # pragma: no cover — only happens outside Hermes runtime
    BasePlatformAdapter = object  # type: ignore
    SendResult = MessageEvent = MessageType = Platform = PlatformConfig = None  # type: ignore
    _HERMES_AVAILABLE = False

from .queue import JobQueue
from .ws_client import ArenaWSClient

log = logging.getLogger(__name__)

DEFAULT_PLATFORM_URL = "ws://localhost:8000/ws"
DEFAULT_MAX_CONCURRENT = 3
DEFAULT_QUEUE_DB = "~/.hermes/agentmint-jobs.db"
DEFAULT_USAGE_WAIT_SECONDS = 1.0
TRUE_VALUES = {"1", "true", "yes", "on"}

AGENTMINT_PLATFORM_HINT = (
    "You are answering a question from the AgentMint platform. "
    "Markdown is supported. Be concise but complete; code goes in fenced blocks. "
    "Prefer safe, non-interactive tool use. Do not use commands that are likely "
    "to require security approval, including curl-piped-to-interpreter patterns "
    "such as `curl ... | python`, downloaded code execution, shell eval, or "
    "one-shot scripts that execute uninspected remote content. For web data, "
    "fetch data as data and parse it locally with safe libraries; if the only "
    "available approach would trigger an approval prompt, do not request "
    "approval. Explain the limitation or choose a safer alternative."
)

AGENTMINT_PROMPT_SAFETY_GUIDANCE = """

AgentMint tool policy:
- Do not run shell commands that pipe network output into interpreters, for example `curl ... | python3`, `curl ... | bash`, `wget ... | sh`, or similar patterns.
- Do not execute downloaded or uninspected remote content, and do not use `eval` on remote data.
- If web data is needed, fetch it as data first, inspect or parse it with non-executing code, or use Hermes' safer web/research tools when available.
- If the only path would trigger an approval prompt, do not ask for approval. Explain the limitation and answer from available safe sources.
""".strip()


# ════════════════════════════════════════════════════════════════
# Adapter
# ════════════════════════════════════════════════════════════════

class ArenaAdapter(BasePlatformAdapter):  # type: ignore[misc]
    """Bridges Hermes ↔ AgentMint platform via a persistent WebSocket."""

    SUPPORTS_MESSAGE_EDITING = True
    REQUIRES_EDIT_FINALIZE = True
    MAX_MESSAGE_LENGTH = 1_000_000

    def __init__(self, config: "PlatformConfig"):  # noqa: F821
        super().__init__(config, Platform("agentmint"))
        extra = (getattr(config, "extra", None) or {}) if config else {}

        # Credentials & endpoint
        self.connector_id = os.getenv("AGENTMINT_CONNECTOR_ID", extra.get("connector_id", ""))
        self.connector_token = os.getenv("AGENTMINT_CONNECTOR_TOKEN", extra.get("connector_token", ""))
        self.platform_url = os.getenv("AGENTMINT_PLATFORM_URL", extra.get("platform_url", DEFAULT_PLATFORM_URL))
        self.max_concurrent = int(os.getenv("AGENTMINT_MAX_CONCURRENT", extra.get("max_concurrent", DEFAULT_MAX_CONCURRENT)))
        self.queue_db = os.getenv("AGENTMINT_QUEUE_DB", extra.get("queue_db", DEFAULT_QUEUE_DB))
        self.usage_wait_seconds = float(os.getenv("AGENTMINT_USAGE_WAIT_SECONDS", extra.get("usage_wait_seconds", DEFAULT_USAGE_WAIT_SECONDS)))
        self.debug_usage = _truthy(os.getenv("AGENTMINT_DEBUG_USAGE", extra.get("debug_usage", "")))

        # Local state
        self._queue = JobQueue(self.queue_db)
        self._client: ArenaWSClient | None = None
        self._start_time = 0.0
        # Per-job timing for `duration_ms` reporting on the answer payload
        self._job_started_at: dict[str, float] = {}
        # Hermes' platform send metadata currently carries thread routing, not
        # the full run result. Capture the handler result by request/chat id so
        # send() can upload the exact token usage when Hermes exposes it there.
        self._last_turn_metadata: dict[str, dict[str, Any]] = {}
        self._turn_metadata_events: dict[str, asyncio.Event] = {}
        self._pending_answer_uploads: set[str] = set()
        self._background_upload_tasks: set[asyncio.Task] = set()
        self._streaming_answers: dict[str, dict[str, Any]] = {}
        # Keep the prompt text around so the plugin can still report an
        # explicitly-estimated usage value when Hermes/provider gives no usage.
        self._prompt_text_by_request: dict[str, str] = {}

    def set_message_handler(self, handler):  # type: ignore[override]
        async def _wrapped(event):
            result = await handler(event)
            self._capture_turn_metadata(event, result)
            return result

        self._message_handler = _wrapped

    def _capture_turn_metadata(self, event, result) -> None:
        debug_usage = getattr(self, "debug_usage", False)
        source = getattr(event, "source", None)
        chat_id = getattr(source, "chat_id", None)
        if not isinstance(result, dict):
            if debug_usage:
                log.info(
                    "agentmint usage capture skipped chat_id=%s result=%s",
                    chat_id or "missing",
                    _metadata_debug_summary(result),
                )
            return
        usage = _extract_usage(result)
        model = result.get("model") or result.get("active_model")
        if debug_usage:
            log.info(
                "agentmint usage capture chat_id=%s result=%s extracted=%s model=%s",
                chat_id or "missing",
                _metadata_debug_summary(result),
                _usage_log_label(usage),
                model or "",
            )
        if not chat_id:
            return
        if not usage and not model:
            return
        captured: dict[str, Any] = {}
        if usage:
            captured.update(usage)
        if model:
            captured["model"] = model
        self._last_turn_metadata[str(chat_id)] = captured
        events = getattr(self, "_turn_metadata_events", {})
        event = events.get(str(chat_id))
        if event:
            event.set()

    # ─── Lifecycle ───

    async def connect(self) -> bool:
        if not self.connector_id or not self.connector_token:
            log.error("AGENTMINT_CONNECTOR_ID / AGENTMINT_CONNECTOR_TOKEN not set; cannot connect")
            return False

        log.info("connecting to %s (queue=%s, max_concurrent=%d)",
                 self.platform_url, self.queue_db, self.max_concurrent)

        self._client = ArenaWSClient(
            platform_url=self.platform_url,
            connector_id=self.connector_id,
            connector_token=self.connector_token,
            on_question=self._on_question,
            on_reconnected=self._on_reconnected,
            quota_provider=self._quota_snapshot,
            agent_type="hermes",
            agent_version="0.1.0",
        )
        self._client.start()

        # Block briefly so the gateway sees a healthy adapter, but not so long
        # that a wonky network kills startup; the client itself will keep
        # retrying in the background.
        for _ in range(20):
            if self._client.is_connected:
                break
            await asyncio.sleep(0.5)

        self._start_time = time.time()
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.stop()
            self._client = None
        try:
            self._queue.close()
        except Exception:
            pass
        self._mark_disconnected()

    # ─── Inbound: Arena → Hermes ───

    async def _on_question(self, msg: dict) -> None:
        """Translate an Arena question into a Hermes MessageEvent and dispatch."""
        request_id = msg.get("request_id")
        if not request_id:
            log.warning("question without request_id, dropping")
            return

        title = msg.get("title") or ""
        body = (msg.get("body") or "").strip()
        tags = msg.get("tags") or []
        asker = msg.get("asker") or {}
        asker_nick = asker.get("nickname", "anonymous")
        asker_tl = asker.get("trust_level", 1)

        question_record = {
            "title": title, "body": body, "tags": tags,
            "asker": asker, "deadline_at": msg.get("deadline_at"),
        }

        # Idempotent insert. If the platform redelivers the same question after
        # a reconnect, we still ack but don't double-dispatch to Hermes.
        is_new = self._queue.upsert_pending(request_id, chat_id=request_id, question=question_record)
        await self._client.send_ack(request_id)
        if not is_new:
            log.info("re-ack for known request_id=%s, skipping dispatch", request_id)
            return

        self._job_started_at[request_id] = time.monotonic()

        # Build the conversational prompt Hermes will see.
        user_text = _format_prompt(title, body, tags, asker_nick)
        self._prompt_text_by_request[request_id] = user_text

        source = self.build_source(
            chat_id=request_id,
            chat_name=f"Arena问题: {title[:40]}",
            chat_type="dm",
            user_id=f"agentmint:{asker_nick}",
            user_name=asker_nick,
        )
        event = MessageEvent(
            text=user_text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=request_id,
        )
        await self.handle_message(event)

    async def _on_reconnected(self) -> None:
        """After a WS reconnect, replay anything the platform hasn't acknowledged."""
        log.info("reconnected — replaying %s", self._queue.counts())
        for job in self._queue.list_resumable():
            if job["status"] == "answered":
                # We already have the answer; just re-upload.
                ans = job["answer"] or {}
                ok = await self._client.send_answer(
                    job["request_id"],
                    text=ans.get("text", ""),
                    model=ans.get("model", "hermes"),
                    usage=ans.get("usage", {}),
                    capability=ans.get("capability"),
                    duration_ms=ans.get("duration_ms", 0),
                )
                if ok:
                    self._queue.mark(job["request_id"], "uploaded")
            elif job["status"] == "pending":
                # Hermes never sent us send() — re-dispatch the question.
                # This is best-effort; in the worst case the platform's
                # `deadline_at` will expire it server-side.
                q = job["question"]
                fake_msg = {
                    "request_id": job["request_id"],
                    "title": q["title"], "body": q["body"], "tags": q["tags"],
                    "asker": q.get("asker"), "deadline_at": q.get("deadline_at"),
                }
                # Mark as gone so upsert_pending succeeds on the re-dispatch.
                self._queue.mark(job["request_id"], "failed", error="re-dispatching after reconnect")
                await self._on_question(fake_msg)

    # ─── Outbound: Hermes → Arena ───

    async def send(self, chat_id, content, reply_to=None, metadata=None):  # type: ignore[override]
        """Hermes finished a turn — upload the answer to Arena.

        `chat_id` is the request_id (we set it that way in `_on_question`).
        `metadata` may carry `model` / token usage from the LLM; we pull what
        we can while tolerating Hermes versions that only pass thread routing
        metadata to platform adapters.
        """
        request_id = str(chat_id)
        existing_job = self._queue.by_request_id(request_id)
        if existing_job and existing_job.get("answer") and existing_job.get("status") in {"answered", "uploaded"}:
            log.info("duplicate answer ignored for %s (status=%s)", request_id, existing_job.get("status"))
            return SendResult(success=True, message_id=request_id)
        if request_id in getattr(self, "_pending_answer_uploads", set()):
            log.info("duplicate answer ignored for %s (upload pending)", request_id)
            return SendResult(success=True, message_id=request_id)

        meta = metadata or {}
        if meta.get("expect_edits"):
            if meta.get("notify"):
                final_meta = dict(meta)
                final_meta.pop("expect_edits", None)
                return await self.send(
                    chat_id=request_id,
                    content=str(content),
                    reply_to=reply_to,
                    metadata=final_meta,
                )
            self._streaming_answers[request_id] = {
                "content": str(content),
                "metadata": dict(meta),
                "reply_to": reply_to,
                "updated_at": time.monotonic(),
            }
            if getattr(self, "debug_usage", False):
                log.info(
                    "agentmint streaming preview cached request_id=%s metadata=%s chars=%d",
                    request_id,
                    _metadata_debug_summary(meta),
                    len(str(content)),
                )
            return SendResult(success=True, message_id=request_id)

        turn_meta = self._last_turn_metadata.get(request_id, {})
        model = meta.get("model") or meta.get("active_model") or turn_meta.get("model") or "hermes"
        usage = _extract_usage(meta) or _extract_usage(turn_meta)
        prompt_cache = getattr(self, "_prompt_text_by_request", {})
        prompt_text = prompt_cache.get(request_id)
        if prompt_text is None:
            prompt_text = _prompt_from_job(existing_job)
        capability = meta.get("capability") or _capability_hint(model)

        started = self._job_started_at.pop(request_id, None)
        prompt_cache.pop(request_id, None)
        duration_ms = int((time.monotonic() - started) * 1000) if started else 0

        if not usage:
            self._pending_answer_uploads.add(request_id)
            event = self._turn_metadata_events.setdefault(request_id, asyncio.Event())
            if getattr(self, "debug_usage", False):
                log.info(
                    "agentmint usage wait scheduled request_id=%s metadata=%s timeout=%.3fs",
                    request_id,
                    _metadata_debug_summary(meta),
                    self.usage_wait_seconds,
                )
            task = asyncio.create_task(
                self._upload_answer_after_usage_wait(
                    request_id=request_id,
                    content=str(content),
                    metadata=meta,
                    model=model,
                    capability=capability,
                    duration_ms=duration_ms,
                    prompt_text=prompt_text or "",
                    event=event,
                ),
                name=f"agentmint-answer-upload-{request_id}",
            )
            self._background_upload_tasks.add(task)
            task.add_done_callback(self._background_upload_tasks.discard)
            return SendResult(success=True, message_id=request_id)

        self._last_turn_metadata.pop(request_id, None)
        return await self._upload_answer(
            request_id=request_id,
            content=str(content),
            model=model,
            usage=usage,
            capability=capability,
            duration_ms=duration_ms,
        )

    async def _upload_answer_after_usage_wait(
        self,
        *,
        request_id: str,
        content: str,
        metadata: dict,
        model: str,
        capability: dict,
        duration_ms: int,
        prompt_text: str,
        event: asyncio.Event,
    ) -> None:
        try:
            timed_out = False
            try:
                await asyncio.wait_for(event.wait(), timeout=max(0.0, self.usage_wait_seconds))
            except asyncio.TimeoutError:
                timed_out = True

            turn_meta = self._last_turn_metadata.pop(request_id, {})
            final_model = metadata.get("model") or metadata.get("active_model") or turn_meta.get("model") or model
            usage = _extract_usage(metadata) or _extract_usage(turn_meta)
            real_usage = bool(usage)
            if not usage:
                usage = _estimate_usage(prompt_text, content, final_model)
            if getattr(self, "debug_usage", False):
                log.info(
                    "agentmint usage wait done request_id=%s timed_out=%s event_set=%s "
                    "metadata=%s turn_meta=%s final_usage=%s real_usage=%s",
                    request_id,
                    timed_out,
                    event.is_set(),
                    _metadata_debug_summary(metadata),
                    _metadata_debug_summary(turn_meta),
                    _usage_log_label(usage),
                    real_usage,
                )
            final_capability = metadata.get("capability") or capability or _capability_hint(final_model)
            await self._upload_answer(
                request_id=request_id,
                content=content,
                model=final_model,
                usage=usage,
                capability=final_capability,
                duration_ms=duration_ms,
            )
        except Exception:
            log.exception("delayed answer upload failed for %s", request_id)
        finally:
            self._pending_answer_uploads.discard(request_id)
            self._turn_metadata_events.pop(request_id, None)

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        content: str,
        *,
        finalize: bool = False,
        metadata: dict | None = None,
    ):
        """Capture Hermes streaming edits and upload only the finalized answer.

        Hermes sends stream previews via `send(..., expect_edits=True)` before
        the agent run has returned usage. AgentMint is a job/result platform,
        not a live chat surface, so previews stay local and only the final edit
        is uploaded through the normal answer pipeline.
        """
        request_id = str(chat_id)
        meta = metadata or {}
        stream_state = self._streaming_answers.setdefault(request_id, {})
        stream_state.update({
            "content": str(content),
            "metadata": dict(meta),
            "message_id": str(message_id),
            "updated_at": time.monotonic(),
        })
        if getattr(self, "debug_usage", False):
            log.info(
                "agentmint streaming edit cached request_id=%s finalize=%s metadata=%s chars=%d",
                request_id,
                finalize,
                _metadata_debug_summary(meta),
                len(str(content)),
            )
        if not finalize:
            return SendResult(success=True, message_id=request_id)

        final_metadata = dict(meta)
        final_metadata.pop("expect_edits", None)
        if "notify" not in final_metadata:
            final_metadata["notify"] = True
        self._streaming_answers.pop(request_id, None)
        return await self.send(
            chat_id=request_id,
            content=str(content),
            reply_to=None,
            metadata=final_metadata,
        )

    async def _upload_answer(
        self,
        *,
        request_id: str,
        content: str,
        model: str,
        usage: dict,
        capability: dict,
        duration_ms: int,
    ):
        answer_payload = {
            "text": content,
            "model": model,
            "usage": usage,
            "capability": capability,
            "duration_ms": duration_ms,
        }
        answer_saved = self._queue.mark(request_id, "answered", answer=answer_payload)
        if not answer_saved:
            log.warning(
                "answer for %s had no local queue row; creating synthetic record (usage=%s)",
                request_id,
                _usage_log_label(usage),
            )
            self._queue.upsert_pending(
                request_id,
                chat_id=request_id,
                question=_synthetic_question_record(request_id),
            )
            self._queue.mark(request_id, "answered", answer=answer_payload)

        if self._client is None:
            log.warning("no ws client; answer for %s sits in queue", request_id)
            return SendResult(success=False, message_id=request_id)

        ok = await self._client.send_answer(
            request_id, text=answer_payload["text"], model=model,
            usage=usage, capability=capability, duration_ms=duration_ms,
        )
        if ok:
            self._queue.mark(request_id, "uploaded")
            log.info("uploaded %s (%dms, usage=%s)", request_id, duration_ms, _usage_log_label(usage))
            return SendResult(success=True, message_id=request_id)
        # WS down — leave job at 'answered'; _on_reconnected will retry.
        return SendResult(success=False, message_id=request_id)

    async def get_chat_info(self, chat_id):  # type: ignore[override]
        job = self._queue.by_chat(str(chat_id))
        if not job:
            return {"name": str(chat_id), "type": "dm"}
        q = job.get("question") or {}
        return {"name": f"Arena: {q.get('title', '')[:40]}", "type": "dm"}

    # ─── Helpers for ctx callbacks ───

    def _quota_snapshot(self) -> dict:
        c = self._queue.counts()
        in_flight = c["pending"] + c["answered"]
        return {
            "used": c["uploaded"],
            "max": self.max_concurrent * 10,
            "remaining_auto": max(0, self.max_concurrent - in_flight),
            "remaining_review": 0,
            "in_flight": in_flight,
        }


# ════════════════════════════════════════════════════════════════
# Module-level helpers Hermes wires into `register_platform(...)`
# ════════════════════════════════════════════════════════════════

def check_requirements() -> bool:
    """`hermes plugins list` uses this to gate the green/red badge."""
    return bool(_configured_connector_id()) and bool(_configured_connector_token())


def validate_config(config) -> bool:
    extra = getattr(config, "extra", {}) or {}
    return bool(
        (os.getenv("AGENTMINT_CONNECTOR_ID") or extra.get("connector_id"))
        and (os.getenv("AGENTMINT_CONNECTOR_TOKEN") or extra.get("connector_token"))
    )


def _env_enablement() -> dict | None:
    """Auto-enable when at minimum the connector credentials are present.

    Hermes calls this during gateway startup; returning None keeps the platform
    dormant. Returning a dict seeds `PlatformConfig.extra`.
    """
    connector_id = _configured_connector_id()
    connector_token = _configured_connector_token()
    if not connector_id or not connector_token:
        return None
    extra: dict[str, Any] = {
        "connector_id": connector_id,
        "connector_token": connector_token,
        "platform_url": _configured_platform_url(),
    }
    home = os.getenv("AGENTMINT_HOME_CHANNEL", "").strip()
    if home:
        extra["home_channel"] = _normalize_home_channel(home)
    return extra


def _apply_yaml_config(yaml_cfg: dict, platform_cfg: dict) -> dict | None:
    """Map `gateway.platforms.agentmint` keys from config.yaml into env / extras."""
    if not isinstance(yaml_cfg, dict) and not isinstance(platform_cfg, dict):
        return None
    source = platform_cfg if isinstance(platform_cfg, dict) and platform_cfg else yaml_cfg
    nested_extra = yaml_cfg.get("extra") if isinstance(yaml_cfg, dict) else None
    if isinstance(source, dict):
        nested_extra = source.get("extra")
    if isinstance(nested_extra, dict):
        source = {**source, **nested_extra}

    out: dict[str, Any] = {}
    for k_yaml, k_extra, env in (
        ("connector_id", "connector_id", "AGENTMINT_CONNECTOR_ID"),
        ("connector_token", "connector_token", "AGENTMINT_CONNECTOR_TOKEN"),
        ("platform_url", "platform_url", "AGENTMINT_PLATFORM_URL"),
        ("max_concurrent", "max_concurrent", "AGENTMINT_MAX_CONCURRENT"),
        ("queue_db", "queue_db", "AGENTMINT_QUEUE_DB"),
        ("usage_wait_seconds", "usage_wait_seconds", "AGENTMINT_USAGE_WAIT_SECONDS"),
        ("debug_usage", "debug_usage", "AGENTMINT_DEBUG_USAGE"),
    ):
        v = source.get(k_yaml)
        if v is None:
            continue
        out[k_extra] = v
        os.environ.setdefault(env, str(v))
    if source.get("home_channel") is not None:
        home = _normalize_home_channel(source["home_channel"])
        if home:
            out["home_channel"] = home
            os.environ.setdefault("AGENTMINT_HOME_CHANNEL", home["chat_id"])
    return out or None


def _normalize_home_channel(value: Any) -> dict[str, str]:
    """Return Hermes' expected HomeChannel seed shape for plugin platforms."""
    if isinstance(value, dict):
        chat_id = str(value.get("chat_id") or value.get("id") or "").strip()
        if not chat_id:
            return {}
        home = {
            "chat_id": chat_id,
            "name": str(value.get("name") or "AgentMint"),
        }
        thread_id = value.get("thread_id")
        if thread_id is not None and str(thread_id).strip():
            home["thread_id"] = str(thread_id).strip()
        return home

    chat_id = str(value or "").strip()
    if not chat_id:
        return {}
    return {"chat_id": chat_id, "name": "AgentMint"}


def _configured_connector_id() -> str:
    return os.getenv("AGENTMINT_CONNECTOR_ID") or _agentmint_config_value("connector_id")


def _configured_connector_token() -> str:
    return os.getenv("AGENTMINT_CONNECTOR_TOKEN") or _agentmint_config_value("connector_token")


def _configured_platform_url() -> str:
    return os.getenv("AGENTMINT_PLATFORM_URL") or _agentmint_config_value("platform_url") or DEFAULT_PLATFORM_URL


def _agentmint_config_value(key: str) -> str:
    cfg = _load_agentmint_yaml_config()
    if not isinstance(cfg, dict):
        return ""
    extra = cfg.get("extra")
    if isinstance(extra, dict) and extra.get(key) is not None:
        return str(extra.get(key) or "")
    if cfg.get(key) is not None:
        return str(cfg.get(key) or "")
    return ""


def _load_agentmint_yaml_config() -> dict:
    path = Path(os.getenv("HERMES_CONFIG", "~/.hermes/config.yaml")).expanduser()
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore
        parsed = yaml.safe_load(text) or {}
        return (((parsed.get("gateway") or {}).get("platforms") or {}).get("agentmint") or {})
    except Exception:
        return _parse_agentmint_config_fallback(text)


def _parse_agentmint_config_fallback(text: str) -> dict:
    out: dict[str, Any] = {}
    in_agentmint = False
    agentmint_indent = 0
    in_extra = False
    extra_indent = 0

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if stripped == "agentmint:":
            in_agentmint = True
            agentmint_indent = indent
            in_extra = False
            continue

        if in_agentmint and indent <= agentmint_indent:
            in_agentmint = False
            in_extra = False
        if not in_agentmint:
            continue

        if stripped == "extra:":
            out.setdefault("extra", {})
            in_extra = True
            extra_indent = indent
            continue

        if in_extra and indent <= extra_indent:
            in_extra = False

        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key in {
            "connector_id",
            "connector_token",
            "platform_url",
            "max_concurrent",
            "queue_db",
            "home_channel",
            "usage_wait_seconds",
            "debug_usage",
        }:
            if in_extra:
                out.setdefault("extra", {})[key] = value
            else:
                out[key] = value
    return out


async def _standalone_send(pconfig, chat_id, message, *, thread_id=None,
                            media_files=None, force_document=False) -> dict:
    """Out-of-process delivery path (cron). Opens a one-shot WS connection,
    uploads the answer, then closes. The platform's `request_id` idempotency
    means double-delivery is harmless.
    """
    extra = (getattr(pconfig, "extra", None) or {})
    cid = os.getenv("AGENTMINT_CONNECTOR_ID") or extra.get("connector_id", "")
    tok = os.getenv("AGENTMINT_CONNECTOR_TOKEN") or extra.get("connector_token", "")
    url = os.getenv("AGENTMINT_PLATFORM_URL") or extra.get("platform_url", DEFAULT_PLATFORM_URL)
    if not cid or not tok:
        return {"error": "AGENTMINT_CONNECTOR_ID/TOKEN not configured"}

    delivered = asyncio.Event()
    result: dict[str, Any] = {}

    async def _on_q(_msg):  # unused
        pass

    async def _on_re():
        pass

    client = ArenaWSClient(
        platform_url=url, connector_id=cid, connector_token=tok,
        on_question=_on_q, on_reconnected=_on_re,
        quota_provider=lambda: {"used": 0, "max": 50, "remaining_auto": 0, "remaining_review": 0},
        agent_type="hermes", agent_version="0.1.0",
    )
    client.start()
    try:
        # Wait briefly for connection
        for _ in range(20):
            if client.is_connected:
                break
            await asyncio.sleep(0.5)
        if not client.is_connected:
            return {"error": "could not connect to Arena platform"}

        ok = await client.send_answer(
            str(chat_id),
            text=str(message),
            model="hermes",
            usage={},
            capability=_capability_hint("hermes"),
        )
        if ok:
            result = {"success": True, "message_id": str(chat_id)}
        else:
            result = {"error": "send_answer returned False"}
    finally:
        await client.stop()
    return result


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

def _format_prompt(title: str, body: str, tags: list, asker_nick: str) -> str:
    """Render an Arena question as a natural Hermes user message."""
    parts = [f"# {title}"]
    if body:
        parts.append(f"\n{body}")
    if tags:
        parts.append(f"\n[标签: {', '.join(tags)}]")
    parts.append(f"\n\n{AGENTMINT_PROMPT_SAFETY_GUIDANCE}")
    parts.append(f"\n— 来自 AgentMint 提问者「{asker_nick}」。请给出清晰、可执行的回答。")
    return "\n".join(parts)


def _prompt_from_job(job: dict | None) -> str:
    if not job:
        return ""
    q = job.get("question") or {}
    asker = q.get("asker") or {}
    return _format_prompt(
        q.get("title") or "",
        (q.get("body") or "").strip(),
        q.get("tags") or [],
        asker.get("nickname", "anonymous"),
    )


def _synthetic_question_record(request_id: str) -> dict:
    return {
        "title": f"AgentMint request {request_id}",
        "body": "",
        "tags": [],
        "asker": {"nickname": "unknown", "trust_level": 1},
        "deadline_at": None,
        "synthetic": True,
    }


def _capability_hint(model: str) -> dict:
    return {
        "engine": {"provider": "hermes", "model": model or "hermes"},
        "skills": [],
        "tools": [],
        "mcp_servers": [],
    }


def _extract_usage(metadata: dict | None) -> dict:
    """Extract token usage from known Hermes metadata/result shapes.

    Current Hermes platform delivery usually passes thread-routing metadata
    only. Newer or locally patched gateways may pass either `usage` directly or
    the full run_conversation result containing prompt/completion totals.
    """
    if not isinstance(metadata, dict):
        return {}

    usage = metadata.get("usage") or metadata.get("token_usage")
    if usage:
        normalized = _normalize_usage_obj(usage)
        if normalized:
            return normalized

    return _normalize_usage_obj(metadata)


def _normalize_usage_obj(value: Any) -> dict:
    if not value:
        return {}

    def _field(name: str) -> int:
        raw = value.get(name) if isinstance(value, dict) else getattr(value, name, 0)
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    prompt = _field("prompt_tokens") or _field("input_tokens")
    completion = _field("completion_tokens") or _field("output_tokens")
    total = _field("total_tokens") or prompt + completion
    cached = _field("cached_tokens") or _field("cache_read_tokens") or _field("cache_write_tokens")

    out = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }
    if cached:
        out["cached_tokens"] = cached
    return out if any(out.values()) else {}


def _usage_log_label(usage: dict | None) -> str:
    if not isinstance(usage, dict) or not usage:
        return "empty"
    total = usage.get("total_tokens", 0)
    source = usage.get("source") or ("estimated" if usage.get("estimated") else "provider")
    return f"{total}:{source}"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES


def _metadata_debug_summary(value: Any) -> str:
    if not isinstance(value, dict):
        return f"type={type(value).__name__}"

    keys = sorted(str(k) for k in value.keys())
    limited_keys = keys[:30]
    if len(keys) > len(limited_keys):
        limited_keys.append(f"...+{len(keys) - len(limited_keys)}")

    token_fields: dict[str, Any] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "last_prompt_tokens",
        "last_completion_tokens",
        "last_total_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "cached_tokens",
    ):
        if key in value:
            token_fields[key] = value.get(key)

    usage = value.get("usage") or value.get("token_usage")
    usage_keys: list[str] = []
    if isinstance(usage, dict):
        usage_keys = sorted(str(k) for k in usage.keys())
    elif usage is not None:
        usage_keys = [f"type:{type(usage).__name__}"]

    return (
        f"type=dict keys={limited_keys} token_fields={token_fields} "
        f"usage_keys={usage_keys} extracted={_usage_log_label(_extract_usage(value))}"
    )


def _estimate_usage(prompt_text: str, completion_text: str, model: str = "hermes") -> dict:
    prompt = _estimate_token_count(prompt_text, model)
    completion = _estimate_token_count(completion_text, model)
    total = prompt + completion
    if total <= 0:
        return {}
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "estimated": True,
        "source": "agentmint_plugin_estimate",
    }


def _estimate_token_count(text: str, model: str = "hermes") -> int:
    if not text:
        return 0

    try:
        import tiktoken  # type: ignore

        try:
            encoding = tiktoken.encoding_for_model(model)
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        pass

    ascii_chars = 0
    cjk_chars = 0
    other_chars = 0
    for ch in text:
        code = ord(ch)
        if ch.isspace():
            continue
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0x3040 <= code <= 0x30FF
            or 0xAC00 <= code <= 0xD7AF
        ):
            cjk_chars += 1
        elif code < 128:
            ascii_chars += 1
        else:
            other_chars += 1

    # Conservative dependency-free approximation:
    # English/code averages near 4 chars/token; CJK is often close to 1 char/token.
    return max(1, math.ceil(ascii_chars / 4) + cjk_chars + math.ceil(other_chars / 2))


# ════════════════════════════════════════════════════════════════
# Plugin entry point — Hermes calls this on startup
# ════════════════════════════════════════════════════════════════

def register(ctx):
    """Wire the Arena platform into Hermes's gateway."""
    if not _HERMES_AVAILABLE:
        log.error("Hermes runtime not detected; agentmint-platform plugin disabled")
        return

    ctx.register_platform(
        name="agentmint",
        label="AgentMint",
        adapter_factory=lambda cfg: ArenaAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        env_enablement_fn=_env_enablement,
        apply_yaml_config_fn=_apply_yaml_config,
        standalone_sender_fn=_standalone_send,
        required_env=["AGENTMINT_CONNECTOR_ID", "AGENTMINT_CONNECTOR_TOKEN"],
        install_hint=(
            "1. 登录 AgentMint Web → /my/agents → 选 Agent → 生成 Connector Token。\n"
            "2. 把 connector_id 设为 AGENTMINT_CONNECTOR_ID, token 设为 AGENTMINT_CONNECTOR_TOKEN。\n"
            "3. （可选）设 AGENTMINT_PLATFORM_URL 指向你的部署地址。"
        ),
        cron_deliver_env_var="AGENTMINT_HOME_CHANNEL",
        max_message_length=0,           # no chunking — AgentMint handles long answers
        platform_hint=AGENTMINT_PLATFORM_HINT,
        emoji="🏟",
    )
