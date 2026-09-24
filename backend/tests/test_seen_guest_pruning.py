import pytest

from app.core.ev_engine import (
    _apply_seen_guest_dominance, _build_rem_map, _is_guest_wind_single,
    _yakuhai_potential_score, calculate_best_discards,
)
from app.schemas import PlayerState

HAND = ['1m', '1m', '1m', '8m', '9m', '1p', '7p', '2s',
        '7s', '8s', '8s', '9s', '9s', 'E']
OPPONENTS = [PlayerState(seat_wind='N', discards=['E']),
             PlayerState(seat_wind='E', is_dealer=True), PlayerState(seat_wind='W')]


@pytest.mark.parametrize('global_river', [[], ['E']])
def test_seen_east_is_unique_best_with_more_ukeire(global_river):
    result = calculate_best_discards(HAND, '6p', False, 'S',
                                    discarded_tiles=global_river, opponents=OPPONENTS,
                                    include_self_gang=False, round_wind='W')
    by = {c['tile']: c for c in result['candidates']}
    assert result['best_tile'] == 'E'
    east = by['E']
    assert east['effective_count'] == 19
    assert max(east['deal_in_risks'].values()) == 0.02
    assert east['guest_pruning_bonus'] == 0  # 基础估值本身已修正，无需强抬分。
    for tile in ['1p', '2s', '7p']:
        assert by[tile]['effective_count'] == 18
        assert east['ev_score'] > by[tile]['ev_score']
    for c in by.values():
        assert c['ev_score'] == pytest.approx(
            c['attack_ev'] - c['defense_loss'] - c['shanten'] * 120, abs=0.0002)


def test_wind_single_vs_actual_scoring_identity():
    rem = _build_rem_map(HAND, ['E'], [], '6p')
    assert _yakuhai_potential_score(['E'], '6p', 'S', rem, 'E') == 0
    assert _yakuhai_potential_score(['E', 'E'], '6p', 'S', rem, 'E') > 0
    assert not _is_guest_wind_single('S', ['S'], '6p', 'S', 'E')
    assert not _is_guest_wind_single('E', ['E'], '6p', 'S', 'E')
    assert not _is_guest_wind_single('E', ['E'], 'E', 'S', 'E')
    assert not _is_guest_wind_single('P', ['P'], 'E', 'S', 'E')


@pytest.mark.parametrize('shanten,ukeire,risk,rem_e,applies', [
    (2, 18, 0.08, 2, True), (1, 18, 0.08, 2, False),
    (2, 20, 0.08, 2, False), (2, 18, 0, 2, False),
    (2, 18, 0.08, 3, False),
])
def test_dominance_guard_scope(shanten, ukeire, risk, rem_e, applies):
    east = dict(tile='E', shanten=2, effective_count=19, deal_in_risks={'W': 0.02},
                defense_loss=1, attack_ev=11, ev_score=-230, note='')
    number = dict(tile='1p', shanten=shanten, effective_count=ukeire,
                  deal_in_risks={'W': risk}, defense_loss=2, attack_ev=42,
                  ev_score=-200, note='')
    _apply_seen_guest_dominance([east, number], HAND, '6p', 'S', 'W', {'E': rem_e})
    assert (east['ev_score'] > number['ev_score']) == applies
    assert east['ev_score'] == east['attack_ev'] - east['defense_loss'] - 240
