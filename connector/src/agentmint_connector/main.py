"""Main scheduling loop — glues WS / Agent / Queue together.

Flow:
1. Open WS, send auth.
2. On startup AND on each reconnect, resume any persisted unfinished jobs:
     - pending/processing → re-call the agent
     - done               → re-upload (request_id makes this idempotent)
3. For each incoming `question`:
     - upsert into queue as 'pending'
     - send `ack` immediately
     - schedule `handle_job` (agent call → upload)
"""
import asyncio
import logging

from .config import Config
from .agent_caller import AgentCaller, build_capability
from .queue import JobQueue
from .ws_client import WSClient

log = logging.getLogger(__name__)


async def run(cfg: Config):
    queue = JobQueue(cfg.queue_db)
    counts = queue.counts()
    log.info("queue at startup: %s", counts)

    caller = AgentCaller(cfg)

    def quota_provider():
        c = queue.counts()
        in_flight = c["pending"] + c["processing"]
        return {
            "used": c["uploaded"],
            "max": cfg.max_concurrent * 10,
            "remaining_auto": max(0, cfg.max_concurrent - in_flight),
            "remaining_review": 0,
            "in_flight": in_flight,
        }

    client = WSClient(cfg, quota_provider=quota_provider)
    in_flight: set[asyncio.Task] = set()

    async def handle_job(request_id: str, question: dict):
        """Run the agent, persist answer, upload to platform.

        Safe to retry: if upload fails the job stays as 'done' and will be
        picked up by `resume_pending` on the next reconnect.
        """
        try:
            queue.mark(request_id, "processing")
            result = await caller.chat(question)

            if result.get("status") == "success":
                answer = {
                    "type": "answer",
                    "request_id": request_id,
                    "status": "success",
                    "content": {"text": result["text"], "attachments": []},
                    "model": result["model"],
                    "usage": result["usage"],
                    "capability": build_capability(cfg, result["model"]),
                    "duration_ms": result["duration_ms"],
                }
                queue.mark(request_id, "done", answer=answer)
                ok = await client.send(answer)
                if ok:
                    queue.mark(request_id, "uploaded")
                    log.info("uploaded %s (%dms, %d tokens)", request_id,
                             result["duration_ms"], result["usage"].get("total_tokens", 0))
                else:
                    log.warning("upload failed for %s, will retry on reconnect", request_id)
            else:
                # Agent error — mark failed and tell platform so it stops waiting.
                err = result.get("error", "unknown")
                answer = {
                    "type": "answer",
                    "request_id": request_id,
                    "status": "error",
                    "error": err,
                    "retryable": False,
                }
                queue.mark(request_id, "failed", error=err)
                await client.send(answer)
                log.warning("agent call failed for %s: %s", request_id, err)
        except Exception as e:
            log.exception("unhandled error processing %s", request_id)
            queue.mark(request_id, "failed", error=str(e))

    async def resume_pending():
        for job in queue.list_resumable():
            rid = job["request_id"]
            status = job["status"]
            if status == "done":
                # Re-upload from persisted answer
                answer = job.get("answer")
                if answer and await client.send(answer):
                    queue.mark(rid, "uploaded")
                    log.info("re-uploaded %s", rid)
                else:
                    log.warning("re-upload of %s deferred — will retry next reconnect", rid)
            elif status in ("pending", "processing"):
                log.info("resuming %s (status was %s)", rid, status)
                _schedule(handle_job(rid, job["question"]))

    def _schedule(coro):
        task = asyncio.create_task(coro)
        in_flight.add(task)
        task.add_done_callback(in_flight.discard)

    # ─── Main message loop ───

    try:
        async for msg in client.messages():
            mtype = msg.get("type")

            if mtype == "__reconnected__":
                log.info("reconnected — replaying persisted jobs")
                await resume_pending()

            elif mtype == "auth_ok":
                # WSClient already logged; resume work after first auth too.
                await resume_pending()

            elif mtype == "question":
                rid = msg.get("request_id")
                if not rid:
                    log.warning("question without request_id, ignored")
                    continue
                question = {
                    "title": msg.get("title", ""),
                    "body": msg.get("body", ""),
                    "tags": msg.get("tags") or [],
                    "asker": msg.get("asker"),
                    "deadline_at": msg.get("deadline_at"),
                }
                # Idempotent insert; if already known, just re-ack and (re)process.
                queue.upsert_pending(rid, question)
                await client.send({"type": "ack", "request_id": rid})
                _schedule(handle_job(rid, question))

            elif mtype == "update_config":
                # MVP: just acknowledge
                await client.send({
                    "type": "config_ack",
                    "applied_fields": list((msg.get("fields") or {}).keys()),
                })
            elif mtype == "auth_fail":
                log.error("auth_fail: %s", msg.get("reason"))
                break
            else:
                log.debug("unhandled msg type: %s", mtype)

    finally:
        # Drain in-flight tasks so SQLite writes complete before close
        if in_flight:
            log.info("waiting for %d in-flight jobs to finish ...", len(in_flight))
            await asyncio.gather(*in_flight, return_exceptions=True)
        await caller.aclose()
        await client.close()
        queue.close()
        log.info("shutdown complete")
