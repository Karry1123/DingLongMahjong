import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

_LOCAL_ORIGINS = [
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

app = FastAPI(title="Mahjong EV API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://[a-zA-Z0-9-]+\.vercel\.app$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Mahjong EV API is running"}
