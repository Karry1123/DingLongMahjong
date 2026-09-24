"""手牌预处理：解析「得」（财神）与白板替身。

严格遵循 rule.md §2「得」与白板替身机制：

情况 A（翻出非白板）：
  - 翻出的那张牌（dealer_tile）全场为百搭 → 映射为 JOKER
  - 白板（P）自动承担原牌物理属性 → 映射为 dealer_tile

情况 B（翻出白板本身）：
  - 白板自身为万能百搭 → 映射为 JOKER
  - 无额外替身牌

公示占用：翻开的「得」摆在牌墙之上，不参与摸牌；
牌墙内可摸百搭上限见 constants.JOKER_WALL_CAPACITY（3）。
"""

from .constants import JOKER


def preprocess_hand(hand_tiles: list[str], dealer_tile: str) -> list[str]:
    """将原始手牌映射为规则引擎可用的逻辑牌面。

    Args:
        hand_tiles: 原始手牌编码列表（如 ["1m", "P", "5s", ...]）。
        dealer_tile: 本局翻开的「得」（财神）牌面编码。

    Returns:
        预处理后的手牌列表：
        - 真正的百搭统一标记为 "JOKER"
        - 情况 A 下，白板已替换为 dealer_tile 的物理身份

    Examples:
        >>> # 情况 A：得 = 5s → 5s 变 JOKER，P 变 5s
        >>> preprocess_hand(["5s", "P", "1m"], "5s")
        ['JOKER', '5s', '1m']

        >>> # 情况 B：得 = P → P 直接变 JOKER
        >>> preprocess_hand(["P", "1m", "2m"], "P")
        ['JOKER', '1m', '2m']
    """
    result: list[str] = []

    if dealer_tile == "P":
        # ── 情况 B：翻出白板 ──
        # 白板自身即为百搭，无替身；其余牌原样保留。
        for tile in hand_tiles:
            if tile == "P":
                result.append(JOKER)
            else:
                result.append(tile)
    else:
        # ── 情况 A：翻出非白板 ──
        # 1) dealer_tile → JOKER（百搭）
        # 2) P → dealer_tile（白板替身，继承原牌物理属性）
        # 3) 其余牌原样保留
        for tile in hand_tiles:
            if tile == dealer_tile:
                result.append(JOKER)
            elif tile == "P":
                result.append(dealer_tile)
            else:
                result.append(tile)

    return result


def normalize_hand_for_eval(
    hand_tiles: list[str], dealer_tile: str
) -> list[str]:
    """胡牌/向听检测入口别名：强制先做白板替身与得→JOKER 映射。

    与 ``preprocess_hand`` 等价；供 evaluator / action_generator /
    结算路径显式调用，避免漏掉情况 A 的白板→原物理牌替换。
    """
    return preprocess_hand(list(hand_tiles or []), dealer_tile)
