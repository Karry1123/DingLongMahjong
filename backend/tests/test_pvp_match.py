from collections import Counter
import random

import pytest
from fastapi import HTTPException
from app.core.constants import build_full_deck
from app.core.deck_engine import setup_new_game
from app.core.pvp_match import PvpMatch, WINDS


def players(ai=False):
    return [{"seat_wind": seat, "nickname": f"玩家{seat}", "is_ai": ai, "is_host": seat == "E"} for seat in WINDS]


def seeded(seed=10, ai=False):
    return PvpMatch(players(ai), opening_seconds=0, deal=setup_new_game("E", rng=random.Random(seed)))


def act(match, seat, kind, tile=None):
    row = next(a for a in match.options[seat] if a["action_type"] == kind and (tile is None or tile in a["tiles"]))
    match.act(seat, {"game_id": match.game_id, "revision": match.revision, "action_id": row["action_id"]})


def pass_all(match):
    while match.phase == "response":
        seat = next(s for s in WINDS if match.options[s])
        act(match, seat, "pass")


def assert_conserved(match):
    physical = [match.god] + match.wall
    for seat in WINDS:
        physical += match.hands[seat] + match.rivers[seat]
        for meld in match.melds[seat]:
            physical += meld["tiles"]
    assert len(physical) == 136
    assert Counter(physical) == Counter(build_full_deck())


def custom(hands, god="1s", turn="E"):
    pool = build_full_deck()
    pool.remove(god)
    for hand in hands.values():
        for tile in hand:
            pool.remove(tile)
    hands = dict(hands)
    for seat in WINDS:
        if seat not in hands:
            hands[seat], pool = pool[:13], pool[13:]
    deal = {"dealer_tile": god, "hands": hands, "wall_tiles": pool}
    match = PvpMatch(players(), opening_seconds=0, deal=deal)
    match.current = turn
    match.drawn = {seat: None for seat in WINDS}
    match.drawn[turn] = match.hands[turn][-1]
    match.begin()
    return match


def test_opening_east_dealer_authentication_revision_and_hidden_data():
    match = seeded()
    with pytest.raises(HTTPException):
        match.act("E", {"game_id": match.game_id, "revision": 0, "action_id": "forged"})
    for seat in WINDS:
        view = match.view(seat)
        assert view["dealer_seat"] == "E" and view["current_turn"] == "E"
        assert view["hand_tiles"] == match.hands[seat]
        assert len(view["hand_tiles"]) == (14 if seat == "E" else 13)
        assert "wall_tiles" not in view and "hands" not in view
        assert not any("hand_tiles" in p for p in view["players"])
        assert not any(key in str(view) for key in ["net_ev", "shanten", "ukeire", "danger", "tenpai"])
    match.begin()
    row = match.options["E"][0]
    command = {"game_id": match.game_id, "revision": match.revision, "action_id": row["action_id"]}
    with pytest.raises(HTTPException):
        match.act("S", command)
    match.act("E", command)
    with pytest.raises(HTTPException):
        match.act("E", command)
    pass_all(match)
    assert match.current == "S" and len(match.hands["S"]) == 14
    assert len(match.wall) == 81
    assert_conserved(match)


def test_pong_uses_exact_tiles_and_turn_goes_to_caller():
    match = custom({"E": "1m 1m 3p 3p 3p 7p 8p 8p 9p 2s 3s 4s C".split(), "N": "1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 2p 4p 5p 6p".split()}, turn="N")
    act(match, "N", "discard", "1m")
    act(match, "E", "pong")
    while match.phase == "response":
        seat = next(s for s in WINDS if match.options[s]); act(match, seat, "pass")
    assert match.current == "E" and match.phase == "discard"
    assert match.melds["E"][0]["tiles"] == ["1m"] * 3
    assert "1m" not in match.hands["E"]
    assert not match.rivers["N"]
    assert len(match.hands["E"]) == 11
    assert_conserved(match)
    act(match, "E", "discard", "C")
    pass_all(match)
    assert len(match.hands["E"]) == 10
    assert_conserved(match)


def test_concealed_kong_draws_tail_and_publishes_identity_to_all_views():
    match = custom({"E": "1m 1m 1m 1m 3m 4m 5m 2p 3p 4p 6s 7s C F".split()})
    tail = match.wall[-1]
    act(match, "E", "an_gang", "1m")
    assert match.drawn["E"] == tail and len(match.wall) == 81
    for seat in WINDS:
        view = match.view(seat)
        assert view["players"][0]["melds"][0]["tiles"] == ["1m"] * 4
        assert view["event"]["tile"] == "1m" and view["event"]["action"] == "GANG"
        assert "hands" not in view and "wall_tiles" not in view
    assert_conserved(match)


def test_self_draw_uses_existing_settlement_without_changing_netting():
    match = custom({"E": "1m 1m 1m 2m 3m 4m 3p 4p 5p 6s 7s 8s C C".split()})
    assert any(a["action_type"] == "self_draw_win" for a in match.options["E"])
    act(match, "E", "self_draw_win")
    assert match.phase == "finished" and match.result["win_type"] == "zimo"
    assert abs(sum(match.result["net_by_seat"].values())) < 1e-8
    assert match.result["winner_seat"] == "E"


def test_chi_variant_consumes_physical_whiteboard_substitute():
    match = custom({"E": "6p P 9p 1m 2m 3m 4m 5m 6m 2s 3s C F".split(),
                    "N": "8p 1p 2p 3p 4p 5p 6p 1s 2s 3s 4s 5s 6s C".split()}, god="7p", turn="N")
    act(match, "N", "discard", "8p")
    combos = [row for row in match.options["E"] if row["action_type"] == "chi"]
    assert len(combos) == 2
    chosen = next(row for row in combos if "9p" in row["tiles"])
    match.act("E", {"game_id": match.game_id, "revision": match.revision, "action_id": chosen["action_id"]})
    pass_all(match)
    assert match.current == "E"
    assert match.melds["E"][0]["tiles"] == ["P", "8p", "9p"]
    assert "6p" in match.hands["E"] and "P" not in match.hands["E"]
    assert_conserved(match)


def test_claimed_kong_replaces_from_tail_and_keeps_caller_turn():
    match = custom({"E": "1m 1m 1m 2p 3p 4p 6p 7p 8p 2s 3s C F".split(),
                    "N": "1m 2m 3m 4m 5m 6m 7m 8m 9m 1p 2p 4p 5p 6p".split()}, turn="N")
    tail = match.wall[-1]
    act(match, "N", "discard", "1m")
    act(match, "E", "ming_gang")
    pass_all(match)
    assert match.current == "E" and match.drawn["E"] == tail
    assert match.melds["E"][0]["tiles"] == ["1m"] * 4
    assert len(match.hands["E"]) == 11 and not match.rivers["N"]
    assert_conserved(match)


def test_rob_added_kong_keeps_original_pong_and_existing_settlement():
    match = custom({"E": "1m 1m 1m 1m 4m 5m 6m 1p 2p 3p 7s 8s 9s F".split(),
                    "S": "2m 3m 4m 5m 6m 2p 3p 4p 6s 7s 8s C C".split()}, god="9p")
    for _ in range(3):
        match.hands["E"].remove("1m")
    match.melds["E"] = [{"meld_type": "pong", "tiles": ["1m"] * 3, "claimed_tile": "1m", "provider_seat": "N"}]
    match._turn_options()
    act(match, "E", "bu_gang")
    act(match, "S", "hu")
    pass_all(match)
    assert match.result["win_type"] == "rob_kong" and match.result["winner_seat"] == "S"
    assert match.melds["E"][0]["meld_type"] == "pong"
    assert abs(sum(match.result["net_by_seat"].values())) < 1e-8
    assert_conserved(match)


@pytest.mark.parametrize("seed", range(8))
def test_ai_runs_legal_full_hand_with_conservation(seed):
    match = seeded(seed, ai=True)
    match.begin()
    for _ in range(400):
        assert_conserved(match)
        if match.phase == "finished":
            break
        choice = match.bot_action()
        assert choice is not None
        seat, row = choice
        match.act(seat, {"game_id": match.game_id, "revision": match.revision, "action_id": row["action_id"]})
    assert match.phase == "finished"
