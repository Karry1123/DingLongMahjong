import pytest

from app.core.scoring import calculate_best_hu_points, calculate_unwon_base_hu
from app.core.settlement import calculate_final_settlement


HAND = ['P', 'P', 'P', '4m', '5m', '1s', '2s', '3s', '5s', '5s']
RED = {'meld_type': 'pong', 'tiles': ['C'] * 3}


def score(hand=HAND, melds=None, dealer='4p', zimo=False):
    return calculate_best_hu_points(hand_tiles=hand, melds=melds or [RED],
                                    win_tile='6m', is_zimo=zimo,
                                    seat_wind='E', dealer_tile=dealer)


@pytest.mark.parametrize('zimo,points', [(False, 144), (True, 160)])
def test_red_white_hard_stack(zimo, points):
    result = score(zimo=zimo)
    assert result['fan_count'] == result['fan'] == 3
    assert result['details']['fans'] == {'dragon_pung_kong': 2, 'hard_hu': 1}
    assert result['final_hu'] == points
    assert any('白板暗刻' in item for item in result['details']['fan_items'])
    assert any('红中明刻' in item for item in result['details']['fan_items'])


@pytest.mark.parametrize('kind,size', [('pong', 3), ('ming_gang', 4), ('an_gang', 4)])
@pytest.mark.parametrize('dealer', ['4p', 'C', 'F'])
def test_physical_white_open_groups_count_once(kind, size, dealer):
    result = score(hand=HAND[3:], melds=[RED, {'meld_type': kind, 'tiles': ['P'] * size}],
                   dealer=dealer)
    assert result['details']['fans']['dragon_pung_kong'] == 2
    assert sum('白板' in item for item in result['details']['fan_items']) == 1


def test_white_in_sequence_is_not_dragon_triplet():
    result = score(hand=['3p', 'P', '5p'] + HAND[3:])
    assert result['details']['fans']['dragon_pung_kong'] == 1


def test_unwon_white_triplet_preserves_dragon_fan():
    result = calculate_unwon_base_hu(['P'] * 3, [RED], 'E', '4p')
    assert result['fans']['dragon_pung_kong'] == 2
    assert result['calculated_points'] == 8 * 4


def test_settlement_uses_updated_fans_and_points():
    players = [dict(seat_wind=s, is_dealer=s == 'E',
                    hand_tiles=HAND if s == 'E' else [], melds=[RED] if s == 'E' else [])
               for s in 'ESWN']
    result = calculate_final_settlement(winner_seat='E', win_type='ron',
                                       dealer_tile='4p', players=players, win_tile='6m')
    assert result['hu_detail']['fan_count'] == 3
    assert result['final_hu'] == 144
