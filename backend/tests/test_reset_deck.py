import random
from app.core.deck_engine import setup_new_game, verify_deck_integrity


def test_redeal_is_independent_and_conserves_full_deck():
    old = setup_new_game('E', rng=random.Random(1))
    old['wall_tiles'].clear()
    old['hands']['S'].clear()
    fresh = setup_new_game('E', rng=random.Random(2))
    assert fresh['wall_count'] == len(fresh['wall_tiles']) == 82
    assert fresh['first_turn_seat'] == 'E'
    assert fresh['hand_counts'] == {'E': 14, 'S': 13, 'W': 13, 'N': 13}
    verify_deck_integrity(dealer_tile=fresh['dealer_tile'], hands=fresh['hands'], wall_tiles=fresh['wall_tiles'])
