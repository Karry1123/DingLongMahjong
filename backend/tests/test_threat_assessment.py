"""Public opponent warning gates for the opening and later round."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.core.threat_assessment import assess_opponent_threats
from app.main import app


class TestOpponentWarningGate(unittest.TestCase):
    def setUp(self):
        self.two_melds = {"seat_wind": "S", "discards": ["4m", "5p"], "melds": [
            {"meld_type": "pong", "tiles": ["E"] * 3},
            {"meld_type": "chi", "tiles": ["2p", "3p", "4p"]},
        ]}

    def test_first_five_rounds_are_quiet_even_with_three_melds(self):
        three_melds = {**self.two_melds, "melds": self.two_melds["melds"] + [
            {"meld_type": "pong", "tiles": ["C"] * 3}
        ]}
        for wall in (80, 70, 64, 56):
            result = assess_opponent_threats([three_melds], "C", wall)[0]
            self.assertEqual((result["level"], result["reason"]), ("safe", "early_round"))
            self.assertNotIn("shanten", result)

    def test_midgame_requires_visible_melds(self):
        for meld_count in (0, 1):
            source = {**self.two_melds, "melds": self.two_melds["melds"][:meld_count]}
            self.assertEqual(assess_opponent_threats([source], "C", 30)[0]["level"], "safe")
        self.assertEqual(assess_opponent_threats([self.two_melds], "C", 50)[0]["level"], "warn")
        self.assertEqual(assess_opponent_threats([self.two_melds], "C", 49)[0]["reason"], "discard_pattern")

    def test_three_melds_warn_at_55_and_tail_is_global(self):
        three = {**self.two_melds, "melds": self.two_melds["melds"] + [
            {"meld_type": "pong", "tiles": ["C"] * 3}
        ]}
        self.assertEqual(assess_opponent_threats([three], "C", 55)[0]["reason"], "many_melds")
        closed = {"seat_wind": "W", "discards": [], "melds": []}
        self.assertEqual(assess_opponent_threats([closed], "C", 25)[0]["reason"], "late_round")

    def test_threat_api_rejects_private_hand_fields(self):
        response = TestClient(app).post("/api/game/threats", json={
            "dealer_tile": "C", "wall_count": 40,
            "opponents": [{**self.two_melds, "hand_tiles": ["1m"] * 7}],
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn("hand_tiles", response.text)


if __name__ == "__main__":
    unittest.main()
