"""出牌后合法动作检测（rule.md §3 / §7）。

响应方在他人打出 ``discarded_tile`` 后可宣布的动作：
吃（仅上家）/ 碰 / 明杠 / 胡 / 过。

关键约束：
- 吃牌不得跨家；顺子中不得用「得」作百搭（白板替身可用）。
- 明杠不得用「得」充第 4 张。
- 点炮：门清+副露凑齐 4 面子 + 1 雀头则生成 HU。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from app.schemas import Meld

from .constants import JOKER, WINDS
from .evaluator import check_win_or_shanten
from .mapper import normalize_hand_for_eval

# 逆时针：东 → 南 → 西 → 北（与前端 WIND_ORDER 一致）
_SEAT_ORDER = list(WINDS)  # E S W N


class ActionType(str, Enum):
    """出牌后可响应的动作类型；另含自家暗杠/补杠。"""

    CHI = "chi"
    PONG = "pong"
    MING_GANG = "ming_gang"
    AN_GANG = "an_gang"
    BU_GANG = "bu_gang"
    KONG_ADD = "bu_gang"  # 补杠的语义别名；接口保留既有 bu_gang 编码
    DISCARD = "discard"
    HU = "hu"
    CATCH_WIN = "catch_win"
    SELF_DRAW_WIN = "self_draw_win"
    PASS = "pass"


@dataclass(frozen=True)
class Action:
    """单个合法响应动作。"""

    action_type: ActionType
    tiles: list[str] = field(default_factory=list)
    provider_seat: str = ""

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "tiles": list(self.tiles),
            "provider_seat": self.provider_seat,
        }


def get_available_actions(
    hand_tiles: list[str],
    melds: list[Meld] | Sequence[Meld],
    discarded_tile: str,
    provider_seat: str,
    player_seat: str,
    dealer_tile: str,
) -> list[Action]:
    """检测响应对 ``discarded_tile`` 的全部合法动作（含 PASS）。

    Args:
        hand_tiles: 响应方门清手牌（物理编码）。
        melds: 响应方已副露。
        discarded_tile: 刚打出的物理牌。
        provider_seat: 出牌方门风 E/S/W/N。
        player_seat: 响应方门风。
        dealer_tile: 本局财神（得）。

    Returns:
        合法 ``Action`` 列表；**始终包含** PASS。
    """
    if provider_seat not in WINDS or player_seat not in WINDS:
        raise ValueError(
            f"座位非法：provider={provider_seat!r}, player={player_seat!r}"
        )
    if provider_seat == player_seat:
        raise ValueError("不能响应自己的出牌")

    meld_list = list(melds or [])
    actions: list[Action] = []

    # —— 吃：仅上家 ——
    # 冗余完整顺子吃仍生成（手动可点），推荐层 call_decision 施加重罚
    kamicha = _kamicha_seat(player_seat)
    if provider_seat == kamicha:
        for combo in _chi_combos(hand_tiles, discarded_tile, dealer_tile):
            actions.append(
                Action(
                    action_type=ActionType.CHI,
                    tiles=combo,
                    provider_seat=provider_seat,
                )
            )
    # 跨家：故意不生成 CHI（§3.2 / §7）

    # —— 碰 / 明杠：全场可响应 ——
    match_n = _count_claim_matches(hand_tiles, discarded_tile, dealer_tile)
    if match_n >= 2:
        pung_tiles = _pick_claim_tiles(
            hand_tiles, discarded_tile, dealer_tile, 2
        ) + [discarded_tile]
        actions.append(
            Action(
                action_type=ActionType.PONG,
                tiles=sorted(pung_tiles),
                provider_seat=provider_seat,
            )
        )
    if match_n >= 3:
        # 明杠：必须 3 张真实匹配，禁止用「得」补第 4 张（§7）
        if _can_ming_gang_without_joker(
            hand_tiles, discarded_tile, dealer_tile
        ):
            gang_tiles = _pick_claim_tiles(
                hand_tiles, discarded_tile, dealer_tile, 3
            ) + [discarded_tile]
            actions.append(
                Action(
                    action_type=ActionType.MING_GANG,
                    tiles=sorted(gang_tiles),
                    provider_seat=provider_seat,
                )
            )

    # —— 点炮胡（捉铳；ActionType.HU，前端可显示为 catch_win）——
    if _can_ron(hand_tiles, meld_list, discarded_tile, dealer_tile):
        actions.append(
            Action(
                action_type=ActionType.HU,
                tiles=[discarded_tile],
                provider_seat=provider_seat,
            )
        )

    # —— 过：始终可选 ——
    actions.append(
        Action(
            action_type=ActionType.PASS,
            tiles=[],
            provider_seat=provider_seat,
        )
    )
    return actions


# ---------------------------------------------------------------------------
# 座位
# ---------------------------------------------------------------------------

def _kamicha_seat(player_seat: str) -> str:
    """响应方的上家（逆时针上一手）。"""
    i = _SEAT_ORDER.index(player_seat)
    return _SEAT_ORDER[(i + 3) % 4]


def assert_chi_provider_is_kamicha(provider_seat: str, player_seat: str) -> None:
    """§7 吃牌方位断言：出牌方必须是响应方上家。"""
    assert provider_seat == _kamicha_seat(player_seat), (
        f"跨家吃牌非法：provider={provider_seat}, "
        f"player={player_seat}, 上家应为 {_kamicha_seat(player_seat)}"
    )


# ---------------------------------------------------------------------------
# 牌面身份（吃/碰用；得不作百搭）
# ---------------------------------------------------------------------------

def _is_joker_physical(tile: str, dealer_tile: str) -> bool:
    """该物理牌是否为「得」百搭（不可用于吃顺 / 不可充杠）。"""
    if dealer_tile == "P":
        return tile == "P"
    return tile == dealer_tile


def _face_for_sequence(tile: str, dealer_tile: str) -> str:
    """顺子/碰比对用的逻辑花色点数：白板替身继承得；得本身不在此当作万能。"""
    if dealer_tile != "P" and tile == "P":
        return dealer_tile
    return tile


def _is_suited(tile: str) -> bool:
    return len(tile) == 2 and tile[1] in ("m", "p", "s") and tile[0].isdigit()


# ---------------------------------------------------------------------------
# 吃
# ---------------------------------------------------------------------------

def _chi_combos(
    hand_tiles: list[str], discarded_tile: str, dealer_tile: str
) -> list[list[str]]:
    """返回所有合法吃牌组合（各含打出张，共 3 张物理编码）。"""
    disc_face = _face_for_sequence(discarded_tile, dealer_tile)
    if not _is_suited(disc_face):
        return []

    # 手牌可用张：排除「得」百搭
    usable: list[str] = [
        t for t in hand_tiles if not _is_joker_physical(t, dealer_tile)
    ]

    n = int(disc_face[0])
    suit = disc_face[1]
    results: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    for start in range(1, 8):
        seq_faces = [f"{start + k}{suit}" for k in range(3)]
        if disc_face not in seq_faces:
            continue
        need_faces = [f for f in seq_faces if f != disc_face]
        # 若打出张在顺子中只出现一次，还需两张
        if seq_faces.count(disc_face) != 1:
            continue

        picked = _take_faces_from_hand(usable, need_faces, dealer_tile)
        if picked is None:
            continue
        # 按逻辑顺序排列，但保留白板物理编码供扣牌和展示。
        combo = sorted(picked + [discarded_tile], key=lambda t: _face_for_sequence(t, dealer_tile))
        key = tuple(combo)
        if key not in seen:
            seen.add(key)
            results.append(combo)

    return results


def is_redundant_complete_sequence_chi(
    hand_tiles: list[str],
    discarded_tile: str,
    chi_tiles: list[str],
    dealer_tile: str,
) -> bool:
    """手里已有完整同面顺子时，再吃同面顺视为冗余（供 call_decision 降权）。

    例：手持 5s6s7s，上家切 5s → 吃 567s 只是暗顺搬明顺。
    """
    return _is_pure_redundant_chi(
        hand_tiles, discarded_tile, chi_tiles, dealer_tile
    )


def _is_pure_redundant_chi(
    hand_tiles: list[str],
    discarded_tile: str,
    chi_tiles: list[str],
    dealer_tile: str,
) -> bool:
    """手里已有完整同面顺子，且吃牌目标三连已在手中各 ≥1。"""
    disc_face = _face_for_sequence(discarded_tile, dealer_tile)
    if not _is_suited(disc_face):
        return False
    faces = [_face_for_sequence(t, dealer_tile) for t in chi_tiles]
    if disc_face not in faces:
        faces = list(faces) + [disc_face]
    suited = [f for f in faces if _is_suited(f)]
    suit = disc_face[1]
    digits = sorted(
        {
            int(f[0])
            for f in suited
            if len(f) == 2 and f[1] == suit and f[0].isdigit()
        }
    )
    seq = None
    for i in range(len(digits) - 2):
        a, b, c = digits[i], digits[i + 1], digits[i + 2]
        if b == a + 1 and c == a + 2 and a <= int(disc_face[0]) <= c:
            seq = [f"{a}{suit}", f"{b}{suit}", f"{c}{suit}"]
            break
    if not seq:
        combo_faces = sorted(
            {
                _face_for_sequence(t, dealer_tile)
                for t in chi_tiles
                if _is_suited(_face_for_sequence(t, dealer_tile))
            }
        )
        if len(combo_faces) == 3:
            d0, d1, d2 = (int(f[0]) for f in combo_faces)
            if (
                combo_faces[0][1] == combo_faces[1][1] == combo_faces[2][1]
                and d1 == d0 + 1
                and d2 == d0 + 2
            ):
                seq = combo_faces
    if not seq:
        return False

    counts: Counter[str] = Counter()
    for t in hand_tiles:
        if _is_joker_physical(t, dealer_tile):
            continue
        counts[_face_for_sequence(t, dealer_tile)] += 1
    return all(counts.get(f, 0) >= 1 for f in seq)


def _take_faces_from_hand(
    hand: list[str],
    need_faces: list[str],
    dealer_tile: str,
) -> list[str] | None:
    """从手牌取出覆盖 need_faces 的物理牌（白板可顶替得花色）。"""
    pool = list(hand)
    taken: list[str] = []
    for face in need_faces:
        idx = _find_tile_for_face(pool, face, dealer_tile)
        if idx < 0:
            return None
        taken.append(pool.pop(idx))
    return taken


def _find_tile_for_face(
    pool: list[str], face: str, dealer_tile: str
) -> int:
    # 优先精确物理同名，再白板替身
    for i, t in enumerate(pool):
        if t == face:
            return i
    for i, t in enumerate(pool):
        if _face_for_sequence(t, dealer_tile) == face:
            return i
    return -1


# ---------------------------------------------------------------------------
# 碰 / 明杠
# ---------------------------------------------------------------------------

def _count_claim_matches(
    hand_tiles: list[str], discarded_tile: str, dealer_tile: str
) -> int:
    """手牌中可与打出张组成碰/杠的匹配数（不含用得万能凑数）。"""
    target = _face_for_sequence(discarded_tile, dealer_tile)
    n = 0
    for t in hand_tiles:
        if _is_joker_physical(t, dealer_tile):
            # 「得」本身：仅当打出的也是同名物理得、且我们按同名实物碰时
            # 同名实物得用于碰可以（碰三张得），但不能拿得去补其它牌的杠。
            if t == discarded_tile and t == dealer_tile:
                n += 1
            continue
        if _face_for_sequence(t, dealer_tile) == target:
            n += 1
    return n


def _pick_claim_tiles(
    hand_tiles: list[str],
    discarded_tile: str,
    dealer_tile: str,
    need: int,
) -> list[str]:
    """选出 need 张用于碰/杠副露展示的手牌。"""
    target = _face_for_sequence(discarded_tile, dealer_tile)
    picked: list[str] = []
    for t in hand_tiles:
        if len(picked) >= need:
            break
        if _is_joker_physical(t, dealer_tile):
            if t == discarded_tile and t == dealer_tile:
                picked.append(t)
            continue
        if _face_for_sequence(t, dealer_tile) == target:
            picked.append(t)
    return picked


def _can_ming_gang_without_joker(
    hand_tiles: list[str], discarded_tile: str, dealer_tile: str
) -> bool:
    """明杠：手中须有 3 张真实匹配；禁止「3 张同名 + 1 得」拼杠。

    判定：在**忽略所有得百搭**后，非百搭匹配数仍 ≥ 3；
    或者打出/手牌均为同名物理得且实物张数足够（三手一打）。
    """
    target = _face_for_sequence(discarded_tile, dealer_tile)

    # 非百搭匹配
    non_joker_matches = [
        t
        for t in hand_tiles
        if (not _is_joker_physical(t, dealer_tile))
        and _face_for_sequence(t, dealer_tile) == target
    ]
    if len(non_joker_matches) >= 3:
        return True

    # 特例：打出物理得，手中另有 3 张物理得 → 四张实物得明杠（未用「得充其它牌」）
    if discarded_tile == dealer_tile or (
        dealer_tile == "P" and discarded_tile == "P"
    ):
        jokers_in_hand = sum(
            1 for t in hand_tiles if _is_joker_physical(t, dealer_tile)
        )
        if jokers_in_hand >= 3:
            return True

    # 典型非法：2 张真牌 + 手中得、或 3 真牌其实不足却想靠得凑
    # 此处已不足 3 非百搭 → 拒绝（即使手中有得）
    return False


# ---------------------------------------------------------------------------
# 点炮
# ---------------------------------------------------------------------------

def _can_ron(
    hand_tiles: list[str],
    melds: Sequence[Meld],
    discarded_tile: str,
    dealer_tile: str,
) -> bool:
    """加入打出张后，门清部分能否与副露凑成和牌（含白板替身）。"""
    needed = 4 - len(melds)
    if needed < 0:
        return False
    expect = needed * 3 + 1
    if len(hand_tiles) != expect:
        return False
    trial = list(hand_tiles) + [discarded_tile]
    logical = normalize_hand_for_eval(trial, dealer_tile)
    return check_win_or_shanten(logical, 0, needed_melds=needed) < 0


def find_catch_win_seats(
    *,
    discarded_tile: str,
    provider_seat: str,
    dealer_tile: str,
    hands_by_seat: dict[str, list[str]],
    melds_by_seat: dict[str, Sequence[Meld]] | None = None,
) -> list[str]:
    """扫描其余三家谁可对 ``discarded_tile`` 捉铳。

    Args:
        hands_by_seat: 各座门清暗手（未含铳张）。
        melds_by_seat: 各座副露；缺省视为无副露。

    Returns:
        可捉铳的座位列表（门风码）。
    """
    melds_map = melds_by_seat or {}
    winners: list[str] = []
    for seat in WINDS:
        if seat == provider_seat:
            continue
        hand = list(hands_by_seat.get(seat) or [])
        melds = list(melds_map.get(seat) or [])
        if _can_ron(hand, melds, discarded_tile, dealer_tile):
            winners.append(seat)
    return winners


# ---------------------------------------------------------------------------
# 自家暗杠 / 补杠（摸牌后或吃碰后、切牌前）
# ---------------------------------------------------------------------------

def detect_self_gang_actions(
    hand_tiles: list[str],
    melds: list[Meld] | Sequence[Meld] | None,
    dealer_tile: str,
) -> list[Action]:
    """检测待切瞬间的暗杠 / 补杠候选（rule.md §3.4 / §3.3）。

    合法性：
    - 暗杠：手牌中某物理牌恰 4 张，且该牌 ≠ dealer_tile（禁止百搭开杠）。
    - 补杠：已有对应 PONG，且手牌再持有至少 1 张同名非百搭物理牌。

    Returns:
        ``Action`` 列表（``AN_GANG`` / ``BU_GANG``）；无候选时为空。
    """
    meld_list = list(melds or [])
    counts = Counter(hand_tiles)
    actions: list[Action] = []

    # —— 暗杠：4 张完全相同的物理牌 ——
    for tile, n in counts.items():
        if n < 4:
            continue
        if tile == dealer_tile:
            # §2 / §7：得绝不可用于开杠
            continue
        actions.append(
            Action(
                action_type=ActionType.AN_GANG,
                tiles=[tile, tile, tile, tile],
                provider_seat="",
            )
        )

    # —— 补杠：碰后摸到第 4 张 ——
    for meld in meld_list:
        mtype = (
            meld.meld_type.value
            if hasattr(meld.meld_type, "value")
            else str(meld.meld_type)
        )
        if mtype not in ("pong", "peng"):
            continue
        tiles = list(meld.tiles or [])
        if not tiles:
            continue
        face = tiles[0]
        if face == dealer_tile:
            continue
        if counts.get(face, 0) < 1:
            continue
        # 避免与暗杠重复（手里已有 4 张时优先暗杠路径）
        if counts.get(face, 0) >= 4:
            continue
        actions.append(
            Action(
                action_type=ActionType.BU_GANG,
                tiles=[face, face, face, face],
                provider_seat="",
            )
        )

    return actions


def get_legal_turn_actions(
    hand_tiles: list[str],
    melds: list[Meld] | Sequence[Meld] | None,
    dealer_tile: str,
) -> list[Action]:
    """待切窗口的合法动作：不同牌面的切牌、暗杠及碰后补杠。"""
    actions = [
        Action(action_type=ActionType.DISCARD, tiles=[tile])
        for tile in dict.fromkeys(hand_tiles)
    ]
    actions.extend(detect_self_gang_actions(hand_tiles, melds, dealer_tile))
    return actions
