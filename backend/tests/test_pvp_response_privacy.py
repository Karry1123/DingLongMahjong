from tests.test_pvp_clocks import competing, timed
from tests.test_pvp_match import act


def test_response_clocks_and_banks_are_private_on_wire_including_suspension():
    match = competing(); now = timed(match)
    match.time_banks = {wind:30000 for wind in 'ESWN'}
    act(match, 'E', 'discard', '5m')
    assert match.phase == 'response'
    for viewer in 'ESWN':
        view = match.view(viewer)
        assert set(view['clocks']) <= {viewer}
        assert all(view['time_banks'][wind] is None for wind in 'ESWN' if wind != viewer)
        assert view['response_wait']['remaining_ms'] == 6000
    assert match.view('S')['clocks']['S']['paused']
    assert not match.view('W')['clocks']['W']['paused']
    assert not match.view('E')['actions'] and not match.view('N')['actions']
    assert match.view('E')['response_wait'] == match.view('N')['response_wait']
    assert not match.view('E')['clocks'] and not match.view('N')['clocks']
    now[0] += 8500
    assert match.view('W')['time_banks']['W'] == 27500
    assert match.view('N')['time_banks']['W'] is None
    act(match, 'W', 'pass')
    assert match.view('E')['time_banks']['W'] is None
    assert match.view('S')['clocks']['S']['deadline'] == now[0] + 6000
    act(match, 'S', 'pass')
    assert match.phase == 'discard'
    assert match.view('E')['response_wait'] is None
    assert match.view('E')['clocks']['S']['kind'] == 'discard'
    assert match.view('E')['time_banks']['W'] is None
