"""Lone honors use public river/meld visibility when offense is equivalent."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.core.danger_model import estimate_tile_danger
from app.core.pool_tracker import get_remaining_tiles
from app.main import app
from app.schemas import HandRequest, Meld, MeldType, PlayerState


class TestHonorVisibilityRecommendation(unittest.TestCase):
    def setUp(self):
        self.request = HandRequest(
            hand_tiles=[
                "1m", "2m", "3m", "4p", "5p", "6p", "7s", "8s", "9s",
                "5m", "E", "W", "N", "F",
            ],
            dealer_tile="2s",
            seat_wind="S",
            round_wind="E",
            is_dealer=False,
            opponents=[
                PlayerState(seat_wind="E", is_dealer=True, discards=["E"]),
                PlayerState(seat_wind="W", discards=["E"]),
                PlayerState(seat_wind="N", discards=["W"]),
            ],
        )

    def test_own_copy_does_not_count_as_publicly_seen(self):
        rem = get_remaining_tiles(self.request)
        opponent = self.request.opponents[2]
        self.assertEqual(estimate_tile_danger("E", self.request.opponents[0], rem, "2s", hand_tiles=self.request.hand_tiles), 0.0)
        self.assertAlmostEqual(estimate_tile_danger("E", opponent, rem, "2s", hand_tiles=self.request.hand_tiles), .02)
        self.assertAlmostEqual(estimate_tile_danger("W", self.request.opponents[0], rem, "2s", hand_tiles=self.request.hand_tiles), .09)
        self.assertAlmostEqual(estimate_tile_danger("N", opponent, rem, "2s", hand_tiles=self.request.hand_tiles), .16)

    def test_recommend_api_prefers_two_seen_east(self):
        response = TestClient(app).post("/api/recommend", json=self.request.model_dump())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["best_tile"], "E", data["candidates"][:4])
        honors = {c["tile"]: c for c in data["candidates"] if c["tile"] in {"E", "W", "N"}}
        self.assertEqual(set(honors), {"E", "W", "N"})
        self.assertGreaterEqual(honors["E"]["effective_count"], honors["W"]["effective_count"])
        self.assertGreaterEqual(honors["W"]["effective_count"], honors["N"]["effective_count"])
        self.assertGreater(honors["E"]["ev_score"], honors["W"]["ev_score"])
        self.assertGreater(honors["W"]["ev_score"], honors["N"]["ev_score"])

    def test_public_melds_contribute_to_honor_visibility(self):
        self.request.opponents[1].discards = []
        self.request.opponents[2].discards = []
        self.request.opponents[1].melds = [Meld(meld_type=MeldType.PONG, tiles=["W"] * 3)]
        rem = get_remaining_tiles(self.request)
        self.assertEqual(estimate_tile_danger("W", self.request.opponents[0], rem, "2s", hand_tiles=self.request.hand_tiles), 0.0)


if __name__ == "__main__":
    unittest.main()
