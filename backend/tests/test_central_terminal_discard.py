import pytest

from app.core.ev_engine import (
    _build_rem_map, _central_synergy_keep_score, _terminal_has_extension,
    calculate_best_discards,
)
from app.schemas import PlayerState


HAND = ['2m', '4m', '7m', '9m', '1p', '2p', '5p', '7p', '8p', '9p',
        '5s', '5s', 'C', '9s']


@pytest.mark.parametrize('with_opponent', [False, True])
def test_terminal_beats_central_with_equal_progress(with_opponent):
    # 九条另有一张可见，但不在该对手牌河，得到 18% / 6% 条件铳率。
    result = calculate_best_discards(
        HAND, '3p', False, 'S', discarded_tiles=['9s'] if with_opponent else [],
        opponents=[PlayerState(seat_wind='E', is_dealer=True)] if with_opponent else [],
        include_self_gang=False,
    )
    by = {c['tile']: c for c in result['candidates']}
    nine, five = by['9s'], by['5p']
    assert result['best_tile'] == '9s'
    assert nine['shanten'] == five['shanten'] == 2
    assert nine['effective_count'] == five['effective_count'] == 15
    assert nine['ev_score'] - five['ev_score'] >= 20
    for c in by.values():
        assert c['ev_score'] == pytest.approx(
            c['attack_ev'] - c['defense_loss'] - c['shanten'] * 120, abs=0.0002)
    if with_opponent:
        assert five['deal_in_risks']['E'] == pytest.approx(0.18)
        assert nine['deal_in_risks']['E'] == pytest.approx(0.06)
        assert five['defense_loss'] > nine['defense_loss'] * 4


def test_far_pair_is_not_extension_and_central_supply_matters():
    rem = _build_rem_map(HAND, [], [], '3p')
    assert not _terminal_has_extension('9s', HAND, '3p', rem)
    assert _central_synergy_keep_score(HAND, '3p', rem) >= 12
    assert _central_synergy_keep_score(HAND, '3p', {**rem, '4p': 0, '6p': 0}) == 0


def test_suit_symmetry():
    swap = {'m': 'p', 'p': 's', 's': 'm'}
    hand = [t[0] + swap[t[1]] if len(t) == 2 else t for t in HAND]
    result = calculate_best_discards(hand, '3s', False, 'S', include_self_gang=False)
    assert result['best_tile'] == '9m'
