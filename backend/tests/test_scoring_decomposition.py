"""未胡固有底胡 + 和牌拆解中的百搭标记。"""

from __future__ import annotations

import unittest

from app.core.scoring import calculate_hu_points, calculate_unwon_base_hu
from app.core.settlement import calculate_final_settlement
from app.schemas import Meld, MeldType


class TestUnwonBaseHu(unittest.TestCase):
    def test_open_pong_and_concealed_anko_seat_pair(self):
        melds = [Meld(meld_type=MeldType.PONG, tiles=["N", "N", "N"])]
        # 门风东：暗刻 8p + 自风对 E
        hand = ["8p", "8p", "8p", "E", "E", "2m", "3m", "5s", "6s", "7s"]
        r = calculate_unwon_base_hu(hand, melds, "E", "5m")
        self.assertEqual(r["total_base_hu"], 4 + 4 + 2)  # 明刻北风4 + 暗刻八筒4 + 东风雀头2
        # 北风非门风/三元：不加番
        self.assertEqual(r["fan_count"], 0)
        self.assertEqual(r["calculated_points"], 10)
        joined = " ".join(r["items"])
        self.assertIn("明刻", joined)
        self.assertIn("暗刻", joined)
        self.assertIn("自风雀头", joined)

    def test_an_gang_honor(self):
        melds = [Meld(meld_type=MeldType.AN_GANG, tiles=["F"] * 4)]
        r = calculate_unwon_base_hu([], melds, "S", "1m")
        self.assertEqual(r["total_base_hu"], 32)
        self.assertEqual(r["fan_count"], 1)
        self.assertEqual(r["calculated_points"], 64)
        self.assertIn("暗杠", r["items"][0])
        self.assertTrue(any("发财" in (fd["name"] or "") for fd in r["fan_details"]))

    def test_open_fa_pong_doubles_for_unwon(self):
        """明刻发财：底胡 4 × 1番 = 结算 8。"""
        from app.core.scoring import calculate_unwon_player_points

        melds = [Meld(meld_type=MeldType.PONG, tiles=["F", "F", "F"])]
        r = calculate_unwon_player_points(
            hand_tiles=[],
            melds=melds,
            seat_wind="N",
            dealer_tile="5m",
        )
        self.assertEqual(r["base_hu"], 4)
        self.assertEqual(r["fan_count"], 1)
        self.assertEqual(r["calculated_points"], 8)
        self.assertEqual(len(r["fan_details"]), 1)
        self.assertIn("发财", r["fan_details"][0]["name"])

    def test_fa_and_zhong_stack_two_fan(self):
        """碰发 + 碰中：2 番 → ×4。"""
        from app.core.scoring import calculate_unwon_player_points

        melds = [
            Meld(meld_type=MeldType.PONG, tiles=["F"] * 3),
            Meld(meld_type=MeldType.PONG, tiles=["C"] * 3),
        ]
        r = calculate_unwon_player_points(
            hand_tiles=[],
            melds=melds,
            seat_wind="N",
            dealer_tile="9p",
        )
        self.assertEqual(r["base_hu"], 8)
        self.assertEqual(r["fan_count"], 2)
        self.assertEqual(r["calculated_points"], 32)

    def test_seat_wind_anko_adds_fan(self):
        """暗刻自风：底胡 8 × 1番 = 16。"""
        from app.core.scoring import calculate_unwon_player_points

        r = calculate_unwon_player_points(
            hand_tiles=["N", "N", "N", "2m", "3m", "5p"],
            melds=[],
            seat_wind="N",
            dealer_tile="5m",
        )
        self.assertEqual(r["base_hu"], 8)
        self.assertEqual(r["fan_count"], 1)
        self.assertEqual(r["calculated_points"], 16)


class TestBestDecomposition(unittest.TestCase):
    def test_joker_in_sequence_marked(self):
        # 得=5m：手含一张 5m 作百搭，胡 6m 成 456m
        melds = [
            Meld(meld_type=MeldType.PONG, tiles=["1p"] * 3),
            Meld(meld_type=MeldType.PONG, tiles=["2p"] * 3),
            Meld(meld_type=MeldType.PONG, tiles=["3p"] * 3),
        ]
        # 门清 4m + 得(5m→JOKER) + 雀头 CC，胡 6m → 456 + CC
        hand = ["4m", "5m", "C", "C"]
        hu = calculate_hu_points(
            melds=melds,
            hand_tiles=hand,
            win_tile="6m",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="5m",
            restored_jokers=0,
        )
        deco = hu["best_decomposition"]
        self.assertIn("head", deco)
        self.assertTrue(deco["melds_and_sequences"])
        chi = next(
            g
            for g in deco["melds_and_sequences"]
            if g["kind"] == "chi" and g.get("jokers_used", 0) > 0
        )
        self.assertEqual(chi["joker_substituted"], "5m")
        self.assertTrue(any(d["is_joker"] for d in chi["display_tiles"]))


class TestSettlementSeatDetails(unittest.TestCase):
    def test_seat_details_include_inherent(self):
        players = [
            {
                "seat_wind": "E",
                "is_dealer": True,
                "melds": [],
                "hand_tiles": [],
            },
            {
                "seat_wind": "S",
                "is_dealer": False,
                "melds": [
                    Meld(meld_type=MeldType.PONG, tiles=["5m", "5m", "5m"])
                ],
                "hand_tiles": [],
            },
            {"seat_wind": "W", "is_dealer": False, "melds": [], "hand_tiles": []},
            {"seat_wind": "N", "is_dealer": False, "melds": [], "hand_tiles": []},
        ]
        r = calculate_final_settlement(
            winner_seat="E",
            win_type="zimo",
            dealer_tile="9p",
            players=players,
            points=10,
        )
        self.assertIn("seat_details", r)
        self.assertEqual(
            r["seat_details"]["S"]["inherent"]["total_base_hu"], 2
        )
        self.assertEqual(
            r["seat_details"]["S"]["inherent"]["calculated_points"], 2
        )
        self.assertIn("E", r["seat_details"])


class TestUnwonYakuhaiFanSettlement(unittest.TestCase):
    def test_fa_pong_side_settlement_uses_doubled_points(self):
        """庄和：北闲明刻发财 → 固有结算 8，高于无副露闲家，应收互结差额。"""
        players = [
            {
                "seat_wind": "E",
                "is_dealer": True,
                "melds": [],
                "hand_tiles": [],
            },
            {
                "seat_wind": "S",
                "is_dealer": False,
                "melds": [],
                "hand_tiles": [],
            },
            {
                "seat_wind": "W",
                "is_dealer": False,
                "melds": [],
                "hand_tiles": [],
            },
            {
                "seat_wind": "N",
                "is_dealer": False,
                "melds": [
                    Meld(meld_type=MeldType.PONG, tiles=["F", "F", "F"])
                ],
                "hand_tiles": [],
            },
        ]
        r = calculate_final_settlement(
            winner_seat="E",
            win_type="zimo",
            dealer_tile="9p",
            players=players,
            points=10,
        )
        inherent_n = r["seat_details"]["N"]["inherent"]
        self.assertEqual(inherent_n["base_hu"], 4)
        self.assertEqual(inherent_n["fan_count"], 1)
        self.assertEqual(inherent_n["calculated_points"], 8)
        # 主支付：E+30，三闲各 -10；再 N 对 S/W 各收 (8-0)/2=4
        self.assertAlmostEqual(r["net_by_seat"]["E"], 30.0)
        self.assertAlmostEqual(r["net_by_seat"]["N"], -10 + 4 + 4)
        self.assertAlmostEqual(r["net_by_seat"]["S"], -10 - 4)
        self.assertAlmostEqual(r["net_by_seat"]["W"], -10 - 4)
        self.assertAlmostEqual(sum(r["net_by_seat"].values()), 0.0)


class TestFaPairWithWhiteboardSubstitute(unittest.TestCase):
    """得=发：雀头 [发,白] 计三元+2，且得还原后硬碰硬。"""

    def test_hard_hu_with_substitute_pair(self):
        from app.core.scoring import calculate_best_hu_points
        from app.schemas import Meld, MeldType

        melds = [Meld(meld_type=MeldType.CHI, tiles=["7m", "8m", "9m"])]
        hand = [
            "3m",
            "3m",
            "3m",
            "7m",
            "8m",
            "9m",
            "2s",
            "3s",
            "F",
            "P",
        ]
        r = calculate_best_hu_points(
            melds=melds,
            hand_tiles=hand,
            win_tile="1s",
            is_zimo=False,
            seat_wind="E",
            dealer_tile="F",
        )
        self.assertEqual(r["tile_hu"], 6)  # 暗刻中张4 + 三元雀头2
        self.assertTrue(r["is_hard_hu"])
        self.assertIn("hard_hu", r["details"]["fans"])
        self.assertNotIn("restored_jokers", r["details"]["fans"])
        # 硬胡不叠得还原番：(6+10) × 2^1 = 32
        self.assertEqual(r["final_hu"], 32)
        self.assertIn("替身", r["details"]["pairs"][0]["note"])
        head = r["best_decomposition"]["head"]["display_tiles"]
        codes = [d["code"] for d in head]
        self.assertIn("F", codes)
        self.assertIn("P", codes)
        win_grp = next(
            g
            for g in r["best_decomposition"]["melds_and_sequences"]
            if g.get("contains_win_tile")
        )
        self.assertTrue(
            any(d.get("is_win_tile") for d in win_grp["display_tiles"])
        )

    def test_settlement_recovers_from_empty_melds_arg(self):
        from app.core.settlement import calculate_final_settlement
        from app.schemas import Meld, MeldType

        melds = [Meld(meld_type=MeldType.CHI, tiles=["7m", "8m", "9m"])]
        hand = [
            "3m",
            "3m",
            "3m",
            "7m",
            "8m",
            "9m",
            "2s",
            "3s",
            "F",
            "P",
        ]
        players = [
            {
                "seat_wind": "E",
                "is_dealer": True,
                "melds": melds,
                "hand_tiles": hand,
            },
            {"seat_wind": "S", "is_dealer": False, "melds": [], "hand_tiles": []},
            {"seat_wind": "W", "is_dealer": False, "melds": [], "hand_tiles": []},
            {"seat_wind": "N", "is_dealer": False, "melds": [], "hand_tiles": []},
        ]
        r = calculate_final_settlement(
            winner_seat="E",
            win_type="ron",
            dealer_tile="F",
            players=players,
            points=None,
            hand_tiles=hand,
            melds=[],  # 模拟前端漏传
            win_tile="1s",
        )
        self.assertEqual(r["points"], 32)
        self.assertIsNotNone(r["hu_detail"])
        self.assertTrue(r["hu_detail"]["is_hard_hu"])


if __name__ == "__main__":
    unittest.main()
