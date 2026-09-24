from collections import Counter

import pytest

from app.core.scoring import calculate_best_hu_points
from app.core.settlement import calculate_final_settlement
from app.schemas import SettlementResponse


HAND = ['6m', '7m', '8m', '6p', 'P', '8p', '3s', '4s', '5s', '7s', '8s', '9s', '5p']


@pytest.mark.parametrize('win_type', ['zimo', 'ron'])
@pytest.mark.parametrize('included', [False, True])
def test_settlement_snapshot_groups(win_type, included):
    players = [dict(seat_wind=s, is_dealer=s == 'E', melds=[],
                    hand_tiles=HAND + (['5p'] if included else []) if s == 'E' else [])
               for s in 'ESWN']
    result = calculate_final_settlement(winner_seat='E', win_type=win_type,
                                       dealer_tile='7p', players=players, win_tile='5p')
    payload = SettlementResponse(**result).model_dump()
    groups = payload['seat_details']['E']['winning_hand_groups']
    assert [g['tiles'] for g in groups] == [
        ['6m', '7m', '8m'], ['6p', 'P', '8p'], ['3s', '4s', '5s'],
        ['7s', '8s', '9s'], ['5p', '5p']]
    assert groups[-1]['type'] == 'PAIR'
    assert groups[-1]['winning_tile_index'] == 1
    assert groups[1]['substitutions'] == {'P': '7p'}
    assert sum(d['is_win_tile'] for g in groups for d in g['display_tiles']) == 1
    assert Counter(payload['seat_details']['E']['hand_tiles_with_win']) == Counter(HAND + ['5p'])


def test_open_meld_does_not_consume_concealed_tiles_or_mark_win():
    hand = ['6p', 'P', '3s', '4s', '5s', '7s', '8s', '9s', '5p', '5p']
    melds = [{'meld_type': 'chi', 'tiles': ['6p', '7p', '8p']}]
    result = calculate_best_hu_points(hand_tiles=hand, melds=melds, win_tile='8p',
                                      is_zimo=True, seat_wind='E', dealer_tile='7p')
    groups = result['winning_hand_groups']
    assert groups[0]['winning_tile_index'] is None
    closed = [g for g in groups if g['source'] != 'open']
    assert Counter(t for g in closed for t in g['tiles']) == Counter(hand + ['8p'])
    assert sum(d['is_win_tile'] for g in groups for d in g['display_tiles']) == 1
