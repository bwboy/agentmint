"""FastAPI WebSocket endpoint — mounted on `/ws` and delegates to Hub."""
from fastapi import APIRouter, WebSocket

from ws.hub import hub

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await hub.handle(websocket)
