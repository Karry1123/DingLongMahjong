"""PvE latency optimization must preserve the full EV result, not just Top 1."""
from app.core import evaluator
from app.core.ev_engine import calculate_best_discards


def test_pve_cached_search_preserves_full_recommendation(monkeypatch):
    hand = ['3m', '9s', '2m', '1p', '5m', '8s', '2s', '5p',
            '7p', '4s', '9m', '6p', '5m', '7p']
    evaluator.clear_shanten_cache()
    cached = calculate_best_discards(hand, '6p', False, 'S', discarded_tiles=['N'])
    assert evaluator._optimistic_remaining_shanten.cache_info().hits > 0
    assert evaluator._sequences_containing.cache_info().hits > 0
    evaluator.clear_shanten_cache()
    with monkeypatch.context() as patch:
        patch.setattr(evaluator, '_optimistic_remaining_shanten',
                      evaluator._optimistic_remaining_shanten.__wrapped__)
        patch.setattr(evaluator, '_sequences_containing',
                      evaluator._sequences_containing.__wrapped__)
        reference = calculate_best_discards(hand, '6p', False, 'S', discarded_tiles=['N'])
    assert cached == reference
    evaluator.clear_shanten_cache()
