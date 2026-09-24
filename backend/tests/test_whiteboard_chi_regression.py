import pytest

from app.core.action_generator import ActionType, get_available_actions


@pytest.mark.parametrize('dealer,discard,hand,combo', [
    ('7m', '6m', ['P', '8m'], ['6m', 'P', '8m']),
    ('7m', '6m', ['5m', 'P'], ['5m', '6m', 'P']),
    ('8m', '7m', ['P', '9m'], ['7m', 'P', '9m']),
])
def test_whiteboard_in_hand_chi(dealer, discard, hand, combo):
    actions = get_available_actions(hand, [], discard, 'E', 'S', dealer)
    chi = [a.tiles for a in actions if a.action_type == ActionType.CHI]
    assert bool(chi)  # can_chi
    assert combo in chi
    assert not any(a.action_type == ActionType.CHI for a in
                   get_available_actions(hand, [], discard, 'E', 'W', dealer))
