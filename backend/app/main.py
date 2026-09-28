import os

from fastapi import FastAPI
from app.core.origins import LanCORSMiddleware

from app.api.routes import router
from app.api.rooms import router as room_router

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

app = FastAPI(title="顶龙麻将", version="0.3.1-beta")

app.add_middleware(
    LanCORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(room_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "顶龙麻将 API is running"}
