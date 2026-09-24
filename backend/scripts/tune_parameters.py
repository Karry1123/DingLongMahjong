#!/usr/bin/env python3
"""离线对局日志分析与 EV / 危险度参数调优建议。

用法（在 backend/ 目录或任意 cwd）::

    python -m scripts.tune_parameters
    python scripts/tune_parameters.py
    python scripts/tune_parameters.py --log-dir data/game_logs

扫描 ``data/game_logs/*.json``，输出：
  1) 自家和牌率 / 平均胡数 / 放铳率 / 决策符合度
  2) 危险度模型偏差（中张生张校准）
  3) 向听系数 / 役牌·客风潜力分的敏感度建议
  4) 可直接粘贴进 ``ev_engine.py`` / ``danger_model.py`` 的常量字典
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# 路径：保证可从 backend/ 或 repo 根目录直接运行
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _SCRIPT_DIR.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.core import danger_model as dm  # noqa: E402
from app.core import ev_engine as ev  # noqa: E402
from app.core.game_logger import DEFAULT_LOG_DIR  # noqa: E402

# ---------------------------------------------------------------------------
# 终端排版
# ---------------------------------------------------------------------------

_W = 72


def _configure_stdout() -> None:
    """Windows GBK 控制台下尽量切到 UTF-8，避免中文/符号炸编码。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def _hr(char: str = "-") -> str:
    return char * _W


def _title(text: str) -> None:
    print()
    print(_hr("="))
    print(f"  {text}")
    print(_hr("="))


def _section(text: str) -> None:
    print()
    print(_hr("-"))
    print(f">> {text}")
    print(_hr("-"))


def _row(label: str, value: str, width: int = 36) -> None:
    print(f"  {label:<{width}} {value}")


def _pct(numer: float, denom: float, digits: int = 1) -> str:
    if denom <= 0:
        return "n/a"
    return f"{100.0 * numer / denom:.{digits}f}%"


def _fmt(n: float | int | None, digits: int = 2) -> str:
    if n is None:
        return "n/a"
    if isinstance(n, int):
        return str(n)
    return f"{n:.{digits}f}"


def _tile_bucket(tile: Optional[str]) -> str:
    """危险度分档：honor / mid456 / near_mid / terminal / other。"""
    if not tile or not isinstance(tile, str):
        return "other"
    if tile in ("E", "S", "W", "N", "C", "F", "P"):
        return "honor"
    if len(tile) == 2 and tile[0].isdigit() and tile[1] in "mps":
        d = int(tile[0])
        if d in (4, 5, 6):
            return "mid456"
        if d in (1, 9):
            return "terminal"
        return "near_mid"
    return "other"


# ---------------------------------------------------------------------------
# 日志加载
# ---------------------------------------------------------------------------


def load_game_records(log_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not log_dir.is_dir():
        return records
    for path in sorted(log_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ! 跳过损坏文件 {path.name}: {exc}")
            continue
        if not isinstance(data, dict):
            continue
        data["_source_file"] = path.name
        records.append(data)
    return records


# ---------------------------------------------------------------------------
# 统计聚合
# ---------------------------------------------------------------------------


@dataclass
class RoundStats:
    round_id: str
    self_seat: str
    dealer_seat: str
    winner_seat: Optional[str]
    win_type: Optional[str]
    points: Optional[float]
    deal_in_seat: Optional[str]
    self_won: bool = False
    self_deal_in: bool = False
    deal_in_to_dealer: bool = False
    self_discards: int = 0
    recommend_comparable: int = 0
    recommend_matched: int = 0
    # 自家切出后被对手 WIN（ron）的牌及其分档
    deal_in_tiles: list[str] = field(default_factory=list)


@dataclass
class AggregateReport:
    rounds: list[RoundStats] = field(default_factory=list)
    # bucket → {discards, deal_ins}
    danger_buckets: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    # 客风 / 役牌相关切牌计数（启发式）
    guest_wind_discards: int = 0
    yakuhai_discards: int = 0
    early_guest_kept_hint: int = 0  # 前 4 巡未切客风却有推荐客风的近似


def _self_seat(rec: dict[str, Any]) -> str:
    cfg = rec.get("config") or {}
    return str(cfg.get("seat_wind") or "E")


def _dealer_seat(rec: dict[str, Any]) -> str:
    cfg = rec.get("config") or {}
    return str(cfg.get("dealer_seat") or "E")


def analyze_records(records: list[dict[str, Any]]) -> AggregateReport:
    report = AggregateReport()

    for rec in records:
        self_seat = _self_seat(rec)
        dealer = _dealer_seat(rec)
        final = rec.get("final_result") or {}
        winner = final.get("winner_seat")
        win_type = final.get("win_type")
        points = final.get("points")
        deal_in = final.get("deal_in_seat")

        rs = RoundStats(
            round_id=str(rec.get("round_id") or rec.get("_source_file") or "?"),
            self_seat=self_seat,
            dealer_seat=dealer,
            winner_seat=winner,
            win_type=win_type,
            points=float(points) if points is not None else None,
            deal_in_seat=deal_in,
            self_won=(winner == self_seat and win_type not in (None, "draw")),
            self_deal_in=(deal_in == self_seat),
            deal_in_to_dealer=(deal_in == self_seat and winner == dealer),
        )

        steps = rec.get("steps") or []
        last_self_discard_tile: Optional[str] = None
        last_self_discard_turn = 0
        early_discards: list[str] = []

        for step in steps:
            if not isinstance(step, dict):
                continue
            action = str(step.get("action") or "").upper()
            seat = step.get("seat")
            tile = step.get("tile")
            turn = int(step.get("turn") or 0)
            bucket = _tile_bucket(tile if isinstance(tile, str) else None)

            if action == "DISCARD" and isinstance(tile, str):
                report.danger_buckets[bucket]["discards"] += 1

            if seat != self_seat:
                continue

            if action == "DISCARD" and isinstance(tile, str):
                rs.self_discards += 1
                last_self_discard_tile = tile
                last_self_discard_turn = turn
                if turn <= 4:
                    early_discards.append(tile)

                rec_snap = step.get("self_recommendation")
                if isinstance(rec_snap, dict) and rec_snap.get("best_tile"):
                    rs.recommend_comparable += 1
                    if rec_snap.get("best_tile") == tile:
                        rs.recommend_matched += 1
                    # 开局痛点：推荐客风但实际未切客风
                    best = rec_snap.get("best_tile")
                    if (
                        turn <= 4
                        and isinstance(best, str)
                        and best in ("E", "S", "W", "N")
                        and tile not in ("E", "S", "W", "N")
                    ):
                        report.early_guest_kept_hint += 1

                if tile in ("E", "S", "W", "N"):
                    # 粗分：非自风视为客风切出（无完整门风上下文时记 guest）
                    if tile != self_seat:
                        report.guest_wind_discards += 1
                if tile in ("C", "F", "P") or tile == self_seat:
                    report.yakuhai_discards += 1

            if action == "WIN" and seat != self_seat and win_type == "ron":
                # 对手捉铳：若放铳方是自家，记危险偏差样本
                if deal_in == self_seat and last_self_discard_tile:
                    rs.deal_in_tiles.append(last_self_discard_tile)
                    b = _tile_bucket(last_self_discard_tile)
                    report.danger_buckets[b]["deal_ins"] += 1

        # 终局再校验：ron 且 deal_in=self，但步骤里未标到
        if rs.self_deal_in and not rs.deal_in_tiles and last_self_discard_tile:
            rs.deal_in_tiles.append(last_self_discard_tile)
            report.danger_buckets[_tile_bucket(last_self_discard_tile)][
                "deal_ins"
            ] += 1

        report.rounds.append(rs)

    return report


# ---------------------------------------------------------------------------
# 指标打印
# ---------------------------------------------------------------------------


def print_overview(report: AggregateReport) -> None:
    _title("台州麻将 · 离线参数调优报告")
    n = len(report.rounds)
    _row("扫描对局数", str(n))
    if n == 0:
        print()
        print("  [!] 未找到任何 game_logs JSON。")
        print("    请先对局终局落盘，或指定 --log-dir。")
        print("    下方仍会给出基于痛点启发式的常量建议。")
        return

    wins = [r for r in report.rounds if r.self_won]
    deal_ins = [r for r in report.rounds if r.self_deal_in]
    draws = [
        r
        for r in report.rounds
        if (r.win_type == "draw") or (r.winner_seat is None and not r.self_won)
    ]
    win_points = [r.points for r in wins if r.points is not None]
    to_dealer = sum(1 for r in deal_ins if r.deal_in_to_dealer)
    to_xian = len(deal_ins) - to_dealer

    cmp_n = sum(r.recommend_comparable for r in report.rounds)
    match_n = sum(r.recommend_matched for r in report.rounds)
    self_disc = sum(r.self_discards for r in report.rounds)

    _section("1. 核心战绩指标（自家视角）")
    _row("和牌局数 / 总局", f"{len(wins)} / {n}")
    _row("自家和牌率 (Win Rate)", _pct(len(wins), n))
    _row(
        "平均和牌胡数 (Avg Hu)",
        _fmt(sum(win_points) / len(win_points) if win_points else None),
    )
    _row("流局占比", _pct(len(draws), n))
    _row("放铳局数 / 总局", f"{len(deal_ins)} / {n}")
    _row("自家放铳率 (Deal-in Rate)", _pct(len(deal_ins), n))
    _row("放铳→庄家 : 放铳→闲家", f"{to_dealer} : {to_xian}")
    if deal_ins:
        _row("  其中放铳给庄家比例", _pct(to_dealer, len(deal_ins)))
        _row("  其中放铳给闲家比例", _pct(to_xian, len(deal_ins)))

    _section("2. 决策符合度（实际切牌 vs 算法第一推荐）")
    _row("可对比切牌手数", str(cmp_n))
    _row("重合手数", str(match_n))
    _row("决策符合度", _pct(match_n, cmp_n))
    _row("自家总切牌手数", str(self_disc))
    if cmp_n == 0:
        print("  （日志中缺少 self_recommendation 快照时无法统计符合度）")


def print_danger_calibration(report: AggregateReport) -> dict[str, Any]:
    _section("3. 危险度模型偏差 · 中张生张校准")

    model_base = {
        "honor": dm.BASE_HONOR_LIVE,
        "mid456": dm.BASE_MID_456,
        "near_mid": dm.BASE_NEAR_MID,
        "terminal": dm.BASE_TERMINAL,
        "other": dm.BASE_NEAR_MID,
    }

    print(
        f"  {'分档':<12}{'切出':>8}{'放铳':>8}{'实证率':>10}"
        f"{'模型基线':>10}{'偏差':>10}"
    )
    print("  " + "-" * 58)

    suggested_mid = dm.BASE_MID_456
    suggested_near = dm.BASE_NEAR_MID
    suggested_honor = dm.BASE_HONOR_LIVE
    buckets_out: dict[str, dict[str, float]] = {}

    order = ["mid456", "near_mid", "terminal", "honor", "other"]
    for key in order:
        c = report.danger_buckets.get(key) or Counter()
        disc = int(c.get("discards", 0))
        dins = int(c.get("deal_ins", 0))
        emp = (dins / disc) if disc > 0 else None
        base = model_base[key]
        bias = (emp - base) if emp is not None else None
        buckets_out[key] = {
            "discards": disc,
            "deal_ins": dins,
            "empirical": emp if emp is not None else float("nan"),
            "model_base": base,
            "bias": bias if bias is not None else float("nan"),
        }
        emp_s = _pct(dins, disc) if disc else "n/a"
        bias_s = f"{bias:+.3f}" if bias is not None else "n/a"
        print(
            f"  {key:<12}{disc:>8}{dins:>8}{emp_s:>10}"
            f"{base:>10.3f}{bias_s:>10}"
        )

        # 样本足够时按贝叶斯收缩校准
        if disc >= 8 and emp is not None:
            # 先验权重：8 次伪计数拉回模型基线
            prior_n = 8.0
            cal = (dins + prior_n * base) / (disc + prior_n)
            if key == "mid456":
                suggested_mid = round(cal, 3)
            elif key == "near_mid":
                suggested_near = round(cal, 3)
            elif key == "honor":
                suggested_honor = round(cal, 3)

    # 样本不足：若 mid 实证偏高，温和上调；偏低则下调
    total_mid_d = int(
        (report.danger_buckets.get("mid456") or {}).get("discards", 0)
    )
    total_mid_i = int(
        (report.danger_buckets.get("mid456") or {}).get("deal_ins", 0)
    )
    if total_mid_d < 8:
        print()
        print("  · 中张样本不足（需 ≥8 次 mid456 切出），采用痛点启发式：")
        print("    生张中张常被低估 → BASE_MID_456 建议 +0.02~0.04")
        suggested_mid = round(min(0.28, dm.BASE_MID_456 + 0.03), 3)
        suggested_near = round(min(0.20, dm.BASE_NEAR_MID + 0.015), 3)

    print()
    _row("建议 BASE_MID_456", f"{dm.BASE_MID_456} → {suggested_mid}")
    _row("建议 BASE_NEAR_MID", f"{dm.BASE_NEAR_MID} → {suggested_near}")
    _row("建议 BASE_HONOR_LIVE", f"{dm.BASE_HONOR_LIVE} → {suggested_honor}")

    return {
        "BASE_MID_456": suggested_mid,
        "BASE_NEAR_MID": suggested_near,
        "BASE_HONOR_LIVE": suggested_honor,
        "BASE_HONOR_DEAD": dm.BASE_HONOR_DEAD,
        "BASE_TERMINAL": dm.BASE_TERMINAL,
        "buckets": buckets_out,
    }


# ---------------------------------------------------------------------------
# 参数敏感度（向听 / 役牌 / 客风）
# ---------------------------------------------------------------------------


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def evaluate_sensitivity(report: AggregateReport) -> dict[str, Any]:
    """基于日志痛点的启发式敏感度评估（无需完整复盘手牌）。

    目标痛点：
      - 一向听自拆雀头 → 向听惩罚过高或雀头保护不足
      - 开局不切客风 → 客风占位惩罚过低 / 役牌保留分相对过高
    """
    _section("4. 参数敏感度评估（向听 · 役牌 · 客风）")

    n = len(report.rounds)
    wins = sum(1 for r in report.rounds if r.self_won)
    deal_ins = sum(1 for r in report.rounds if r.self_deal_in)
    cmp_n = sum(r.recommend_comparable for r in report.rounds)
    match_n = sum(r.recommend_matched for r in report.rounds)
    match_rate = (match_n / cmp_n) if cmp_n else None
    win_rate = (wins / n) if n else None
    deal_rate = (deal_ins / n) if n else None

    cur_shanten = float(ev.SHANTEN_PENALTY)
    cur_deep = float(ev._DEEP_SHANTEN_UNIT)
    cur_guest = float(ev._GUEST_WIND_SINGLE_PENALTY)
    cur_yaku = float(ev._YAKUHAI_SINGLE_POTENTIAL)
    cur_jantou = float(ev._JANTOU_BREAK_PENALTY)
    cur_push = float(ev._GOOD_SHAPE_PUSH_BONUS)
    cur_def_scale = float(ev._GOOD_SHAPE_DEFENSE_SCALE)

    print("  当前常量快照：")
    _row("  SHANTEN_PENALTY", _fmt(cur_shanten, 0))
    _row("  _DEEP_SHANTEN_UNIT", _fmt(cur_deep, 0))
    _row("  _JANTOU_BREAK_PENALTY", _fmt(cur_jantou, 1))
    _row("  _GOOD_SHAPE_PUSH_BONUS", _fmt(cur_push, 1))
    _row("  _GOOD_SHAPE_DEFENSE_SCALE", _fmt(cur_def_scale, 2))
    _row("  _YAKUHAI_SINGLE_POTENTIAL", _fmt(cur_yaku, 1))
    _row("  _GUEST_WIND_SINGLE_PENALTY", _fmt(cur_guest, 1))

    # ---- 向听系数网格评分 ----
    # 代理损失：符合度低 + 放铳高 → 倾向略降向听压迫、加强形/雀头；
    # 和牌率低且符合度高但胡数低 → 可略升进攻推进。
    print()
    print("  向听系数 (SHANTEN_PENALTY) 网格扫描：")
    print(f"  {'候选':>8}{'相对分':>10}{'说明'}")
    print("  " + "-" * 56)

    grid = [80, 100, 110, 120, 130, 140, 160]
    scores: list[tuple[int, float, str]] = []
    for cand in grid:
        # 基准 120；偏离代价二次
        score = 0.0
        note_parts: list[str] = []

        # 痛点：拆雀头 —— 过高的向听压迫会让「切一张降向听」压过雀头保护
        # 目标：略低于当前或维持，并靠 JANTOU 补强
        if cand > 130:
            score -= (cand - 130) * 0.15
            note_parts.append("易诱拆雀头")
        if cand < 100:
            score -= (100 - cand) * 0.12
            note_parts.append("进攻偏弱")

        if match_rate is not None and match_rate < 0.55 and cand >= 130:
            score -= 4.0
            note_parts.append("符合度低×高压")
        if deal_rate is not None and deal_rate > 0.25 and cand >= 130:
            score -= 3.0
            note_parts.append("放铳高仍高压")
        if win_rate is not None and win_rate < 0.22 and cand <= 100:
            score -= 2.0
            note_parts.append("和率低且过软")

        # 贴近经验甜点 110~120
        score -= 0.02 * (cand - 115) ** 2 / 25.0
        if 110 <= cand <= 120:
            score += 2.5
            note_parts.append("甜点区")

        scores.append((cand, score, "；".join(note_parts) or "—"))

    scores.sort(key=lambda x: -x[1])
    for cand, sc, note in scores:
        mark = "  << recommended" if cand == scores[0][0] else ""
        print(f"  {cand:>8}{sc:>10.2f}  {note}{mark}")

    best_shanten = scores[0][0]
    # 最优区间：推荐值 ±10，并落在 [100, 130]
    lo = max(100, best_shanten - 10)
    hi = min(130, best_shanten + 10)

    # ---- 役牌 / 客风 ----
    # 开局不切客风：提高客风惩罚；役牌单张保持或略升
    guest_boost = 0.0
    if report.early_guest_kept_hint > 0:
        guest_boost = 2.0 + min(4.0, report.early_guest_kept_hint * 0.5)
        print()
        _row(
            "开局「荐客风却未切」次数",
            str(report.early_guest_kept_hint),
        )
    else:
        # 无日志证据时仍按已知痛点给默认增量
        guest_boost = 2.0
        print()
        print("  · 无充分「开局客风」日志证据，按已知痛点默认 +2.0 客风惩罚")

    sug_guest = round(_clamp(cur_guest + guest_boost, 6.0, 14.0), 1)
    sug_yaku = round(_clamp(cur_yaku + 1.0, 10.0, 16.0), 1)
    sug_yaku_pair = round(_clamp(ev._YAKUHAI_PAIR_POTENTIAL + 1.0, 16.0, 22.0), 1)
    sug_jantou = round(_clamp(cur_jantou + 6.0, 20.0, 32.0), 1)
    sug_push = round(_clamp(cur_push + 2.0, 10.0, 16.0), 1)
    sug_def_scale = round(_clamp(cur_def_scale - 0.05, 0.30, 0.50), 2)
    sug_deep = int(round(_clamp(cur_deep, 20, 30)))

    print()
    print("  役牌 / 客风保留价值（tile_potential_score）：")
    _row("  _YAKUHAI_SINGLE_POTENTIAL", f"{cur_yaku} → {sug_yaku}")
    _row("  _YAKUHAI_PAIR_POTENTIAL", f"{ev._YAKUHAI_PAIR_POTENTIAL} → {sug_yaku_pair}")
    _row("  _GUEST_WIND_SINGLE_PENALTY", f"{cur_guest} → {sug_guest}")
    print()
    print("  一向听雀头保护 / 好形推进：")
    _row("  _JANTOU_BREAK_PENALTY", f"{cur_jantou} → {sug_jantou}")
    _row("  _GOOD_SHAPE_PUSH_BONUS", f"{cur_push} → {sug_push}")
    _row("  _GOOD_SHAPE_DEFENSE_SCALE", f"{cur_def_scale} → {sug_def_scale}")

    print()
    _row("向听系数最优区间", f"[{lo}, {hi}]（点估计 {best_shanten}）")

    return {
        "shanten_penalty": best_shanten,
        "shanten_penalty_range": (lo, hi),
        "deep_shanten_unit": sug_deep,
        "yakuhai_single": sug_yaku,
        "yakuhai_pair": sug_yaku_pair,
        "guest_wind_single": sug_guest,
        "jantou_break": sug_jantou,
        "good_shape_push": sug_push,
        "good_shape_defense_scale": sug_def_scale,
        "grid": scores,
    }


def print_recommended_dicts(
    sens: dict[str, Any],
    danger: dict[str, Any],
) -> None:
    _section("5. 推荐常量配置（可直接更新源码）")

    ev_dict = {
        "SHANTEN_PENALTY": int(sens["shanten_penalty"]),
        "_DEEP_SHANTEN_UNIT": int(sens["deep_shanten_unit"]),
        "_YAKUHAI_SINGLE_POTENTIAL": float(sens["yakuhai_single"]),
        "_YAKUHAI_PAIR_POTENTIAL": float(sens["yakuhai_pair"]),
        "_YAKUHAI_PUNG_POTENTIAL": float(ev._YAKUHAI_PUNG_POTENTIAL),
        "_GUEST_WIND_SINGLE_PENALTY": float(sens["guest_wind_single"]),
        "_GUEST_WIND_PAIR_PENALTY": float(ev._GUEST_WIND_PAIR_PENALTY),
        "_JANTOU_BREAK_PENALTY": float(sens["jantou_break"]),
        "_ISOLATED_CUT_BONUS": float(ev._ISOLATED_CUT_BONUS),
        "_ISOLATED_KEEP_PENALTY": float(ev._ISOLATED_KEEP_PENALTY),
        "_GOOD_SHAPE_PUSH_BONUS": float(sens["good_shape_push"]),
        "_GOOD_SHAPE_DEFENSE_SCALE": float(sens["good_shape_defense_scale"]),
        "_UKEIRE_QUALITY_WEIGHT": float(ev._UKEIRE_QUALITY_WEIGHT),
    }

    danger_dict = {
        "BASE_HONOR_LIVE": float(danger["BASE_HONOR_LIVE"]),
        "BASE_HONOR_DEAD": float(danger["BASE_HONOR_DEAD"]),
        "BASE_MID_456": float(danger["BASE_MID_456"]),
        "BASE_NEAR_MID": float(danger["BASE_NEAR_MID"]),
        "BASE_TERMINAL": float(danger["BASE_TERMINAL"]),
        "DYE_OWN_SUIT_MID_FACTOR": float(dm.DYE_OWN_SUIT_MID_FACTOR),
        "DYE_OTHER_SUIT_FACTOR": float(dm.DYE_OTHER_SUIT_FACTOR),
    }

    print()
    print("  # ---- 建议写入 app/core/ev_engine.py ----")
    print("  RECOMMENDED_EV_CONSTANTS = ", end="")
    print(json.dumps(ev_dict, ensure_ascii=False, indent=2).replace("\n", "\n  "))

    print()
    print("  # ---- 建议写入 app/core/danger_model.py ----")
    print("  RECOMMENDED_DANGER_CONSTANTS = ", end="")
    print(
        json.dumps(danger_dict, ensure_ascii=False, indent=2).replace("\n", "\n  ")
    )

    print()
    print("  应用提示：")
    print("  1. 先改 SHANTEN_PENALTY 与 _JANTOU_BREAK_PENALTY，回归一向听拆雀头用例")
    print("  2. 再调 _GUEST_WIND_SINGLE_PENALTY，确认开局客风优先被切")
    print("  3. BASE_MID_456 上调后观察放铳率是否下降、进攻是否过度保守")
    print()
    print(_hr("="))
    print("  报告结束")
    print(_hr("="))
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[Iterable[str]] = None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="扫描 game_logs 并输出 EV/危险度参数调优建议",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help=f"对局 JSON 目录（默认 {DEFAULT_LOG_DIR}）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    log_dir = args.log_dir
    if not log_dir.is_absolute():
        # 相对路径相对 backend/
        cand = (_BACKEND_ROOT / log_dir).resolve()
        if cand.is_dir():
            log_dir = cand
        else:
            log_dir = log_dir.resolve()

    _title("加载对局日志")
    _row("日志目录", str(log_dir))
    records = load_game_records(log_dir)
    _row("成功加载", f"{len(records)} 份")

    report = analyze_records(records)
    print_overview(report)
    danger = print_danger_calibration(report)
    sens = evaluate_sensitivity(report)
    print_recommended_dicts(sens, danger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
