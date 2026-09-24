"""暗杠 / 补杠检测与推荐 EV。"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.core.action_generator import ActionType, detect_self_gang_actions, get_legal_turn_actions
from app.core.ev_engine import calculate_best_discards
from app.main import app
from app.schemas import Meld, MeldType


class TestDetectSelfGang(unittest.TestCase):
    def test_drawn_fourth_one_pin_generates_add_kong_and_discard(self):
        hand = ["1p", "1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m", "2s"]
        melds = [Meld(meld_type=MeldType.PONG, tiles=["1p"] * 3)]
        actions = get_legal_turn_actions(hand, melds, "9p")
        self.assertIn(ActionType.KONG_ADD, {a.action_type for a in actions})
        self.assertIn(ActionType.DISCARD, {a.action_type for a in actions})
        self.assertEqual(next(a for a in actions if a.action_type == ActionType.KONG_ADD).tiles, ["1p"] * 4)

    def test_an_gang_four_identical(self):
        hand = [
            "2s",
            "2s",
            "2s",
            "2s",
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
        ]
        actions = detect_self_gang_actions(hand, [], "9p")
        types = {a.action_type for a in actions}
        self.assertIn(ActionType.AN_GANG, types)
        gang = next(a for a in actions if a.action_type == ActionType.AN_GANG)
        self.assertEqual(gang.tiles, ["2s", "2s", "2s", "2s"])

    def test_an_gang_forbidden_on_dealer_tile(self):
        hand = ["9p"] * 4 + [
            "1m",
            "2m",
            "3m",
            "4m",
            "5m",
            "6m",
            "7m",
            "8m",
            "1p",
            "2p",
        ]
        actions = detect_self_gang_actions(hand, [], "9p")
        self.assertEqual(actions, [])

    def test_bu_gang_after_pong(self):
        hand = [
            "2s",
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
        ]
        melds = [Meld(meld_type=MeldType.PONG, tiles=["2s", "2s", "2s"])]
        actions = detect_self_gang_actions(hand, melds, "9p")
        self.assertTrue(
            any(a.action_type == ActionType.BU_GANG for a in actions)
        )


class TestSelfGangRecommendApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_recommend_includes_an_gang_candidate(self):
        payload = {
            "hand_tiles": [
                "2s",
                "2s",
                "2s",
                "2s",
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
        gangs = data.get("self_gang_candidates") or []
        self.assertTrue(gangs, "应返回暗杠候选")
        self.assertEqual(gangs[0]["action_type"], "an_gang")
        self.assertEqual(gangs[0]["tile"], "2s")
        self.assertGreaterEqual(gangs[0]["est_hu_bonus"], 12)

    def test_recommend_selects_add_kong_over_discarding_fourth_one_pin(self):
        payload = {
            "hand_tiles": ["1p", "1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m", "2s"],
            "melds": [{"meld_type": "pong", "tiles": ["1p"] * 3}],
            "discards": [], "dealer_tile": "9p", "seat_wind": "S", "round_wind": "E", "is_dealer": False,
            "opponents": [],
        }
        response = self.client.post("/api/recommend", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["best_tile"], "1p")  # 原切牌器会把第四张当孤张
        self.assertEqual(result["best_action"]["action_type"], "bu_gang")
        self.assertEqual(result["best_action"]["tile"], "1p")
        self.assertEqual(result["self_gang_candidates"][0]["est_hu_bonus"], 12)

    def test_opponent_add_kong_upgrades_pong_without_claiming_river(self):
        payload = {
            "hand_tiles": ["1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m", "2p", "3p", "4p", "2s", "3s"],
            "melds": [], "discards": [], "dealer_tile": "9p", "seat_wind": "E", "round_wind": "E", "is_dealer": True,
            "opponents": [{"seat_wind": "S", "is_dealer": False, "melds": [{"meld_type": "pong", "tiles": ["1p"] * 3}], "discards": []}],
            "event": {"actor_seat": "S", "event_type": "MELD", "tile": "1p", "meld": {"meld_type": "ming_gang", "tiles": ["1p"] * 4}},
        }
        response = self.client.post("/api/game/step", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        opponent = response.json()["updated_state"]["opponents"][0]
        self.assertEqual(len(opponent["melds"]), 1)
        self.assertEqual(opponent["melds"][0]["meld_type"], "ming_gang")
        self.assertEqual(opponent["discards"], [])

    def test_an_gang_step_enters_draw(self):
        payload = {
            "hand_tiles": [
                "2s",
                "2s",
                "2s",
                "2s",
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
            "event": {
                "actor_seat": "E",
                "event_type": "MELD",
                "tile": "2s",
                "meld": {
                    "meld_type": "an_gang",
                    "tiles": ["2s", "2s", "2s", "2s"],
                },
            },
        }
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["action_phase"], "DRAW")
        self.assertEqual(len(data["updated_state"]["hand_tiles"]), 10)
        self.assertEqual(
            data["updated_state"]["melds"][0]["meld_type"], "an_gang"
        )


class TestSelfGangEvEngine(unittest.TestCase):
    def test_calculate_best_discards_attaches_self_gang(self):
        hand = [
            "2s",
            "2s",
            "2s",
            "2s",
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
        ]
        result = calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="9p",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=[],
            melds=[],
            opponents=[],
        )
        self.assertTrue(result["self_gang_candidates"])
        self.assertEqual(result["self_gang_candidates"][0]["tile"], "2s")


if __name__ == "__main__":
    unittest.main()
