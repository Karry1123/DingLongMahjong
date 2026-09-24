"""POST /api/calculate-hu 接口测试。

也可手动验证（后端默认 http://localhost:8000）：

curl -X POST http://localhost:8000/api/calculate-hu ^
  -H "Content-Type: application/json" ^
  -d "{\\"hand_tiles\\":[\\"1p\\",\\"1p\\",\\"4p\\",\\"4p\\"],\\"melds\\":[{\\"meld_type\\":\\"pong\\",\\"tiles\\":[\\"1m\\",\\"1m\\",\\"1m\\"]},{\\"meld_type\\":\\"chi\\",\\"tiles\\":[\\"1m\\",\\"2m\\",\\"3m\\"]},{\\"meld_type\\":\\"chi\\",\\"tiles\\":[\\"2m\\",\\"3m\\",\\"4m\\"]}],\\"win_tile\\":\\"1p\\",\\"is_zimo\\":true,\\"seat_wind\\":\\"E\\",\\"dealer_tile\\":\\"5m\\",\\"restored_jokers\\":0,\\"base_hu\\":10,\\"is_dealer\\":false}"
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app


class TestCalculateHuApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_calculate_hu_hard_zimo(self):
        payload = {
            "hand_tiles": ["1p", "1p", "4p", "4p"],
            "melds": [
                {"meld_type": "pong", "tiles": ["1m", "1m", "1m"]},
                {"meld_type": "chi", "tiles": ["1m", "2m", "3m"]},
                {"meld_type": "chi", "tiles": ["2m", "3m", "4m"]},
            ],
            "win_tile": "1p",
            "is_zimo": True,
            "seat_wind": "E",
            "dealer_tile": "5m",
            "restored_jokers": 0,
            "base_hu": 10,
            "is_dealer": False,
        }
        res = self.client.post("/api/calculate-hu", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["tile_hu"], 14)
        self.assertEqual(data["base_hu"], 10)
        self.assertEqual(data["fan"], 1)
        self.assertEqual(data["final_hu"], 48)
        self.assertTrue(data["is_hard_hu"])
        self.assertIn("details", data)
        self.assertIn("melds", data["details"])
        self.assertEqual(data["settlement_factor"], 2.0)
        self.assertEqual(data["settlement_income"], 96.0)

    def test_calculate_hu_invalid_shape_returns_400(self):
        payload = {
            "hand_tiles": ["1p", "1p"],  # 张数不对
            "melds": [],
            "win_tile": "1p",
            "is_zimo": True,
            "seat_wind": "E",
            "dealer_tile": "5m",
        }
        res = self.client.post("/api/calculate-hu", json=payload)
        self.assertEqual(res.status_code, 422)  # Pydantic 校验


if __name__ == "__main__":
    unittest.main()
