"""对局完整轨迹落盘：序列化为 JSON 写入 data/game_logs/。

GameRecord 结构（与 schemas.GameRecordRequest 对齐）：
  round_id / config / steps[] / final_result
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

# backend/app/core/game_logger.py → parents[2] = backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = _BACKEND_ROOT / "data" / "game_logs"

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-.]{1,128}$")

GameAction = Literal["DRAW", "DISCARD", "CHI", "PONG", "GANG", "WIN"]


def new_round_id() -> str:
    """生成可读 round_id：UTC 时间戳 + 短 UUID。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}_{uuid.uuid4().hex[:8]}"


def ensure_log_dir(log_dir: Path | None = None) -> Path:
    """确保日志目录存在，返回绝对路径。"""
    target = Path(log_dir) if log_dir is not None else DEFAULT_LOG_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target.resolve()


def _sanitize_round_id(round_id: str) -> str:
    rid = (round_id or "").strip()
    if not rid:
        raise ValueError("round_id 不能为空")
    if not _SAFE_ID_RE.match(rid):
        raise ValueError(
            "round_id 仅允许字母数字、下划线、短横线与点号，且长度 ≤128"
        )
    return rid


def record_to_dict(record: dict[str, Any]) -> dict[str, Any]:
    """规范化 GameRecord 为可 JSON 序列化的纯 dict。"""
    rid = _sanitize_round_id(str(record.get("round_id") or ""))
    config = record.get("config") or {}
    steps = record.get("steps") or []
    final_result = record.get("final_result")

    if not isinstance(config, dict):
        raise ValueError("config 必须为对象")
    if not isinstance(steps, list):
        raise ValueError("steps 必须为数组")

    out: dict[str, Any] = {
        "round_id": rid,
        "config": {
            "dealer_seat": config.get("dealer_seat"),
            "dealer_tile": config.get("dealer_tile"),
            "seat_wind": config.get("seat_wind"),
        },
        "steps": [_normalize_step(s, i) for i, s in enumerate(steps)],
        "final_result": _normalize_final(final_result),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    return out


def _normalize_step(step: Any, index: int) -> dict[str, Any]:
    if not isinstance(step, dict):
        raise ValueError(f"steps[{index}] 必须为对象")
    action = str(step.get("action") or "").upper()
    allowed = {"DRAW", "DISCARD", "CHI", "PONG", "GANG", "WIN"}
    if action not in allowed:
        raise ValueError(
            f"steps[{index}].action={action!r} 非法；允许 {sorted(allowed)}"
        )
    rec = step.get("self_recommendation")
    self_rec: Optional[dict[str, Any]] = None
    if isinstance(rec, dict) and rec:
        best = rec.get("best_tile")
        net = rec.get("net_ev")
        self_rec = {
            "best_tile": best,
            "net_ev": float(net) if net is not None else None,
        }
    return {
        "turn": int(step.get("turn") or 0),
        "seat": step.get("seat"),
        "action": action,
        "tile": step.get("tile"),
        "self_recommendation": self_rec,
    }


def _normalize_final(final_result: Any) -> Optional[dict[str, Any]]:
    if final_result is None:
        return None
    if not isinstance(final_result, dict):
        raise ValueError("final_result 必须为对象或 null")
    return {
        "winner_seat": final_result.get("winner_seat"),
        "win_type": final_result.get("win_type"),
        "points": final_result.get("points"),
        "deal_in_seat": final_result.get("deal_in_seat"),
        "details": final_result.get("details"),
    }


def save_game_record(
    record: dict[str, Any],
    *,
    log_dir: Path | None = None,
) -> dict[str, Any]:
    """将 GameRecord 写入 `{log_dir}/{round_id}.json`。

    Returns:
        { round_id, path, absolute_path, bytes_written }
    """
    payload = record_to_dict(record)
    rid = payload["round_id"]
    directory = ensure_log_dir(log_dir)
    path = directory / f"{rid}.json"

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")

    return {
        "round_id": rid,
        "path": str(path.relative_to(_BACKEND_ROOT)).replace("\\", "/"),
        "absolute_path": str(path),
        "bytes_written": len(text.encode("utf-8")),
        "steps_count": len(payload["steps"]),
    }
