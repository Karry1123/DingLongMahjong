from app.core.danger_model import estimate_tile_danger
from app.core.ev_engine import calculate_best_discards
from app.schemas import Meld, MeldType, PlayerState


def test_124_terminal_is_candidate_and_beats_unsafe_4m():
    hand = ['N', '1m', '2m', '4m', '6m', '7m', '8m', '1s', 'E', 'E', '3s']
    melds = [Meld(meld_type=MeldType.PONG, tiles=['9m'] * 3)]
    opponents = [
        PlayerState(seat_wind=seat, is_dealer=seat == 'N',
                    discards=['1m'] if seat in ('S', 'W') else [], melds=[])
        for seat in ('S', 'W', 'N')
    ]
    result = calculate_best_discards(
        hand, dealer_tile='N', is_dealer=False, seat_wind='E',
        discarded_tiles=['1m', '1m'], melds=melds, opponents=opponents,
        round_wind='E',
    )
    by_tile = {candidate['tile']: candidate for candidate in result['candidates']}
    assert result['best_tile'] == '1m'
    assert by_tile['1m']['ev_score'] > by_tile['4m']['ev_score']
    assert by_tile['1m']['effective_count'] == by_tile['4m']['effective_count']
    assert by_tile['1m']['shape_upgrade_bonus'] == 7.0
    assert by_tile['1m']['anti_pong_safety_bonus'] == 3.0
    assert by_tile['1m']['deal_in_risks']['N'] < by_tile['4m']['deal_in_risks']['N']


def test_two_public_terminal_copies_make_pong_impossible_but_not_ron_safe():
    opponent = PlayerState(seat_wind='S', discards=[], melds=[])
    rem = {tile: 4 for tile in ['1m', '2m', '3m', '4m', '5m', '6m']}
    rem['1m'] = 1  # one in our hand, two publicly seen, one outside unknown pool
    rem['4m'] = 3
    terminal = estimate_tile_danger('1m', opponent, rem, 'N', hand_tiles=['1m'])
    middle = estimate_tile_danger('4m', opponent, rem, 'N', hand_tiles=['4m'])
    assert 0 < terminal < middle
