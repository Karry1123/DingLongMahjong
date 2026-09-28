"""Room registration and authenticated real-time room endpoints."""
import asyncio
import os
import re
import secrets
import sqlite3
import unicodedata
from pathlib import Path
from uuid import UUID
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class Visitor(BaseModel):
    client_id: UUID
    nickname: str = Field(max_length=64)


class CreateRoom(Visitor):
    capacity: int = Field(ge=2, le=4)


class Membership(BaseModel):
    client_id: UUID


def validate_nickname(value: str) -> str:
    name = value.strip()
    normalized = unicodedata.normalize("NFKC", name)
    compact = re.sub(r"[\s\W_]", "", normalized, flags=re.UNICODE)
    if not compact or any(unicodedata.category(c).startswith("C") for c in name):
        raise HTTPException(422, "请输入有效昵称")
    if len(name) > 6:
        raise HTTPException(422, "昵称最多 6 个字")
    if re.search(r"ai[1-4一二三四](?![0-9])", compact, re.IGNORECASE):
        raise HTTPException(422, "AI 1号至 AI 4号为系统保留昵称，请换一个名字")
    return name


@contextmanager
def connect():
    path = Path(os.getenv("ROOM_DB_PATH", str(Path(__file__).resolve().parents[2] / "data" / "rooms.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, capacity INTEGER NOT NULL, host TEXT NOT NULL, closed INTEGER NOT NULL DEFAULT 0)")
    db.execute("CREATE TABLE IF NOT EXISTS members (room_id TEXT REFERENCES rooms(id), client_id TEXT, nickname TEXT NOT NULL, seat INTEGER NOT NULL, PRIMARY KEY(room_id, client_id), UNIQUE(room_id, seat))")
    # Upgrade databases created by Phase 1 without losing room-number reservations.
    for table, column, definition in [("rooms", "status", "TEXT NOT NULL DEFAULT 'waiting'"), ("rooms", "start_at", "REAL"), ("members", "ready", "INTEGER NOT NULL DEFAULT 0")]:
        if column not in {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError as error:
                if "duplicate column" not in str(error):
                    raise
    db.commit()
    try:
        with db:
            yield db
    finally:
        db.close()


def snapshot(db, room_id):
    room = db.execute("SELECT * FROM rooms WHERE id=? AND closed=0", (room_id,)).fetchone()
    if room is None:
        raise HTTPException(404, "房间不存在或已关闭，请核对房间号")
    players = db.execute("SELECT nickname, seat, client_id, ready FROM members WHERE room_id=? ORDER BY seat", (room_id,)).fetchall()
    # Client identifiers are membership credentials and must never be broadcast.
    humans = [{"nickname": p["nickname"], "seat": p["seat"], "seat_wind": "ESWN"[p["seat"]], "is_host": p["client_id"] == room["host"], "is_ai": False, "ready": bool(p["ready"])} for p in players]
    ai = []
    if len(humans) == room["capacity"]:
        empty = [seat for seat in range(4) if seat not in {p["seat"] for p in players}]
        ai = [{"nickname": f"AI {index + 1}号", "seat": seat, "seat_wind": "ESWN"[seat], "is_host": False, "is_ai": True, "ready": True} for index, seat in enumerate(empty)]
    return {"room_id": room_id, "capacity": room["capacity"], "players": sorted(humans + ai, key=lambda p: p["seat"]), "human_count": len(humans), "status": room["status"], "start_at": room["start_at"]}


def membership_snapshot(db, room_id, client_id):
    result = snapshot(db, room_id)
    member = db.execute("SELECT seat FROM members WHERE room_id=? AND client_id=?", (room_id, client_id)).fetchone()
    if member is None:
        raise HTTPException(403, "你已离开此房间，请重新加入")
    return {**result, "my_seat": member["seat"]}


@router.post("")
def create_room(payload: CreateRoom):
    nickname = validate_nickname(payload.nickname)
    client_id = str(payload.client_id)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for _ in range(100):
            room_id = str(secrets.randbelow(900000) + 100000)
            try:
                db.execute("INSERT INTO rooms(id, capacity, host) VALUES(?, ?, ?)", (room_id, payload.capacity, client_id))
                break
            except sqlite3.IntegrityError:
                continue
        else:
            raise HTTPException(503, "房间号暂时无法分配，请稍后重试")
        db.execute("INSERT INTO members(room_id, client_id, nickname, seat) VALUES(?, ?, ?, 0)", (room_id, client_id, nickname))
        return membership_snapshot(db, room_id, client_id)


@router.post("/{room_id}/join")
def join_room(room_id: str, payload: Visitor):
    nickname = validate_nickname(payload.nickname)
    client_id = str(payload.client_id)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        room = snapshot(db, room_id)
        if room["status"] != "waiting":
            raise HTTPException(409, "对局已开始或正在倒计时，不能加入")
        existing = db.execute("SELECT seat FROM members WHERE room_id=? AND client_id=?", (room_id, client_id)).fetchone()
        duplicate = db.execute("SELECT nickname FROM members WHERE room_id=? AND client_id!=?", (room_id, client_id)).fetchall()
        if any(p["nickname"].casefold() == nickname.casefold() for p in duplicate):
            raise HTTPException(409, "房间内已有同名玩家，请修改昵称")
        if existing:
            db.execute("UPDATE members SET nickname=? WHERE room_id=? AND client_id=?", (nickname, room_id, client_id))
        else:
            seats = {p["seat"] for p in room["players"] if not p["is_ai"]}
            if len(seats) >= room["capacity"]:
                raise HTTPException(409, "房间已满，请加入其他房间")
            seat = next(s for s in range(4) if s not in seats)
            db.execute("INSERT INTO members(room_id, client_id, nickname, seat) VALUES(?, ?, ?, ?)", (room_id, client_id, nickname, seat))
        return membership_snapshot(db, room_id, client_id)


@router.post("/{room_id}/state")
def room_state(room_id: str, payload: Membership):
    with connect() as db:
        return membership_snapshot(db, room_id, str(payload.client_id))


@router.post("/{room_id}/leave")
async def leave_room(room_id: str, payload: Membership):
    client_id = str(payload.client_id)
    with connect() as db:
        membership_snapshot(db, room_id, client_id)
    await rooms_manager.dissolve(room_id, client_id, "退出")
    return {"left": True}


# Imported after the storage functions so the manager can reuse the registration database.
from app.core.rooms_manager import RoomsManager

rooms_manager = RoomsManager()


@router.websocket("/{room_id}/ws")
async def room_socket(websocket: WebSocket, room_id: str):
    # Browser requests must originate from an allowed frontend (CORS alone does not cover WS).
    origin = websocket.headers.get("origin")
    if origin:
        from app.main import allowed_origins
        from app.core.origins import origin_allowed
        if not origin_allowed(origin, allowed_origins):
            await websocket.close(code=1008)
            return
    await websocket.accept()
    client_id = None
    try:
        hello = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if not isinstance(hello, dict) or hello.get("type") != "join":
            raise HTTPException(422, "请先提交入房信息")
        visitor = Visitor.model_validate(hello)
        client_id = str(visitor.client_id)
        await rooms_manager.attach(room_id, visitor, websocket)
        while True:
            message = await asyncio.wait_for(websocket.receive_json(), timeout=35)
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "message": "无效的房间消息"})
                continue
            try:
                await rooms_manager.handle(room_id, client_id, websocket, message)
                if message.get("type") == "leave":
                    return
            except HTTPException as error:
                await websocket.send_json({"type": "error", "message": error.detail})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except (HTTPException, ValueError) as error:
        try:
            await websocket.send_json({"type": "error", "message": getattr(error, "detail", "入房信息无效")})
            await websocket.close(code=1008)
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        if client_id:
            await rooms_manager.detach(room_id, client_id, websocket)
