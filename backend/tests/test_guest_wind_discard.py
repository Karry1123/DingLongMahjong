"""已有对子时，优先清理无役客风，保留数牌延伸靠搭。"""

import unittest

from app.core.ev_engine import (
    _apply_equal_ukeire_isolate_tiebreak,
    _build_rem_map,
    _existing_pair_count,
    _isolate_discard_priority,
    _terminal_has_extension,
    calculate_best_discards,
)


HAND = [
    "1p", "4p", "5p", "5p", "2s", "3s", "5s",
    "7s", "8s", "9s", "E", "W", "N", "N",
]


class TestGuestWindDiscard(unittest.TestCase):
    def test_opening_west_beats_one_pin_with_equal_ukeire(self):
        # 原案例未给出得牌；用项目默认 5m，圈风东，无公开弃牌。
        result = calculate_best_discards(
            hand_tiles=HAND, dealer_tile="5m", is_dealer=True,
            seat_wind="E", round_wind="E", include_self_gang=False,
        )
        by = {c["tile"]: c for c in result["candidates"]}
        self.assertEqual(result["best_tile"], "W")
        self.assertEqual(result["candidates"][0]["tile"], "W")
        self.assertEqual(by["W"]["shanten"], 3)
        self.assertEqual(by["W"]["shanten"], by["1p"]["shanten"])
        self.assertEqual(by["W"]["effective_count"], 56)
        self.assertEqual(by["1p"]["effective_count"], 56)
        self.assertGreater(by["W"]["ev_score"], by["1p"]["ev_score"])
        self.assertIn("优先切除无役客风", by["W"]["note"])
        self.assertIn("已有 2 组对子", by["W"]["note"])
        for c in by.values():
            self.assertAlmostEqual(
                c["ev_score"], c["attack_ev"] - c["defense_loss"]
                - c["shanten"] * 120, places=3,
            )

    def test_same_shape_other_suit_and_opposite_terminal(self):
        # 不绑定 1p/W 牌码：同样验证九万与南风。
        hand = [
            f"{10 - int(t[0])}m" if t.endswith("p")
            else "S" if t == "W" else t for t in HAND
        ]
        result = calculate_best_discards(
            hand, "5p", True, "E", include_self_gang=False,
        )
        by = {c["tile"]: c for c in result["candidates"]}
        self.assertEqual(result["best_tile"], "S")
        self.assertGreater(by["S"]["ev_score"], by["9m"]["ev_score"])

    def test_wind_identity_exclusions_and_pair_requirement(self):
        rem = _build_rem_map(HAND, [], [], "5m")
        self.assertEqual(_existing_pair_count(HAND, "5m"), 2)
        self.assertEqual(_isolate_discard_priority("W", HAND, "5m", "E", "E", rem), 2)
        for seat, circle, dealer in [("W", "E", "5m"), ("E", "E", "W")]:
            with self.subTest(seat=seat, circle=circle, dealer=dealer):
                self.assertIsNone(_isolate_discard_priority("W", HAND, dealer, seat, circle, rem))
        substitute_hand = ["P" if t == "W" else t for t in HAND]
        self.assertIsNone(_isolate_discard_priority("P", substitute_hand, "W", "E", "E", rem))
        no_pairs = ["1p", "4p", "5p", "W"]
        self.assertEqual(_existing_pair_count(no_pairs, "5m"), 0)
        self.assertIsNone(_isolate_discard_priority("W", no_pairs, "5m", "E", "E", rem))

    def test_extension_requires_same_suit_and_live_bridge(self):
        rem = _build_rem_map(HAND, [], [], "5m")
        self.assertTrue(_terminal_has_extension("1p", HAND, "5m", rem))
        self.assertFalse(_terminal_has_extension("1p", ["1p", "4s", "5s"], "5m", rem))
        self.assertFalse(_terminal_has_extension("1p", ["1p", "6p"], "5m", rem))
        self.assertFalse(_terminal_has_extension("1p", HAND, "5m", {**rem, "2p": 0, "3p": 0}))
        # 白板承接 4p 的逻辑联系也应计入。
        self.assertTrue(_terminal_has_extension("1p", ["1p", "P"], "4p", rem))

    def test_round_wind_single_has_no_special_retention(self):
        result = calculate_best_discards(
            HAND, "5m", True, "E", round_wind="W", include_self_gang=False,
        )
        west = next(c for c in result["candidates"] if c["tile"] == "W")
        self.assertEqual(result["best_tile"], "W")
        self.assertNotIn("优先切除无役客风孤张", west["note"])

    def test_equal_progress_order_seen_fresh_terminal(self):
        hand = HAND + ["S"]
        rem = _build_rem_map(hand, ["S"], [], "5m")
        rows = []
        for tile, ev in [("1p", 3), ("W", 2), ("S", 1)]:
            rows.append({
                "tile": tile, "ev_score": ev, "shanten": 3,
                "effective_count": 56,
                "_isolate_priority": _isolate_discard_priority(
                    tile, hand, "5m", "E", "E", rem,
                ),
            })
        _apply_equal_ukeire_isolate_tiebreak(rows)
        self.assertEqual([c["tile"] for c in rows], ["S", "W", "1p"])
        rem["S"] = 0
        self.assertEqual(_isolate_discard_priority("S", hand, "5m", "E", "E", rem), 3)

    def test_different_progress_is_not_an_isolate_tie(self):
        for shanten, ukeire in [(2, 56), (3, 60)]:
            with self.subTest(shanten=shanten, ukeire=ukeire):
                rows = [
                    {"tile": "1p", "ev_score": 10, "shanten": shanten,
                     "effective_count": ukeire, "_isolate_priority": 0},
                    {"tile": "W", "ev_score": 9, "shanten": 3,
                     "effective_count": 56, "_isolate_priority": 2},
                ]
                _apply_equal_ukeire_isolate_tiebreak(rows)
                self.assertEqual(rows[0]["tile"], "1p")


if __name__ == "__main__":
    unittest.main()
