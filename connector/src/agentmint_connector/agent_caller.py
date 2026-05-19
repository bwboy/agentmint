"""Local Agent caller — talks to any OpenAI-compatible /v1/chat/completions.

Tested against:
  - OpenAI         https://api.openai.com/v1
  - Anthropic      via OpenAI-compat layer (some proxies)
  - Ollama         http://localhost:11434/v1
  - vLLM           http://localhost:8000/v1
  - OpenClaw       http://127.0.0.1:18789/v1
  - Hermes         (Python service exposing /v1/chat/completions)

Concurrency is bounded by Config.max_concurrent so we never overwhelm the local
agent; the platform side already paces deliveries via push_question.
"""
import asyncio
import logging
import time
from typing import Any

import httpx

from .config import Config

log = logging.getLogger(__name__)


class AgentCaller:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._sem = asyncio.Semaphore(max(1, cfg.max_concurrent))
        headers = {"Content-Type": "application/json"}
        if cfg.agent_api_key:
            headers["Authorization"] = f"Bearer {cfg.agent_api_key}"
        self._client = httpx.AsyncClient(
            base_url=cfg.agent_api_base.rstrip("/"),
            timeout=httpx.Timeout(cfg.agent_timeout, connect=10),
            headers=headers,
        )

    async def aclose(self):
        await self._client.aclose()

    async def chat(self, question: dict) -> dict:
        """Call the local agent and return a normalized result.

        Returns:
            {
              "status":   "success" | "error",
              "text":     "<assistant content>",
              "model":    "<echoed model>",
              "usage":    {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N},
              "duration_ms": int,
              "error":    "<message>",   # only when status=error
            }
        """
        async with self._sem:
            return await self._call_once(question)

    async def _call_once(self, question: dict) -> dict:
        title = question.get("title", "")
        body = question.get("body", "") or ""
        tags = question.get("tags") or []
        user_content = self._format_prompt(title, body, tags)

        payload = {
            "model": self.cfg.agent_model,
            "messages": [
                {"role": "system", "content": self.cfg.system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.4,
        }

        start = time.monotonic()
        try:
            resp = await self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as e:
            return {"status": "error", "error": f"network: {e}", "duration_ms": _ms(start)}

        if resp.status_code != 200:
            err_text = (resp.text or "")[:500]
            log.warning("agent api %d: %s", resp.status_code, err_text)
            return {"status": "error", "error": f"HTTP {resp.status_code}: {err_text}",
                    "duration_ms": _ms(start)}

        try:
            data = resp.json()
        except Exception:
            return {"status": "error", "error": "agent returned non-JSON",
                    "duration_ms": _ms(start)}

        text = self._extract_content(data)
        if not text:
            return {"status": "error", "error": "agent returned empty content",
                    "duration_ms": _ms(start)}

        usage = self._normalize_usage(data.get("usage") or {})
        return {
            "status": "success",
            "text": text,
            "model": data.get("model") or self.cfg.agent_model,
            "usage": usage,
            "duration_ms": _ms(start),
        }

    # ─── Helpers ───

    @staticmethod
    def _format_prompt(title: str, body: str, tags: list) -> str:
        parts = [f"# 问题\n{title}"]
        if body.strip():
            parts.append(f"\n## 补充说明\n{body.strip()}")
        if tags:
            parts.append(f"\n## 标签\n{', '.join(tags)}")
        parts.append("\n请生成一份清晰、可执行的回答。")
        return "\n".join(parts)

    @staticmethod
    def _extract_content(data: dict) -> str:
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError):
            return ""
        msg = choice.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content
        # Some providers stream content as a list of parts
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return ""

    @staticmethod
    def _normalize_usage(usage: dict) -> dict:
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        tt = int(usage.get("total_tokens") or (pt + ct))
        return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def build_capability(cfg: Config, model: str) -> dict:
    """Produce a capability fingerprint for the answer.

    MVP: derive engine from base URL + model. Real Plugin would scan local
    Skills / MCP / KB and merge them in.
    """
    base = (cfg.agent_api_base or "").lower()
    if "openai.com" in base:
        provider = "openai"
    elif "anthropic" in base:
        provider = "anthropic"
    elif "ollama" in base or ":11434" in base:
        provider = "ollama"
    elif "vllm" in base or ":8000" in base:
        provider = "vllm"
    elif ":18789" in base:
        provider = "openclaw"
    else:
        provider = cfg.agent_type
    return {
        "engine": {"provider": provider, "model": model},
        "skills": [],
        "tools": [],
        "mcp_servers": [],
    }
