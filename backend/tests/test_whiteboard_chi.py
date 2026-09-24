import pytest
from app.core.action_generator import get_available_actions, ActionType


@pytest.mark.parametrize('hand,expected', [
    (['7s', '9s'], [['7s', 'P', '9s']]),
    (['6s', '7s'], [['6s', '7s', 'P']]),
    (['6s', '7s', '9s'], [['6s', '7s', 'P'], ['7s', 'P', '9s']]),
    (['9s'], []),
])
def test_south_white_west_chi(hand, expected):
    actions = get_available_actions(hand, [], 'P', 'S', 'W', '8s')
    assert [a.tiles for a in actions if a.action_type == ActionType.CHI] == expected


@pytest.mark.parametrize('seat,dealer', [('E', '8s'), ('N', '8s'), ('W', 'P'), ('W', 'E')])
def test_white_chi_restrictions(seat, dealer):
    actions = get_available_actions(['6s', '7s', '9s'], [], 'P', 'S', seat, dealer)
    assert not any(a.action_type == ActionType.CHI for a in actions)
