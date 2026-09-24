import pytest

from app.core.scoring import MAX_PAYMENT_PER_PLAYER
from app.core.settlement import calculate_final_settlement


def settle(points, winner='S', win_type='ron', side=False):
    players = [dict(seat_wind=s, is_dealer=s == 'E', melds=[], hand_tiles=[])
               for s in 'ESWN']
    if side:
        players[2]['melds'] = [{'meld_type': 'an_gang', 'tiles': ['C'] * 4}]
    return calculate_final_settlement(winner_seat=winner, win_type=win_type,
                                      dealer_tile='8s', players=players, points=points,
                                      discarder_seat='E' if winner != 'E' else 'S')


def test_128_xian_win_pays_100_64_64():
    r = settle(128)
    assert MAX_PAYMENT_PER_PLAYER == 100
    assert r['final_hu'] == 128
    assert r['net_by_seat'] == {'E': -100, 'S': 228, 'W': -64, 'N': -64}
    assert r['payments']['winner_income'] == 228
    assert r['payments']['from_dealer'] == 100
    assert r['payments']['from_each_xian'] == 64
    assert r['seat_details']['E']['payment_capped']
    assert not r['seat_details']['W']['payment_capped']
    assert r['transfers'][0]['raw_amount'] == 128
    assert r['transfers'][0]['transaction_type'] == 'winner_payout'


@pytest.mark.parametrize('winner', ['E', 'S'])
@pytest.mark.parametrize('win_type', ['ron', 'zimo'])
@pytest.mark.parametrize('points', [99, 100, 101, 128, 256, 1024])
@pytest.mark.parametrize('side', [False, True])
def test_cap_zero_sum_and_transfer_consistency(winner, win_type, points, side):
    r = settle(points, winner, win_type, side)
    for seat in 'ESWN':
        paid = sum(t['amount'] for t in r['transfers'] if t['from'] == seat)
        received = sum(t['amount'] for t in r['transfers'] if t['to'] == seat)
        winner_paid = sum(t['amount'] for t in r['transfers']
                          if t['from'] == seat and t['to'] == winner)
        assert winner_paid <= 100 + 1e-8
        assert r['net_by_seat'][seat] == pytest.approx(received - paid, abs=1e-4)
    assert sum(r['net_by_seat'].values()) == pytest.approx(0, abs=1e-4)
    assert r['payments']['winner_income'] == r['net_by_seat'][winner]


def test_exact_limit_does_not_show_clipped_badge():
    assert not settle(100)['seat_details']['E']['payment_capped']


def test_dealer_winner_cap_does_not_consume_mutual_settlement_budget():
    players = [dict(seat_wind=s, is_dealer=s == 'W', melds=[], hand_tiles=[])
               for s in 'ESWN']
    players[1]['melds'] = [{'meld_type': 'pong', 'tiles': ['S'] * 3}]
    players[2]['melds'] = [{'meld_type': 'pong', 'tiles': ['5m'] * 3}]
    players[3]['melds'] = [{'meld_type': 'pong', 'tiles': ['4s'] * 3}]
    result = calculate_final_settlement(
        winner_seat='E', win_type='zimo', dealer_tile='8s', players=players,
        points=104, round_wind='S',
    )
    payouts = result['payments']['winner_payout_transactions']
    mutual = result['payments']['mutual_settlement_transactions']
    assert next(t for t in payouts if t['from'] == 'W')['amount'] == 100
    assert next(t for t in payouts if t['from'] == 'W')['raw_amount'] == 104
    assert next(t for t in mutual if t['from'] == 'W' and t['to'] == 'S')['amount'] == 14
    assert next(t for t in mutual if t['from'] == 'N' and t['to'] == 'S')['amount'] == 7
    assert result['net_by_seat'] == {'E': 204.0, 'S': -31.0, 'W': -114.0, 'N': -59.0}
    assert sum(result['net_by_seat'].values()) == 0
