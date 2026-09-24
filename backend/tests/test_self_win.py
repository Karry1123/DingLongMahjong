"""自摸和牌检测。"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.core.evaluator import check_self_drawn_win
from app.main import app
from app.schemas import Meld, MeldType


class TestCheckSelfDrawnWin(unittest.TestCase):
    def test_simple_zimo_closed(self):
        # 门清和：111m 222m 333m 444m 55m，摸 5m
        hand = [
            "1m",
            "1m",
            "1m",
            "2m",
            "2m",
            "2m",
            "3m",
            "3m",
            "3m",
            "4m",
            "4m",
            "4m",
            "5m",
            "5m",
        ]
        info = check_self_drawn_win(
            hand,
            [],
            dealer_tile="9p",
            seat_wind="E",
            is_dealer=False,
            win_tile="5m",
        )
        self.assertIsNotNone(info)
        assert info is not None
        self.assertTrue(info["is_win"])
        self.assertTrue(info["is_zimo"])
        self.assertTrue(info["is_hard_hu"])
        self.assertGreaterEqual(info["final_hu"], 10)
        self.assertIn("details", info)

    def test_not_win_returns_none(self):
        hand = [
            "1m",
            "2m",
            "3m",
            "4m",
            "5m",
            "6m",
            "7m",
            "8m",
            "9m",
            "1p",
            "2p",
            "3p",
            "4p",
            "9s",
        ]
        self.assertIsNone(
            check_self_drawn_win(
                hand, [], "5m", "E", is_dealer=False, win_tile="9s"
            )
        )

    def test_zimo_with_melds(self):
        hand = ["8m", "8m", "8m", "9m", "9m"]
        melds = [
            Meld(meld_type=MeldType.PONG, tiles=["1m", "1m", "1m"]),
            Meld(meld_type=MeldType.PONG, tiles=["2s", "2s", "2s"]),
            Meld(meld_type=MeldType.CHI, tiles=["3p", "4p", "5p"]),
        ]
        info = check_self_drawn_win(
            hand,
            melds,
            dealer_tile="6m",
            seat_wind="S",
            is_dealer=True,
            win_tile="9m",
        )
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info["payments"]["winner_income"], info["final_hu"] * 3)


class TestSelfWinRecommendApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_recommend_flags_self_win(self):
        payload = {
            "hand_tiles": [
                "1m",
                "1m",
                "1m",
                "2m",
                "2m",
                "2m",
                "3m",
                "3m",
                "3m",
                "4m",
                "4m",
                "4m",
                "5m",
                "5m",
            ],
            "melds": [],
            "discards": [],
            "dealer_tile": "9p",
            "seat_wind": "E",
            "round_wind": "E",
            "is_dealer": False,
            "opponents": [
                {
                    "seat_wind": "S",
                    "is_dealer": False,
                    "melds": [],
                    "discards": [],
                },
                {
                    "seat_wind": "W",
                    "is_dealer": True,
                    "melds": [],
                    "discards": [],
                },
                {
                    "seat_wind": "N",
                    "is_dealer": False,
                    "melds": [],
                    "discards": [],
                },
            ],
        }
        res = self.client.post("/api/recommend", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertTrue(data.get("can_self_win"))
        self.assertIsNotNone(data.get("self_win_info"))
        self.assertTrue(data["self_win_info"]["is_hard_hu"])


if __name__ == "__main__":
    unittest.main()
