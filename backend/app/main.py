import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from app.storage.db import ensure_schema, connect, utcnow
from app.api import auth, friends, matches, realtime
from app.core.origins import LanCORSMiddleware

from app.api.routes import router
from app.api.rooms import router as room_router
from app.api.app_update import router as app_update_router
from app.core.ai_weights import ai_weights_session

_LOCAL_ORIGINS = [
    "https://ding-long-mahjong.vercel.app",
    "https://karry1123.github.io",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
def _parse_allowed_origins(raw: str) -> list[str]:
    return list(dict.fromkeys(_LOCAL_ORIGINS + [
        origin.strip().rstrip("/")
        for origin in raw.split(",")
        if origin.strip()
    ]))


allowed_origins = _parse_allowed_origins(os.getenv("ALLOWED_ORIGINS", ""))

@asynccontextmanager
async def lifespan(application):
    ensure_schema()
    with connect() as db:
        db.execute("UPDATE matches SET status='aborted', start_at=NULL,updated_at=? WHERE status IN ('inviting','waiting','countdown','playing')", (utcnow(),))
        db.execute("UPDATE invitations SET status='cancelled',responded_at=? WHERE status='pending'", (utcnow(),))
    with ai_weights_session() as policy:
        application.state.ai_policy = policy
        yield

app = FastAPI(title="顶龙麻将", version="0.4.3-beta", lifespan=lifespan)

app.add_middleware(
    LanCORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(room_router)
app.include_router(app_update_router)
for api_router in (auth.router, friends.router, matches.router, realtime.router):
    app.include_router(api_router)

@app.exception_handler(HTTPException)
async def api_error(request, error):
    if not social_path(request.url.path):
        return await http_exception_handler(request, error)
    detail = error.detail
    return JSONResponse(status_code=error.status_code,content=detail if isinstance(detail, dict) else {"detail":detail,"code":"request_failed"},headers=error.headers)

@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    if not social_path(request.url.path):
        return await request_validation_exception_handler(request, error)
    return JSONResponse(status_code=422,content={"detail":"请求参数格式不正确","code":"validation_error"})

def social_path(path):
    return any(path == prefix or path.startswith(prefix + '/') for prefix in (
        '/api/auth', '/api/me', '/api/users', '/api/friends', '/api/friend-requests',
        '/api/matches', '/api/invitations', '/api/realtime'))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "顶龙麻将 API is running"}
