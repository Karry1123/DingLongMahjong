"""回归：其余三家副露（含暗杠）必须贯通 Rem / 听牌 / 染手 / EstLoss。"""

from __future__ import annotations

import unittest

from app.core.constants import ALL_TILES
from app.core.danger_model import estimate_tile_danger
from app.core.ev_engine import (
    _build_opponent_threat,
    _build_rem_map,
    calculate_best_discards,
)
from app.core.pool_tracker import get_remaining_tiles
from app.core.scoring import AN_GANG_SIMPLE_HU, calculate_meld_points
from app.core.tenpai_model import estimate_opponents_tenpai
from app.schemas import HandRequest, Meld, MeldType, PlayerState


def _hand14() -> list[str]:
    return (
        ["1m", "2m", "3m", "4m", "5m", "6m", "7m"]
        + ["1p", "2p", "3p", "4p", "5p", "6p", "7p"]
    )


def _an_gang(tile: str) -> Meld:
    return Meld(meld_type=MeldType.AN_GANG, tiles=[tile] * 4)


def _pong(tile: str) -> Meld:
    return Meld(meld_type=MeldType.PONG, tiles=[tile] * 3)


def _chi(*tiles: str) -> Meld:
    return Meld(meld_type=MeldType.CHI, tiles=list(tiles))


class TestRemIncludesOpponentMelds(unittest.TestCase):
    def test_opponent_an_gang_zeros_rem(self):
        req = HandRequest(
            hand_tiles=_hand14(),
            melds=[],
            discards=[],
            dealer_tile="9s",
            seat_wind="E",
            is_dealer=False,
            opponents=[
                PlayerState(
                    seat_wind="S",
                    melds=[_an_gang("8s")],
                ),
                PlayerState(seat_wind="W"),
                PlayerState(seat_wind="N"),
            ],
        )
        rem = get_remaining_tiles(req)
        self.assertEqual(rem["8s"], 0)
        self.assertEqual(req.collect_all_meld_tiles().count("8s"), 4)

    def test_ev_fallback_rem_includes_opp_melds(self):
        """未传 rem_tiles 时，calculate_best_discards 回退也须扣对手副露。"""
        hand = _hand14()
        opps = [
            PlayerState(seat_wind="S", melds=[_an_gang("E")]),
            PlayerState(seat_wind="W"),
            PlayerState(seat_wind="N"),
        ]
        # 不传 rem_tiles → 走 _build_rem_map 回退
        result = calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="9s",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=[],
            melds=[],
            opponents=opps,
            rem_tiles=None,
        )
        self.assertTrue(result["candidates"])
        # 对照：显式全场 Rem 中 E 应为 0
        req = HandRequest(
            hand_tiles=hand,
            dealer_tile="9s",
            seat_wind="E",
            is_dealer=False,
            opponents=opps,
        )
        self.assertEqual(get_remaining_tiles(req)["E"], 0)

    def test_build_rem_map_with_opp_meld_phys(self):
        rem = _build_rem_map(
            _hand14(),
            [],
            ["8p"] * 4,  # 对手暗杠 8p
            "9s",
        )
        self.assertEqual(rem["8p"], 0)


class TestTenpaiAndDyeFromMelds(unittest.TestCase):
    def test_three_melds_near_certain_tenpai(self):
        opp = PlayerState(
            seat_wind="S",
            discards=[],
            melds=[_pong("1s"), _pong("9s"), _an_gang("2p")],
        )
        p = estimate_opponents_tenpai([opp])["S"]
        self.assertGreaterEqual(p, 0.90)

    def test_an_gang_same_suit_dyes(self):
        """单组暗杠同门序数 → 染手：该色中张加权、它色打折。"""
        opp = PlayerState(seat_wind="W", melds=[_an_gang("5p")])
        rem = {t: 4 for t in ALL_TILES}
        rem["9s"] = 3
        dyed = estimate_tile_danger("6p", opp, rem, "9s")
        plain = estimate_tile_danger(
            "6p", PlayerState(seat_wind="W"), rem, "9s"
        )
        self.assertAlmostEqual(dyed, plain * 2.2, places=5)
        other = estimate_tile_danger("6m", opp, rem, "9s")
        self.assertAlmostEqual(other, plain * 0.25, places=5)


class TestEstLossFromOpenMelds(unittest.TestCase):
    def test_an_gang_raises_loss_vs_chi(self):
        dealer = "9s"
        chi_opp = PlayerState(
            seat_wind="S",
            is_dealer=False,
            melds=[_chi("2p", "3p", "4p")],
        )
        gang_opp = PlayerState(
            seat_wind="S",
            is_dealer=False,
            melds=[_an_gang("5p")],
        )
        self.assertEqual(
            calculate_meld_points(gang_opp.melds[0], dealer),
            AN_GANG_SIMPLE_HU,
        )
        chi_threat = _build_opponent_threat(chi_opp, dealer, False)
        gang_threat = _build_opponent_threat(gang_opp, dealer, False)
        # 闲家对闲：半额；暗杠 16 胡 vs 吃 0 胡 → 暗杠 EstLoss 显著更高
        self.assertGreater(gang_threat["loss_ron"], chi_threat["loss_ron"])
        self.assertGreaterEqual(gang_threat["ron_points"], 10 + 16)

    def test_honor_an_gang_32_hu(self):
        m = _an_gang("E")
        self.assertEqual(calculate_meld_points(m, "9s"), 32)


if __name__ == "__main__":
    unittest.main()
