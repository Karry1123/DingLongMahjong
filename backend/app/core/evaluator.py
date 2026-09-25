"""向听数 / 和牌判定（支持副露后的 needed_melds）。

严格遵循 rule.md §4.1 基本和牌型：
    全手 14 张 = 4 × 面子 + 1 × 雀头
若已有公开副露 ``open_melds`` 组，则门清部分只需：
    needed_melds (= 4 - open_melds) × 面子 + 1 × 雀头

不含七对、国士等特殊牌型（文档未定义，禁止臆造）。
百搭 ``JOKER`` 可替代任意序数牌或字牌（rule.md §2）。

算法：递归回溯拆解面子 / 搭子 / 雀头；``needed_melds`` 约束面子上限，
避免副露后仍按 4 面子搜索导致死循环或错误剪枝。
带「得」时对 ``(牌计数, 百搭数, needed_melds)`` 做 LRU 记忆化，
雀头枚举仅扫描手中实牌（禁止对空牌种空转 34 次）。
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Sequence

from .constants import ALL_TILES, JOKER


def check_win_or_shanten(
    tiles: list[str],
    joker_count: int = 0,
    needed_melds: int = 4,
) -> int:
    """计算门清手牌距离听牌的向听数。

    Args:
        tiles: 预处理后的**门清**手牌，可含 ``"JOKER"``。
        joker_count: 额外百搭数（tiles 已含 JOKER 时通常传 0）。
        needed_melds: 门清还需凑齐的面子数，取值 ``0..4``，
            等于 ``4 - len(melds)``（已副露组数）。

    Returns:
        - ``-1``：已和牌（needed_melds 个面子 + 1 雀头）
        - ``0``：听牌
        - ``> 0``：向听数
    """
    if not 0 <= needed_melds <= 4:
        raise ValueError(f"needed_melds 须在 0..4，当前为 {needed_melds}")

    counts: Counter[str] = Counter()
    jokers = joker_count
    for tile in tiles:
        if tile == JOKER:
            jokers += 1
        else:
            counts[tile] += 1

    total = sum(counts.values()) + jokers
    # 和牌时门清张数：面子×3 + 雀头×2
    win_size = needed_melds * 3 + 2

    if total == win_size:
        if _can_win(counts, jokers, needed_melds):
            return -1
        # 多一张待切：枚举切牌后的最小向听
        return _min_shanten_after_discard(counts, jokers, needed_melds)

    return _standard_shanten(counts, jokers, needed_melds)


def is_complete_win(
    tiles: list[str],
    joker_count: int = 0,
    needed_melds: int = 4,
) -> bool:
    """仅判定是否已和（needed_melds 面子 + 雀头），不做向听穷举。

    供进张扫描：听牌手摸入后只问「能否胡」，避免 14 张未和时
    掉进 ``_min_shanten_after_discard`` 的切牌全枚举。
    """
    if not 0 <= needed_melds <= 4:
        raise ValueError(f"needed_melds 须在 0..4，当前为 {needed_melds}")
    counts: Counter[str] = Counter()
    jokers = joker_count
    for tile in tiles:
        if tile == JOKER:
            jokers += 1
        else:
            counts[tile] += 1
    win_size = needed_melds * 3 + 2
    if sum(counts.values()) + jokers != win_size:
        return False
    return _can_win(counts, jokers, needed_melds)


def clear_shanten_cache() -> None:
    """测试 / 热更新时可清空向听记忆化。"""
    _standard_shanten_cached.cache_clear()
    _can_win_cached.cache_clear()
    _optimistic_remaining_shanten.cache_clear()


def _counts_key(counts: Counter[str]) -> tuple[tuple[str, int], ...]:
    """稳定缓存键：仅正计数，排序后元组（与百搭数字段分离存储）。"""
    return tuple(sorted((t, int(n)) for t, n in counts.items() if n > 0))


# ===========================================================================
# 和牌判定：needed_melds 面子 + 1 雀头
# ===========================================================================

def _can_win(counts: Counter[str], jokers: int, needed_melds: int) -> bool:
    """门清部分能否组成 needed_melds 面子 + 1 雀头。"""
    if sum(counts.values()) + jokers != needed_melds * 3 + 2:
        return False
    return _can_win_cached(_counts_key(counts), jokers, needed_melds)


@lru_cache(maxsize=262144)
def _can_win_cached(
    key: tuple[tuple[str, int], ...], jokers: int, needed_melds: int
) -> bool:
    counts = Counter(dict(key))
    # 仅枚举手中实牌作雀头（含百搭补对）；禁止扫全副 34 空位
    for tile, n in list(counts.items()):
        if n >= 2:
            counts[tile] -= 2
            ok = _can_form_n_melds(counts, jokers, needed_melds)
            counts[tile] += 2
            if ok:
                return True
        elif n == 1 and jokers >= 1:
            counts[tile] -= 1
            ok = _can_form_n_melds(counts, jokers - 1, needed_melds)
            counts[tile] += 1
            if ok:
                return True

    if jokers >= 2 and _can_form_n_melds(counts, jokers - 2, needed_melds):
        return True
    return False


def _can_form_n_melds(
    counts: Counter[str], jokers: int, melds_left: int
) -> bool:
    """雀头已摘除后，剩余牌能否恰好拆成 melds_left 个面子。"""
    if melds_left < 0:
        return False

    tile = _first_nonzero(counts)
    if tile is None:
        # 实牌耗尽：剩余百搭须刚好凑 melds_left 个面子（各 3 张）
        return jokers == melds_left * 3

    if melds_left == 0:
        # 还需要 0 个面子，但还有实牌 → 失败
        return False

    have = counts[tile]

    # 分支 A：刻子（不足用百搭补）
    if have + jokers >= 3:
        use = min(have, 3)
        need = 3 - use
        counts[tile] -= use
        if _can_form_n_melds(counts, jokers - need, melds_left - 1):
            counts[tile] += use
            return True
        counts[tile] += use

    # 分支 B：顺子 —— 百搭仅补当前顺子缺口，不另起无邻接空顺
    if _is_suited(tile) and _win_try_sequences(
        counts, jokers, tile, melds_left
    ):
        return True

    return False


def _win_try_sequences(
    counts: Counter[str],
    jokers: int,
    tile: str,
    melds_left: int,
) -> bool:
    """以当前张为成员，回溯尝试覆盖它的顺子。"""
    num, suit = int(tile[0]), tile[1]

    for start in (num, num - 1, num - 2):
        if not 1 <= start <= 7:
            continue
        seq = [f"{start + k}{suit}" for k in range(3)]
        if tile not in seq:
            continue

        need = 0
        taken: list[str] = []
        for t in seq:
            if counts[t] > 0:
                counts[t] -= 1
                taken.append(t)
            else:
                need += 1

        # 至少保留 1 张实牌锚定，禁止纯百搭空想顺子
        if not taken:
            continue

        if need <= jokers and _can_form_n_melds(
            counts, jokers - need, melds_left - 1
        ):
            for t in taken:
                counts[t] += 1
            return True
        for t in taken:
            counts[t] += 1

    return False


# ===========================================================================
# 向听数（目标：needed_melds 面子 + 1 雀头）
# ===========================================================================

def _min_shanten_after_discard(
    counts: Counter[str], jokers: int, needed_melds: int
) -> int:
    """待切状态（多一张）未和：枚举切牌，取最小向听。"""
    best = _shanten_ceiling(needed_melds)
    for tile in list(counts.keys()):
        if counts[tile] <= 0:
            continue
        counts[tile] -= 1
        best = min(best, _standard_shanten(counts, jokers, needed_melds))
        counts[tile] += 1
        if best <= 0:
            break
    if jokers > 0 and best > 0:
        best = min(best, _standard_shanten(counts, jokers - 1, needed_melds))
    return best


def _standard_shanten(
    counts: Counter[str], jokers: int, needed_melds: int
) -> int:
    """一般形向听搜索入口（带 LRU）。"""
    return _standard_shanten_cached(_counts_key(counts), jokers, needed_melds)


@lru_cache(maxsize=262144)
def _standard_shanten_cached(
    key: tuple[tuple[str, int], ...], jokers: int, needed_melds: int
) -> int:
    counts = Counter(dict(key))
    ceiling = _shanten_ceiling(needed_melds)
    best = [ceiling]

    # 无雀头
    _dfs_shanten(
        Counter(counts), jokers, 0, 0, False, needed_melds, best
    )

    # 枚举雀头：仅手中实牌；百搭优先补对/雀头，不扫空牌种
    if best[0] > -1:
        for tile, n in list(counts.items()):
            if n >= 2:
                counts[tile] -= 2
                _dfs_shanten(
                    Counter(counts), jokers, 0, 0, True, needed_melds, best
                )
                counts[tile] += 2
            elif n == 1 and jokers >= 1:
                counts[tile] -= 1
                _dfs_shanten(
                    Counter(counts),
                    jokers - 1,
                    0,
                    0,
                    True,
                    needed_melds,
                    best,
                )
                counts[tile] += 1
            if best[0] <= 0:
                break

    if jokers >= 2 and best[0] > 0:
        _dfs_shanten(
            Counter(counts), jokers - 2, 0, 0, True, needed_melds, best
        )

    return best[0]


def _dfs_shanten(
    counts: Counter[str],
    jokers: int,
    mentsu: int,
    taatsu: int,
    has_head: bool,
    needed_melds: int,
    best: list[int],
) -> None:
    """按固定牌序处理首张；面子/搭子上限为 needed_melds。"""
    # 乐观剪枝：必须计入「已有搭子/雀头」，并允许剩余牌拆成搭子（不可只按 remain//3 面子估）
    remain = sum(counts.values()) + jokers
    opt = _optimistic_remaining_shanten(
        mentsu, taatsu, has_head, remain, needed_melds
    )
    if opt >= best[0]:
        return

    tile = _first_nonzero(counts)
    if tile is None:
        best[0] = min(
            best[0],
            _best_with_spare_jokers(
                mentsu, taatsu, has_head, jokers, needed_melds
            ),
        )
        return

    have = counts[tile]
    can_meld = mentsu < needed_melds
    can_taatsu = mentsu + taatsu < needed_melds

    # —— 1. 刻子 ——
    if can_meld and have + jokers >= 3:
        use = min(have, 3)
        need = 3 - use
        counts[tile] -= use
        _dfs_shanten(
            counts,
            jokers - need,
            mentsu + 1,
            taatsu,
            has_head,
            needed_melds,
            best,
        )
        counts[tile] += use

    # —— 2. 顺子（须有实牌锚点；百搭只补缺口）——
    if can_meld and _is_suited(tile):
        _shanten_sequences(
            counts, jokers, mentsu, taatsu, has_head, needed_melds, best, tile
        )

    # —— 3. 对子搭子 ——
    if can_taatsu and have + jokers >= 2:
        use = min(have, 2)
        need = 2 - use
        counts[tile] -= use
        _dfs_shanten(
            counts,
            jokers - need,
            mentsu,
            taatsu + 1,
            has_head,
            needed_melds,
            best,
        )
        counts[tile] += use

    # —— 4. 两面 / 边张 / 嵌张 ——
    if can_taatsu and _is_suited(tile):
        _shanten_taatsu(
            counts, jokers, mentsu, taatsu, has_head, needed_melds, best, tile
        )

    # —— 5. 孤张：本种牌一次清零推进（防止逐张死循环）——
    n = counts[tile]
    counts[tile] = 0
    _dfs_shanten(
        counts, jokers, mentsu, taatsu, has_head, needed_melds, best
    )
    counts[tile] = n


@lru_cache(maxsize=4096)
def _optimistic_remaining_shanten(
    mentsu: int,
    taatsu: int,
    has_head: bool,
    remain: int,
    needed_melds: int,
) -> int:
    """剩余牌的最乐观向听下界（剪枝用）。

    旧实现只用 ``mentsu + remain//3`` 且把 taatsu 置 0，会在
    「已有搭子、剩余不足 3 张」时把乐观值抬回天花板，导致整枝被剪光、
    向听恒为 ``2N``（副露后碰牌 EV 崩坏的根因）。
    """
    best = 99
    head_opts = (0, 1) if not has_head else (0,)
    for head_add in head_opts:
        if head_add and remain < 2:
            continue
        pool = remain - 2 * head_add
        h = has_head or bool(head_add)
        slots = needed_melds - mentsu
        if slots < 0:
            continue
        max_dm = min(slots, pool // 3) if slots > 0 else 0
        for dm in range(max_dm + 1):
            pool2 = pool - 3 * dm
            max_dt = min(needed_melds - mentsu - dm - taatsu, pool2 // 2)
            if max_dt < 0:
                continue
            # 取最大搭子增量 → 最低向听
            best = min(
                best,
                _formula(mentsu + dm, taatsu + max_dt, h, needed_melds),
            )
    return best if best < 99 else _shanten_ceiling(needed_melds)


@lru_cache(maxsize=27)
def _sequences_containing(tile: str) -> tuple[tuple[str, ...], ...]:
    """只缓存固定牌型，不缓存任何牌局信息。"""
    num, suit = int(tile[0]), tile[1]
    return tuple(
        tuple(f"{start + k}{suit}" for k in range(3))
        for start in (num, num - 1, num - 2) if 1 <= start <= 7
    )


def _shanten_sequences(
    counts: Counter[str],
    jokers: int,
    mentsu: int,
    taatsu: int,
    has_head: bool,
    needed_melds: int,
    best: list[int],
    tile: str,
) -> None:
    for seq in _sequences_containing(tile):
        need = 0
        taken: list[str] = []
        for t in seq:
            if counts[t] > 0:
                counts[t] -= 1
                taken.append(t)
            else:
                need += 1

        # 至少 1 张实牌锚定，禁止纯百搭空想顺子
        if taken and need <= jokers:
            _dfs_shanten(
                counts,
                jokers - need,
                mentsu + 1,
                taatsu,
                has_head,
                needed_melds,
                best,
            )
        for t in taken:
            counts[t] += 1


def _shanten_taatsu(
    counts: Counter[str],
    jokers: int,
    mentsu: int,
    taatsu: int,
    has_head: bool,
    needed_melds: int,
    best: list[int],
    tile: str,
) -> None:
    num, suit = int(tile[0]), tile[1]
    partners: list[str] = []
    if num + 1 <= 9:
        partners.append(f"{num + 1}{suit}")
    if num + 2 <= 9:
        partners.append(f"{num + 2}{suit}")

    for other in partners:
        if counts[tile] <= 0:
            continue
        if counts[other] > 0:
            counts[tile] -= 1
            counts[other] -= 1
            _dfs_shanten(
                counts,
                jokers,
                mentsu,
                taatsu + 1,
                has_head,
                needed_melds,
                best,
            )
            counts[tile] += 1
            counts[other] += 1
        elif jokers >= 1:
            counts[tile] -= 1
            _dfs_shanten(
                counts,
                jokers - 1,
                mentsu,
                taatsu + 1,
                has_head,
                needed_melds,
                best,
            )
            counts[tile] += 1


def _best_with_spare_jokers(
    mentsu: int,
    taatsu: int,
    has_head: bool,
    jokers: int,
    needed_melds: int,
) -> int:
    """实牌拆完后，枚举剩余百搭转为面子 / 搭子 / 雀头。"""
    best = _formula(mentsu, taatsu, has_head, needed_melds)
    head_options = (0, 1) if not has_head else (0,)

    for use_head in head_options:
        j1 = jokers - 2 * use_head
        if j1 < 0:
            continue
        h = has_head or bool(use_head)
        max_dm = min(needed_melds - mentsu, j1 // 3)
        if max_dm < 0:
            continue
        for dm in range(max_dm + 1):
            j2 = j1 - 3 * dm
            max_dt = min(needed_melds - mentsu - dm - taatsu, j2 // 2)
            if max_dt < 0:
                continue
            for dt in range(max_dt + 1):
                best = min(
                    best, _formula(mentsu + dm, taatsu + dt, h, needed_melds)
                )
    return best


def _shanten_ceiling(needed_melds: int) -> int:
    """向听上界：2 × needed_melds（无面子无雀头时的基准）。"""
    return 2 * needed_melds


def _formula(
    mentsu: int, taatsu: int, has_head: bool, needed_melds: int
) -> int:
    """一般形向听：``2N - 2×面子 - 搭子 - 雀头``，面子+搭子 ≤ N。"""
    n = needed_melds
    mentsu = min(mentsu, n)
    if mentsu + taatsu > n:
        taatsu = n - mentsu
    return _shanten_ceiling(n) - 2 * mentsu - taatsu - (1 if has_head else 0)


# ===========================================================================
# 工具
# ===========================================================================

def _first_nonzero(counts: Counter[str]) -> str | None:
    # 固定全副顺序，保证拆解确定性；仅检查计数>0 的键更快
    present = {t for t, n in counts.items() if n > 0}
    if not present:
        return None
    for tile in ALL_TILES:
        if tile in present:
            return tile
    return None


def _is_suited(tile: str) -> bool:
    return len(tile) == 2 and tile[1] in ("m", "p", "s")


# ===========================================================================
# 自摸 / 捉铳和牌检测 + 结算挂载
# ===========================================================================

def check_self_drawn_win(
    hand_tiles: list[str],
    melds: list | Sequence | None,
    dealer_tile: str,
    seat_wind: str,
    round_wind: str = "E",
    is_dealer: bool = False,
    *,
    win_tile: str | None = None,
    players: Sequence | None = None,
) -> dict | None:
    """检测待切满手（含刚摸入张）是否已可自摸和牌。

    Args:
        hand_tiles: 暗手全量（含自摸进张），张数 = ``14 - 3*len(melds)``。
        melds: 已副露。
        dealer_tile: 本局「得」。
        seat_wind / round_wind: 门风 / 场风（场风预留）。
        is_dealer: 是否庄家。
        win_tile: 优先视为胡张的物理牌（通常为刚摸入）。
        players: 可选四家公开状态；传入则挂载完整 §6 结算矩阵。

    Returns:
        和牌时返回明细字典；未和则 ``None``。
    """
    return _check_complete_win(
        hand_tiles=list(hand_tiles),
        melds=list(melds or []),
        dealer_tile=dealer_tile,
        seat_wind=seat_wind,
        is_dealer=is_dealer,
        is_zimo=True,
        win_tile=win_tile,
        win_tile_required=False,
        players=players,
        round_wind=round_wind,
    )


def check_ron_win(
    hand_tiles: list[str],
    melds: list | Sequence | None,
    discarded_tile: str,
    dealer_tile: str,
    seat_wind: str,
    round_wind: str = "E",
    is_dealer: bool = False,
    *,
    players: Sequence | None = None,
    discarder_seat: str | None = None,
) -> dict | None:
    """检测门清听牌手是否可对 ``discarded_tile`` 捉铳。

    Args:
        hand_tiles: 响应方门清（未含铳张），张数 = ``13 - 3*len(melds)``。
        discarded_tile: 出枪张（胡张）。
        discarder_seat: 出枪方（结算记录用）。
    """
    return _check_complete_win(
        hand_tiles=list(hand_tiles),
        melds=list(melds or []),
        dealer_tile=dealer_tile,
        seat_wind=seat_wind,
        is_dealer=is_dealer,
        is_zimo=False,
        win_tile=discarded_tile,
        win_tile_required=True,
        players=players,
        round_wind=round_wind,
        discarder_seat=discarder_seat,
    )


def _check_complete_win(
    *,
    hand_tiles: list[str],
    melds: list,
    dealer_tile: str,
    seat_wind: str,
    is_dealer: bool,
    is_zimo: bool,
    win_tile: str | None,
    win_tile_required: bool,
    players: Sequence | None,
    round_wind: str,
    discarder_seat: str | None = None,
) -> dict | None:
    from typing import Any

    from .mapper import normalize_hand_for_eval
    from .scoring import DEFAULT_BASE_HU, MAX_PAYMENT_PER_PLAYER, calculate_hu_points
    from .settlement import calculate_final_settlement

    meld_list: list = list(melds or [])
    needed = 4 - len(meld_list)
    if not 0 <= needed <= 4:
        return None

    if is_zimo:
        expect = needed * 3 + 2
        if len(hand_tiles) != expect:
            return None
        logical = normalize_hand_for_eval(list(hand_tiles), dealer_tile)
        if check_win_or_shanten(logical, 0, needed_melds=needed) != -1:
            return None
        # The physical draw is fixed once supplied. Reinterpreting another tile
        # as the winning tile can change the scored shape and hide a joker draw.
        if win_tile:
            if win_tile not in hand_tiles:
                return None
            candidates = [win_tile]
        else:
            candidates = list(dict.fromkeys(hand_tiles))
    else:
        expect = needed * 3 + 1
        if len(hand_tiles) != expect:
            return None
        if not win_tile:
            return None
        # 听牌手 + 铳张须能和（白板替身经 normalize_hand_for_eval）
        trial = list(hand_tiles) + [win_tile]
        logical = normalize_hand_for_eval(trial, dealer_tile)
        if check_win_or_shanten(logical, 0, needed_melds=needed) != -1:
            return None
        candidates = [win_tile]

    if win_tile_required and not candidates:
        return None

    best: dict[str, Any] | None = None
    best_win: str | None = None
    best_restored = 0
    best_remain: list[str] | None = None

    for wt in candidates:
        if is_zimo:
            remain = list(hand_tiles)
            try:
                remain.remove(wt)
            except ValueError:
                continue
            trial_logical = normalize_hand_for_eval(remain + [wt], dealer_tile)
            if check_win_or_shanten(trial_logical, 0, needed_melds=needed) != -1:
                continue
            joker_src = trial_logical
        else:
            remain = list(hand_tiles)
            trial_logical = normalize_hand_for_eval(remain + [wt], dealer_tile)
            if check_win_or_shanten(trial_logical, 0, needed_melds=needed) != -1:
                continue
            joker_src = trial_logical

        max_restore = sum(1 for t in joker_src if t == JOKER)
        for restored in range(0, max_restore + 1):
            try:
                hu = calculate_hu_points(
                    melds=meld_list,
                    hand_tiles=remain,
                    win_tile=wt,
                    is_zimo=is_zimo,
                    seat_wind=seat_wind,
                    dealer_tile=dealer_tile,
                    base_hu=DEFAULT_BASE_HU,
                    restored_jokers=restored,
                    round_wind=round_wind,
                )
            except ValueError:
                continue
            if best is None or hu["final_hu"] > best["final_hu"]:
                best = hu
                best_win = wt
                best_restored = restored
                best_remain = list(remain)

    if best is None or best_win is None or best_remain is None:
        return None

    points = int(best["final_hu"])
    factor = 3.0 if is_dealer else 2.0
    if is_dealer:
        payments = {
            "from_each_xian": min(points, MAX_PAYMENT_PER_PLAYER),
            "from_dealer": 0,
            "winner_income": min(points, MAX_PAYMENT_PER_PLAYER) * 3,
            "label": "庄家和牌：三家各付全额",
        }
    else:
        payments = {
            "from_each_xian": min(points / 2, MAX_PAYMENT_PER_PLAYER),
            "from_dealer": min(points, MAX_PAYMENT_PER_PLAYER),
            "winner_income": min(points, MAX_PAYMENT_PER_PLAYER) + 2 * min(points / 2, MAX_PAYMENT_PER_PLAYER),
            "label": "闲家和牌：庄付全额、两闲各付半额",
        }

    _ = round_wind  # already forwarded into calculate_hu_points
    result: dict[str, Any] = {
        "is_win": True,
        "is_zimo": bool(is_zimo),
        "win_type": "zimo" if is_zimo else "ron",
        "action_type": "self_draw_win" if is_zimo else "catch_win",
        "is_hard_hu": bool(best["is_hard_hu"]),
        "win_tile": best_win,
        "restored_jokers": best_restored,
        "tile_hu": int(best["tile_hu"]),
        "base_hu": int(best["base_hu"]),
        "fan": int(best["fan"]),
        "final_hu": points,
        "final_points": points,
        "details": best.get("details") or {},
        "others_hu": best.get("others_hu"),
        "settlement_factor": factor,
        "settlement_income": float(payments["winner_income"]),
        "payments": payments,
        "hard_hu_label": "硬胡" if best["is_hard_hu"] else "软胡",
        "seat_wind": seat_wind,
        "is_dealer": bool(is_dealer),
        "wrap_penalty": False,
    }

    if players is not None:
        settlement = calculate_final_settlement(
            winner_seat=seat_wind,
            win_type="zimo" if is_zimo else "ron",
            dealer_tile=dealer_tile,
            players=players,
            points=points,
            hand_tiles=best_remain,
            melds=meld_list,
            win_tile=best_win,
            seat_wind=seat_wind,
            is_dealer=is_dealer,
            discarder_seat=discarder_seat,
            wrap_penalty=False,
            restored_jokers=best_restored,
            round_wind=round_wind,
        )
        result["settlement"] = settlement
        result["payments"] = settlement["payments"]
        result["net_by_seat"] = settlement["net_by_seat"]
        result["transfers"] = settlement["transfers"]

    return result
