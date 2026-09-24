"""Read-only production connectivity check; game endpoints remain stateless."""

from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

FRONTEND = "https://ding-long-mahjong.vercel.app"
TIMEOUT = 90


def request(url: str, *, method: str = "GET", payload: dict | None = None,
            headers: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method=method, headers=headers or {})
    with urlopen(req, timeout=TIMEOUT) as response:
        data = response.read()
        return response.status, response.headers, data


def main():
    _, _, html = request(FRONTEND + "/")
    asset = re.search(rb'src="(/assets/[^" ]+\.js)"', html)
    assert asset, "Frontend HTML has no JS bundle"
    _, _, bundle = request(FRONTEND + asset.group(1).decode())
    origins = set(re.findall(rb'https://[A-Za-z0-9.-]+\.onrender\.com', bundle))
    assert len(origins) == 1, f"Expected one Render API origin, found {len(origins)}"
    api = origins.pop().decode()
    assert b"localhost:8000" not in bundle, "Production bundle contains localhost fallback"

    status, _, raw = request(api + "/health")
    assert status == 200 and json.loads(raw) == {"status": "ok"}

    common = {"Origin": FRONTEND}
    for path in ("/api/game/auto-deal", "/api/recommend"):
        status, headers, _ = request(api + path, method="OPTIONS", headers={
            **common,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        assert status == 200
        assert headers.get("Access-Control-Allow-Origin") == FRONTEND

    post_headers = {**common, "Content-Type": "application/json"}
    status, headers, raw = request(api + "/api/game/auto-deal", method="POST",
                                   payload={"dealer_seat": "E"}, headers=post_headers)
    deal = json.loads(raw)
    assert status == 200 and headers.get("Access-Control-Allow-Origin") == FRONTEND
    assert len(deal["hands"]["E"]) == 14 and deal["wall_count"] == 82

    hand = {
        "hand_tiles": deal["hands"]["E"], "melds": [], "discards": [],
        "dealer_tile": deal["dealer_tile"], "seat_wind": "E",
        "round_wind": "E", "is_dealer": True,
        "opponents": [{"seat_wind": seat, "is_dealer": False,
                       "melds": [], "discards": []} for seat in "SWN"],
        "discarded_tiles": [],
    }
    status, headers, raw = request(api + "/api/recommend", method="POST",
                                   payload=hand, headers=post_headers)
    recommendation = json.loads(raw)
    assert status == 200 and headers.get("Access-Control-Allow-Origin") == FRONTEND
    assert recommendation["best_tile"] in hand["hand_tiles"]
    assert recommendation["candidates"]
    assert all("ev_score" in candidate and "effective_count" in candidate
               for candidate in recommendation["candidates"])
    print(json.dumps({
        "frontend": FRONTEND, "backend": api, "health": "ok",
        "cors_preflight": "ok", "dealer_hand": len(deal["hands"]["E"]),
        "wall_count": deal["wall_count"],
        "recommend_candidates": len(recommendation["candidates"]),
        "best_tile": recommendation["best_tile"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
