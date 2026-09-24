"""终局结算矩阵 + 捉铳检测。"""

from __future__ import annotations

import unittest

from app.core.evaluator import check_ron_win, check_self_drawn_win
from app.core.settlement import calculate_final_settlement, inherent_hu_from_melds
from app.schemas import Meld, MeldType


def _players(
    *,
    e_melds=None,
    s_melds=None,
    w_melds=None,
    n_melds=None,
    dealer="E",
):
    seats = {
        "E": e_melds or [],
        "S": s_melds or [],
        "W": w_melds or [],
        "N": n_melds or [],
    }
    return [
        {
            "seat_wind": s,
            "is_dealer": s == dealer,
            "melds": seats[s],
        }
        for s in ("E", "S", "W", "N")
    ]


class TestCalculateFinalSettlement(unittest.TestCase):
    def test_wrap_penalty_must_be_false(self):
        with self.assertRaises(AssertionError):
            calculate_final_settlement(
                winner_seat="E",
                win_type="zimo",
                dealer_tile="9p",
                players=_players(),
                points=20,
                wrap_penalty=True,
            )

    def test_dealer_win_three_full_payments(self):
        r = calculate_final_settlement(
            winner_seat="E",
            win_type="self_draw_win",
            dealer_tile="9p",
            players=_players(),
            points=30,
            wrap_penalty=False,
        )
        self.assertFalse(r["wrap_penalty"])
        self.assertEqual(r["win_type"], "zimo")
        self.assertEqual(r["net_by_seat"]["E"], 90)
        self.assertEqual(r["net_by_seat"]["S"], -30)
        self.assertEqual(r["net_by_seat"]["W"], -30)
        self.assertEqual(r["net_by_seat"]["N"], -30)
        self.assertAlmostEqual(sum(r["net_by_seat"].values()), 0.0)

    def test_xian_win_dealer_full_others_half(self):
        r = calculate_final_settlement(
            winner_seat="S",
            win_type="catch_win",
            dealer_tile="9p",
            players=_players(),
            points=40,
            discarder_seat="W",
            wrap_penalty=False,
        )
        self.assertEqual(r["win_type"], "ron")
        # 庄 40 + 两闲各 20 = 80
        self.assertEqual(r["net_by_seat"]["S"], 80)
        self.assertEqual(r["net_by_seat"]["E"], -40)
        self.assertEqual(r["net_by_seat"]["W"], -20)
        self.assertEqual(r["net_by_seat"]["N"], -20)

    def test_rob_kong_is_ron_with_distinct_label(self):
        r = calculate_final_settlement(
            winner_seat="E", win_type="rob_kong", dealer_tile="9s",
            players=_players(), points=20, discarder_seat="S",
            wrap_penalty=False,
        )
        self.assertEqual(r["win_type"], "ron")
        self.assertEqual(r["win_type_label"], "抢杠胡")
        self.assertEqual(r["discarder_seat"], "S")

    def test_one_pin_add_kong_upgrades_inherent_hu_from_four_to_sixteen(self):
        pong = Meld(meld_type=MeldType.PONG, tiles=["1p"] * 3)
        kong = Meld(meld_type=MeldType.MING_GANG, tiles=["1p"] * 4)
        self.assertEqual(inherent_hu_from_melds([pong], "9s"), 4)
        self.assertEqual(inherent_hu_from_melds([kong], "9s"), 16)

    def test_side_settlement_among_xian_when_dealer_wins(self):
        # S 碰中张 2 胡；W 无副露 0 → S 收 W 1 胡
        s_melds = [Meld(meld_type=MeldType.PONG, tiles=["5m", "5m", "5m"])]
        r = calculate_final_settlement(
            winner_seat="E",
            win_type="zimo",
            dealer_tile="9p",
            players=_players(s_melds=s_melds),
            points=10,
            wrap_penalty=False,
        )
        # 主支付后 E=+30, 三闲各 -10；再 S←W / S←N 各收 1
        self.assertEqual(r["net_by_seat"]["E"], 30)
        self.assertAlmostEqual(r["net_by_seat"]["S"], -8.0)
        self.assertAlmostEqual(r["net_by_seat"]["W"], -11.0)
        self.assertAlmostEqual(r["net_by_seat"]["N"], -11.0)
        self.assertAlmostEqual(sum(r["net_by_seat"].values()), 0.0)


class TestCheckRonWin(unittest.TestCase):
    def test_ron_closed_hand(self):
        # 听 5m：111m 222m 333m 444m 5
        wait = (
            ["1m"] * 3
            + ["2m"] * 3
            + ["3m"] * 3
            + ["4m"] * 3
            + ["5m"]
        )
        players = _players(dealer="E")
        info = check_ron_win(
            wait,
            [],
            "5m",
            "9p",
            "E",
            is_dealer=True,
            players=players,
            discarder_seat="S",
        )
        self.assertIsNotNone(info)
        assert info is not None
        self.assertFalse(info["is_zimo"])
        self.assertEqual(info["action_type"], "catch_win")
        self.assertIn("settlement", info)
        self.assertFalse(info["wrap_penalty"])

    def test_not_ron(self):
        wait = (
            ["1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m"]
            + ["1p", "2p", "3p", "9s"]
        )
        self.assertIsNone(
            check_ron_win(wait, [], "5s", "9p", "E", is_dealer=False)
        )


class TestSelfDrawWithSettlement(unittest.TestCase):
    def test_zimo_attaches_settlement(self):
        hand = (
            ["1m"] * 3
            + ["2m"] * 3
            + ["3m"] * 3
            + ["4m"] * 3
            + ["5m", "5m"]
        )
        info = check_self_drawn_win(
            hand,
            [],
            "9p",
            "S",
            is_dealer=False,
            win_tile="5m",
            players=_players(dealer="E"),
        )
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info["action_type"], "self_draw_win")
        self.assertIn("net_by_seat", info)
        self.assertAlmostEqual(sum(info["net_by_seat"].values()), 0.0)


if __name__ == "__main__":
    unittest.main()
