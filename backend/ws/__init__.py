"""Embedded WebSocket hub package.

Single-process model for MVP: the FastAPI uvicorn worker hosts both REST API
and the WebSocket hub. `hub` is a module-level singleton, so REST routers
(notably `questions.create_question`) can push directly into it after matching.
"""
from .hub import hub, Hub, WSClient

__all__ = ["hub", "Hub", "WSClient"]
