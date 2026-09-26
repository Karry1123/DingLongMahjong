"""Completed-game archive and PvE opponent warning regressions."""

import os
import re
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app.core.record_manager import (
    MAX_RECORDS, archive_completed_game, get_game_record, list_game_record_summaries,
)
from app.core.threat_assessment import assess_opponent_threats

try:
    from fastapi.testclient import TestClient
    from app.main import app
except ImportError:
    TestClient = None
    app = None


def completed(round_id):
    return {"round_id": round_id,
            "config": {"dealer_seat": "E", "dealer_tile": "1p", "seat_wind": "E",
                       "initial_hands": {"E": ["1m"]}, "initial_wall_tiles": ["9s", "8s"]},
            "steps": [{"turn": 1, "seat": "E", "action": "DISCARD", "tile": "9s",
                       "self_recommendation": {"best_tile": "9s", "net_ev": 12,
                                               "candidates": [{"tile": "9s", "ev_score": 12}]}}],
            "final_result": {"winner_seat": None, "win_type": "draw", "points": 0}}


class TestGameRecords(unittest.TestCase):
    def test_history_summary_uses_actual_net_and_relative_seats(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "records.sqlite3"
            record = completed("summary-round")
            record["config"]["seat_wind"] = "S"
            record["steps"].append({"turn": 2, "seat": "W", "action": "WIN", "tile": "4m",
                                    "snapshot": {"self": {"roundWind": "E"}}})
            record["final_result"] = {"winner_seat": "W", "win_type": "ron",
                "points": 12, "deal_in_seat": "S", "details": {
                    "net_by_seat": {"S": 21, "W": 24, "N": -15, "E": -30},
                    "hu_detail": {"final_hu": 12, "base_hu": 10, "fan": 0,
                                  "details": {"score_items": [{"label": "明刻 八万", "hu": 2}]}},
                    "payments": {"inherent_detail": {
                        "S": {"calculated_points": 18, "base_hu": 18,
                              "items": ["明杠 九万 (+16胡)"]},
                        "W": {"calculated_points": 2},
                        "N": {"calculated_points": 0}, "E": {"calculated_points": 0}}}}}
            game_id = archive_completed_game(record, db_path=db)["game_id"]
            summary = list_game_record_summaries(db_path=db)[0]
            self.assertEqual(summary["game_id"], game_id)
            self.assertEqual(summary["winner_name"], "下家·西风捉铳 四万")
            self.assertEqual(summary["round_wind"], "E")
            self.assertEqual([(summary[field]["seat"], summary[field]["net"]) for field in
                              ("self_score", "xiajia_score", "duijia_score", "shangjia_score")],
                             [("S", 21), ("W", 24), ("N", -15), ("E", -30)])
            self.assertEqual(summary["self_score"]["hu_items"], ["明杠 九万 (+16胡)"])
            self.assertEqual(summary["xiajia_score"]["hu"], 12)

    def test_only_completed_idempotent_and_retrievable(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "records.sqlite3"
            with self.assertRaises(ValueError):
                archive_completed_game({**completed("unfinished"), "final_result": None}, db_path=db)
            first = archive_completed_game(completed("round-1"), db_path=db)
            duplicate = completed("round-1")
            duplicate["steps"] = []
            second = archive_completed_game(duplicate, db_path=db)
            self.assertRegex(first["game_id"], r"^GM-[0-9A-F]{6}$")
            self.assertEqual(first["game_id"], second["game_id"])
            self.assertEqual(first["steps_count"], second["steps_count"])
            self.assertEqual(first["bytes_written"], second["bytes_written"])
            self.assertGreater(first["bytes_written"], 0)
            record = get_game_record(first["game_id"], db_path=db)
            self.assertEqual(record["config"]["initial_wall_tiles"], ["9s", "8s"])
            self.assertEqual(record["steps"][0]["self_recommendation"]["candidates"][0]["tile"], "9s")

    def test_fifo_evicts_oldest_after_200_and_uses_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "records.sqlite3"
            first = archive_completed_game(completed("round-0"), db_path=db)["game_id"]
            for i in range(1, 200):
                latest = archive_completed_game(completed(f"round-{i}"), db_path=db)["game_id"]
            self.assertEqual(MAX_RECORDS, 200)
            self.assertEqual(len(list_game_record_summaries(db_path=db)), 200)
            self.assertIsNotNone(get_game_record(first, db_path=db))
            # The oldest timestamp wins over insertion order if an imported row is older.
            import sqlite3
            with closing(sqlite3.connect(db)) as connection:
                connection.execute("UPDATE game_records SET timestamp=? WHERE game_id=?",
                                   ("2000-01-01T00:00:00+00:00", latest))
                connection.commit()
            next_record = archive_completed_game(completed("round-200"), db_path=db)["game_id"]
            self.assertIsNotNone(get_game_record(first, db_path=db))
            self.assertIsNone(get_game_record(latest, db_path=db))
            self.assertIsNotNone(get_game_record(next_record, db_path=db))
            last_record = archive_completed_game(completed("round-201"), db_path=db)["game_id"]
            self.assertIsNone(get_game_record(first, db_path=db))
            self.assertIsNotNone(get_game_record(last_record, db_path=db))
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM game_records").fetchone()[0], 200)


class TestOpponentThreats(unittest.TestCase):
    def test_three_melds_switches_from_safe_to_warning(self):
        base = {"seat_wind": "W", "is_dealer": False, "discards": [], "melds": []}
        safe = assess_opponent_threats([base], "1p", 60)[0]
        warned = assess_opponent_threats([{**base, "melds": [
            {"meld_type": "chi", "tiles": tiles} for tiles in
            (["1m", "2m", "3m"], ["4m", "5m", "6m"], ["7m", "8m", "9m"])
        ]}], "1p", 39)[0]
        self.assertEqual(safe["level"], "safe")
        self.assertIn(warned["level"], ("warn", "high"))
        self.assertEqual(warned["reason"], "many_melds")


@unittest.skipIf(TestClient is None, "FastAPI test dependency not installed")
class TestGameRecordApi(unittest.TestCase):
    def test_post_then_get_and_missing_returns_404(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"GAME_RECORD_DB_PATH": str(Path(temp) / "records.sqlite3")}):
            client = TestClient(app)
            payload = completed("api-round")
            payload["config"]["initial_hands"] = {}
            posted = client.post("/api/game/record", json=payload)
            self.assertEqual(posted.status_code, 200, posted.text)
            game_id = posted.json()["game_id"]
            self.assertGreater(posted.json()["bytes_written"], 0)
            self.assertEqual(client.get(f"/api/game/records/{game_id}").json()["round_id"], "api-round")
            listed = client.get("/api/game/records")
            self.assertEqual(listed.status_code, 200, listed.text)
            head = client.head("/api/game/records")
            self.assertEqual(head.status_code, 200, head.text)
            self.assertEqual(head.content, b"")
            detail_head = client.head(f"/api/game/records/{game_id}")
            self.assertEqual(detail_head.status_code, 200)
            self.assertEqual(detail_head.content, b"")
            self.assertEqual(posted.json()["summary"]["game_id"], game_id)
            self.assertEqual(listed.json()["records"][0]["game_id"], game_id)
            self.assertEqual(listed.json()["records"][0]["self_score"]["net"], 0)
            self.assertNotIn("initial_wall_tiles", listed.text)
            self.assertNotIn("initial_hands", listed.text)
            self.assertEqual(client.get("/api/game/records/GM-000000").status_code, 404)

    def test_cloud_lookup_survives_local_ten_game_window(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"GAME_RECORD_DB_PATH": str(Path(temp) / "records.sqlite3")}):
            client = TestClient(app)
            first = archive_completed_game(completed("first"))["game_id"]
            for i in range(10):
                archive_completed_game(completed(f"later-{i}"))
            self.assertEqual(len(client.get("/api/game/records").json()["records"]), 11)
            response = client.get(f"/api/game/records/{first}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["config"]["initial_wall_tiles"], ["9s", "8s"])

    def test_threat_endpoint_reports_three_melds(self):
        client = TestClient(app)
        response = client.post("/api/game/threats", json={"dealer_tile": "1p", "wall_count": 39,
            "opponents": [{"seat_wind": "W", "is_dealer": False, "discards": [],
                           "melds": [{"meld_type": "chi", "tiles": tiles} for tiles in
                                     (["1m", "2m", "3m"], ["4m", "5m", "6m"], ["7m", "8m", "9m"])],
                           }]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["threats"][0]["reason"], "many_melds")
