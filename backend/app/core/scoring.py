"""黄岩麻将胡数计算模块。

核心公式
--------
胡牌者最终胡数 = (牌型胡数 + 底胡) × (2 ^ 翻数)
未胡者参考胡数 = 牌型胡数 × (2 ^ 翻数)

牌型胡数来自：雀头 / 明刻 / 暗刻 / 明杠 / 暗杠 / 自摸 / 嵌档。
顺子一律 0 胡。翻数来自：三元刻杠、门风刻杠、圈风刻杠、硬碰硬、得还原、混/清一色。

本模块为独立计分入口；EV 引擎等调用方应逐步迁移到 ``calculate_hu_points``。
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.schemas import Meld, MeldType

from .constants import ALL_TILES, DRAGONS, JOKER, WINDS
from .mapper import preprocess_hand

# ---------------------------------------------------------------------------
# 可调常量（分值集中定义，便于后续改规则）
# ---------------------------------------------------------------------------

# 底胡（仅胡牌者计入最终公式）
DEFAULT_BASE_HU = 10
MAX_PAYMENT_PER_PLAYER = 100  # 单家单局实际支付上限；不截断牌型 final_hu

# 雀头
PAIR_SEAT_WIND_HU = 2  # 自家门风对
PAIR_DRAGON_HU = 2  # 中 / 发 / 白 对
PAIR_NORMAL_HU = 0  # 普通对子

# 明刻（碰）
PONG_TERMINAL_HONOR_HU = 4  # 风 / 幺九 / 字
PONG_SIMPLE_HU = 2  # 2~8 中张

# 暗刻（手里三张未碰；四张未开杠也按暗刻计）
ANKO_TERMINAL_HONOR_HU = 8
ANKO_SIMPLE_HU = 4

# 明杠
MING_GANG_TERMINAL_HONOR_HU = 16
MING_GANG_SIMPLE_HU = 8

# 暗杠
AN_GANG_TERMINAL_HONOR_HU = 32
AN_GANG_SIMPLE_HU = 16

# 其他加胡
ZIMO_HU = 2  # 自摸只加胡、不加番
KANZHANG_HU = 2  # 嵌档（卡张）
CHI_HU = 0  # 顺子恒 0

# 翻数
FAN_DRAGON_PUNG_OR_KONG = 1  # 中/发/白 每组刻或杠
FAN_SEAT_WIND_PUNG_OR_KONG = 1  # 自家门风刻或杠
FAN_ROUND_WIND_PUNG_OR_KONG = 1  # 圈风刻或杠（可与门风叠加）
FAN_HARD_HU = 1  # 硬碰硬（无「得」作百搭）
FAN_RESTORED_JOKER = 1  # 得还原：每张 +1，最多 3
MAX_RESTORED_JOKER_FAN = 3
FAN_HALF_FLUSH = 1  # 混一色
FAN_FULL_FLUSH = 3  # 清一色（与混一色互斥，取清）

_DRAGON_FAN_CN = {"C": "红中", "F": "发财", "P": "白板"}
_WIND_FAN_CN = {"E": "东风", "S": "南风", "W": "西风", "N": "北风"}
_MELD_FAN_CN = {
    "anko": "暗刻",
    "pong": "明刻",
    "ming_gang": "明杠",
    "an_gang": "暗杠",
}


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------

def calculate_hu_points(
    melds: list | Sequence[Meld],
    hand_tiles: list[str],
    win_tile: str,
    is_zimo: bool,
    seat_wind: str,
    dealer_tile: str,
    base_hu: int = DEFAULT_BASE_HU,
    restored_jokers: int = 0,
    round_wind: str = "E",
) -> dict[str, Any]:
    """计算一笔胡牌的完整胡数明细。

    Args:
        melds: 副露列表；每项含类型（chi/pong/ming_gang/an_gang）与牌。
        hand_tiles: 门清剩余手牌（已去除副露，**不含**胡牌张）。
        win_tile: 胡的那张牌（自摸摸入 / 点炮打出）。
        is_zimo: 是否自摸。
        seat_wind: 自风 E/S/W/N。
        dealer_tile: 本局财神（得）。
        base_hu: 底胡，默认 10。
        restored_jokers: 得还原张数（把「得」按本身牌面使用的张数）。
        round_wind: 圈风 E/S/W/N（与门风同时成立时可叠番）。

    Returns:
        含 tile_hu / base_hu / fan / final_hu / is_hard_hu / details 的字典。

    Raises:
        ValueError: 牌数不合法、无法拆出和牌型、还原张数非法等。
    """
    open_melds = [_normalize_meld(m) for m in melds]
    _validate_counts(hand_tiles, open_melds, win_tile)

    if restored_jokers < 0:
        raise ValueError(f"restored_jokers 不能为负：{restored_jokers}")
    if seat_wind not in WINDS:
        raise ValueError(f"seat_wind 非法：{seat_wind!r}")
    if round_wind not in WINDS:
        raise ValueError(f"round_wind 非法：{round_wind!r}")

    # 物理牌 → 逻辑牌（得→JOKER，白板替身）
    full_physical = list(hand_tiles) + [win_tile]
    logical = preprocess_hand(full_physical, dealer_tile)
    win_logical = preprocess_hand([win_tile], dealer_tile)[0]

    raw_jokers = sum(1 for t in logical if t == JOKER)
    if restored_jokers > raw_jokers:
        raise ValueError(
            f"得还原 {restored_jokers} 张超过手中「得」{raw_jokers} 张"
        )

    # 得还原：把若干 JOKER 还原为财神本身牌面
    restored = restored_jokers
    working: list[str] = []
    for t in logical:
        if t == JOKER and restored > 0:
            # 还原为财神本身牌面（得=白 时即为 P）
            working.append(dealer_tile)
            restored -= 1
        else:
            working.append(t)

    # 还原后的「得」百搭数（硬碰硬看这个）
    # 规则：得仅作本身刻/杠/雀头（含与白板替身成对）→ 须还原后判定，无残留百搭即为硬胡
    wild_jokers = sum(1 for t in working if t == JOKER)
    is_hard_hu = wild_jokers == 0

    needed_melds = 4 - len(open_melds)
    shapes = _enumerate_win_shapes(working, needed_melds)
    if not shapes:
        raise ValueError("无法拆解为合法和牌型（面子+雀头）")

    # 比较拆型、物理牌分配及胡张归属，不能先按牌型胡贪心选面子。
    best: dict[str, Any] | None = None
    for shape in shapes:
        for variant, displays in _physical_shape_variants(shape, full_physical, dealer_tile):
            for winning_group, display in enumerate(displays):
                if not any(d['code'] == win_tile for d in display):
                    continue
                scored = _score_shape(
                    shape=variant,
                    open_melds=open_melds,
                    win_logical=win_logical,
                    win_tile_physical=win_tile,
                    is_zimo=is_zimo,
                    seat_wind=seat_wind,
                    round_wind=round_wind,
                    dealer_tile=dealer_tile,
                    base_hu=base_hu,
                    restored_jokers=restored_jokers,
                    is_hard_hu=is_hard_hu,
                    physical_tiles=full_physical,
                    physical_groups=displays,
                    winning_group=winning_group,
                )
                if best is None or hu_selection_key(scored) > hu_selection_key(best):
                    best = scored

    assert best is not None
    return best


def calculate_best_hu_points(
    melds: list | Sequence[Meld],
    hand_tiles: list[str],
    win_tile: str,
    is_zimo: bool,
    seat_wind: str,
    dealer_tile: str,
    base_hu: int = DEFAULT_BASE_HU,
    round_wind: str = "E",
) -> dict[str, Any]:
    """枚举得还原张数，取最终胡数最高的声明，同分优先硬胡。

    用于结算 / 捉铳入口：避免调用方漏传 restored_jokers 导致误判软胡、漏计番。
    """
    full = list(hand_tiles) + [win_tile]
    logical = preprocess_hand(full, dealer_tile)
    max_restore = sum(1 for t in logical if t == JOKER)

    best: dict[str, Any] | None = None
    last_err: Exception | None = None
    for restored in range(0, max_restore + 1):
        try:
            hu = calculate_hu_points(
                melds=melds,
                hand_tiles=hand_tiles,
                win_tile=win_tile,
                is_zimo=is_zimo,
                seat_wind=seat_wind,
                dealer_tile=dealer_tile,
                base_hu=base_hu,
                restored_jokers=restored,
                round_wind=round_wind,
            )
        except ValueError as exc:
            last_err = exc
            continue
        if best is None or hu_selection_key(hu) > hu_selection_key(best):
            best = hu
    if best is None:
        raise ValueError(
            str(last_err) if last_err else "无法拆解为合法和牌型（面子+雀头）"
        )
    return best


def hu_selection_key(hu: Mapping[str, Any]) -> tuple[int, bool, int]:
    """结算与评估共用的优先级：最终胡数、硬胡、牌型胡。"""
    return (hu["final_hu"], bool(hu["is_hard_hu"]), hu["tile_hu"])


def calculate_meld_points(meld: Meld, dealer_tile: str) -> int:
    """单组副露的牌型胡（兼容旧接口 score_calc.calculate_meld_points）。"""
    item = _score_open_meld(_normalize_meld(meld), dealer_tile)
    return int(item["hu"])


# ---------------------------------------------------------------------------
# 计分：拆型 → 明细
# ---------------------------------------------------------------------------

@dataclass
class _ConcealedMeld:
    """门清面子。"""

    kind: str  # "chi" | "anko"
    tiles: list[str]  # 逻辑牌面（顺子为三张序数；刻子为三张同名）
    jokers_used: int = 0
    # 百搭实际充当的逻辑牌（与 tiles 对齐的缺失位）
    joker_filled: list[str] = field(default_factory=list)


@dataclass
class _WinShape:
    """一种和牌拆法。"""

    pair_tile: str  # 雀头逻辑牌；纯百搭雀头用 JOKER
    pair_jokers: int
    melds: list[_ConcealedMeld] = field(default_factory=list)


def _physical_shape_variants(shape, physical_tiles, dealer_tile):
    """枚举替身/还原得在各组的分配，保留物理牌守恒及百搭使用身份。"""
    specs = [(cm.tiles, cm.joker_filled) for cm in shape.melds]
    specs.append(([shape.pair_tile] * 2, [shape.pair_tile] * shape.pair_jokers))
    slots = []
    for group_index, (tiles, filled) in enumerate(specs):
        wild = Counter(filled)
        for face in tiles:
            is_wild = wild[face] > 0
            wild[face] -= int(is_wild)
            slots.append((group_index, face, is_wild))
    pool = Counter(physical_tiles)
    groups = [[] for _ in specs]

    def assign(index):
        if index == len(slots):
            yield from white_variants(deepcopy(shape), deepcopy(groups), 0)
            return
        gi, face, wild = slots[index]
        choices = [dealer_tile] if wild else (
            ['P', dealer_tile] if face == dealer_tile and dealer_tile != 'P' else [face]
        )
        for code in choices:
            if pool[code] <= 0:
                continue
            pool[code] -= 1
            substitute = code == 'P' and dealer_tile != 'P'
            restored = code == dealer_tile and not wild
            label = (f'得·代{_tile_cn(face)}' if wild else
                     f'白(替{_tile_cn(dealer_tile)})' if substitute else
                     f'得·本{_tile_cn(dealer_tile)}' if restored else _tile_cn(code))
            groups[gi].append(dict(code=code, is_joker=wild or restored,
                                   is_restored=restored, is_substitute=substitute,
                                   is_win_tile=False, substituted_as=face, label=label))
            yield from assign(index + 1)
            groups[gi].pop()
            pool[code] += 1

    def white_variants(variant, displays, index):
        if index == len(variant.melds):
            yield variant, displays
            return
        yield from white_variants(variant, displays, index + 1)
        cm = variant.melds[index]
        group = displays[index]
        # 白板与百搭得同组成刻子时，可另解释为得变白板；这条路径仍是软胡。
        if (dealer_tile != 'P' and cm.kind == 'anko' and cm.tiles[0] == dealer_tile
                and cm.jokers_used and any(d['code'] == 'P' for d in group)
                and all(d['code'] == 'P' or (d['is_joker'] and not d['is_restored']) for d in group)):
            alternate, shown = deepcopy(variant), deepcopy(displays)
            alternate.melds[index].tiles = ['P'] * 3
            alternate.melds[index].joker_filled = ['P'] * cm.jokers_used
            for d in shown[index]:
                d.update(substituted_as='P', is_substitute=False,
                         label='得·代白' if d['is_joker'] else '白')
            yield from white_variants(alternate, shown, index + 1)

    yield from assign(0)


def _score_shape(
    *,
    shape: _WinShape,
    open_melds: list[dict[str, Any]],
    win_logical: str,
    win_tile_physical: str,
    is_zimo: bool,
    seat_wind: str,
    round_wind: str,
    dealer_tile: str,
    base_hu: int,
    restored_jokers: int,
    is_hard_hu: bool,
    physical_tiles: list[str] | None = None,
    physical_groups: list | None = None,
    winning_group: int | None = None,
) -> dict[str, Any]:
    """对一种拆法累计牌型胡与翻数，并套公式。"""
    details_pairs: list[dict[str, Any]] = []
    details_melds: list[dict[str, Any]] = []
    fans: dict[str, int] = {}
    fan_items: list[str] = []

    tile_hu = 0

    # —— 雀头 ——
    pair_hu = _pair_hu(shape.pair_tile, seat_wind)
    pair_note = _pair_note(
        shape.pair_tile,
        seat_wind,
        dealer_tile=dealer_tile,
        physical_tiles=physical_tiles,
        pair_jokers=shape.pair_jokers,
        restored_jokers=restored_jokers,
    )
    details_pairs.append(
        {
            "tile": shape.pair_tile,
            "hu": pair_hu,
            "jokers_used": shape.pair_jokers,
            "note": pair_note,
        }
    )
    tile_hu += pair_hu

    # —— 副露 ——
    for m in open_melds:
        item = _score_open_meld(m, dealer_tile)
        details_melds.append(item)
        tile_hu += item["hu"]

    # —— 门清明刻 / 顺子 ——
    for ci, cm in enumerate(shape.melds):
        if cm.kind == "chi":
            details_melds.append(
                {
                    "source": "concealed",
                    "type": "chi",
                    "tiles": list(cm.tiles),
                    "hu": CHI_HU,
                    "jokers_used": cm.jokers_used,
                }
            )
            continue

        # anko：四张未开杠也只按暗刻
        identity = cm.tiles[0]
        ron_pung = not is_zimo and ci == winning_group
        hu = ((PONG_TERMINAL_HONOR_HU if _is_terminal_or_honor(identity) else PONG_SIMPLE_HU)
              if ron_pung else
              (ANKO_TERMINAL_HONOR_HU if _is_terminal_or_honor(identity) else ANKO_SIMPLE_HU))
        details_melds.append(
            {
                "source": "concealed",
                "type": "pong" if ron_pung else "anko",
                "tiles": list(cm.tiles),
                "hu": hu,
                "jokers_used": cm.jokers_used,
            }
        )
        tile_hu += hu

    # —— 自摸 / 嵌档 ——
    zimo_hu = ZIMO_HU if is_zimo else 0
    tile_hu += zimo_hu

    # 嵌档只看实际胡张所在顺子，不能借另一组同名牌加胡。
    winning_cm = shape.melds[winning_group] if winning_group is not None and winning_group < len(shape.melds) else None
    is_kanzhang = bool(winning_cm and winning_cm.kind == 'chi'
                       and physical_groups[winning_group][1]['code'] == win_tile_physical
                       and win_logical != JOKER)
    kanzhang_hu = KANZHANG_HU if is_kanzhang else 0
    tile_hu += kanzhang_hu

    # 保留每组物理牌，三元番不能仅由替身映射后的逻辑身份判定。
    decomposition = _build_best_decomposition(
        shape=shape,
        open_melds=open_melds,
        dealer_tile=dealer_tile,
        details_pairs=details_pairs,
        details_melds=details_melds,
        physical_tiles=physical_tiles or [],
        win_tile=win_tile_physical,
        restored_jokers=restored_jokers,
        physical_groups=physical_groups,
        winning_group=winning_group,
    )

    # —— 翻数（字牌刻杠胡数与加番相互独立）——
    fan = 0
    dragon_groups = 0
    seat_wind_groups = 0
    round_wind_groups = 0

    for item, group in zip(details_melds, decomposition["winning_hand_groups"]):
        if item["type"] == "chi":
            continue
        identity = item['tiles'][0] if item['source'] == 'concealed' else _group_identity(item, dealer_tile)
        kind_cn = _MELD_FAN_CN.get(str(item["type"]), "刻/杠")
        dragon = ('P' if item['source'] == 'concealed' and identity == 'P'
                  else _dragon_group_identity(identity, group["tiles"], dealer_tile))
        if dragon:
            dragon_groups += 1
            name = _DRAGON_FAN_CN.get(dragon, dragon)
            fan_items.append(f"{name}{kind_cn} (翻番 ×2)")
        if identity == seat_wind:
            seat_wind_groups += 1
            fan_items.append(
                f"本门风{_WIND_FAN_CN.get(identity, identity)}"
                f"{kind_cn} (翻番 ×2)"
            )
        if identity == round_wind:
            round_wind_groups += 1
            fan_items.append(
                f"圈风{_WIND_FAN_CN.get(identity, identity)}"
                f"{kind_cn} (翻番 ×2)"
            )

    if dragon_groups:
        fans["dragon_pung_kong"] = dragon_groups * FAN_DRAGON_PUNG_OR_KONG
        fan += fans["dragon_pung_kong"]
    if seat_wind_groups:
        fans["seat_wind_pung_kong"] = (
            seat_wind_groups * FAN_SEAT_WIND_PUNG_OR_KONG
        )
        fan += fans["seat_wind_pung_kong"]
    if round_wind_groups:
        fans["round_wind_pung_kong"] = (
            round_wind_groups * FAN_ROUND_WIND_PUNG_OR_KONG
        )
        fan += fans["round_wind_pung_kong"]

    if is_hard_hu:
        fans["hard_hu"] = FAN_HARD_HU
        fan += FAN_HARD_HU
        fan_items.append("硬碰硬 (翻番 ×2)")

    # 硬胡与得还原互斥：归零所有还原番，避免同一手既认定未用百搭又奖励还原。
    restored_for_fan = sum(d['is_restored'] for g in physical_groups
                           if not any(d['code'] == 'P' for d in g) for d in g)
    if is_hard_hu:
        restored_for_fan = 0
    restored_fan = min(restored_for_fan, MAX_RESTORED_JOKER_FAN) * FAN_RESTORED_JOKER
    if restored_fan:
        fans["restored_jokers"] = restored_fan
        fan += restored_fan
        fan_items.append(f"得还原 ×{restored_for_fan} (翻番 ×{2 ** restored_fan})")

    flush_tiles = [_logical_tile(t, dealer_tile) for m in open_melds for t in m['tiles']]
    flush_tiles += [t for cm in shape.melds for t in cm.tiles] + [shape.pair_tile] * 2
    flush_fan, flush_name = _flush_fan(flush_tiles)
    if flush_fan:
        fans[flush_name] = flush_fan
        fan += flush_fan
        flush_cn = "清一色" if flush_name == "full_flush" else "混一色"
        fan_items.append(f"{flush_cn} (翻番 ×{2 ** flush_fan})")

    # —— 公式 ——
    final_hu = (tile_hu + base_hu) * (2 ** fan)
    others_hu = tile_hu * (2 ** fan)

    return {
        "tile_hu": tile_hu,
        "base_hu": base_hu,
        "fan": fan,
        "fan_count": fan,
        "final_hu": final_hu,
        "others_hu": others_hu,  # 未胡者参考：牌型胡 × 2^翻
        "is_hard_hu": is_hard_hu,
        "best_decomposition": decomposition,
        "winning_hand_groups": decomposition["winning_hand_groups"],
        "details": {
            "pairs": details_pairs,
            "melds": details_melds,
            "zimo": zimo_hu,
            "kanzhang": kanzhang_hu,
            "fans": fans,
            "fan_items": fan_items,
            "win_tile_logical": win_logical,
            "restored_jokers": restored_jokers,
            "restored_jokers_for_fan": restored_for_fan,
            "best_decomposition": decomposition,
            "seat_wind": seat_wind,
            "round_wind": round_wind,
        },
    }


def _build_best_decomposition(
    *,
    shape: _WinShape,
    open_melds: list[dict[str, Any]],
    dealer_tile: str,
    details_pairs: list[dict[str, Any]],
    details_melds: list[dict[str, Any]],
    physical_tiles: Sequence[str] | None = None,
    win_tile: str | None = None,
    restored_jokers: int = 0,
    physical_groups: list | None = None,
    winning_group: int | None = None,
) -> dict[str, Any]:
    """最佳和牌型：雀头 + 面子，并标注百搭代入 / 白板替身 / 胡张。"""
    pool = Counter(list(physical_tiles or []))
    pair_hu = details_pairs[0]["hu"] if details_pairs else 0
    pair_note = details_pairs[0].get("note") if details_pairs else ""
    pair_filled = (
        [shape.pair_tile] * shape.pair_jokers
        if shape.pair_tile != JOKER
        else [JOKER] * shape.pair_jokers
    )
    head_display = deepcopy(physical_groups[-1]) if physical_groups is not None else _display_pair_physical(
        pair_tile=shape.pair_tile,
        pair_jokers=shape.pair_jokers,
        dealer_tile=dealer_tile,
        pool=pool,
        win_tile=win_tile,
        restored_jokers=restored_jokers,
    )
    head = {
        "kind": "head",
        "tiles": [shape.pair_tile, shape.pair_tile],
        "jokers_used": shape.pair_jokers,
        "joker_filled": pair_filled,
        "joker_substituted": shape.pair_tile if shape.pair_jokers else None,
        "display_tiles": head_display,
        "hu": pair_hu,
        "note": pair_note,
    }

    groups: list[dict[str, Any]] = []
    # 副露（无百搭代入）
    for item in details_melds:
        if item.get("source") != "open":
            continue
        tiles = list(item.get("tiles") or [])
        # physical_tiles 仅含暗手及胡张，副露不能消耗这个池。
        groups.append(
            {
                "kind": item.get("type"),
                "source": "open",
                "tiles": tiles,
                "claimed_tile": item.get("claimed_tile"),
                "provider_seat": item.get("provider_seat"),
                "jokers_used": 0,
                "joker_filled": [],
                "joker_substituted": None,
                "display_tiles": _display_tiles_with_joker(
                    tiles, [], dealer_tile, pool=None, win_tile=win_tile
                ),
                "hu": int(item.get("hu") or 0),
                "contains_win_tile": bool(
                    win_tile and win_tile in tiles
                ),
            }
        )

    # 门清面子：与 shape.melds 顺序一致
    concealed_items = [
        m for m in details_melds if m.get("source") == "concealed"
    ]
    for idx, cm in enumerate(shape.melds):
        filled = list(cm.joker_filled or [])
        detail = concealed_items[idx] if idx < len(concealed_items) else {}
        sub = None
        if filled:
            uniq = list(dict.fromkeys(filled))
            sub = uniq[0] if len(uniq) == 1 else None
        display = deepcopy(physical_groups[idx]) if physical_groups is not None else _display_tiles_with_joker(
            list(cm.tiles),
            filled,
            dealer_tile,
            pool=pool,
            win_tile=win_tile,
        )
        groups.append(
            {
                "kind": detail.get('type', cm.kind),
                "source": "concealed",
                "tiles": list(cm.tiles),
                "jokers_used": cm.jokers_used,
                "joker_filled": filled,
                "joker_substituted": sub,
                "display_tiles": display,
                "hu": int(detail.get("hu") or 0),
                "contains_win_tile": any(
                    d.get("is_win_tile") for d in display
                ),
            }
        )

    # 全手只标记一个物理胡张；优先雀头末张，否则选暗手面子。
    ordered = groups + [head]
    for group in ordered:
        for tile in group["display_tiles"]:
            tile["is_win_tile"] = False
            if tile["code"] == "P" and dealer_tile != "P" and group.get('source') == 'open':
                tile.update(is_substitute=True, substituted_as=dealer_tile,
                            label=f"白(替{_tile_cn(dealer_tile)})")
    concealed_groups = [g for g in groups if g['source'] == 'concealed'] + [head]
    candidates = ([concealed_groups[winning_group]] if winning_group is not None
                  else [head] + concealed_groups[:-1])
    for group in candidates:
        matches = [d for d in group["display_tiles"] if d["code"] == win_tile]
        if matches:
            matches[-1]["is_win_tile"] = True
            break
    winning_hand_groups = []
    for group in ordered:
        display = group["display_tiles"]
        index = next((i for i, d in enumerate(display) if d["is_win_tile"]), None)
        group["contains_win_tile"] = index is not None
        winning_hand_groups.append({
            **group,
            "type": "PAIR" if group["kind"] == "head" else group["kind"].upper(),
            "source": group.get("source", "concealed"),
            "tiles": [d["code"] for d in display],
            "substitutions": {d["code"]: d["substituted_as"] for d in display
                              if d.get("is_substitute")},
            "winning_tile_index": index,
        })
    return {
        "winning_hand_groups": winning_hand_groups,
        "head": head,
        "melds_and_sequences": groups,
        "dealer_tile": dealer_tile,
        "win_tile": win_tile,
    }


def _take_physical_for_logical(
    logical: str,
    dealer_tile: str,
    pool: Counter[str],
    *,
    prefer_substitute: bool = False,
) -> tuple[str, bool, bool]:
    """从物理牌池取出一张对应逻辑身份的牌。

    Returns:
        (physical_code, is_joker_wild, is_substitute_whiteboard)
    """
    if logical == JOKER:
        # 仍作百搭的得
        if pool[dealer_tile] > 0:
            pool[dealer_tile] -= 1
            return dealer_tile, True, False
        return dealer_tile, True, False

    # 白板替身 → 逻辑得牌面
    if (
        dealer_tile != "P"
        and logical == dealer_tile
        and prefer_substitute
        and pool["P"] > 0
    ):
        pool["P"] -= 1
        return "P", False, True

    if pool[logical] > 0:
        # 物理得作本身牌面（还原）或普通同名牌
        pool[logical] -= 1
        return logical, False, False

    if dealer_tile != "P" and logical == dealer_tile and pool["P"] > 0:
        pool["P"] -= 1
        return "P", False, True

    # 池耗尽：回退逻辑码
    return logical if logical != JOKER else dealer_tile, logical == JOKER, False


def _display_pair_physical(
    *,
    pair_tile: str,
    pair_jokers: int,
    dealer_tile: str,
    pool: Counter[str],
    win_tile: str | None,
    restored_jokers: int,
) -> list[dict[str, Any]]:
    """雀头展示：优先保留白板替身物理面，并标明还原得 / 百搭得。"""
    out: list[dict[str, Any]] = []
    wild_left = int(pair_jokers)
    can_sub = (
        dealer_tile != "P"
        and pair_tile == dealer_tile
        and pool["P"] > 0
    )
    for i in range(2):
        if wild_left > 0:
            wild_left -= 1
            code, _, _ = _take_physical_for_logical(
                JOKER, dealer_tile, pool
            )
            as_tile = pair_tile if pair_tile != JOKER else dealer_tile
            out.append(
                {
                    "code": code,
                    "is_joker": True,
                    "is_restored": False,
                    "is_substitute": False,
                    "is_win_tile": bool(win_tile and code == win_tile),
                    "substituted_as": as_tile,
                    "label": f"得·代{_tile_cn(as_tile)}",
                }
            )
            continue

        prefer_sub = bool(can_sub and i == 1)
        code, is_wild, is_sub = _take_physical_for_logical(
            pair_tile if pair_tile != JOKER else JOKER,
            dealer_tile,
            pool,
            prefer_substitute=prefer_sub,
        )
        is_restored = (
            not is_wild
            and not is_sub
            and code == dealer_tile
            and pair_tile == dealer_tile
            and restored_jokers > 0
        )
        label = _tile_cn(code)
        if is_sub:
            label = f"白(替{_tile_cn(dealer_tile)})"
        elif is_wild:
            label = f"得·代{_tile_cn(pair_tile if pair_tile != JOKER else dealer_tile)}"
        elif is_restored:
            label = f"得·本{_tile_cn(dealer_tile)}"
        out.append(
            {
                "code": code,
                "is_joker": is_wild or is_restored,
                "is_restored": is_restored,
                "is_substitute": is_sub,
                "is_win_tile": bool(win_tile and code == win_tile),
                "substituted_as": pair_tile if pair_tile != JOKER else dealer_tile,
                "label": label,
            }
        )
    return out


def _display_tiles_with_joker(
    logical_tiles: list[str],
    joker_filled: list[str],
    dealer_tile: str,
    pool: Counter[str] | None = None,
    win_tile: str | None = None,
) -> list[dict[str, Any]]:
    """把逻辑面子展开为展示张：百搭位 / 替身白板 / 胡张标记。"""
    need = Counter(joker_filled or [])
    used = Counter()
    local_pool = pool if pool is not None else Counter()
    out: list[dict[str, Any]] = []
    win_marked = False
    for t in logical_tiles:
        is_joker_slot = used[t] < need[t]
        if is_joker_slot:
            used[t] += 1
        if pool is not None:
            if is_joker_slot:
                code, is_wild, is_sub = _take_physical_for_logical(
                    JOKER, dealer_tile, local_pool
                )
                as_tile = t if t != JOKER else dealer_tile
                is_win = False
                if win_tile and not win_marked and code == win_tile:
                    is_win = True
                    win_marked = True
                out.append(
                    {
                        "code": code,
                        "is_joker": True,
                        "is_restored": False,
                        "is_substitute": False,
                        "is_win_tile": is_win,
                        "substituted_as": as_tile,
                        "label": f"得·代{_tile_cn(as_tile)}",
                    }
                )
            else:
                code, is_wild, is_sub = _take_physical_for_logical(
                    t, dealer_tile, local_pool, prefer_substitute=True
                )
                is_win = False
                if win_tile and not win_marked and code == win_tile:
                    is_win = True
                    win_marked = True
                label = _tile_cn(code)
                if is_sub:
                    label = f"白(替{_tile_cn(dealer_tile)})"
                out.append(
                    {
                        "code": code,
                        "is_joker": is_wild,
                        "is_restored": False,
                        "is_substitute": is_sub,
                        "is_win_tile": is_win,
                        "substituted_as": t if t != JOKER else dealer_tile,
                        "label": label,
                    }
                )
        else:
            # 无物理池（副露）：按逻辑/原码展示
            if is_joker_slot:
                as_tile = t if t != JOKER else dealer_tile
                out.append(
                    {
                        "code": dealer_tile,
                        "is_joker": True,
                        "is_restored": False,
                        "is_substitute": False,
                        "is_win_tile": False,
                        "substituted_as": as_tile,
                        "label": f"得·代{_tile_cn(as_tile)}",
                    }
                )
            else:
                code = t if t != JOKER else dealer_tile
                is_win = bool(
                    win_tile and not win_marked and code == win_tile
                )
                if is_win:
                    win_marked = True
                out.append(
                    {
                        "code": code,
                        "is_joker": t == JOKER,
                        "is_restored": False,
                        "is_substitute": False,
                        "is_win_tile": is_win,
                        "substituted_as": t if t != JOKER else dealer_tile,
                        "label": _tile_cn(code),
                    }
                )
    return out


_TILE_CN_NUM = {
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}
_TILE_CN_SUIT = {"m": "万", "p": "筒", "s": "条"}
_TILE_CN_HONOR = {
    "E": "东风",
    "S": "南风",
    "W": "西风",
    "N": "北风",
    "C": "中",
    "F": "发",
    "P": "白",
    JOKER: "百搭",
}


def _tile_cn(tile: str) -> str:
    if tile in _TILE_CN_HONOR:
        return _TILE_CN_HONOR[tile]
    if len(tile) == 2 and tile[1] in _TILE_CN_SUIT:
        return f"{_TILE_CN_NUM.get(tile[0], tile[0])}{_TILE_CN_SUIT[tile[1]]}"
    return tile


def calculate_unwon_base_hu(
    hand_tiles: list[str] | None,
    melds: Sequence[Meld] | Sequence[dict[str, Any]] | None,
    seat_wind: str,
    dealer_tile: str,
    *,
    round_wind: str = "E",
) -> dict[str, Any]:
    """未胡者固有底胡 + 字牌/门风/圈风刻杠加番后的结算胡数。

    公式（与和牌者牌型部分一致，不含默认 10 底）：
        calculated_points = total_base_hu × (2 ^ fan_count)

    Returns:
        ``{
          total_base_hu, base_hu, fan_count, calculated_points,
          items, breakdown, hu_details, fan_details, fans, seat_wind
        }``
        items 为可读字符串列表，如 ``'明碰 南风 (+4胡)'``。
    """
    items: list[str] = []
    breakdown: list[dict[str, Any]] = []
    total = 0

    open_melds = [_normalize_meld(m) for m in (melds or [])]
    for m in open_melds:
        scored = _score_open_meld(m, dealer_tile)
        hu = int(scored.get("hu") or 0)
        if hu <= 0 and scored.get("type") == "chi":
            continue
        typ = scored.get("type")
        identity = scored.get("identity") or (
            _logical_tile((scored.get("tiles") or ["?"])[0], dealer_tile)
            if scored.get("tiles")
            else "?"
        )
        label = {
            "pong": "明碰",
            "ming_gang": "明杠",
            "an_gang": "暗杠",
            "chi": "吃",
        }.get(str(typ), str(typ))
        name = _tile_cn(identity) if identity else ""
        if hu > 0:
            text = f"{label} {name} (+{hu}胡)"
            items.append(text)
            breakdown.append(
                {
                    "kind": typ,
                    "source": "open",
                    "tile": identity,
                    "physical_tiles": list(scored["tiles"]),
                    "hu": hu,
                    "label": text,
                }
            )
            total += hu

    # 暗手：确定性质的暗刻 / 役牌雀头（百搭不臆造暗刻）
    logical = preprocess_hand(list(hand_tiles or []), dealer_tile)
    counts: Counter[str] = Counter(
        t for t in logical if t != JOKER
    )
    # 未和固有：手中「得」按本身牌面计入（与白板替身可组成役牌雀头/暗刻）
    joker_n = sum(1 for t in logical if t == JOKER)
    if joker_n:
        counts[dealer_tile] = int(counts.get(dealer_tile, 0)) + joker_n
    for tile, n in sorted(counts.items()):
        remaining = n
        if remaining >= 3:
            hu = (
                ANKO_TERMINAL_HONOR_HU
                if _is_terminal_or_honor(tile)
                else ANKO_SIMPLE_HU
            )
            text = f"暗刻 {_tile_cn(tile)} (+{hu}胡)"
            items.append(text)
            breakdown.append(
                {
                    "kind": "anko",
                    "source": "concealed",
                    "tile": tile,
                    "physical_tiles": (
                        ["P"] * 3 if tile == dealer_tile
                        and list(hand_tiles or []).count("P") >= 3 else []
                    ),
                    "hu": hu,
                    "label": text,
                }
            )
            total += hu
            remaining -= 3
        if remaining >= 2 and (
            tile == seat_wind or tile in DRAGONS
        ):
            hu = (
                PAIR_SEAT_WIND_HU
                if tile == seat_wind
                else PAIR_DRAGON_HU
            )
            note = "自风雀头" if tile == seat_wind else "三元雀头"
            text = f"{note} {_tile_cn(tile)} (+{hu}胡)"
            items.append(text)
            breakdown.append(
                {
                    "kind": "pair",
                    "source": "concealed",
                    "tile": tile,
                    "hu": hu,
                    "label": text,
                }
            )
            total += hu

    fan_count, fans, fan_details = _unwon_yakuhai_fan(
        breakdown=breakdown,
        seat_wind=seat_wind,
        dealer_tile=dealer_tile,
        round_wind=round_wind,
    )
    calculated = int(total) * (2 ** int(fan_count))

    return {
        "total_base_hu": int(total),
        "base_hu": int(total),
        "fan_count": int(fan_count),
        "fan": int(fan_count),
        "calculated_points": int(calculated),
        "items": items,
        "breakdown": breakdown,
        "hu_details": breakdown,
        "fan_details": fan_details,
        "fans": fans,
        "seat_wind": seat_wind,
        "round_wind": round_wind,
    }


def calculate_unwon_player_points(
    player: Mapping[str, Any] | None = None,
    *,
    hand_tiles: list[str] | None = None,
    melds: Sequence[Meld] | Sequence[dict[str, Any]] | None = None,
    seat_wind: str | None = None,
    dealer_tile: str,
    round_wind: str = "E",
) -> dict[str, Any]:
    """未和牌方点数：固有底胡 × 2^字牌/门风/圈风番。

    可直接传入 ``player`` 字典（含 hand_tiles / melds / seat_wind），
    或显式传入手牌与副露。
    """
    if player is not None:
        hand_tiles = list(player.get("hand_tiles") or hand_tiles or [])
        melds = player.get("melds") if melds is None else melds
        seat_wind = str(player.get("seat_wind") or seat_wind or "E")
    seat = seat_wind or "E"
    return calculate_unwon_base_hu(
        hand_tiles=hand_tiles,
        melds=melds,
        seat_wind=seat,
        dealer_tile=dealer_tile,
        round_wind=round_wind,
    )


def _unwon_yakuhai_fan(
    *,
    breakdown: Sequence[Mapping[str, Any]],
    seat_wind: str,
    dealer_tile: str,
    round_wind: str = "E",
) -> tuple[int, dict[str, int], list[dict[str, Any]]]:
    """从固有底胡明细提取三元/门风/圈风刻杠番（雀头不加番）。"""
    fan = 0
    fans: dict[str, int] = {}
    fan_details: list[dict[str, Any]] = []
    dragon_n = 0
    seat_n = 0
    round_n = 0

    for item in breakdown:
        kind = str(item.get("kind") or "")
        if kind not in ("pong", "anko", "ming_gang", "an_gang"):
            continue
        identity = str(item.get("tile") or "")
        if not identity:
            continue
        kind_cn = {
            "pong": "明碰",
            "anko": "暗刻",
            "ming_gang": "明杠",
            "an_gang": "暗杠",
        }.get(kind, kind)

        dragon = _dragon_group_identity(identity, item.get("physical_tiles", []), dealer_tile)
        if dragon:
            dragon_n += 1
            name = _DRAGON_FAN_CN.get(dragon, _tile_cn(dragon))
            label = f"{kind_cn}{name}"
            fan_details.append(
                {
                    "name": label,
                    "kind": "dragon",
                    "tile": dragon,
                    "fan": 1,
                    "multiplier": 2,
                    "label": f"{label} (+1番)",
                }
            )
        if identity == seat_wind:
            seat_n += 1
            wind_cn = _WIND_FAN_CN.get(identity, identity)
            label = f"自风{kind_cn}{wind_cn}"
            fan_details.append(
                {
                    "name": label,
                    "kind": "seat_wind",
                    "tile": identity,
                    "fan": 1,
                    "multiplier": 2,
                    "label": f"{label} (+1番)",
                }
            )
        if identity == round_wind:
            round_n += 1
            wind_cn = _WIND_FAN_CN.get(identity, identity)
            label = f"圈风{kind_cn}{wind_cn}"
            fan_details.append(
                {
                    "name": label,
                    "kind": "round_wind",
                    "tile": identity,
                    "fan": 1,
                    "multiplier": 2,
                    "label": f"{label} (+1番)",
                }
            )

    if dragon_n:
        fans["dragon_pung_kong"] = dragon_n * FAN_DRAGON_PUNG_OR_KONG
        fan += fans["dragon_pung_kong"]
    if seat_n:
        fans["seat_wind_pung_kong"] = seat_n * FAN_SEAT_WIND_PUNG_OR_KONG
        fan += fans["seat_wind_pung_kong"]
    if round_n:
        fans["round_wind_pung_kong"] = round_n * FAN_ROUND_WIND_PUNG_OR_KONG
        fan += fans["round_wind_pung_kong"]

    return fan, fans, fan_details


def _pair_hu(tile: str, seat_wind: str) -> int:
    if tile == JOKER:
        # 纯百搭雀头：无法认定门风/三元，按普通对
        return PAIR_NORMAL_HU
    if tile == seat_wind:
        return PAIR_SEAT_WIND_HU
    if tile in DRAGONS:
        return PAIR_DRAGON_HU
    return PAIR_NORMAL_HU


def _pair_note(
    tile: str,
    seat_wind: str,
    *,
    dealer_tile: str | None = None,
    physical_tiles: Sequence[str] | None = None,
    pair_jokers: int = 0,
    restored_jokers: int = 0,
) -> str:
    phys = list(physical_tiles or [])
    has_sub = bool(
        dealer_tile
        and dealer_tile != "P"
        and tile == dealer_tile
        and "P" in phys
        and (dealer_tile in phys or pair_jokers > 0 or restored_jokers > 0)
    )
    if tile == JOKER:
        return "百搭雀头"
    if tile == seat_wind:
        note = "门风对"
        return f"{note} (白板替身)" if has_sub else note
    if tile in DRAGONS:
        name = _DRAGON_FAN_CN.get(tile, _tile_cn(tile))
        if has_sub:
            return f"{name}对 (白板替身)"
        return "字牌对（中发白）"
    return "普通对子"


def _score_open_meld(meld: dict[str, Any], dealer_tile: str) -> dict[str, Any]:
    """计算一组副露的牌型胡明细。"""
    mtype: str = meld["meld_type"]
    tiles: list[str] = list(meld["tiles"])

    if mtype == MeldType.CHI.value or mtype == "chi":
        return {
            "source": "open",
            "type": "chi",
            "tiles": tiles,
            "claimed_tile": meld.get("claimed_tile"),
            "provider_seat": meld.get("provider_seat"),
            "hu": CHI_HU,
            "identity": None,
        }

    identity = _logical_tile(tiles[0], dealer_tile)
    terminal = _is_terminal_or_honor(identity)

    if mtype in (MeldType.PONG.value, "pong", "peng"):
        hu = PONG_TERMINAL_HONOR_HU if terminal else PONG_SIMPLE_HU
        typ = "pong"
    elif mtype in (MeldType.MING_GANG.value, "ming_gang"):
        hu = (
            MING_GANG_TERMINAL_HONOR_HU if terminal else MING_GANG_SIMPLE_HU
        )
        typ = "ming_gang"
    elif mtype in (MeldType.AN_GANG.value, "an_gang"):
        hu = AN_GANG_TERMINAL_HONOR_HU if terminal else AN_GANG_SIMPLE_HU
        typ = "an_gang"
    else:
        raise ValueError(f"未知副露类型：{mtype!r}")

    return {
        "source": "open",
        "type": typ,
        "tiles": tiles,
        "hu": hu,
        "identity": identity,
    }


def _group_identity(item: dict[str, Any], dealer_tile: str) -> str:
    if item.get("identity"):
        return item["identity"]
    tiles = item.get("tiles") or []
    if not tiles:
        return ""
    return _logical_tile(tiles[0], dealer_tile)


def _is_dragon_yakuhai_identity(identity: str, dealer_tile: str) -> bool:
    """三元役牌身份：中/发恒成立；白板仅当得=白（本身为三元）。

    得≠白时物理白板已映射为得牌面，若得为中/发则 identity 为 C/F，仍计三元。
    """
    if identity in ("C", "F"):
        return True
    return identity == "P" and dealer_tile == "P"


def _dragon_group_identity(
    identity: str, physical_tiles: Sequence[str], dealer_tile: str,
) -> str | None:
    """纯物理中发白刻杠保留三元番；与逻辑三元身份每组只计一次。"""
    if len(physical_tiles) in (3, 4) and len(set(physical_tiles)) == 1:
        physical = physical_tiles[0]
        if physical in DRAGONS:
            return physical
    return identity if _is_dragon_yakuhai_identity(identity, dealer_tile) else None


def _is_kanzhang(shape: _WinShape, win_logical: str) -> bool:
    """嵌档：胡牌张是某组顺子的中间张。"""
    if win_logical == JOKER:
        return False
    if not _is_suited(win_logical):
        return False
    for cm in shape.melds:
        if cm.kind != "chi":
            continue
        ordered = sorted(cm.tiles, key=lambda t: int(t[0]))
        if len(ordered) == 3 and ordered[1] == win_logical:
            return True
    return False


def _flush_fan(tiles: list[str]) -> tuple[int, str]:
    """清一色 +3 / 混一色 +1；字牌清一色不算（无序数花色）。"""
    suits: set[str] = set()
    has_honor = False
    for t in tiles:
        if t == JOKER:
            continue
        if t in WINDS or t in DRAGONS:
            has_honor = True
        elif len(t) == 2 and t[1] in ("m", "p", "s"):
            suits.add(t[1])
        else:
            # 未知编码：不判花色番
            return 0, ""

    if len(suits) == 1 and not has_honor:
        return FAN_FULL_FLUSH, "full_flush"
    if len(suits) == 1 and has_honor:
        return FAN_HALF_FLUSH, "half_flush"
    return 0, ""


def _collect_flush_tiles(
    open_melds: list[dict[str, Any]],
    working_hand: list[str],
    dealer_tile: str,
) -> list[str]:
    """花色判定用的全部逻辑牌（副露已替身映射）。"""
    tiles: list[str] = []
    for m in open_melds:
        for t in m["tiles"]:
            tiles.append(_logical_tile(t, dealer_tile))
    tiles.extend(t for t in working_hand if t != JOKER)
    # 剩余百搭不计入花色（视为可适应）；硬碰硬时已无百搭
    return tiles


# ---------------------------------------------------------------------------
# 和牌拆解
# ---------------------------------------------------------------------------

def _enumerate_win_shapes(
    tiles: list[str], needed_melds: int
) -> list[_WinShape]:
    counts: Counter[str] = Counter()
    jokers = 0
    for t in tiles:
        if t == JOKER:
            jokers += 1
        else:
            counts[t] += 1

    if sum(counts.values()) + jokers != needed_melds * 3 + 2:
        return []

    results: list[_WinShape] = []

    # 即使已有实对，也须考虑实牌留给面子、用百搭组成雀头的路径。
    for tile in ALL_TILES if jokers >= 2 else list(counts.keys()):
        for real in range(max(0, 2 - jokers), min(2, counts[tile]) + 1):
            counts[tile] -= real
            _search_melds(
                counts,
                jokers - (2 - real),
                needed_melds,
                _WinShape(pair_tile=tile, pair_jokers=2 - real),
                results,
            )
            counts[tile] += real

    return results


def _search_melds(
    counts: Counter[str],
    jokers: int,
    melds_left: int,
    shape: _WinShape,
    out: list[_WinShape],
) -> None:
    if melds_left == 0:
        if sum(counts.values()) == 0 and jokers == 0:
            out.append(
                _WinShape(
                    pair_tile=shape.pair_tile,
                    pair_jokers=shape.pair_jokers,
                    melds=list(shape.melds),
                )
            )
        return

    tile = _first_nonzero(counts)
    if tile is None:
        # 实牌耗尽：剩余百搭须正好凑面子
        if jokers == melds_left * 3 and jokers > 0:
            # 纯百搭必须明确身份后计番；同花色幺九刻支配零胡顺子。
            for identity in ALL_TILES:
                shape.melds.append(_ConcealedMeld('anko', [identity] * 3, 3, [identity] * 3))
                _search_melds(counts, jokers - 3, melds_left - 1, shape, out)
                shape.melds.pop()
        return

    have = counts[tile]

    # 暗刻（不足用百搭补）
    for use in range(max(1, 3 - jokers), min(have, 3) + 1):
        need = 3 - use
        counts[tile] -= use
        shape.melds.append(
            _ConcealedMeld(
                kind="anko",
                tiles=[tile, tile, tile],
                jokers_used=need,
                joker_filled=[tile] * need,
            )
        )
        _search_melds(counts, jokers - need, melds_left - 1, shape, out)
        shape.melds.pop()
        counts[tile] += use

    # 顺子
    if _is_suited(tile):
        num, suit = int(tile[0]), tile[1]
        for start in (num, num - 1, num - 2):
            if not 1 <= start <= 7:
                continue
            seq = [f"{start + k}{suit}" for k in range(3)]
            if tile not in seq:
                continue
            # 实牌可留给别组：枚举每一位置用实牌或百搭，而非固定先耗实牌。
            for mask in range(8):
                taken = [t for i, t in enumerate(seq) if mask & (1 << i)]
                missing = [t for i, t in enumerate(seq) if not mask & (1 << i)]
                need = len(missing)
                if tile not in taken or need > jokers or any(counts[t] <= 0 for t in taken):
                    continue
                for t in taken:
                    counts[t] -= 1
                shape.melds.append(
                    _ConcealedMeld(
                        kind="chi",
                        tiles=seq,
                        jokers_used=need,
                        joker_filled=missing,
                    )
                )
                _search_melds(
                    counts, jokers - need, melds_left - 1, shape, out
                )
                shape.melds.pop()
                for t in taken:
                    counts[t] += 1


def _first_nonzero(counts: Counter[str]) -> str | None:
    for t in ALL_TILES:
        if counts[t] > 0:
            return t
    return None


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _normalize_meld(meld: Meld | dict[str, Any]) -> dict[str, Any]:
    if isinstance(meld, Meld):
        return {**meld.model_dump(), "meld_type": meld.meld_type.value, "tiles": list(meld.tiles)}
    if isinstance(meld, dict):
        mtype = meld.get("meld_type") or meld.get("type")
        if isinstance(mtype, MeldType):
            mtype = mtype.value
        tiles = meld.get("tiles")
        if mtype is None or tiles is None:
            raise ValueError(f"副露缺少 meld_type/tiles：{meld!r}")
        # 兼容中文/别名
        alias = {
            "peng": "pong",
            "碰": "pong",
            "吃": "chi",
            "明杠": "ming_gang",
            "暗杠": "an_gang",
        }
        mtype = alias.get(str(mtype), str(mtype))
        return {**meld, "meld_type": mtype, "tiles": list(tiles)}
    raise TypeError(f"不支持的副露类型：{type(meld)!r}")


def _validate_counts(
    hand_tiles: list[str],
    open_melds: list[dict[str, Any]],
    win_tile: str,
) -> None:
    if not win_tile:
        raise ValueError("win_tile 不能为空")
    # 杠占 1 面子位：门清张数 + 胡牌 = needed*3+2
    needed = 4 - len(open_melds)
    expect = needed * 3 + 1  # 未计入 win_tile 前的听牌张数
    if len(hand_tiles) != expect:
        raise ValueError(
            f"手牌张数应为 {expect}（副露 {len(open_melds)} 组时），"
            f"当前 {len(hand_tiles)}"
        )


def _logical_tile(tile: str, dealer_tile: str) -> str:
    """副露/单张的计分身份：得≠白 时白板继承得的花色点数。"""
    if tile == JOKER:
        return JOKER
    if dealer_tile == "P":
        return tile
    if tile == "P":
        return dealer_tile
    return tile


def _is_terminal_or_honor(tile: str) -> bool:
    if tile == JOKER:
        # 纯百搭刻：身份不明，按中张处理
        return False
    if tile in WINDS or tile in DRAGONS:
        return True
    if len(tile) == 2 and tile[1] in ("m", "p", "s"):
        return tile[0] in ("1", "9")
    raise ValueError(f"无法识别的牌面编码：{tile!r}")


def _is_suited(tile: str) -> bool:
    return len(tile) == 2 and tile[1] in ("m", "p", "s") and tile[0].isdigit()
