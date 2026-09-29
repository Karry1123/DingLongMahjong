import pytest

from app.core.pvp_match import PvpMatch, WINDS
from tests.test_pvp_match import players, act


@pytest.mark.parametrize("dealer", WINDS)
def test_hand_winds_rotate_without_moving_players_or_scores(dealer):
    scores = dict(zip(WINDS, [120, -30, -40, -50]))
    match = PvpMatch(players(), dealer_seat=dealer, scores=scores)
    for index, room_seat in enumerate(WINDS):
        wind = WINDS[(index - WINDS.index(dealer)) % 4]
        assert match.wind_for_room_seat(room_seat) == wind
        view = match.view(wind)
        assert view["seat_wind"] == wind
        assert view["dealer_seat"] == "E"
        assert match.players[wind]["nickname"] == f"玩家{room_seat}"
        assert view["scores"][wind] == scores[room_seat]
        assert len(view["hand_tiles"]) == (14 if wind == "E" else 13)
    assert match.room_scores == scores
    match.phase = "finished"
    match.result = {"winner_seat": "E"}
    assert match.next_dealer == dealer  # Dealer win retains the same mapping.


@pytest.mark.parametrize("wind", ["E", "S"])
def test_new_dealer_and_neighbor_wind_triplets_use_current_wind(wind):
    match = PvpMatch(players(), dealer_seat="S")
    match.god = "9s"
    hand = [wind] * 3 + "2m 3m 4m 3p 4p 5p 6s 7s 8s C C".split()
    match.hands[wind] = hand
    match.current = wind
    match.drawn[wind] = "C"
    match.begin()
    info = match._win_info(wind, zimo=True)
    assert info is not None
    act(match, wind, "self_draw_win")
    detail = match.result["hu_detail"]
    assert detail["final_hu"] == info["final_hu"]
    assert detail["details"]["fans"]["seat_wind_pung_kong"] == 1
    assert match.result["seat_details"][wind]["is_dealer"] == (wind == "E")


@pytest.mark.parametrize("wind", ["E", "S"])
def test_open_own_wind_pong_scores_after_rotation_on_draw(wind):
    match = PvpMatch(players(), dealer_seat="S")
    match.god = "9s"
    match.hands[wind] = "2m 3m 4m 3p 4p 5p 6s 7s 8s C".split()
    match.melds[wind] = [{"meld_type": "pong", "tiles": [wind] * 3}]
    match.wall = []
    match._draw("E")
    inherent = match.result["seat_details"][wind]["inherent"]
    assert any(row["kind"] == "seat_wind" for row in inherent["fan_details"])


def test_non_dealer_win_keeps_scores_with_players_in_next_hand():
    match = PvpMatch(players(), dealer_seat="S")
    match.god = "9s"
    match.hands["S"] = "S S S 2m 3m 4m 3p 4p 5p 6s 7s 8s C C".split()
    match.current = "S"
    match.drawn["S"] = "C"
    match.begin()
    act(match, "S", "self_draw_win")
    assert match.next_dealer == "W"
    following = PvpMatch(players(), dealer_seat=match.next_dealer, scores=match.room_scores)
    assert following.players["E"]["nickname"] == "玩家W"
    for room_seat in WINDS:
        assert following.scores[following.wind_for_room_seat(room_seat)] == match.scores[match.wind_for_room_seat(room_seat)]
