"""单张对特定对手的放铳率估算 P(DealIn | Tenpai)。

防守特征（台州无包牌）：
- 现物 → 0
- 绝张 / Rem=0 → 0
- 壁牌断相邻顺子搭 → 下调序数危险
- 副露染手（序数花色单一：≥2 组同门，或含同门碰/杠）→ 该色 3~7 加倍、它色序数打折
- 生熟度：字牌 / 中张 / 幺九分档

物理牌与白板替身：
- Rem / 现物 / 绝张一律按**物理编码**（P 与 dealer_tile 隔离，与 pool_tracker 一致）。
- 副露染手花色判定时，P 在得≠白时映射为 dealer_tile 的花色（rule.md §2 情况 A）。
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence

from app.schemas import Meld, PlayerState

from .constants import DRAGONS, WINDS

# ---------------------------------------------------------------------------
# 基础危险度常量
# ---------------------------------------------------------------------------

BASE_HONOR_LIVE = 0.16  # 字牌生张
BASE_HONOR_DEAD = 0.02  # 字牌已见 ≥2（熟张上限）
BASE_MID_456 = 0.18  # 序数 4/5/6
BASE_TERMINAL = 0.08  # 序数 1/9
BASE_NEAR_MID = 0.12  # 序数 2/3/7/8（介于幺九与深中张之间）

# 壁牌断搭折扣（两侧邻居 Rem 均耗尽时）
WALL_BOTH_SIDES_FACTOR = 0.45
WALL_ONE_SIDE_EDGE_FACTOR = 0.70  # 边张仅一侧可连且已断

# 染手倍率
DYE_OWN_SUIT_MID_FACTOR = 2.2  # 染手花色 3~7
DYE_OTHER_SUIT_FACTOR = 0.25  # 其余两门序数


def estimate_tile_danger(
    tile: str,
    opponent: PlayerState,
    rem_tiles: Mapping[str, int],
    dealer_tile: str,
    *,
    hand_tiles: Sequence[str] | None = None,
) -> float:
    """估算 ``tile`` 对 ``opponent`` 的放铳概率 P(DealIn | Tenpai)。

    Args:
        tile: 物理牌编码（与 Rem 字典键一致）。
        opponent: 目标对手公开状态。
        rem_tiles: 全场物理壁牌剩余（``get_remaining_tiles`` 的结果）。
        dealer_tile: 本局财神（得）。

    Returns:
        ``[0.0, 1.0]`` 内的放铳率。
    """
    # 1) 现物：打过的牌对此人绝对安全（无包牌）
    if tile in opponent.discards:
        return 0.0

    # 2) 绝张：壁牌已无（不考虑极端单骑）
    if rem_tiles.get(tile, 0) <= 0:
        return 0.0

    own_count = list(hand_tiles or ()).count(tile)
    appeared_public = max(0, _appeared_count(tile, rem_tiles) - own_count)
    # Rem also subtracts our concealed hand. For a discard, that copy has not
    # appeared on the table and must not make a live honor look "seen".
    danger = _base_danger(tile, rem_tiles, dealer_tile, appeared_public)
    danger = _apply_sequence_wall_discount(danger, tile, rem_tiles)
    danger = _apply_dye_modifier(danger, tile, opponent, dealer_tile)

    # 公共已见至少两张幺九时外部只剩一张，无法被碰；仍保留单张和牌风险。
    if _is_suited(tile) and int(tile[0]) in (1, 9) and appeared_public >= 2:
        danger *= 0.75
    return _clamp(danger, 0.0, 1.0)


# ---------------------------------------------------------------------------
# 生熟度基础危险
# ---------------------------------------------------------------------------

def _base_danger(
    tile: str, rem_tiles: Mapping[str, int], dealer_tile: str,
    appeared_public: int,
) -> float:
    appeared = _appeared_count(tile, rem_tiles)

    if _is_honor(tile):
        if appeared_public >= 2:
            return BASE_HONOR_DEAD
        if appeared_public == 1:
            # 见过 1 张：介于生熟之间
            return (BASE_HONOR_LIVE + BASE_HONOR_DEAD) / 2.0
        return BASE_HONOR_LIVE

    if not _is_suited(tile):
        return BASE_NEAR_MID

    digit = int(tile[0])
    if digit in (4, 5, 6):
        base = BASE_MID_456
    elif digit in (1, 9):
        base = BASE_TERMINAL
    else:
        base = BASE_NEAR_MID

    # 序数过熟：已见 ≥3 时略降（仍保留结构危险）
    if appeared >= 3:
        base *= 0.5
    elif appeared >= 2:
        base *= 0.75
    return base


def _appeared_count(tile: str, rem_tiles: Mapping[str, int]) -> int:
    """已离开牌墙的物理张数 ≈ 4 - Rem（含手牌/副露/河/公示）。"""
    rem = rem_tiles.get(tile, 0)
    return max(0, 4 - rem)


# ---------------------------------------------------------------------------
# 壁牌断顺子搭
# ---------------------------------------------------------------------------

def _apply_sequence_wall_discount(
    danger: float, tile: str, rem_tiles: Mapping[str, int]
) -> float:
    """相邻顺子搭子因壁牌断张时，下调序数听牌危险度。"""
    if not _is_suited(tile):
        return danger

    digit = int(tile[0])
    suit = tile[1]
    left = f"{digit - 1}{suit}" if digit >= 2 else None
    right = f"{digit + 1}{suit}" if digit <= 8 else None

    left_dead = left is None or rem_tiles.get(left, 0) <= 0
    right_dead = right is None or rem_tiles.get(right, 0) <= 0

    if digit in (1, 9):
        # 边张：唯一邻接已绝 → 两面/边张听大幅削弱
        if (digit == 1 and right_dead) or (digit == 9 and left_dead):
            return danger * WALL_ONE_SIDE_EDGE_FACTOR
        return danger

    if left_dead and right_dead:
        return danger * WALL_BOTH_SIDES_FACTOR
    if left_dead or right_dead:
        return danger * WALL_ONE_SIDE_EDGE_FACTOR
    return danger


# ---------------------------------------------------------------------------
# 副露染手
# ---------------------------------------------------------------------------

def _apply_dye_modifier(
    danger: float,
    tile: str,
    opponent: PlayerState,
    dealer_tile: str,
) -> float:
    dye_suit = _detect_dye_suit(opponent.melds, dealer_tile)
    if dye_suit is None:
        return danger

    # 字牌不受序数染手倍率（既不加倍也不按「它色」打折）
    if not _is_suited(tile):
        return danger

    logical = _logical_tile(tile, dealer_tile)
    if not _is_suited(logical):
        return danger

    suit = logical[1]
    digit = int(logical[0])

    if suit == dye_suit and digit in (3, 4, 5, 6, 7):
        return danger * DYE_OWN_SUIT_MID_FACTOR
    if suit != dye_suit:
        return danger * DYE_OTHER_SUIT_FACTOR
    return danger


def _detect_dye_suit(
    melds: list[Meld], dealer_tile: str
) -> str | None:
    """若副露序数花色单一（全同门），判定染手并返回 m/p/s。

    条件：无杂色序数副露，且（≥2 组同门）或（至少 1 组碰/杠同门）。
    纯字牌副露不构成序数染手；单吃顺不单独判染。
    """
    suit_counts: Counter[str] = Counter()
    has_triplet_or_kong = False
    for meld in melds:
        suit = _meld_suit(meld, dealer_tile)
        if suit is None:
            continue
        suit_counts[suit] += 1
        mtype = str(getattr(meld.meld_type, "value", meld.meld_type))
        if mtype in ("pong", "peng", "ming_gang", "an_gang"):
            has_triplet_or_kong = True

    if not suit_counts:
        return None
    if len(suit_counts) != 1:
        return None
    suit, n = next(iter(suit_counts.items()))
    if n >= 2 or has_triplet_or_kong:
        return suit
    return None


def _meld_suit(meld: Meld, dealer_tile: str) -> str | None:
    """副露主花色；字牌刻/杠返回 None。白板按替身映射。"""
    if not meld.tiles:
        return None
    # 吃：看逻辑后的序数花色
    suits: set[str] = set()
    for t in meld.tiles:
        logical = _logical_tile(t, dealer_tile)
        if _is_suited(logical):
            suits.add(logical[1])
        elif _is_honor(logical):
            continue
    if len(suits) == 1:
        return next(iter(suits))
    return None


# ---------------------------------------------------------------------------
# 牌面工具（物理 / 白板替身）
# ---------------------------------------------------------------------------

def _logical_tile(tile: str, dealer_tile: str) -> str:
    """计分/染手用逻辑身份：得≠白时 P → dealer_tile。"""
    if dealer_tile == "P":
        return tile
    if tile == "P":
        return dealer_tile
    return tile


def _is_suited(tile: str) -> bool:
    return len(tile) == 2 and tile[1] in ("m", "p", "s") and tile[0].isdigit()


def _is_honor(tile: str) -> bool:
    return tile in WINDS or tile in DRAGONS


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
