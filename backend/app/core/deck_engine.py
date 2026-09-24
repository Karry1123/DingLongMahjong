"""牌墙引擎：136 张洗牌、翻得、发牌与摸牌（rule.md §1 / §2）。

守恒：
    136 = 1（得公示） + 14（庄） + 13×3（闲） + len(wall_tiles)
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Any

from .constants import (
    FULL_DECK_SIZE,
    TILES_PER_TYPE,
    WINDS,
    build_full_deck,
)

# 逆时针座次（庄起）
_SEAT_ORDER = list(WINDS)  # E → S → W → N


def setup_new_game(
    dealer_seat: str,
    *,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """洗牌、翻得、发牌，返回开局局面。

    Args:
        dealer_seat: 庄家门风 E/S/W/N（起手 14 张，第一手出牌权）。
        rng: 可选随机源（单测可注入）。

    Returns:
        ``dealer_seat / dealer_tile / hands / wall_tiles / wall_count /
        shown_occupied / total_tiles`` 等。
    """
    if dealer_seat not in WINDS:
        raise ValueError(f"dealer_seat 非法：{dealer_seat!r}，须为 E/S/W/N")

    shuffle_rng = rng if rng is not None else random
    deck = build_full_deck()
    assert len(deck) == FULL_DECK_SIZE
    shuffle_rng.shuffle(deck)

    # §2：翻开牌墙尾部 1 张为「得」，公示占用，不可再摸
    dealer_tile = deck.pop()  # 尾部
    shown_occupied = True

    # 发牌：自庄家起逆时针，庄 14、闲 13
    order = _deal_order(dealer_seat)
    hands: dict[str, list[str]] = {s: [] for s in WINDS}
    # 先各家 13 张（共 52），再庄家补 1 张 → 14
    for _ in range(13):
        for seat in order:
            if not deck:
                raise RuntimeError("发牌时牌堆耗尽")
            hands[seat].append(deck.pop(0))
    hands[dealer_seat].append(deck.pop(0))

    wall_tiles = list(deck)  # 剩余为可摸牌墙（队列：头部先摸）

    _assert_conservation(
        dealer_tile=dealer_tile,
        hands=hands,
        wall_tiles=wall_tiles,
        dealer_seat=dealer_seat,
    )

    return {
        "dealer_seat": dealer_seat,
        "dealer_tile": dealer_tile,
        "shown_occupied": shown_occupied,
        "hands": {s: list(hands[s]) for s in WINDS},
        "hand_counts": {s: len(hands[s]) for s in WINDS},
        "wall_tiles": wall_tiles,
        "wall_count": len(wall_tiles),
        "total_tiles": FULL_DECK_SIZE,
        "first_turn_seat": dealer_seat,
        "is_exhausted": False,
    }


def draw_tile_from_wall(
    wall_tiles: list[str],
) -> dict[str, Any]:
    """从牌墙头部摸 1 张。

    Returns:
        ``tile / wall_tiles / wall_count / is_exhausted``。
        牌墙已空时 ``tile=None, is_exhausted=True``（荒牌流局标记）。
    """
    wall = list(wall_tiles or [])
    if not wall:
        return {
            "tile": None,
            "wall_tiles": [],
            "wall_count": 0,
            "is_exhausted": True,
            "note": "牌墙已空，荒牌流局",
        }
    tile = wall.pop(0)
    return {
        "tile": tile,
        "wall_tiles": wall,
        "wall_count": len(wall),
        "is_exhausted": len(wall) == 0,
        "note": "牌墙已空，下家将无法再摸" if not wall else "",
    }


def expected_closed_hand_count(meld_count: int, *, phase: str = "wait") -> int:
    """副露后暗手张数公式（rule_2.md §3）。

    Args:
        meld_count: 副露组数（吃/碰/杠各计 1）。
        phase: ``wait`` = 摸牌前（13-3n）；``discard`` = 出牌阶段（14-3n）。
    """
    n = max(0, int(meld_count or 0))
    if phase == "discard":
        return 14 - 3 * n
    return 13 - 3 * n


def verify_deck_integrity(
    *,
    dealer_tile: str,
    hands: dict[str, list[str]],
    wall_tiles: list[str],
) -> None:
    """公开校验：张数守恒 + 每种物理牌恰好 4 张。"""
    _assert_conservation(
        dealer_tile=dealer_tile,
        hands=hands,
        wall_tiles=wall_tiles,
        dealer_seat=None,
    )


def _deal_order(dealer_seat: str) -> list[str]:
    i = _SEAT_ORDER.index(dealer_seat)
    return _SEAT_ORDER[i:] + _SEAT_ORDER[:i]


def _assert_conservation(
    *,
    dealer_tile: str,
    hands: dict[str, list[str]],
    wall_tiles: list[str],
    dealer_seat: str | None,
) -> None:
    all_tiles: list[str] = [dealer_tile]
    for seat in WINDS:
        all_tiles.extend(hands.get(seat) or [])
    all_tiles.extend(wall_tiles)

    if len(all_tiles) != FULL_DECK_SIZE:
        raise AssertionError(
            f"牌数不守恒：合计 {len(all_tiles)} ≠ {FULL_DECK_SIZE}"
        )

    counts = Counter(all_tiles)
    for tile, n in counts.items():
        if n != TILES_PER_TYPE:
            raise AssertionError(
                f"物理牌 {tile!r} 出现 {n} 次，须恰好 {TILES_PER_TYPE}"
            )
    # 不得缺种：允许某些牌全在某一区域，但 34 种须齐
    from .constants import ALL_TILES

    missing = [t for t in ALL_TILES if counts[t] != TILES_PER_TYPE]
    if missing:
        raise AssertionError(f"牌种计数异常：{missing[:5]}...")

    if dealer_seat is not None:
        if len(hands.get(dealer_seat) or []) != 14:
            raise AssertionError("庄家须 14 张")
        for s in WINDS:
            if s == dealer_seat:
                continue
            if len(hands.get(s) or []) != 13:
                raise AssertionError(f"闲家 {s} 须 13 张")
        expected_wall = FULL_DECK_SIZE - 1 - 14 - 13 * 3
        if len(wall_tiles) != expected_wall:
            raise AssertionError(
                f"牌墙张数 {len(wall_tiles)} ≠ 期望 {expected_wall}"
            )
