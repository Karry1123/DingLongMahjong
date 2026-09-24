"""白板替身 + 全桌捉铳扫描回归。"""

from __future__ import annotations

import unittest

from app.core.action_generator import find_catch_win_seats, get_available_actions
from app.core.evaluator import check_ron_win
from app.core.mapper import normalize_hand_for_eval, preprocess_hand
from app.schemas import Meld, MeldType


class TestWhiteboardProxyRon(unittest.TestCase):
    def test_normalize_maps_p_to_dealer(self):
        self.assertEqual(
            normalize_hand_for_eval(["4s", "P", "6s", "C"], "5s"),
            ["4s", "5s", "6s", "C"],
        )
        self.assertEqual(
            preprocess_hand(["5s", "P"], "5s"),
            ["JOKER", "5s"],
        )

    def test_north_ron_zhong_with_p_as_5s(self):
        """得=5s：北风 [1m2m3m][4s P 6s][C] + 副露两吃，对西打出中可捉铳。"""
        hand = ["1m", "2m", "3m", "4s", "P", "6s", "C"]
        melds = [
            Meld(meld_type=MeldType.CHI, tiles=["7s", "8s", "9s"]),
            Meld(meld_type=MeldType.CHI, tiles=["1s", "2s", "3s"]),
        ]
        r = check_ron_win(
            hand,
            melds,
            "C",
            "5s",
            "N",
            is_dealer=False,
            discarder_seat="W",
        )
        self.assertIsNotNone(r)
        self.assertEqual(r["action_type"], "catch_win")

        winners = find_catch_win_seats(
            discarded_tile="C",
            provider_seat="W",
            dealer_tile="5s",
            hands_by_seat={"N": hand, "E": ["1m"] * 13, "S": ["2p"] * 13},
            melds_by_seat={"N": melds},
        )
        self.assertEqual(winners, ["N"])

        actions = get_available_actions(hand, melds, "C", "W", "N", "5s")
        types = {a.action_type.value for a in actions}
        self.assertIn("hu", types)


if __name__ == "__main__":
    unittest.main()
