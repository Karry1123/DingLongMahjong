"""Completed PvE game archives. A transaction keeps the latest 200 games."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
import zlib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "game_records.sqlite3"
MAX_RECORDS = 200
_WIND_ORDER = ("E", "S", "W", "N")
_WIND_NAMES = {"E": "东风", "S": "南风", "W": "西风", "N": "北风"}
_HONOR_NAMES = {**_WIND_NAMES, "C": "红中", "F": "发财", "P": "白板"}
_DIGITS = "一二三四五六七八九"


def _tile_name(tile: str | None) -> str:
    if not tile:
        return ""
    if tile in _HONOR_NAMES:
        return _HONOR_NAMES[tile]
    if len(tile) == 2 and tile[0] in "123456789" and tile[1] in "mps":
        return _DIGITS[int(tile[0]) - 1] + {"m": "万", "p": "筒", "s": "条"}[tile[1]]
    return tile


def _summary(record: dict[str, Any]) -> dict[str, Any]:
    """Build a compact, seat-relative history row from archived settlement facts."""
    config = record.get("config") or {}
    final = record.get("final_result") or {}
    details = final.get("details") or {}
    payments = details.get("payments") or {}
    inherent = payments.get("inherent_detail") or {}
    net = details.get("net_by_seat") or {}
    hu_detail = details.get("hu_detail") or {}
    self_seat = config.get("seat_wind") if config.get("seat_wind") in _WIND_ORDER else "E"
    i = _WIND_ORDER.index(self_seat)
    seats = {"self_score": self_seat, "xiajia_score": _WIND_ORDER[(i + 1) % 4],
             "duijia_score": _WIND_ORDER[(i + 2) % 4],
             "shangjia_score": _WIND_ORDER[(i + 3) % 4]}
    winner = final.get("winner_seat")
    win_type = final.get("win_type") or "draw"
    is_draw = win_type == "draw" or not winner
    win_tile = next((step.get("tile") for step in reversed(record.get("steps") or [])
                     if step.get("action") == "WIN" and step.get("tile")), None)
    win_tile = win_tile or (hu_detail.get("best_decomposition") or {}).get("win_tile")
    role_names = {self_seat: "自家", seats["xiajia_score"]: "下家",
                  seats["duijia_score"]: "对家", seats["shangjia_score"]: "上家"}
    score_fields = {}
    for field, seat in seats.items():
        raw = inherent.get(seat) or {}
        if not isinstance(raw, dict):
            raw = {"calculated_points": raw}
        is_winner = seat == winner and not is_draw
        score_fields[field] = {
            "seat": seat, "net": int(net.get(seat) or 0),
            "hu": int((hu_detail.get("final_hu") if is_winner else raw.get("calculated_points")) or 0),
            "base_hu": int((hu_detail.get("base_hu") if is_winner else raw.get("base_hu")) or 0),
            "fan": int((hu_detail.get("fan") if is_winner else raw.get("fan_count")) or 0),
            "hu_items": ((hu_detail.get("details") or {}).get("score_items") or [])
                        if is_winner else list(raw.get("items") or []),
            "fan_items": ((hu_detail.get("details") or {}).get("fan_items") or [])
                         if is_winner else list(raw.get("fan_details") or []),
        }
    snapshot = (record.get("steps") or [{}])[-1].get("snapshot") or {}
    round_wind = (snapshot.get("self") or {}).get("roundWind") or "E"
    return {
        "game_id": record.get("game_id"), "timestamp": record.get("timestamp"),
        "round_id": record.get("round_id"), "round_wind": round_wind,
        "circle_index": config.get("circle_index"), "round_index": config.get("round_index"),
        "dealer_seat": config.get("dealer_seat") or "E", "self_seat": self_seat,
        "win_type": win_type, "winner_seat": winner, "win_tile": win_tile,
        "winner_name": "荒牌流局" if is_draw else
            f"{role_names.get(winner, '玩家')}·{_WIND_NAMES.get(winner, winner)}"
            f"{'自摸' if win_type in ('zimo', 'self_draw_win') else '捉铳'}"
            f"{(' ' + _tile_name(win_tile)) if win_tile else ''}",
        "win_tile_name": _tile_name(win_tile),
        "points": int(final.get("points") or 0), "fan": int(hu_detail.get("fan") or 0),
        "is_lazi": bool(payments.get("is_lazi") or
                        any(item.get("capped") for item in payments.get("winner_payout_transactions") or [])),
        **score_fields,
    }


def list_game_record_summaries(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Return the retained games newest first without sending walls or private hands."""
    pg_url = _postgres_url(db_path)
    if pg_url:
        with _pg_connect(pg_url) as db:
            rows = db.execute("SELECT payload FROM game_records ORDER BY timestamp DESC, id DESC LIMIT %s",
                              (MAX_RECORDS,)).fetchall()
    else:
        path = _db_path(db_path)
        if not path.exists():
            return []
        with closing(_connect(path)) as db:
            rows = db.execute("SELECT payload FROM game_records ORDER BY timestamp DESC, id DESC LIMIT ?",
                              (MAX_RECORDS,)).fetchall()
    return [_summary(json.loads(zlib.decompress(row[0]))) for row in rows]


def _postgres_url(db_path: Path | None) -> str | None:
    if db_path is not None or os.getenv("GAME_RECORD_DB_PATH"):
        return None
    url = os.getenv("DATABASE_URL", "")
    return url if url.startswith(("postgres://", "postgresql://")) else None


def _pg_connect(url: str):
    import psycopg

    db = psycopg.connect(url, connect_timeout=15)
    db.execute("""CREATE TABLE IF NOT EXISTS game_records (
        id BIGSERIAL PRIMARY KEY,
        game_id TEXT NOT NULL UNIQUE,
        round_id TEXT NOT NULL UNIQUE,
        timestamp TEXT NOT NULL,
        payload BYTEA NOT NULL
    )""")
    db.commit()
    return db


def _db_path(path: Path | None = None) -> Path:
    return Path(path or os.getenv("GAME_RECORD_DB_PATH") or DEFAULT_DB_PATH).resolve()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS game_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id TEXT NOT NULL UNIQUE,
        round_id TEXT NOT NULL UNIQUE,
        timestamp TEXT NOT NULL,
        payload BLOB NOT NULL
    )""")
    return db


def archive_completed_game(record: dict[str, Any], *, db_path: Path | None = None) -> dict[str, Any]:
    """Archive exactly once per round_id; unfinished games are never persisted."""
    result = record.get("final_result")
    if not isinstance(result, dict) or result.get("win_type") not in {
        "zimo", "ron", "draw", "rob_kong", "self_draw_win", "catch_win"
    }:
        raise ValueError("仅正式和牌或流局结算后可归档")
    round_id = str(record.get("round_id") or "")
    if not round_id or len(round_id) > 128:
        raise ValueError("round_id 非法")
    pg_url = _postgres_url(db_path)
    if pg_url:
        return _archive_postgres(record, round_id, pg_url)
    path = _db_path(db_path)
    with closing(_connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT game_id, timestamp, payload FROM game_records WHERE round_id=?", (round_id,)
        ).fetchone()
        if existing:
            saved = json.loads(zlib.decompress(existing[2]))
            return {"game_id": existing[0], "round_id": round_id,
                    "timestamp": existing[1], "steps_count": len(saved.get("steps") or []),
                    "bytes_written": len(existing[2]), "path": str(path), "summary": _summary(saved)}
        timestamp = datetime.now(timezone.utc).isoformat()
        payload = dict(record)
        payload["timestamp"] = timestamp
        for _ in range(8):
            game_id = f"GM-{uuid.uuid4().hex[:6].upper()}"
            if not db.execute("SELECT 1 FROM game_records WHERE game_id=?", (game_id,)).fetchone():
                break
        else:
            raise RuntimeError("无法生成唯一牌谱编号")
        payload["game_id"] = game_id
        encoded = zlib.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
        db.execute("INSERT INTO game_records(game_id,round_id,timestamp,payload) VALUES(?,?,?,?)",
                   (game_id, round_id, timestamp, encoded))
        db.execute("""DELETE FROM game_records WHERE id IN (
            SELECT id FROM game_records ORDER BY timestamp DESC, id DESC LIMIT -1 OFFSET ?
        )""", (MAX_RECORDS,))
    return {"game_id": game_id, "round_id": round_id, "timestamp": timestamp,
            "steps_count": len(record.get("steps") or []), "bytes_written": len(encoded),
            "path": str(path), "summary": _summary(payload)}


def get_game_record(game_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    if not game_id.startswith("GM-") or len(game_id) != 9:
        return None
    pg_url = _postgres_url(db_path)
    if pg_url:
        with _pg_connect(pg_url) as db:
            row = db.execute("SELECT payload FROM game_records WHERE game_id=%s", (game_id,)).fetchone()
        return json.loads(zlib.decompress(row[0])) if row else None
    path = _db_path(db_path)
    if not path.exists():
        return None
    with closing(_connect(path)) as db:
        row = db.execute("SELECT payload FROM game_records WHERE game_id=?", (game_id,)).fetchone()
    return json.loads(zlib.decompress(row[0])) if row else None


def _archive_postgres(record: dict[str, Any], round_id: str, url: str) -> dict[str, Any]:
    # Serializing writers keeps the same FIFO order under concurrent requests.
    with _pg_connect(url) as db:
        db.execute("LOCK TABLE game_records IN EXCLUSIVE MODE")
        existing = db.execute(
            "SELECT game_id,timestamp,payload FROM game_records WHERE round_id=%s", (round_id,)
        ).fetchone()
        if existing:
            saved = json.loads(zlib.decompress(existing[2]))
            return {"game_id": existing[0], "round_id": round_id,
                    "timestamp": existing[1], "steps_count": len(saved.get("steps") or []),
                    "bytes_written": len(existing[2]), "path": "postgresql", "summary": _summary(saved)}
        timestamp = datetime.now(timezone.utc).isoformat()
        for _ in range(8):
            game_id = f"GM-{uuid.uuid4().hex[:6].upper()}"
            if not db.execute("SELECT 1 FROM game_records WHERE game_id=%s", (game_id,)).fetchone():
                break
        else:
            raise RuntimeError("无法生成唯一牌谱编号")
        payload = dict(record, game_id=game_id, timestamp=timestamp)
        encoded = zlib.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
        db.execute("INSERT INTO game_records(game_id,round_id,timestamp,payload) VALUES(%s,%s,%s,%s)",
                   (game_id, round_id, timestamp, encoded))
        db.execute("""DELETE FROM game_records WHERE id IN (
            SELECT id FROM game_records ORDER BY timestamp DESC, id DESC OFFSET %s
        )""", (MAX_RECORDS,))
    return {"game_id": game_id, "round_id": round_id, "timestamp": timestamp,
            "steps_count": len(record.get("steps") or []), "bytes_written": len(encoded),
            "path": "postgresql", "summary": _summary(payload)}
