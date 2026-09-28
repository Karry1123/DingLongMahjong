"""Loopback-only browser smoke fixtures; never imported by the production app.

Run from backend: .venv\Scripts\python.exe -m tests.pvp_phase4_server
"""
import os
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from app.core.constants import build_full_deck
from app.core.pvp_match import PvpMatch, WINDS
from tests.test_pvp_clocks import competing


def deal_for(hands, god):
    pool = build_full_deck()
    pool.remove(god)
    for hand in hands.values():
        for tile in hand:
            pool.remove(tile)
    for seat in WINDS:
        if seat not in hands:
            hands[seat], pool = pool[:13], pool[13:]
    return {"hands": hands, "dealer_tile": god, "wall_tiles": pool}


def fixture_match(players, **kwargs):
    name = next(p["nickname"] for p in players if p["is_host"])
    if name.startswith("暗杠"):
        kwargs["deal"] = deal_for({"E": "1m 1m 1m 1m 3m 4m 5m 2p 3p 4p 6s 7s C F".split()}, "9s")
    elif name.startswith('隐私'):
        kwargs['deal'] = deepcopy(competing().deal)
        hands = kwargs['deal']['hands']
        hands['S'], hands['W'], hands['N'] = hands['W'], hands['N'], hands['S']
    elif name.startswith(("抢断", "计时", "耗尽")):
        kwargs["deal"] = competing().deal
    elif name.startswith("结算"):
        kwargs['deal'] = deal_for({'E': '1m 1m 1m 2m 3m 4m 3p 4p 5p 6s 7s 8s C C'.split(),
                                 'S': '9m 9m 9m 8p 8p 8p 8p C C S S 1s 2s 3s'.split()}, '9s')
    elif name.startswith(("自摸", "加时和牌")):
        dealer = kwargs.get("dealer_seat", "E")
        kwargs["deal"] = deal_for({dealer: "1m 1m 1m 2m 3m 4m 3p 4p 5p 6s 7s 8s C C".split()}, "9s")
    elif name.startswith("捉铳"):
        kwargs["deal"] = deal_for({"E": "4m 5m 6m 2p 3p 4p 7p 8p 9p 2s 3s E F 1m".split(),
                                    "S": "2m 3m 4m 5m 6m 2p 3p 4p 6s 7s 8s C C".split()}, "9s")
    elif name.startswith("尾圈") and kwargs.get("hand_number", 1) == 1:
        kwargs["dealer_seat"] = "N"
        kwargs["hand_number"] = 4
        kwargs["deal"] = deal_for({"N": "1m 2m 6m 8m 1p 3p 5p 9p 2s 4s 6s 8s N 9s".split()}, "9s")
        kwargs["deal"]["wall_tiles"] = []  # Deterministic last-turn draw / circle boundary.
    match = PvpMatch(players, **kwargs)
    if name.startswith('结算'):
        match.melds['S'] = [{'meld_type':'pong','tiles':['9m']*3,'provider_seat':'W','claimed_tile':'9m'},
                            {'meld_type':'an_gang','tiles':['8p']*4}]
        for tile in ['9m']*3 + ['8p']*4:
            match.hands['S'].remove(tile)
    # Legacy arbitration smoke fixtures exercise an already-exhausted reserve.
    # The new time-bank fixtures use all four real 30-second reserves.
    if name.startswith(("抢断", "自摸", "捉铳", "尾圈")):
        match.time_banks = {wind: 0 for wind in WINDS}
    return match


if __name__ == "__main__":
    with TemporaryDirectory(prefix="dinglong-phase4-") as folder:
        os.environ["ROOM_DB_PATH"] = str(Path(folder) / "rooms.sqlite3")
        os.environ["PVP_RECORD_DB_PATH"] = str(Path(folder) / "pvp_records.sqlite3")
        os.environ["ALLOWED_ORIGINS"] = "http://127.0.0.1:5182"
        import app.core.rooms_manager as manager
        manager.PvpMatch = fixture_match
        from app.main import app
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
