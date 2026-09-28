import pytest
from fastapi import HTTPException
from app.core.pvp_match import WINDS
from tests.test_pvp_match import custom, act, assert_conserved
from tests.test_pvp_clocks import competing, timed


def reserve(match):
    now = timed(match)
    match.time_banks = {wind: 30000 for wind in WINDS}
    return now


def test_bank_transition_accepts_action_and_preserves_exact_unused_milliseconds():
    match = competing()
    now = reserve(match)
    now[0] = 11000
    assert not match.tick()
    for viewer in WINDS:
        view = match.view(viewer)
        assert view['clocks']['E']['stage'] == 'bank'
        assert view['clocks']['E']['deadline'] == 41000
        assert view['time_banks']['E'] == 30000
    now[0] = 13450
    act(match, 'E', 'discard', '5m')
    assert match.time_banks['E'] == 27550
    now[0] += 4000
    assert match.view('E')['time_banks']['E'] == 27550
    assert match.view('S')['time_banks']['S'] == 30000  # Paused chi spends nothing.
    assert match.view('S')['time_banks']['E'] is None
    assert_conserved(match)


def test_exhausted_reserve_auto_discards_and_never_returns_on_a_later_turn():
    match = competing()
    now = reserve(match)
    now[0] = 40999
    assert not match.tick()
    assert match.view('N')['time_banks']['E'] == 1
    row = next(a for a in match.options['E'] if a['action_type'] == 'discard')
    now[0] = 41000
    with pytest.raises(HTTPException):
        match.act('E', {'game_id':match.game_id,'revision':match.revision,'action_id':row['action_id']})
    assert match.tick() and match.rivers['E'] == ['5m']
    assert match.time_banks['E'] == 0
    match._draw('E'); match._refresh_clocks()
    assert match.clocks['E']['deadline'] == now[0] + 10000
    now[0] += 10000
    assert match.tick() and match.time_banks['E'] == 0
    assert_conserved(match)


def test_response_bank_then_pass_resumes_full_chi_clock_without_drain():
    match = competing()
    now = reserve(match)
    act(match, 'E', 'discard', '5m')
    now[0] += 8500
    assert not match.tick()
    assert match.view('W')['time_banks']['W'] == 27500
    assert match.view('S')['time_banks']['S'] == 30000
    act(match, 'W', 'pass')
    assert match.time_banks['W'] == 27500
    assert match.clocks['S']['deadline'] == now[0] + 6000
    now[0] += 8000
    act(match, 'S', 'chi')
    assert match.time_banks['S'] == 28000
    assert match.clocks['S']['kind'] == 'discard'
    assert match.view('N')['time_banks']['S'] == 28000
    assert_conserved(match)


def test_hu_uses_six_seconds_plus_reserve_and_auto_wins_only_at_final_expiry():
    match = custom({'E':'1m 1m 1m 2m 3m 4m 3p 4p 5p 6s 7s 8s C C'.split()})
    now = reserve(match)
    now[0] += 6000
    assert not match.tick() and match.view('S')['clocks']['E']['stage'] == 'bank'
    now[0] += 29999
    assert not match.tick()
    now[0] += 1
    assert match.tick() and match.result['win_type'] == 'zimo'
    assert match.time_banks['E'] == 0
    assert sum(match.scores.values()) == 0


def test_ai_discard_clocks_are_public_but_response_clocks_are_private_and_delays_are_per_action():
    match = competing()
    match.players['E']['is_ai'] = True
    match.players['W']['is_ai'] = True
    now = reserve(match)
    assert 'E' in match.view('S')['clocks']
    now[0] += 5999
    assert match.bot_action(ready_only=True) is None
    now[0] += 1
    assert match.bot_action(ready_only=True)[0] == 'E'
    act(match, 'E', 'discard', '5m')
    assert 'W' not in match.view('S')['clocks']
    assert match.view('W')['clocks']['W']['kind'] == 'response'
    now[0] += 2999
    assert match.bot_action(ready_only=True) is None
    now[0] += 1
    seat, choice = match.bot_action(ready_only=True)
    assert seat == 'W' and choice['action_type'] == 'pong'
    match.act(seat, {'game_id':match.game_id,'revision':match.revision,'action_id':choice['action_id']})
    assert match.bot_action(ready_only=True) is None
    now[0] += 6000
    assert match.bot_action(ready_only=True)[0] == 'W'
    assert match.time_banks['W'] == 30000


def test_new_hand_has_four_fresh_reserves():
    match = competing()
    reserve(match)
    match.time_banks['E'] = 0
    other = custom({})
    assert other.time_banks == {wind:30000 for wind in WINDS}
