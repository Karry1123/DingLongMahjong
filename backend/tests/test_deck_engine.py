"""牌墙引擎：136 张守恒、发牌与摸牌。"""

from __future__ import annotations

import random
import unittest
from collections import Counter

from fastapi.testclient import TestClient

from app.core.constants import (
    ALL_TILES,
    FULL_DECK_SIZE,
    TILES_PER_TYPE,
    build_full_deck,
)
from app.core.deck_engine import (
    draw_tile_from_wall,
    setup_new_game,
    verify_deck_integrity,
)
from app.main import app


class TestFullDeck(unittest.TestCase):
    def test_build_full_deck_size_and_counts(self):
        deck = build_full_deck()
        self.assertEqual(len(deck), FULL_DECK_SIZE)
        self.assertEqual(FULL_DECK_SIZE, 136)
        counts = Counter(deck)
        self.assertEqual(len(counts), 34)
        for t in ALL_TILES:
            self.assertEqual(counts[t], TILES_PER_TYPE)


class TestSetupNewGame(unittest.TestCase):
    def test_conservation_and_hand_sizes(self):
        rng = random.Random(42)
        deal = setup_new_game("E", rng=rng)
        self.assertEqual(deal["total_tiles"], 136)
        self.assertTrue(deal["shown_occupied"])
        self.assertEqual(deal["dealer_seat"], "E")
        self.assertEqual(deal["first_turn_seat"], "E")
        self.assertEqual(deal["hand_counts"]["E"], 14)
        for s in ("S", "W", "N"):
            self.assertEqual(deal["hand_counts"][s], 13)
        # 136 - 1 - 14 - 39 = 82
        self.assertEqual(deal["wall_count"], 82)
        self.assertEqual(len(deal["wall_tiles"]), 82)

        verify_deck_integrity(
            dealer_tile=deal["dealer_tile"],
            hands=deal["hands"],
            wall_tiles=deal["wall_tiles"],
        )

        # 得不在牌墙、不在手牌重复占用外的额外张
        all_parts = (
            [deal["dealer_tile"]]
            + [t for hand in deal["hands"].values() for t in hand]
            + deal["wall_tiles"]
        )
        self.assertEqual(len(all_parts), 136)
        self.assertEqual(set(Counter(all_parts).values()), {4})

    def test_dealer_south_gets_14(self):
        deal = setup_new_game("S", rng=random.Random(7))
        self.assertEqual(len(deal["hands"]["S"]), 14)
        self.assertEqual(len(deal["hands"]["E"]), 13)
        self.assertEqual(deal["first_turn_seat"], "S")

    def test_invalid_dealer_seat(self):
        with self.assertRaises(ValueError):
            setup_new_game("X")


class TestDrawTile(unittest.TestCase):
    def test_draw_from_head(self):
        wall = ["1m", "2m", "3m"]
        r = draw_tile_from_wall(wall)
        self.assertEqual(r["tile"], "1m")
        self.assertEqual(r["wall_tiles"], ["2m", "3m"])
        self.assertEqual(r["wall_count"], 2)
        self.assertFalse(r["is_exhausted"])
        # 原列表不被原地修改
        self.assertEqual(wall, ["1m", "2m", "3m"])

    def test_empty_wall_marks_draw(self):
        r = draw_tile_from_wall([])
        self.assertIsNone(r["tile"])
        self.assertTrue(r["is_exhausted"])
        self.assertEqual(r["wall_count"], 0)

    def test_draw_until_exhausted_conserves(self):
        deal = setup_new_game("E", rng=random.Random(1))
        wall = list(deal["wall_tiles"])
        drawn = []
        while True:
            r = draw_tile_from_wall(wall)
            if r["tile"] is None:
                break
            drawn.append(r["tile"])
            wall = r["wall_tiles"]
        self.assertEqual(len(drawn), 82)
        # 得+手+已摸 = 136
        total = (
            1
            + sum(len(h) for h in deal["hands"].values())
            + len(drawn)
        )
        self.assertEqual(total, 136)
        counts = Counter(
            [deal["dealer_tile"]]
            + [t for h in deal["hands"].values() for t in h]
            + drawn
        )
        self.assertEqual(set(counts.values()), {4})
        self.assertEqual(len(counts), 34)


class TestAutoDealApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_auto_deal_endpoint(self):
        res = self.client.post(
            "/api/game/auto-deal",
            json={"dealer_seat": "E"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["wall_count"], 82)
        self.assertEqual(data["hand_counts"]["E"], 14)
        self.assertIn(data["dealer_tile"], ALL_TILES)

    def test_draw_card_endpoint(self):
        deal = self.client.post(
            "/api/game/auto-deal",
            json={"dealer_seat": "W"},
        ).json()
        res = self.client.post(
            "/api/game/draw-card",
            json={"wall_tiles": deal["wall_tiles"]},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNotNone(body["tile"])
        self.assertEqual(body["wall_count"], deal["wall_count"] - 1)

    def test_draw_empty_wall(self):
        res = self.client.post(
            "/api/game/draw-card",
            json={"wall_tiles": []},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNone(body["tile"])
        self.assertTrue(body["is_exhausted"])


if __name__ == "__main__":
    unittest.main()
