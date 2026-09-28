from app.core.ev_engine import calculate_best_discards
from app.schemas import PlayerState


HAND = [
    '2m', '4m', '6m', '1p', '8p', '1s', '3s', '7s', '8s',
    'E', 'N', 'C', 'F', '5s',
]


def test_seen_guest_wind_outweighs_god_neighbor_singleton_with_more_live_and_specific_genbutsu():
    opponents = [
        PlayerState(seat_wind='E', is_dealer=True),
        PlayerState(seat_wind='S'),
        PlayerState(seat_wind='W', discards=['E']),
    ]
    result = calculate_best_discards(
        hand_tiles=HAND,
        dealer_tile='3p',
        is_dealer=False,
        seat_wind='N',
        round_wind='S',
        discarded_tiles=['E'],
        opponents=opponents,
        include_self_gang=False,
    )
    by_tile = {candidate['tile']: candidate for candidate in result['candidates']}
    east = by_tile['E']
    one_pin = by_tile['1p']

    assert east['effective_count'] > one_pin['effective_count']
    # East is genbutsu only for the opponent who discarded it, not for every player.
    assert east['deal_in_risks']['W'] == 0
    assert east['deal_in_risks']['E'] > 0
    assert east['deal_in_risks']['S'] > 0
    assert one_pin['deal_in_risks']['W'] > 0
    assert east['dealer_neighbor_keep_bonus'] == 15.0
    assert one_pin['dealer_neighbor_keep_bonus'] == 0.0
    assert result['best_tile'] == 'E'
    assert east['ev_score'] > one_pin['ev_score']
