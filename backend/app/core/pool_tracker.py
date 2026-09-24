"""全场剩余牌 / 壁牌追踪（rule.md §2）。

Rem 公式（物理牌隔离）：
    Rem(T) = 4
           - count_in_hand(T)
           - count_in_discarded(T)
           - count_in_melds(T)
           - 1[T == dealer_tile]

说明：
- 扣减一律按**物理牌**编码；白板（P）与「得」同名牌互不混计。
- 进张枚举使用本模块给出的 Rem；入逻辑手牌时再经 ``mapper.preprocess_hand``
  做白板替身 / 百搭映射（情况 A/B）。
- Rem(T) <= 0 的牌不再贡献有效进张（调用方可过滤，或使用本模块已钳制为 0 的值）。
"""

from __future__ import annotations

from collections import Counter

from app.schemas import HandRequest

from .constants import ALL_TILES


def get_remaining_tiles(request: HandRequest) -> dict[str, int]:
    """计算全场每种物理牌的壁牌剩余枚数 Rem(T)。

    Args:
        request: 含自家手牌/副露/牌河、对手公开状态、得牌的决策请求。

    Returns:
        ``{tile_code: rem}``，覆盖全部 34 种牌；``rem`` 已钳制为 ``>= 0``。
    """
    hand_counts = Counter(request.hand_tiles)
    discard_counts = Counter(request.collect_all_discards())
    meld_counts = Counter(request.collect_all_meld_tiles())
    dealer = request.dealer_tile

    remaining: dict[str, int] = {}
    for tile in ALL_TILES:
        rem = rem_tile(
            tile,
            hand_count=hand_counts.get(tile, 0),
            discard_count=discard_counts.get(tile, 0),
            meld_count=meld_counts.get(tile, 0),
            dealer_tile=dealer,
        )
        remaining[tile] = rem
    return remaining


def rem_tile(
    tile: str,
    *,
    hand_count: int,
    discard_count: int,
    meld_count: int,
    dealer_tile: str,
) -> int:
    """单张物理牌 Rem(T)，结果 ``>= 0``。

    公示占用：仅当 ``tile == dealer_tile`` 时再减 1（与手牌中的同名牌分开计）。
    """
    shown = 1 if tile == dealer_tile else 0
    rem = 4 - hand_count - discard_count - meld_count - shown
    return max(rem, 0)


def get_effective_remaining(request: HandRequest) -> dict[str, int]:
    """仅返回 Rem(T) > 0 的物理牌（可直接作进张权重）。"""
    return {t: n for t, n in get_remaining_tiles(request).items() if n > 0}
