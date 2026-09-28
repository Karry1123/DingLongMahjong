import pytest
from fastapi import HTTPException
from app.core.pvp_match import PvpMatch, WINDS
from tests.test_pvp_match import custom, act, players, assert_conserved


def timed(match):
    now = [1000]
    match.now_ms = lambda: now[0]
    # These regressions cover arbitration after the per-hand reserve is exhausted.
    match.time_banks = {wind: 0 for wind in WINDS}
    match.clocks = {}
    match._refresh_clocks()
    return now


def competing():
    return custom({
        "E": "1p 2p 3p 5p 6p 7p 2s 3s 4s E S W N 5m".split(),
        "S": "3m 4m 7m 9m 2p 4p 6p 8p 1s 3s 5s 7s C".split(),
        "W": "5m 5m 1m 4m 7m 1p 4p 7p 1s 4s 7s F P".split(),
        "N": "1m 2m 6m 8m 1p 3p 5p 9p 2s 4s 6s 8s N".split(),
    }, god="9s")


def test_discard_timeout_uses_drawn_tile_at_ten_seconds_and_rejects_late_action():
    match = competing()
    now = timed(match)
    assert match.clocks["E"]["deadline"] == 11000
    old_action = match.options["E"][0]
    command = {"game_id": match.game_id, "revision": match.revision, "action_id": old_action["action_id"]}
    now[0] = 10999
    assert not match.tick()
    now[0] += 1
    with pytest.raises(HTTPException):
        match.act("E", command)
    assert match.tick() and match.rivers["E"] == ["5m"]
    assert match.clocks["S"]["paused"] and match.clocks["S"]["deadline"] is None
    assert match.clocks["W"]["deadline"] == 17000
    assert_conserved(match)


def test_chi_hangs_then_gets_full_six_seconds_only_after_pong_pass():
    match = competing()
    now = timed(match)
    act(match, "E", "discard", "5m")
    chi = next(row for row in match.options["S"] if row["action_type"] == "chi")
    with pytest.raises(HTTPException):
        match.act("S", {"game_id": match.game_id, "revision": match.revision, "action_id": chi["action_id"]})
    now[0] += 4500
    act(match, "W", "pass")
    assert match.clocks["S"]["deadline"] == 11500
    assert not match.clocks["S"]["paused"]
    now[0] = 11499
    assert not match.tick()
    now[0] = 11500
    assert match.tick()
    assert match.phase == "discard" and match.current == "S" and len(match.hands["S"]) == 14
    assert match.clocks["S"]["deadline"] == 21500
    assert_conserved(match)


def test_pong_interrupts_paused_chi_without_waiting_and_timeout_after_claim_has_no_draw():
    match = competing()
    now = timed(match)
    act(match, "E", "discard", "5m")
    act(match, "W", "pong")
    assert match.current == "W" and match.phase == "discard"
    assert not match.options["S"] and "S" not in match.clocks
    assert match.drawn["W"] is None
    fallback = match.hands["W"][-1]
    now[0] += 10000
    assert match.tick() and match.rivers["W"][-1] == fallback
    assert_conserved(match)


def test_pong_timeout_passes_and_resumes_chi_without_spending_its_time():
    match = competing()
    now = timed(match)
    act(match, "E", "discard", "5m")
    now[0] += 6000
    assert match.tick()
    assert match.phase == "response" and not match.options["W"]
    assert match.clocks["S"]["deadline"] == 13000
    act(match, "S", "chi")
    assert match.current == "S" and match.drawn["S"] is None
    assert_conserved(match)


def test_self_draw_timeout_auto_wins_at_six_seconds_and_confirmation_is_idempotent():
    match = custom({"E": "1m 1m 1m 2m 3m 4m 3p 4p 5p 6s 7s 8s C C".split()})
    now = timed(match)
    assert match.clocks["E"]["kind"] == "win" and match.clocks["E"]["deadline"] == 7000
    now[0] += 6000
    assert match.tick() and match.result["win_type"] == "zimo" and not match.clocks
    before = dict(match.scores)
    assert not match.confirm_next("E", match.game_id)
    revision = match.revision
    assert not match.confirm_next("E", match.game_id) and match.revision == revision
    for seat in "SW":
        assert not match.confirm_next(seat, match.game_id)
    assert match.confirm_next("N", match.game_id)
    assert before == match.scores and match.next_dealer == "E"
    with pytest.raises(HTTPException):
        match.confirm_next("S", "old-game")


def test_ron_timeout_preempts_lower_claims_and_preserves_netting():
    match = custom({"E": "1m 4m 5m 6m 2p 3p 4p 7p 8p 9p 2s 3s E F".split(),
                    "S": "2m 3m 4m 5m 6m 2p 3p 4p 6s 7s 8s C C".split()}, god="9s")
    now = timed(match)
    act(match, "E", "discard", "1m")
    assert match.clocks["S"]["kind"] == "win"
    now[0] += 6000
    assert match.tick()
    assert match.phase == "finished" and match.result["winner_seat"] == "S"
    assert abs(sum(match.scores.values())) < 1e-8
    assert match.next_dealer == "S"
    assert_conserved(match)


def test_pong_waits_for_hu_and_nearest_equal_priority_winner_takes_precedence():
    waiting = "2m 3m 4m 5m 6m 2p 3p 4p 6s 7s 8s C C".split()
    match = custom({"E": "1p 1p 5p 5p 7p 7p 2s 2s E S W N F 1m".split(),
                    "S": waiting, "N": list(waiting),
                    "W": "1m 1m 1s 4s 7s 2p 5p 8p 1p 4p 7p F P".split()}, god="9s")
    now = timed(match)
    act(match, "E", "discard", "1m")
    act(match, "W", "pong")
    assert match.phase == "response" and not match.melds["W"]
    act(match, "N", "hu")
    assert match.phase == "response"  # South has the nearer, equally ranked win.
    assert match.clocks["S"]["deadline"] == 7000  # Other responses never reset this clock.
    now[0] = 7000
    assert match.tick() and match.result["winner_seat"] == "S"
    assert not match.melds["W"]
    assert_conserved(match)


@pytest.mark.parametrize("dealer", list(WINDS))
def test_next_dealer_circle_boundary_and_only_real_players_confirm(dealer):
    lineup = players(ai=True)
    lineup[0]["is_ai"] = lineup[1]["is_ai"] = False
    match = PvpMatch(lineup, dealer_seat=dealer)
    assert len(match.hands[dealer]) == 14 and match.current == dealer
    match.phase = "finished"
    match.result = {"kind": "draw"}
    assert match.next_dealer == WINDS[(WINDS.index(dealer) + 1) % 4]
    assert match.circle_complete == (dealer == "N")
    assert not match.confirm_next("E", match.game_id)
    assert match.confirm_next("S", match.game_id)
