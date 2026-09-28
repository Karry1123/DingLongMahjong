"""GM-362005 report: keep the suited core and discard a lone guest North."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.constants import JOKER
from app.core.ev_engine import calculate_best_discards, _deep_quality_ukeire_count
from app.core.mapper import preprocess_hand
from app.schemas import PlayerState

HAND = '3m 6m 6m 7m 3p 4p 2s 4s 7s 8s P N C 4p'.split()

@pytest.mark.parametrize('seat', ['W', 'S'])
@pytest.mark.parametrize('public', [False, True])
def test_reported_hand_discards_north_before_three_man_and_four_pin(seat, public):
    others = [wind for wind in ['E', 'S', 'W', 'N'] if wind != seat]
    rivers = [['S', '1p'], ['W', '9m'], ['9s', '3m']]
    opponents = [PlayerState(seat_wind=wind, is_dealer=wind=='E',
                  discards=rivers[i] if public else []) for i, wind in enumerate(others)]
    result = calculate_best_discards(HAND, 'E', False, seat, round_wind='E',
                 opponents=opponents, discarded_tiles=['W'] if public else [], include_self_gang=False)
    by = {row['tile']:row for row in result['candidates']}
    assert result['best_tile'] == result['candidates'][0]['tile'] == 'N'
    assert by['N']['ev_score'] > by['3m']['ev_score']
    assert all(by['N']['ev_score'] > row['ev_score'] for row in result['candidates'] if row['tile']=='4p')
    assert by['N']['shanten'] > 1
    logical = preprocess_hand(HAND, 'E')
    assert logical.count(JOKER) == 0
    assert logical.count('E') == 1  # P is fixed East, never a joker for N/C.

def test_recommend_endpoint_preserves_seat_and_round_context():
    with TestClient(app) as client:
        response = client.post('/api/recommend', json={'hand_tiles':HAND, 'dealer_tile':'E',
            'seat_wind':'W', 'round_wind':'E', 'is_dealer':False, 'latest_drawn_tile':'4p'})
    assert response.status_code == 200
    result = response.json()
    assert result['best_tile'] == 'N'
    assert result['candidates'][0]['tile'] == 'N'

def test_guest_pair_progress_is_discounted_without_losing_real_ukeire():
    waits = [{'tile':'N', 'rem':3}, {'tile':'4m', 'rem':4}]
    def quality(hand, dealer='E', seat='W', circle='E'):
        return _deep_quality_ukeire_count(hand, waits, dealer, seat_wind=seat, round_wind=circle)
    assert quality(['N', 'P']) == pytest.approx(5.05)
    assert quality(['N', 'E']) == pytest.approx(5.05)  # A joker does not upgrade a guest pair's quality.
    assert quality(['N', 'N']) == 7  # Established pair: a third copy completes a triplet.
    assert quality(['N'], seat='N') == 7
    assert quality(['N'], circle='N') == pytest.approx(5.05)
    assert quality(['N'], dealer='N') == 7  # Drawing the real wildcard stays full value.
    assert _deep_quality_ukeire_count(['N'], waits, 'E', seat_wind='W', shanten=1) == 7
