"""台州麻将合法牌面常量。

严格遵循 rule.md §1：
- 序数牌：万（1m~9m）、筒（1p~9p）、条（1s~9s），各 9 种
- 字牌：东（E）、南（S）、西（W）、北（N）、中（C）、发（F）、白板（P），共 7 种
合计 34 种牌型（无花牌）。
"""

# 序数牌
MANS = [f"{i}m" for i in range(1, 10)]   # 1m ~ 9m
PINS = [f"{i}p" for i in range(1, 10)]   # 1p ~ 9p
SOUS = [f"{i}s" for i in range(1, 10)]   # 1s ~ 9s

# 字牌：东、南、西、北、中、发、白板
HONORS = ["E", "S", "W", "N", "C", "F", "P"]

# 风牌（门风候选）
WINDS = ["E", "S", "W", "N"]

# 三元牌（中发白）
DRAGONS = ["C", "F", "P"]

# 全副 34 种合法牌型代码（顺序：万 → 筒 → 条 → 字）
ALL_TILES: list[str] = MANS + PINS + SOUS + HONORS

# 每种物理牌 4 张；全副 136 张（无花牌）
TILES_PER_TYPE = 4
FULL_DECK_SIZE = 136

# 预处理后的百搭占位符（对应 rule.md 中的「得」万能属性）
JOKER = "JOKER"

# rule.md §2：翻开的「得」公示占用 1 张，牌墙内可摸百搭上限为 3
JOKER_WALL_CAPACITY = 3

assert len(ALL_TILES) == 34, "台州麻将合法牌型必须恰好为 34 种"
assert FULL_DECK_SIZE == len(ALL_TILES) * TILES_PER_TYPE


def build_full_deck() -> list[str]:
    """构造一副完整 136 张物理牌（每种 4 张）。"""
    return [t for t in ALL_TILES for _ in range(TILES_PER_TYPE)]
