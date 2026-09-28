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


def test_all_pin_chi_choices_preserve_physical_whiteboard():
    actions = get_available_actions(['P', '7p', '9p'], [], '8p', 'N', 'E', '6p')
    assert [a.tiles for a in actions if a.action_type == ActionType.CHI] == [
        ['P', '7p', '8p'], ['7p', '8p', '9p'],
    ]


@pytest.mark.parametrize('dealer,hand,expected', [
    ('7p', ['P', '9p'], [['P', '8p', '9p']]),
    ('7p', ['P', '6p'], [['6p', 'P', '8p']]),
    ('5p', ['P', '9p'], []),
    ('P', ['P', '9p'], []),
    ('E', ['P', '9p'], []),
    ('8p', ['7p', '9p'], []),
])
def test_whiteboard_is_a_fixed_substitute_not_a_meld_wildcard(dealer, hand, expected):
    actions = get_available_actions(hand, [], '8p', 'N', 'E', dealer)
    assert [a.tiles for a in actions if a.action_type == ActionType.CHI] == expected


@pytest.mark.parametrize('dealer,discard,hand,expected', [
    ('6p', 'P', ['P', 'P', 'P'], {'pong', 'ming_gang'}),
    ('6p', 'P', ['P', 'P'], {'pong'}),
    ('6p', '9p', ['9p', 'P'], set()),
    ('6p', '9p', ['9p', '9p', 'P'], {'pong'}),
    ('P', 'P', ['P', 'P', 'P'], set()),
])
def test_whiteboard_pong_kong_never_use_wildcards(dealer, discard, hand, expected):
    actions = get_available_actions(hand, [], discard, 'N', 'E', dealer)
    assert {a.action_type.value for a in actions if a.action_type in (
        ActionType.PONG, ActionType.MING_GANG,
    )} == expected
