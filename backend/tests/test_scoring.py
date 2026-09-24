"""黄岩麻将 calculate_hu_points 单元测试。"""

from __future__ import annotations

import unittest

from app.core.scoring import calculate_hu_points, calculate_meld_points
from app.schemas import Meld, MeldType


def _m(meld_type: MeldType, tiles: list[str]) -> Meld:
    return Meld(meld_type=meld_type, tiles=tiles)


class TestMeldPointsCompat(unittest.TestCase):
    """旧副露接口仍可用。"""

    def test_pong_and_gang_table(self):
        self.assertEqual(
            calculate_meld_points(
                _m(MeldType.PONG, ["5m"] * 3), "3p"
            ),
            2,
        )
        self.assertEqual(
            calculate_meld_points(
                _m(MeldType.PONG, ["1s"] * 3), "3p"
            ),
            4,
        )
        self.assertEqual(
            calculate_meld_points(
                _m(MeldType.MING_GANG, ["9m"] * 4), "E"
            ),
            16,
        )
        self.assertEqual(
            calculate_meld_points(
                _m(MeldType.AN_GANG, ["6s"] * 4), "E"
            ),
            16,
        )


class TestOrdinaryZimo(unittest.TestCase):
    """普通自摸：底胡 + 自摸 +2，无额外翻。"""

    def test_simple_zimo_no_fan(self):
        # 副露三个中张顺子；门清 5m5m + 听 6m6m6m
        melds = [
            _m(MeldType.CHI, ["1m", "2m", "3m"]),
            _m(MeldType.CHI, ["4p", "5p", "6p"]),
            _m(MeldType.CHI, ["7s", "8s", "9s"]),
        ]
        # 听牌手：雀头 2p2p，搭子暗刻位 5m5m，胡 5m
        hand = ["2p", "2p", "5m", "5m"]
        r = calculate_hu_points(
            melds=melds,
            hand_tiles=hand,
            win_tile="5m",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="9p",  # 与手牌无关，保证无得
            base_hu=10,
        )
        # 牌型：暗刻中张4 + 自摸2 = 6；翻=0（软？无得→硬碰硬+1）
        # 手中无得 → 硬碰硬 +1 翻
        self.assertEqual(r["tile_hu"], 6)
        self.assertTrue(r["is_hard_hu"])
        self.assertEqual(r["fan"], 1)
        self.assertEqual(r["details"]["zimo"], 2)
        self.assertEqual(r["final_hu"], (6 + 10) * 2)


class TestConcealedAnko(unittest.TestCase):
    """带暗刻（幺九暗刻 8 胡）。"""

    def test_terminal_anko(self):
        melds = [
            _m(MeldType.CHI, ["2m", "3m", "4m"]),
            _m(MeldType.CHI, ["5m", "6m", "7m"]),
            _m(MeldType.CHI, ["2p", "3p", "4p"]),
        ]
        hand = ["1s", "1s", "5p", "5p"]
        r = calculate_hu_points(
            melds=melds,
            hand_tiles=hand,
            win_tile="1s",
            is_zimo=True,
            seat_wind="S",
            dealer_tile="9m",
        )
        # 幺九暗刻 8 + 自摸 2 = 10；硬碰硬 +1
        self.assertEqual(r["tile_hu"], 10)
        self.assertEqual(r["details"]["zimo"], 2)
        anko = [m for m in r["details"]["melds"] if m["type"] == "anko"]
        self.assertEqual(anko[0]["hu"], 8)
        self.assertEqual(r["final_hu"], (10 + 10) * 2)


class TestMingGang(unittest.TestCase):
    """带明杠。"""

    def test_ming_gang_simple(self):
        melds = [
            _m(MeldType.MING_GANG, ["5m"] * 4),  # 中张明杠 8
            _m(MeldType.CHI, ["1p", "2p", "3p"]),
            _m(MeldType.CHI, ["4p", "5p", "6p"]),
        ]
        hand = ["7s", "7s", "2s", "2s"]
        r = calculate_hu_points(
            melds=melds,
            hand_tiles=hand,
            win_tile="2s",
            is_zimo=False,
            seat_wind="E",
            dealer_tile="9m",
        )
        # 明杠8 + 非自摸胡张构成的中张明刻2 = 10；硬碰硬+1
        self.assertEqual(r["details"]["zimo"], 0)
        gang = [m for m in r["details"]["melds"] if m["type"] == "ming_gang"]
        self.assertEqual(gang[0]["hu"], 8)
        self.assertEqual(r["tile_hu"], 10)
        self.assertEqual(r["final_hu"], (10 + 10) * 2)


class TestHardHu(unittest.TestCase):
    """硬碰硬：手中无「得」作百搭 → +1 翻。"""

    def test_hard_vs_soft(self):
        melds = [
            _m(MeldType.CHI, ["1m", "2m", "3m"]),
            _m(MeldType.CHI, ["4m", "5m", "6m"]),
            _m(MeldType.CHI, ["7m", "8m", "9m"]),
        ]
        # 硬：无得
        hard = calculate_hu_points(
            melds=melds,
            hand_tiles=["2p", "2p", "3p", "3p"],
            win_tile="3p",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="5s",
        )
        self.assertTrue(hard["is_hard_hu"])
        self.assertIn("hard_hu", hard["details"]["fans"])

        # 软：手里有一张得（5s），胡 3p 时用得补暗刻
        soft = calculate_hu_points(
            melds=melds,
            hand_tiles=["2p", "2p", "3p", "5s"],
            win_tile="3p",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="5s",
            restored_jokers=0,
        )
        self.assertFalse(soft["is_hard_hu"])
        self.assertNotIn("hard_hu", soft["details"]["fans"])


class TestFullFlush(unittest.TestCase):
    """清一色 +3 翻。"""

    def test_chinitsu(self):
        melds = [
            _m(MeldType.CHI, ["1p", "2p", "3p"]),
            _m(MeldType.CHI, ["4p", "5p", "6p"]),
            _m(MeldType.PONG, ["7p"] * 3),
        ]
        r = calculate_hu_points(
            melds=melds,
            hand_tiles=["8p", "8p", "9p", "9p"],
            win_tile="9p",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="1m",
        )
        self.assertEqual(r["details"]["fans"].get("full_flush"), 3)
        # 明刻中张2 + 暗刻幺九8 + 自摸2 = 12；硬+1 + 清+3 = 4翻
        self.assertEqual(r["tile_hu"], 12)
        self.assertEqual(r["fan"], 4)
        self.assertEqual(r["final_hu"], (12 + 10) * (2**4))


class TestRestoredJokers(unittest.TestCase):
    """得还原：每张 +1 翻（最多 3）。"""

    def test_restore_one(self):
        melds = [
            _m(MeldType.CHI, ["1m", "2m", "3m"]),
            _m(MeldType.CHI, ["4m", "5m", "6m"]),
            _m(MeldType.CHI, ["7m", "8m", "9m"]),
        ]
        # 得=2p；手牌含一张 2p（得）与一张真 2p，还原 1 张后做雀头 2p2p，
        # 再胡 3p 做暗刻 3p3p3p——听牌形：2p,2p(得),3p,3p 胡 3p，还原1
        r = calculate_hu_points(
            melds=melds,
            hand_tiles=["2p", "2p", "3p", "3p"],
            win_tile="3p",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="2p",
            restored_jokers=1,
        )
        # 物理两张 2p 都是得 → 预处理后 2 张 JOKER；还原 1 张 → 剩 1 百搭
        # 若听牌手是 2p(得), 2p(得), 3p, 3p —— 两张都是得
        self.assertEqual(r["details"]["restored_jokers"], 1)
        self.assertEqual(r["details"]["fans"].get("restored_jokers"), 1)
        # 还原后仍有 1 张百搭 → 非硬碰硬
        self.assertFalse(r["is_hard_hu"])

    def test_restore_all_becomes_hard(self):
        """两张得全部还原 → 无百搭剩余 → 硬碰硬。"""
        melds = [
            _m(MeldType.CHI, ["1m", "2m", "3m"]),
            _m(MeldType.CHI, ["4m", "5m", "6m"]),
            _m(MeldType.CHI, ["7m", "8m", "9m"]),
        ]
        # 得=3p；手牌 3p,3p,2s,2s 胡 2s：两张得还原后作暗刻/雀头？
        # 还原 2：working = 3p,3p,2s,2s + 2s → 雀头 3p + 暗刻 2s
        r = calculate_hu_points(
            melds=melds,
            hand_tiles=["3p", "3p", "2s", "2s"],
            win_tile="2s",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="3p",
            restored_jokers=2,
        )
        self.assertTrue(r["is_hard_hu"])
        self.assertNotIn("restored_jokers", r["details"]["fans"])
        self.assertEqual(r["details"]["fans"].get("hard_hu"), 1)


class TestRonPungAndBestRestorePath(unittest.TestCase):
    def test_whiteboard_dealer_alternatives_choose_max_hu_and_ron_is_open(self):
        from app.core.scoring import calculate_best_hu_points

        melds = [
            _m(MeldType.PONG, ["S"] * 3),
            _m(MeldType.CHI, ["6s", "7s", "8s"]),
        ]
        result = calculate_best_hu_points(
            melds=melds,
            hand_tiles=["2m", "3m", "4m", "2p", "2p", "1s", "1s"],
            win_tile="P",
            is_zimo=False,
            seat_wind="W",
            dealer_tile="1s",
        )
        # 明碰南4 + 点炮组成的一條明刻4；硬胡×2，不能再叠还原番。
        self.assertEqual(result["tile_hu"], 8)
        self.assertEqual(result["final_hu"], 36)
        self.assertEqual(result["fan"], 1)
        self.assertTrue(result["is_hard_hu"])
        self.assertNotIn("restored_jokers", result["details"]["fans"])
        win_group = next(g for g in result["winning_hand_groups"] if g["contains_win_tile"])
        self.assertEqual(win_group["kind"], "pong")
        self.assertEqual(win_group["hu"], 4)


class TestKanzhang(unittest.TestCase):
    """嵌档 +2 胡。"""

    def test_kanzhang_middle(self):
        melds = [
            _m(MeldType.CHI, ["1m", "2m", "3m"]),
            _m(MeldType.CHI, ["4m", "5m", "6m"]),
            _m(MeldType.PONG, ["9s"] * 3),
        ]
        # 听 4p 6p，胡 5p 嵌档；雀头 7p7p
        r = calculate_hu_points(
            melds=melds,
            hand_tiles=["7p", "7p", "4p", "6p"],
            win_tile="5p",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="1s",
        )
        self.assertEqual(r["details"]["kanzhang"], 2)
        # 明刻幺九4 + 自摸2 + 嵌档2 = 8
        self.assertEqual(r["tile_hu"], 8)


class TestCaseStudyDiscard9p(unittest.TestCase):
    """案例：副露碰1m+吃123m+吃234m，听 1p/4p。"""

    def setUp(self):
        self.melds = [
            _m(MeldType.PONG, ["1m"] * 3),
            _m(MeldType.CHI, ["1m", "2m", "3m"]),
            _m(MeldType.CHI, ["2m", "3m", "4m"]),
        ]
        self.hand = ["1p", "1p", "4p", "4p"]

    def test_win_1p_zimo_hard(self):
        r = calculate_hu_points(
            melds=self.melds,
            hand_tiles=self.hand,
            win_tile="1p",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="5m",
        )
        # 明刻幺九4 + 暗刻幺九8 + 自摸2 = 14；硬+1
        self.assertEqual(r["tile_hu"], 14)
        self.assertTrue(r["is_hard_hu"])
        self.assertEqual(r["final_hu"], 48)

    def test_win_4p_zimo_hard(self):
        r = calculate_hu_points(
            melds=self.melds,
            hand_tiles=self.hand,
            win_tile="4p",
            is_zimo=True,
            seat_wind="E",
            dealer_tile="5m",
        )
        # 明刻4 + 暗刻中张4 + 自摸2 = 10；硬+1 → 40
        self.assertEqual(r["tile_hu"], 10)
        self.assertEqual(r["final_hu"], 40)


class TestDragonAnkoFan(unittest.TestCase):
    """红中暗刻：8 胡 + 三元翻番。"""

    def test_zhong_anko_adds_dragon_fan(self):
        melds = [
            _m(MeldType.PONG, ["1m"] * 3),
            _m(MeldType.CHI, ["2m", "3m", "4m"]),
            _m(MeldType.CHI, ["5m", "6m", "7m"]),
        ]
        hand = ["C", "C", "W", "W"]
        r = calculate_hu_points(
            melds=melds,
            hand_tiles=hand,
            win_tile="C",
            is_zimo=True,
            seat_wind="S",
            dealer_tile="5p",
            round_wind="E",
        )
        anko = [m for m in r["details"]["melds"] if m["type"] == "anko"]
        self.assertEqual(anko[0]["hu"], 8)
        self.assertEqual(r["details"]["fans"].get("dragon_pung_kong"), 1)
        self.assertTrue(
            any("红中" in x for x in r["details"]["fan_items"]),
            r["details"]["fan_items"],
        )
        # 暗刻8 + 自摸2 + 硬碰硬+红中 = fan≥2
        self.assertGreaterEqual(r["fan"], 2)
        self.assertEqual(r["final_hu"], (r["tile_hu"] + 10) * (2 ** r["fan"]))

    def test_seat_and_round_wind_stack(self):
        """门风=圈风=东：东风刻叠两番。"""
        melds = [
            _m(MeldType.PONG, ["E"] * 3),
            _m(MeldType.CHI, ["2m", "3m", "4m"]),
            _m(MeldType.CHI, ["5m", "6m", "7m"]),
        ]
        hand = ["2p", "2p", "5s", "5s"]
        r = calculate_hu_points(
            melds=melds,
            hand_tiles=hand,
            win_tile="5s",
            is_zimo=False,
            seat_wind="E",
            dealer_tile="9p",
            round_wind="E",
        )
        self.assertEqual(r["details"]["fans"].get("seat_wind_pung_kong"), 1)
        self.assertEqual(r["details"]["fans"].get("round_wind_pung_kong"), 1)
        self.assertTrue(any("本门风" in x for x in r["details"]["fan_items"]))
        self.assertTrue(any("圈风" in x for x in r["details"]["fan_items"]))


if __name__ == "__main__":
    unittest.main()
