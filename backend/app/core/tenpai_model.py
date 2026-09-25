"""对手听牌概率估算（弃牌河贝叶斯修正）。

模型（不窥探暗手，仅用公开副露 + 牌河 + 壁牌 Rem）：

    P = P_base(turn, n_melds)
    P ← 庄家积极度修正（×1.12）
    P ← 弃牌河动态加权（中张切出 / 字→幺九→中张序列 / 连打绝张安牌）
    P ← clip(P, 0.02, 0.95)

P_base（门清）：
    早巡 (1~6) 约 3%~8%；中巡 (7~11) 抬升至约 15%~25%；
    采用右移 Sigmoid，避免开局虚高。
副露：在门清先验上叠加阶梯增益（台州快和）。

中张定义（本模块）：序数 **4/5/6**（非 2~8 宽中张）。
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from app.schemas import PlayerState

# —— 门清基础先验：右移 Sigmoid ——
# P_closed(t) = P_FLOOR + P_SPAN / (1 + exp(-k*(t - T0)))
_P_FLOOR = 0.028
_P_SPAN = 0.52
_SIGMOID_CENTER = 11.0
_SIGMOID_STEEPNESS = 0.42

# 副露阶梯（加在门清先验上，再封顶）
_MELD_ADD = {1: 0.14, 2: 0.30, 3: 0.48, 4: 0.55}
_MELD_CAP = {1: 0.82, 2: 0.90, 3: 0.93, 4: 0.95}
_MELD3_FLOOR = 0.90  # 三组副露仅余一搭与雀头，至少列为高听牌风险

# 庄家进攻烈度
_DEALER_BOOST = 1.12

# 中张（4/5/6）切出
_CENTRAL_DIGITS = frozenset({"4", "5", "6"})
_CENTRAL_LOOKBACK = 2
_CENTRAL_MULT = 1.28  # 每次主动中张
_CENTRAL_ADD = 0.055
_CENTRAL_EARLY_TURN = 4  # ≥此巡才计中张增益（避免开局误伤）

# 字牌 → 幺九 → 中张 正规序列
_PROGRESSION_MULT = 1.18
_PROGRESSION_ADD = 0.04

# 中巡后连续绝张/安牌（Rem≤1）
_SAFE_STREAK_MIN_TURN = 5
_SAFE_STREAK_LOOKBACK = 3
_SAFE_STREAK_NEED = 2
_SAFE_STREAK_MULT = 1.15
_SAFE_STREAK_ADD = 0.035

# 概率边界
_P_MIN = 0.02
_P_MAX = 0.95


def estimate_opponents_tenpai(
    opponents: list[PlayerState] | Sequence[PlayerState],
    *,
    dealer_tile: str | None = None,
    rem_map: Mapping[str, int] | None = None,
) -> dict[str, float]:
    """估算各对手听牌概率。

    Args:
        opponents: 对手公开状态列表。
        dealer_tile: 本局得（预留；当前舍牌分析不依赖替身）。
        rem_map: 全场壁牌 Rem（用于识别绝张/跟打安牌）；缺省则跳过安牌分支。

    Returns:
        ``{seat_wind: probability}``，落在 ``[_P_MIN, _P_MAX]``。
    """
    _ = dealer_tile
    result: dict[str, float] = {}
    for opp in opponents:
        result[opp.seat_wind] = estimate_tenpai_probability(
            opp,
            turn_count=len(opp.discards),
            dealer_tile=dealer_tile,
            rem_pool=rem_map,
        )
    return result


def estimate_tenpai_probability(
    opponent: PlayerState,
    turn_count: int | None = None,
    dealer_tile: str | None = None,
    rem_pool: Mapping[str, int] | None = None,
) -> float:
    """单家听牌概率：基础先验 + 巡目 + 弃牌河贝叶斯修正。

    Args:
        opponent: 单家公开状态（副露 / 牌河 / 是否庄）。
        turn_count: 巡目；默认 ``len(discards)``。
        dealer_tile: 本局得（接口对齐，预留）。
        rem_pool: 壁牌剩余；用于「绝张安牌」识别。

    Returns:
        ``[0.02, 0.95]`` 内的听牌概率。
    """
    _ = dealer_tile
    turn = int(turn_count if turn_count is not None else len(opponent.discards))
    turn = max(turn, 0)
    n_melds = len(opponent.melds or [])
    discards = list(opponent.discards or [])

    p = _base_tenpai_prob(turn, n_melds)
    if opponent.is_dealer:
        p *= _DEALER_BOOST
    p = _apply_discard_analysis(p, discards, turn, rem_pool)
    return _clamp(p, _P_MIN, _P_MAX)


# ---------------------------------------------------------------------------
# 基础先验
# ---------------------------------------------------------------------------

def _base_tenpai_prob(turn: int, meld_count: int) -> float:
    """P_base(turn, melds)。

    门清：
        P_closed(t) = 0.028 + 0.52 / (1 + exp(-0.42*(t-11)))
        → t=3≈4.0%，t=6≈7.5%，t=9≈16%，t=11≈29%（再经舍牌修正）。
    副露：P = min(cap, P_closed + add)；3 副露另设下限。
    """
    p = _closed_prior(turn)
    if meld_count <= 0:
        return p
    add = _MELD_ADD.get(min(meld_count, 4), _MELD_ADD[4])
    cap = _MELD_CAP.get(min(meld_count, 4), _MELD_CAP[4])
    p = min(cap, p + add)
    if meld_count >= 3:
        p = max(_MELD3_FLOOR, p)
    return p


def _closed_prior(turn: int) -> float:
    x = _SIGMOID_STEEPNESS * (turn - _SIGMOID_CENTER)
    return _P_FLOOR + _P_SPAN / (1.0 + math.exp(-x))


# ---------------------------------------------------------------------------
# 弃牌河分析
# ---------------------------------------------------------------------------

def _apply_discard_analysis(
    p: float,
    discards: list[str],
    turn: int,
    rem_pool: Mapping[str, int] | None,
) -> float:
    """舍牌动态加权：中张主动切 / 正规进张序列 / 连打安牌。"""
    if not discards:
        return p

    p = _apply_central_tile_boost(p, discards, turn, rem_pool)
    p = _apply_progression_boost(p, discards, turn)
    p = _apply_safe_streak_boost(p, discards, turn, rem_pool)
    return p


def _apply_central_tile_boost(
    p: float,
    discards: list[str],
    turn: int,
    rem_pool: Mapping[str, int] | None,
) -> float:
    """最近 1~2 巡主动切 4/5/6：每次 ×1.28 并 +0.055。

    「主动」：非绝张跟打（Rem 在切后仍显示该牌并非早已耗尽时，
    以当前 Rem≥2 近似「当时非跟打现物」；无 rem_pool 则凡中张均计）。
    """
    if turn < _CENTRAL_EARLY_TURN or len(discards) < 1:
        return p
    recent = discards[-_CENTRAL_LOOKBACK:]
    hits = 0
    for t in recent:
        if not _is_central_simple(t):
            continue
        if _is_likely_genbutsu_or_dead(t, rem_pool):
            continue
        hits += 1
    for _ in range(hits):
        p = p * _CENTRAL_MULT + _CENTRAL_ADD
    return p


def _apply_progression_boost(
    p: float, discards: list[str], turn: int
) -> float:
    """字牌/幺九先切、其后出现中张 → 「面子趋满」增益。"""
    if turn < _CENTRAL_EARLY_TURN or len(discards) < 4:
        return p
    early = discards[:-_CENTRAL_LOOKBACK] if len(discards) > _CENTRAL_LOOKBACK else discards[:2]
    late = discards[-_CENTRAL_LOOKBACK:]
    early_ok = any(_is_honor(t) or _is_terminal(t) for t in early)
    late_mid = any(_is_central_simple(t) for t in late)
    # 早期应以废牌为主：中张占比不高
    early_mid_ratio = (
        sum(1 for t in early if _is_central_simple(t)) / max(len(early), 1)
    )
    if early_ok and late_mid and early_mid_ratio <= 0.35:
        p = p * _PROGRESSION_MULT + _PROGRESSION_ADD
    return p


def _apply_safe_streak_boost(
    p: float,
    discards: list[str],
    turn: int,
    rem_pool: Mapping[str, int] | None,
) -> float:
    """中巡后连续切绝张/安牌（Rem≤1）：暗示听牌后摸切留安。"""
    if rem_pool is None or turn < _SAFE_STREAK_MIN_TURN:
        return p
    if len(discards) < _SAFE_STREAK_NEED:
        return p
    recent = discards[-_SAFE_STREAK_LOOKBACK:]
    safe_n = sum(1 for t in recent if _is_likely_genbutsu_or_dead(t, rem_pool))
    if safe_n >= _SAFE_STREAK_NEED:
        p = p * _SAFE_STREAK_MULT + _SAFE_STREAK_ADD
    return p


# ---------------------------------------------------------------------------
# 牌面工具
# ---------------------------------------------------------------------------

def _is_central_simple(tile: str) -> bool:
    """核心中张：4/5/6 万筒条。"""
    if len(tile) != 2 or tile[1] not in ("m", "p", "s"):
        return False
    return tile[0] in _CENTRAL_DIGITS


def _is_terminal(tile: str) -> bool:
    if len(tile) != 2 or tile[1] not in ("m", "p", "s"):
        return False
    return tile[0] in ("1", "9")


def _is_honor(tile: str) -> bool:
    return tile in {"E", "S", "W", "N", "C", "F", "P"}


def _is_likely_genbutsu_or_dead(
    tile: str, rem_pool: Mapping[str, int] | None
) -> bool:
    """当前 Rem≤1 → 近乎绝张/现物，视为跟打或安牌而非主动拆中张。"""
    if rem_pool is None:
        return False
    return int(rem_pool.get(tile, 4)) <= 1


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
