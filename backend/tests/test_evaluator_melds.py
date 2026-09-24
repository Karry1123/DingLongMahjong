"""向听 / 和牌判定：needed_melds 与副露场景。"""

from __future__ import annotations

import unittest

from app.core.evaluator import check_win_or_shanten


class TestNeededMelds(unittest.TestCase):
    def test_full_hand_default_needed_4(self):
        """无副露：14 张标准和牌 → -1。"""
        win = (
            ["1m"] * 3
            + ["2m"] * 3
            + ["3m"] * 3
            + ["4m"] * 3
            + ["5m", "5m"]
        )
        self.assertEqual(check_win_or_shanten(win, 0), -1)
        self.assertEqual(check_win_or_shanten(win, 0, needed_melds=4), -1)

    def test_one_open_meld_tenpai(self):
        """已副露 1 组：needed_melds=3，门清 10 张听牌（3×3+1）。"""
        # 暗：1m刻 2m刻 3m刻 + 单钓 5m → 10 张，听 5m
        tenpai = ["1m"] * 3 + ["2m"] * 3 + ["3m"] * 3 + ["5m"]
        self.assertEqual(
            check_win_or_shanten(tenpai, 0, needed_melds=3), 0
        )
        # 摸进 5m → 和
        win = tenpai + ["5m"]
        self.assertEqual(check_win_or_shanten(win, 0, needed_melds=3), -1)

    def test_needed_melds_zero_tanki(self):
        """副露 4 组：needed_melds=0，单钓听牌 / 对子和牌。"""
        self.assertEqual(
            check_win_or_shanten(["5m"], 0, needed_melds=0), 0
        )
        self.assertEqual(
            check_win_or_shanten(["5m", "5m"], 0, needed_melds=0), -1
        )
        # 百搭凑对
        self.assertEqual(
            check_win_or_shanten(["5m", "JOKER"], 0, needed_melds=0), -1
        )

    def test_joker_with_partial_melds(self):
        """副露后仍支持 JOKER：needed_melds=2，用百搭凑刻。"""
        # 需要 2 面子 + 雀头；手牌：1m1m + JOKER(=刻) + 2m2m2m + 3m3m
        tiles = ["1m", "1m", "JOKER", "2m", "2m", "2m", "3m", "3m"]
        self.assertEqual(check_win_or_shanten(tiles, 0, needed_melds=2), -1)


if __name__ == "__main__":
    unittest.main()
