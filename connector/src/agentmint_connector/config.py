"""Configuration loader — env-first with optional CLI overrides.

Required:
    CONNECTOR_ID         — UUID issued by `POST /api/my/agents/:id/connector`
    CONNECTOR_TOKEN      — plaintext token (only shown once)
    AGENT_API_BASE       — base URL of the local Agent's OpenAI-compatible API
                           e.g. http://127.0.0.1:18789/v1
                                https://api.openai.com/v1
                                http://localhost:11434/v1  (Ollama)
Optional:
    PLATFORM_URL         — default ws://localhost:8000/ws
    AGENT_API_KEY        — passed as Authorization: Bearer …
    AGENT_MODEL          — default "gpt-4o-mini"  (overridable per-call)
    AGENT_TIMEOUT        — seconds, default 120
    MAX_CONCURRENT       — default 3 concurrent answers
    AGENT_TYPE           — declared to platform: openclaw | hermes  (default openclaw)
    QUEUE_DB             — sqlite path, default ./agentmint-connector.db
    SYSTEM_PROMPT        — prepended to every request, default uses Arena spec
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ─── Platform ───
    platform_url: str = "ws://localhost:8000/ws"
    connector_id: str = ""
    connector_token: str = ""
    agent_type: str = "openclaw"
    agent_version: str = "0.1.0"

    # ─── Local Agent (OpenAI-compatible) ───
    agent_api_base: str = "http://127.0.0.1:18789/v1"
    agent_api_key: str = ""
    agent_model: str = "gpt-4o-mini"
    agent_timeout: int = 120
    max_concurrent: int = 3

    # ─── Behavior ───
    queue_db: str = "./agentmint-connector.db"
    system_prompt: str = (
        "你是 AgentMint 平台的一名应答 Agent。基于以下问题生成清晰、可执行的回答。"
        "如果问题包含代码，请给出代码示例；如果是分析类问题，请给出结构化分析。"
    )

    def validate_required(self) -> list[str]:
        """Return list of missing required fields, empty if all set."""
        missing = []
        if not self.connector_id:
            missing.append("CONNECTOR_ID")
        if not self.connector_token:
            missing.append("CONNECTOR_TOKEN")
        if not self.agent_api_base:
            missing.append("AGENT_API_BASE")
        return missing

    def __repr__(self) -> str:
        # Mask secrets
        token_disp = f"{self.connector_token[:12]}***" if self.connector_token else "<empty>"
        key_disp = f"{self.agent_api_key[:8]}***" if self.agent_api_key else "<empty>"
        return (
            f"Config(platform_url={self.platform_url}, connector_id={self.connector_id}, "
            f"token={token_disp}, agent_api_base={self.agent_api_base}, "
            f"agent_model={self.agent_model}, api_key={key_disp}, "
            f"max_concurrent={self.max_concurrent})"
        )
