"""POST /api/game/step 时序步进与错误边界。"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app


def _base_state_13(**overrides):
    """待摸/响应：13 门清。"""
    payload = {
        "hand_tiles": [
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
    payload.update(overrides)
    return payload


def _base_state_14(**overrides):
    """待切：14 门清。"""
    p = _base_state_13()
    p["hand_tiles"] = p["hand_tiles"] + ["4p"]
    p.update(overrides)
    return p


class TestGameStepApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_self_ming_gang_from_west_uses_bound_discard_position(self):
        hand = ["9s"] * 3 + ["1m", "2m", "3m", "4m", "5m", "6m", "1p", "2p", "3p", "E"]
        payload = _base_state_13(
            hand_tiles=hand,
            opponents=[
                {"seat_wind": "S", "is_dealer": False, "melds": [], "discards": []},
                {"seat_wind": "W", "is_dealer": True, "melds": [], "discards": ["2p", "9s", "3p"]},
                {"seat_wind": "N", "is_dealer": False, "melds": [], "discards": ["7p"]},
            ],
            event={
                "actor_seat": "E", "event_type": "MELD", "tile": "9s",
                "provider_seat": "W", "claimed_discard_index": 1,
                "meld": {"meld_type": "ming_gang", "tiles": ["9s"] * 4,
                         "claimed_tile": "9s", "provider_seat": "W"},
            },
        )
        response = self.client.post("/api/game/step", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        after = response.json()["updated_state"]
        west = next(o for o in after["opponents"] if o["seat_wind"] == "W")
        north = next(o for o in after["opponents"] if o["seat_wind"] == "N")
        self.assertEqual(west["discards"], ["2p", "3p"])
        self.assertEqual(north["discards"], ["7p"])
        self.assertEqual(after["hand_tiles"], hand[3:])
        self.assertEqual(after["melds"][0]["provider_seat"], "W")
        self.assertEqual(response.json()["action_phase"], "DRAW")

        payload["event"]["claimed_discard_index"] = 0
        wrong = self.client.post("/api/game/step", json=payload)
        self.assertEqual(wrong.status_code, 400)
        self.assertIn("原响应位置", wrong.json()["detail"])

    def test_chi_claims_only_bound_provider_river_tail_when_two_rivers_match(self):
        state = _base_state_13(
            discards=["7p"],
            opponents=[
                {"seat_wind": "S", "is_dealer": False, "melds": [], "discards": []},
                {"seat_wind": "W", "is_dealer": True, "melds": [], "discards": []},
                {"seat_wind": "N", "is_dealer": False, "melds": [], "discards": ["7p"]},
            ],
            event={
                "actor_seat": "S", "event_type": "MELD", "tile": "7p",
                "provider_seat": "E",
                "meld": {"meld_type": "chi", "tiles": ["5p", "6p", "7p"],
                         "claimed_tile": "7p", "provider_seat": "E"},
            },
        )
        res = self.client.post("/api/game/step", json=state)
        self.assertEqual(res.status_code, 200, res.text)
        after = res.json()["updated_state"]
        self.assertEqual(after["discards"], [])
        north = next(o for o in after["opponents"] if o["seat_wind"] == "N")
        south = next(o for o in after["opponents"] if o["seat_wind"] == "S")
        self.assertEqual(north["discards"], ["7p"])
        self.assertEqual(south["melds"][0]["provider_seat"], "E")
        self.assertEqual(south["melds"][0]["claimed_tile"], "7p")

        # 事件与副露记录不能各自指向一条同名牌河。
        state["event"]["meld"]["provider_seat"] = "N"
        conflicting = self.client.post("/api/game/step", json=state)
        self.assertEqual(conflicting.status_code, 422)
        self.assertIn("provider_seat 不一致", str(conflicting.json()["detail"]))
        state["event"]["meld"]["provider_seat"] = "E"

        # 无来源时拒绝猜测；旧牌即使同名也不得被搜走。
        state["event"].pop("provider_seat")
        state["event"]["meld"].pop("provider_seat")
        ambiguous = self.client.post("/api/game/step", json=state)
        self.assertEqual(ambiguous.status_code, 400)
        self.assertIn("供牌方不明确", ambiguous.json()["detail"])

        state["event"]["provider_seat"] = "E"
        state["discards"] = ["7p", "4p"]
        stale = self.client.post("/api/game/step", json=state)
        self.assertEqual(stale.status_code, 400)
        self.assertIn("牌河末张", stale.json()["detail"])

    def test_pass_uses_bound_provider_when_rivers_end_with_same_tile(self):
        payload = _base_state_13(
            discards=["7p"],
            opponents=[
                {"seat_wind": "S", "is_dealer": False, "melds": [], "discards": []},
                {"seat_wind": "W", "is_dealer": True, "melds": [], "discards": []},
                {"seat_wind": "N", "is_dealer": False, "melds": [], "discards": ["7p"]},
            ],
            event={"actor_seat": "S", "event_type": "PASS", "tile": "7p",
                   "provider_seat": "E"},
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["next_turn_seat"], "S")

    def test_guest_wind_priority_and_round_wind_through_api(self):
        from tests.test_guest_wind_discard import HAND

        for circle in ("E", "W"):
            for endpoint in ("/api/recommend", "/api/game/step"):
                with self.subTest(circle=circle, endpoint=endpoint):
                    payload = _base_state_14(
                        hand_tiles=list(HAND), dealer_tile="5m",
                        seat_wind="E", is_dealer=True, round_wind=circle,
                        opponents=[],
                    )
                    if endpoint.endswith("step"):
                        payload["hand_tiles"] = HAND[:-1]
                        payload["event"] = {
                            "event_type": "DRAW", "actor_seat": "E", "tile": HAND[-1],
                        }
                    res = self.client.post(endpoint, json=payload)
                    self.assertEqual(res.status_code, 200, res.text)
                    rec = res.json()
                    if endpoint.endswith("step"):
                        rec = rec["recommend_discard"]
                    if circle == "E":
                        self.assertEqual(rec["best_tile"], "W")
                        self.assertIn("优先切除无役客风", rec["candidates"][0]["note"])
                    else:
                        west = next(c for c in rec["candidates"] if c["tile"] == "W")
                        self.assertNotIn("优先切除无役客风孤张", west["note"])
                        self.assertFalse(west.get("guest_pruning_bonus"))

    def test_self_draw_returns_discard_recommend(self):
        payload = _base_state_13(
            event={"actor_seat": "E", "event_type": "DRAW", "tile": "4p"}
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["action_phase"], "DISCARD")
        self.assertTrue(data["need_self_action"])
        self.assertEqual(data["next_turn_seat"], "E")
        self.assertIsNotNone(data["recommend_discard"])
        self.assertIsNone(data["call_decision"])
        self.assertEqual(
            len(data["updated_state"]["hand_tiles"]), 14
        )

    def test_opponent_discard_with_pong_enters_call(self):
        payload = _base_state_13(
            event={
                "actor_seat": "S",
                "event_type": "DISCARD",
                "tile": "5m",
            }
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["action_phase"], "CALL")
        self.assertTrue(data["need_self_action"])
        self.assertEqual(data["next_turn_seat"], "E")
        self.assertIsNotNone(data["call_decision"])
        types = {
            c["action"]["action_type"]
            for c in data["call_decision"]["candidates"]
        }
        self.assertIn("pong", types)
        self.assertIn("pass", types)
        # 牌河已写入南家
        south = next(
            o
            for o in data["updated_state"]["opponents"]
            if o["seat_wind"] == "S"
        )
        self.assertEqual(south["discards"][-1], "5m")

    def test_opponent_discard_no_call_waits_next(self):
        payload = _base_state_13(
            hand_tiles=[
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
            ],
            event={
                "actor_seat": "S",
                "event_type": "DISCARD",
                "tile": "9s",
            },
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["action_phase"], "WAIT")
        self.assertFalse(data["need_self_action"])
        self.assertEqual(data["next_turn_seat"], "W")  # S 的下家
        self.assertIsNone(data["call_decision"])
        self.assertIsNone(data["recommend_discard"])

    def test_self_meld_after_claim_returns_discard(self):
        # 南家已出 5m 在河；自家碰后待切
        state = _base_state_13(
            opponents=[
                {
                    "seat_wind": "S",
                    "is_dealer": False,
                    "melds": [],
                    "discards": ["5m"],
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
            event={
                "actor_seat": "E",
                "event_type": "MELD",
                "tile": "5m",
                "provider_seat": "S",
                "meld": {
                    "meld_type": "pong",
                    "tiles": ["5m", "5m", "5m"],
                },
            },
        )
        res = self.client.post("/api/game/step", json=state)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["action_phase"], "DISCARD")
        self.assertTrue(data["need_self_action"])
        self.assertIsNotNone(data["recommend_discard"])
        # 手牌去掉 2 张 5m，副露 +1 → 11+3=14
        self.assertEqual(len(data["updated_state"]["melds"]), 1)
        self.assertEqual(
            len(data["updated_state"]["hand_tiles"])
            + 3 * len(data["updated_state"]["melds"]),
            14,
        )
        south = next(
            o
            for o in data["updated_state"]["opponents"]
            if o["seat_wind"] == "S"
        )
        self.assertNotIn("5m", south["discards"])

    def test_pass_advances_to_next_of_provider(self):
        payload = _base_state_13(
            opponents=[
                {
                    "seat_wind": "S",
                    "is_dealer": False,
                    "melds": [],
                    "discards": ["9s"],
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
            event={
                "actor_seat": "E",
                "event_type": "PASS",
                "tile": "9s",
                "provider_seat": "S",
            },
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["action_phase"], "WAIT")
        self.assertFalse(data["need_self_action"])
        self.assertEqual(data["next_turn_seat"], "W")

    def test_ming_gang_enters_draw_for_kong_replacement(self):
        """明杠后 slots=13 → action_phase=DRAW，须岭上补牌。"""
        payload = _base_state_13(
            hand_tiles=[
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
                "2s",
                "2s",
                "2s",
            ],
            opponents=[
                {
                    "seat_wind": "S",
                    "is_dealer": False,
                    "melds": [],
                    "discards": ["2s"],
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
            event={
                "actor_seat": "E",
                "event_type": "MELD",
                "tile": "2s",
                "provider_seat": "S",
                "meld": {
                    "meld_type": "ming_gang",
                    "tiles": ["2s", "2s", "2s", "2s"],
                },
            },
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["action_phase"], "DRAW")
        self.assertTrue(data["need_self_action"])
        self.assertEqual(data["next_turn_seat"], "E")
        self.assertIsNone(data["recommend_discard"])
        state = data["updated_state"]
        # 暗手 10 + 1 杠面子 → slots=13
        self.assertEqual(len(state["hand_tiles"]), 10)
        self.assertEqual(len(state["melds"]), 1)
        self.assertEqual(state["melds"][0]["meld_type"], "ming_gang")
        south = next(o for o in state["opponents"] if o["seat_wind"] == "S")
        self.assertNotIn("2s", south["discards"])

    def test_recommend_after_meld_uses_dynamic_hand_count(self):
        """副露后切牌：hand+3*melds==14（暗手 11），允许 /api/recommend。"""
        payload = {
            "hand_tiles": [
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
            ],
            "melds": [
                {"meld_type": "pong", "tiles": ["3s", "3s", "3s"]},
            ],
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
        self.assertTrue(data.get("best_tile") or data.get("candidates"))

    # ---- 错误边界 ----

    def test_draw_without_tile_422(self):
        payload = _base_state_13(
            event={"actor_seat": "E", "event_type": "DRAW"}
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 422)

    def test_draw_when_already_14_400(self):
        payload = _base_state_14(
            event={"actor_seat": "E", "event_type": "DRAW", "tile": "1s"}
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("13", res.json()["detail"])

    def test_discard_missing_tile_in_hand_400(self):
        payload = _base_state_14(
            event={
                "actor_seat": "E",
                "event_type": "DISCARD",
                "tile": "9s",
            }
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("9s", res.json()["detail"])

    def test_meld_without_meld_body_422(self):
        payload = _base_state_13(
            event={"actor_seat": "E", "event_type": "MELD", "tile": "5m"}
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 422)

    def test_meld_river_missing_claimed_tile_400(self):
        payload = _base_state_13(
            event={
                "actor_seat": "E",
                "event_type": "MELD",
                "tile": "5m",
                "meld": {
                    "meld_type": "pong",
                    "tiles": ["5m", "5m", "5m"],
                },
            }
        )
        res = self.client.post("/api/game/step", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("牌河", res.json()["detail"])

    def test_recommend_rejects_13_tile_hand(self):
        payload = _base_state_13()
        res = self.client.post("/api/recommend", json=payload)
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
