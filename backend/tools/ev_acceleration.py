"""Exact offline memoization; never patches production modules or prunes viable draws."""
from collections import Counter
from functools import lru_cache
from app.core.evaluator import check_win_or_shanten, is_complete_win
from tools.shanten_kernel import shanten

@lru_cache(maxsize=65536)
def _shanten(tiles, jokers, needed):
    return shanten(tiles, jokers, needed)

def cached_shanten(tiles, joker_count=0, needed_melds=4):
    return _shanten(tuple(sorted(tiles)), joker_count, needed_melds)

@lru_cache(maxsize=32768)
def _win(tiles, jokers, needed):
    return is_complete_win(list(tiles), jokers, needed)

def cached_win(tiles, joker_count=0, needed_melds=4):
    return _win(tuple(sorted(tiles)), joker_count, needed_melds)

@lru_cache(maxsize=8192)
def identity_counts(hand, god):
    # Frozen policy only reads this Counter. Counter supplies zero for absent tiles.
    return Counter('JOKER' if t == god else god if t == 'P' and god != 'P' else t for t in hand)

def install(modules):
    ev = modules['ev_engine']
    overlap_original=ev._overlap_pair_ryanmen_shape
    def overlap_physical(hand_tiles,dealer_tile):
        shape=overlap_original(hand_tiles,dealer_tile)
        if shape is not None:
            shape=dict(shape)
            shape['choices']={'P' if t==dealer_tile and dealer_tile!='P' else t for t in shape['choices']}
        return shape
    ev._overlap_pair_ryanmen_shape=overlap_physical
    for mod in (ev, modules['call_decision']):
        mod.check_win_or_shanten = cached_shanten
        if hasattr(mod, 'is_complete_win'): mod.is_complete_win = cached_win
    ev._hand_identity_counts = lambda hand, god: identity_counts(tuple(hand), god)
    original = ev.generate_candidate_discards
    @lru_cache(maxsize=4096)
    def candidates(hand, god, rem, seat, round_wind):
        return tuple(original(hand_tiles=list(hand), dealer_tile=god, rem_map=dict(rem), seat_wind=seat, round_wind=round_wind))
    def select(*, hand_tiles, dealer_tile, rem_map, seat_wind, round_wind='E'):
        return list(candidates(tuple(hand_tiles), dealer_tile, tuple(sorted(rem_map.items())), seat_wind, round_wind))
    ev.generate_candidate_discards = select
    @lru_cache(maxsize=8192)
    def improves(hand, draw, god, rem, seat, needed, base):
        # The just-drawn tile can be discarded, leaving exactly the old hand;
        # that branch cannot strictly improve its already computed shanten.
        trial=list(hand)+[draw]
        if cached_win(ev.preprocess_hand(trial,god),0,needed): return True
        pool=ev._select_discard_candidates(hand_tiles=trial,dealer_tile=god,rem_map=dict(rem),seat_wind=seat)
        original_base=cached_shanten(ev.preprocess_hand(list(hand),god),0,needed)
        for discard in dict.fromkeys([draw,*pool]):
            if discard==draw and original_base>=base: continue
            if discard not in trial: continue
            after=ev._remove_one(trial,discard)
            if cached_shanten(ev.preprocess_hand(after,god),0,needed)<base: return True
        return False
    def draw(*, remain_raw, draw_tile, dealer_tile, rem_map, seat_wind, needed_melds, base_shanten):
        if rem_map.get(draw_tile, 0) <= 0: return False
        return improves(tuple(remain_raw), draw_tile, dealer_tile, tuple(sorted(rem_map.items())), seat_wind, needed_melds, base_shanten)
    ev._draw_improves_shanten = draw
    ev._offline_cache_info = lambda: {'candidates': candidates.cache_info()._asdict(), 'draws': improves.cache_info()._asdict(), 'shanten': _shanten.cache_info()._asdict()}
