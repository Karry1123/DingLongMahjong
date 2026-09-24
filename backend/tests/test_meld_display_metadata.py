from app.schemas import Meld
from app.core.scoring import calculate_hu_points


def test_claimed_tile_survives_scoring_and_is_not_marked_as_win():
    meld = Meld(meld_type='chi', tiles=['4s', '5s', '6s'], claimed_tile='5s', provider_seat='N')
    result = calculate_hu_points(
        melds=[meld], hand_tiles=['4m','6m','1p','2p','3p','7p','8p','9p','E','E'],
        win_tile='5m', dealer_tile='8s', seat_wind='E', is_zimo=False,
    )
    groups = result['details']['best_decomposition']['winning_hand_groups']
    opened = next(g for g in groups if g['source'] == 'open')
    assert opened['claimed_tile'] == '5s'
    assert opened['provider_seat'] == 'N'
    assert all(not t['is_win_tile'] for t in opened['display_tiles'])
    winner = next(g for g in groups if g['winning_tile_index'] is not None)
    assert winner['tiles'][winner['winning_tile_index']] == '5m'
