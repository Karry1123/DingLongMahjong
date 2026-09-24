"""副露胡头 calculate_meld_points 单测（rule.md §5.1 + §2 白板替身）。"""

from __future__ import annotations

import unittest

from app.core.score_calc import calculate_meld_points
from app.schemas import Meld, MeldType


class TestCalculateMeldPoints(unittest.TestCase):
    def test_chi_always_zero(self):
        """样例 1：吃牌顺子恒为 0 胡。"""
        meld = Meld(meld_type=MeldType.CHI, tiles=["2m", "3m", "4m"])
        self.assertEqual(calculate_meld_points(meld, dealer_tile="7p"), 0)

    def test_pong_mid_vs_terminal(self):
        """样例 2：明刻 — 中张 2 胡，幺九/字牌 4 胡。"""
        mid = Meld(meld_type=MeldType.PONG, tiles=["5m", "5m", "5m"])
        yao = Meld(meld_type=MeldType.PONG, tiles=["1s", "1s", "1s"])
        honor = Meld(meld_type=MeldType.PONG, tiles=["E", "E", "E"])
        self.assertEqual(calculate_meld_points(mid, "3p"), 2)
        self.assertEqual(calculate_meld_points(yao, "3p"), 4)
        self.assertEqual(calculate_meld_points(honor, "3p"), 4)

    def test_whiteboard_substitute_and_kongs(self):
        """样例 3：白板替身 + 明/暗杠分档。

        得=5m（中张）时，碰白板按 5m 计 → 明刻 2 胡；
        得=1p（幺九）时，碰白板按 1p 计 → 明刻 4 胡；
        中张明杠 8 / 暗杠 16；幺九明杠 16 / 暗杠 32。
        """
        pong_p = Meld(meld_type=MeldType.PONG, tiles=["P", "P", "P"])
        self.assertEqual(calculate_meld_points(pong_p, dealer_tile="5m"), 2)
        self.assertEqual(calculate_meld_points(pong_p, dealer_tile="1p"), 4)

        ming_mid = Meld(meld_type=MeldType.MING_GANG, tiles=["6s"] * 4)
        an_mid = Meld(meld_type=MeldType.AN_GANG, tiles=["6s"] * 4)
        ming_yao = Meld(meld_type=MeldType.MING_GANG, tiles=["9m"] * 4)
        an_yao = Meld(meld_type=MeldType.AN_GANG, tiles=["9m"] * 4)
        self.assertEqual(calculate_meld_points(ming_mid, "E"), 8)
        self.assertEqual(calculate_meld_points(an_mid, "E"), 16)
        self.assertEqual(calculate_meld_points(ming_yao, "E"), 16)
        self.assertEqual(calculate_meld_points(an_yao, "E"), 32)

        # 得非白时，明杠白板按得的身份计（得=9s → 幺九明杠 16）
        ming_p = Meld(meld_type=MeldType.MING_GANG, tiles=["P"] * 4)
        self.assertEqual(calculate_meld_points(ming_p, dealer_tile="9s"), 16)


if __name__ == "__main__":
    unittest.main()
