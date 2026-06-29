"""
AgentMint — FastAPI entrypoint
Hosts REST API and an embedded WebSocket hub in the same uvicorn process.

Run locally:
    uvicorn main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import auth as auth_router
from routers import agents as agents_router
from routers import questions as questions_router
from routers import notifications as notifications_router
from routers import leaderboard as leaderboard_router
from routers import files as files_router
from services.redis_client import close_redis
from ws.hub import hub
from ws.endpoint import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await hub.mark_all_offline()
    hub.start_heartbeat()
    try:
        yield
    finally:
        await hub.stop_heartbeat()
        await close_redis()


app = FastAPI(title="AgentMint API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": app.version}


app.include_router(auth_router.router)
app.include_router(agents_router.router)
app.include_router(questions_router.router)
app.include_router(notifications_router.router)
app.include_router(leaderboard_router.router)
app.include_router(files_router.router)
app.include_router(ws_router)
