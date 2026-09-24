"""终局筹码结算矩阵（rule.md §6，绝对无包牌）。

Points = 赢家 H_final（§5.1）。
支付：
  - 庄家和：三闲各付全额 Points；三闲之间按固有结算胡差额折半互结。
  - 闲家和：庄付全额，其余两闲各付半额；未和各家固有结算胡折半互结。

固有结算胡 = 固有底胡 × 2^字牌/门风/圈风番（见 scoring.calculate_unwon_player_points）。
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Literal, Mapping, Sequence

from app.schemas import Meld

from .constants import WINDS
from .scoring import (
    DEFAULT_BASE_HU,
    MAX_PAYMENT_PER_PLAYER,
    ZIMO_HU,
    calculate_best_hu_points,
    calculate_unwon_base_hu,
    calculate_unwon_player_points,
)

WinType = Literal["zimo", "ron", "self_draw", "catch", "self_draw_win", "catch_win", "rob_kong"]


def normalize_win_type(win_type: str) -> Literal["zimo", "ron"]:
    t = (win_type or "").strip().lower()
    if t in ("zimo", "self_draw", "self_draw_win"):
        return "zimo"
    if t in ("ron", "catch", "catch_win", "rob_kong", "hu"):
        return "ron"
    raise ValueError(f"未知 win_type：{win_type!r}")


def inherent_hu_from_melds(
    melds: Sequence[Meld] | None, dealer_tile: str
) -> float:
    """未胡者固有胡头（仅公开副露底胡，兼容旧调用；不含加番）。"""
    return float(
        calculate_unwon_base_hu(
            hand_tiles=None,
            melds=melds,
            seat_wind="E",  # 无暗手时雀头项为 0，seat 无关
            dealer_tile=dealer_tile,
        )["total_base_hu"]
    )


def _player_inherent(
    player: Mapping[str, Any],
    dealer_tile: str,
    *,
    round_wind: str = "E",
) -> dict[str, Any]:
    """单家固有底胡 + 字牌加番后的结算胡数。"""
    return calculate_unwon_player_points(
        player,
        dealer_tile=dealer_tile,
        round_wind=round_wind,
    )


def estimate_points_from_open(
    melds: Sequence[Meld],
    dealer_tile: str,
    seat_wind: str,
    *,
    is_zimo: bool,
    round_wind: str = "E",
) -> int:
    """无暗手时：底胡 + 副露胡 + 自摸胡，再 ×2^可见役牌翻。"""
    detail = calculate_unwon_player_points(
        hand_tiles=[],
        melds=melds,
        seat_wind=seat_wind,
        dealer_tile=dealer_tile,
        round_wind=round_wind,
    )
    meld_fu = float(detail["total_base_hu"])
    fan = int(detail["fan_count"])
    tile_part = DEFAULT_BASE_HU + meld_fu + (ZIMO_HU if is_zimo else 0)
    return int(tile_part * (2 ** fan))


def calculate_final_settlement(
    *,
    winner_seat: str,
    win_type: str,
    dealer_tile: str,
    players: Sequence[Mapping[str, Any]],
    points: int | float | None = None,
    hand_tiles: list[str] | None = None,
    melds: Sequence[Meld] | None = None,
    win_tile: str | None = None,
    seat_wind: str | None = None,
    is_dealer: bool | None = None,
    discarder_seat: str | None = None,
    wrap_penalty: bool = False,
    restored_jokers: int = 0,
    round_wind: str = "E",
) -> dict[str, Any]:
    """计算四人终局筹码净变动（含主支付 + 固有胡头副结算）。

    Args:
        winner_seat: 胡牌方门风。
        win_type: zimo/ron（及 self_draw_win/catch_win 别名）。
        dealer_tile: 本局得。
        players: 四家公开状态，每项至少含 ``seat_wind`` / ``is_dealer`` / ``melds``。
        points: 若已算好的 H_final；缺省则用 hand_tiles+melds+win_tile 计分。
        hand_tiles / melds / win_tile: 赢家计分用（hand 为未含胡张的门清）。
        wrap_penalty: 必须为 False（§7 禁止包牌）。
        discarder_seat: 捉铳时的出枪方（仅记录，不改变无包牌三人分摊）。
        round_wind: 圈风（字牌刻杠叠番）。

    Returns:
        含 ``points / win_type / net_by_seat / transfers / payments / wrap_penalty`` 等。
    """
    # §7：绝无一人承包全桌
    assert wrap_penalty is False, "台州规则禁止包牌（wrap_penalty 必须为 False）"

    if winner_seat not in WINDS:
        raise ValueError(f"winner_seat 非法：{winner_seat!r}")

    kind = normalize_win_type(win_type)
    table = _normalize_players(players)
    if winner_seat not in table:
        raise ValueError(f"players 中缺少赢家座位 {winner_seat}")

    winner = table[winner_seat]
    win_is_dealer = (
        bool(is_dealer)
        if is_dealer is not None
        else bool(winner.get("is_dealer"))
    )
    # 空列表视为未传，回退到玩家副露（避免前端漏传 melds=[] 导致无法计分）
    if melds is not None and len(list(melds)) > 0:
        win_melds = list(melds)
    else:
        win_melds = list(winner.get("melds") or [])
    win_wind = seat_wind or winner_seat
    if hand_tiles is None and win_tile:
        hand_tiles = list(winner.get("hand_tiles") or [])
        # 玩家快照在自摸时可能已含摸入张；计分接口要求去掉该张。
        if len(hand_tiles) == (4 - len(win_melds)) * 3 + 2 and win_tile in hand_tiles:
            hand_tiles.remove(win_tile)
    if hand_tiles is not None:
        table[winner_seat]["hand_tiles"] = list(hand_tiles)
    if melds is not None and len(list(melds)) > 0:
        table[winner_seat]["melds"] = list(win_melds)

    hu_detail: dict[str, Any] | None = None
    best_restored = int(restored_jokers or 0)
    if win_tile is not None and hand_tiles is not None:
        try:
            # 始终枚举得还原，取最高胡数（硬胡+得还原可并存）
            hu_detail = calculate_best_hu_points(
                melds=win_melds,
                hand_tiles=list(hand_tiles),
                win_tile=win_tile,
                is_zimo=(kind == "zimo"),
                seat_wind=win_wind,
                dealer_tile=dealer_tile,
                base_hu=DEFAULT_BASE_HU,
                round_wind=round_wind,
            )
            best_restored = int(
                (hu_detail.get("details") or {}).get(
                    "restored_jokers", best_restored
                )
            )
        except ValueError:
            hu_detail = None

    if hu_detail is not None:
        final_points = float(hu_detail["final_hu"])
    elif points is not None:
        final_points = float(points)
    else:
        final_points = float(
            estimate_points_from_open(
                win_melds,
                dealer_tile,
                win_wind,
                is_zimo=(kind == "zimo"),
                round_wind=round_wind,
            )
        )

    pts = int(round(final_points))
    net: dict[str, float] = {s: 0.0 for s in table}
    transfers: list[dict[str, Any]] = []

    dealer_seat = next(s for s, p in table.items() if p.get("is_dealer"))
    xian_seats = [s for s in table if s != dealer_seat]

    if win_is_dealer:
        for xs in xian_seats:
            _pay(net, transfers, xs, winner_seat, pts, "闲家全额→庄家")
        side_pool = list(xian_seats)
        main_label = "庄家和牌：三闲各付全额"
    else:
        _pay(net, transfers, dealer_seat, winner_seat, pts, "庄家全额→闲家胡")
        other_xian = [s for s in xian_seats if s != winner_seat]
        half = pts / 2.0
        for xs in other_xian:
            _pay(net, transfers, xs, winner_seat, half, "闲家半额→闲家胡")
        side_pool = [s for s in table if s != winner_seat]
        main_label = "闲家和牌：庄全额、两闲半额"

    inherent_detail = {
        s: _player_inherent(table[s], dealer_tile, round_wind=round_wind)
        for s in table
    }
    # 互结必须用加番后的结算胡数（calculated_points），不能只用裸底胡
    inherent = {
        s: float(inherent_detail[s]["calculated_points"]) for s in side_pool
    }
    for a, b in combinations(side_pool, 2):
        ha, hb = inherent[a], inherent[b]
        if abs(ha - hb) < 1e-9:
            transfers.append({
                "from": a, "to": b, "amount": 0.0, "raw_amount": 0.0,
                "note": f"固有胡头相等 ({ha:.0f} = {hb:.0f})",
                "transaction_type": "mutual_settlement", "capped": False,
            })
            continue
        if hb > ha:
            # 庄家承担全额胡头差；闲家之间按规则折半。
            pay = (hb - ha) if table[a].get("is_dealer") else (hb - ha) / 2.0
            _pay(
                net,
                transfers,
                a,
                b,
                pay,
                f"固有胡头互结 ({ha:.0f}→{hb:.0f})",
                transaction_type="mutual_settlement",
            )
        else:
            pay = (ha - hb) if table[b].get("is_dealer") else (ha - hb) / 2.0
            _pay(
                net,
                transfers,
                b,
                a,
                pay,
                f"固有胡头互结 ({hb:.0f}→{ha:.0f})",
                transaction_type="mutual_settlement",
            )

    # 将两类账目显式并列返回，便于结算弹窗分别展示和核对。

    # 和牌赔付独立逐家封顶；未胡玩家间互结单独结算，不占用和牌赔付额度。
    net = {s: 0.0 for s in table}
    capped_seats = set()
    for seat in table:
        outgoing = [t for t in transfers if t["from"] == seat]
        main = [t for t in outgoing if t["to"] == winner_seat]
        side = [t for t in outgoing if t["to"] != winner_seat]
        for t in main:
            raw = t["amount"]
            actual = min(raw, float(MAX_PAYMENT_PER_PLAYER))
            t.update(raw_amount=raw, amount=actual, capped=actual < raw)
        for t in side:
            raw = t["amount"]
            t.update(raw_amount=raw, amount=raw, capped=False)
        for t in outgoing:
            net[seat] -= t["amount"]
            net[t["to"]] += t["amount"]
            if t["capped"]:
                capped_seats.add(seat)

    total = sum(net.values())
    if abs(total) > 1e-6:
        raise AssertionError(f"结算非零和：sum={total}")

    payments = {
        "label": main_label,
        "points": pts,
        "winner_income": net[winner_seat],
        "from_dealer": min(pts, MAX_PAYMENT_PER_PLAYER) if not win_is_dealer else 0,
        "from_each_xian": min(pts if win_is_dealer else pts / 2.0, MAX_PAYMENT_PER_PLAYER),
        "payment_cap": MAX_PAYMENT_PER_PLAYER,
        "capped_seats": sorted(capped_seats),
        "inherent_hu": {
            s: float(inherent_detail[s]["calculated_points"]) for s in table
        },
        "inherent_detail": inherent_detail,
        "mutual_settlement_transactions": [
            t for t in transfers if t.get("transaction_type") == "mutual_settlement"
        ],
        "winner_payout_transactions": [
            t for t in transfers if t.get("transaction_type") == "winner_payout"
        ],
    }

    seat_details = {
        s: {
            "seat_wind": s,
            "is_dealer": bool(table[s].get("is_dealer")),
            "is_winner": s == winner_seat,
            "hand_tiles": list(table[s].get("hand_tiles") or []),
            "melds": [
                m if isinstance(m, dict) else m.model_dump(mode="json")
                for m in (table[s].get("melds") or [])
            ],
            "net": round(net[s], 4),
            "payment_capped": s in capped_seats,
            "payment_cap": MAX_PAYMENT_PER_PLAYER,
            "actual_payment": round(sum(t["amount"] for t in transfers if t["from"] == s), 4),
            "inherent": inherent_detail[s],
        }
        for s in table
    }
    if win_tile and winner_seat in seat_details:
        seat_details[winner_seat]["win_tile"] = win_tile
        # 展示用：门清 + 胡张（不改变计分用 hand）
        closed = list(seat_details[winner_seat]["hand_tiles"])
        seat_details[winner_seat]["hand_tiles_with_win"] = closed + [win_tile]
    if hu_detail and hu_detail.get("best_decomposition"):
        seat_details[winner_seat]["winning_hand_groups"] = hu_detail["winning_hand_groups"]
        seat_details[winner_seat]["best_decomposition"] = hu_detail[
            "best_decomposition"
        ]
        seat_details[winner_seat]["hu_detail"] = {
            "tile_hu": hu_detail.get("tile_hu"),
            "base_hu": hu_detail.get("base_hu"),
            "fan": hu_detail.get("fan"),
            "final_hu": hu_detail.get("final_hu"),
            "is_hard_hu": hu_detail.get("is_hard_hu"),
            "details": hu_detail.get("details"),
            "restored_jokers": (hu_detail.get("details") or {}).get(
                "restored_jokers", best_restored
            ),
        }

    return {
        "winner_seat": winner_seat,
        "win_type": kind,
        "win_type_label": "抢杠胡" if win_type == "rob_kong" else ("自摸" if kind == "zimo" else "捉铳"),
        "is_zimo": kind == "zimo",
        "is_dealer_win": win_is_dealer,
        "points": pts,
        "final_hu": pts,
        "final_points": pts,
        "wrap_penalty": False,
        "discarder_seat": discarder_seat,
        "net_by_seat": {s: round(v, 4) for s, v in net.items()},
        "transfers": transfers,
        "payments": payments,
        "hu_detail": hu_detail,
        "dealer_seat": dealer_seat,
        "dealer_tile": dealer_tile,
        "seat_details": seat_details,
    }


def _normalize_players(
    players: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for p in players:
        seat = p.get("seat_wind")
        if seat not in WINDS:
            raise ValueError(f"非法 seat_wind：{seat!r}")
        table[seat] = {
            "seat_wind": seat,
            "is_dealer": bool(p.get("is_dealer")),
            "melds": list(p.get("melds") or []),
            "hand_tiles": list(p.get("hand_tiles") or []),
        }
    if len(table) != 4:
        raise ValueError(f"结算需要恰好四家，当前 {len(table)}")
    dealers = [s for s, p in table.items() if p["is_dealer"]]
    if len(dealers) != 1:
        raise ValueError(f"庄家标记须恰好 1 人，当前 {dealers}")
    return table


def _pay(
    net: dict[str, float],
    transfers: list[dict[str, Any]],
    frm: str,
    to: str,
    amount: float,
    note: str,
    transaction_type: str = "winner_payout",
) -> None:
    if amount <= 0:
        return
    net[frm] -= amount
    net[to] += amount
    transfers.append(
        {
            "from": frm,
            "to": to,
            "amount": round(float(amount), 4),
            "note": note,
            "transaction_type": transaction_type,
        }
    )
