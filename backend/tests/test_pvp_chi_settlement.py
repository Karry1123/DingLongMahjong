from app.core.pvp_match import WINDS
from tests.pvp_phase4_server import fixture_match
from tests.test_pvp_match import players, act, pass_all, assert_conserved


def test_claimed_chi_tile_and_provider_survive_win_and_broadcast():
    lineup = players()
    lineup[0]['nickname'] = '吃牌房主'
    match = fixture_match(lineup, opening_seconds=0)
    match.begin()
    act(match, 'E', 'discard', '5m')
    act(match, 'S', 'chi')
    pass_all(match)
    act(match, 'S', 'discard', 'F')
    pass_all(match)
    act(match, 'W', 'discard', '2s')
    pass_all(match)
    act(match, 'N', 'discard', '3s')
    pass_all(match)
    act(match, 'E', 'discard', '9p')
    act(match, 'S', 'hu')
    assert_conserved(match)
    for seat in WINDS:
        detail = match.view(seat)['result']['seat_details']['S']
        meld = detail['melds'][0]
        assert meld['meld_type'] == 'chi'
        assert meld['claimed_tile'] == '5m'
        assert meld['provider_seat'] == 'E'
        group = next(g for g in detail['winning_hand_groups'] if g['source'] == 'open')
        assert group['kind'] == 'chi'
        assert group['claimed_tile'] == '5m'
        assert group['provider_seat'] == 'E'
        assert [tile['code'] for tile in group['display_tiles']] == ['3m', '4m', '5m']
