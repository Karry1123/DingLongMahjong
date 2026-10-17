"""Shared 12 EV weights and a cheap, explicitly approximate exploration policy."""
import math
from collections import Counter
from tools.weights import POOL, load_weights

CORE_KEYS = [
    'ev_engine.SHANTEN_PENALTY', 'ev_engine._DEEP_SHANTEN_UNIT',
    'ev_engine._UKEIRE_QUALITY_WEIGHT', 'ev_engine._SHAPE_JOKER',
    'ev_engine._JOKER_MID_CUT_PENALTY', 'ev_engine._YAKUHAI_SINGLE_POTENTIAL',
    'ev_engine._YAKUHAI_PAIR_POTENTIAL', 'ev_engine._JANTOU_BREAK_PENALTY',
    'ev_engine._GOOD_SHAPE_DEFENSE_SCALE', 'ev_engine._DEFENSE_RISK_REFERENCE',
    'tenpai_model._SIGMOID_CENTER', 'tenpai_model._SIGMOID_STEEPNESS',
]
V0 = load_weights(POOL/'baseline_v0.json')['weights']

def exploration_scores(match, seat, rows, weights):
    """Retention proxy, not shanten/EV: only public tiles and own hand are read.

    Ratios project the same EV core parameters into cheap local shape features.
    Exact EV is always required for validation, even if the proxy scores well.
    """
    def ratio(name): return weights['ev_engine.'+name]/V0['ev_engine.'+name]
    counts = Counter(match.hands[seat])
    public = Counter(t for s in 'ESWN' for t in match.rivers[s])
    public.update(t for s in 'ESWN' for m in match.melds[s] for t in m['tiles'])
    pairs = sum(n >= 2 for t,n in counts.items() if t != match.god)
    center = weights['tenpai_model._SIGMOID_CENTER']
    steep = weights['tenpai_model._SIGMOID_STEEPNESS']
    scores = []
    for a in rows:
        if a['action_type'] != 'discard': continue
        tile = a['tiles'][0]
        face = match.god if tile == 'P' and match.god != 'P' else tile
        value = 100*ratio('_SHAPE_JOKER') if tile == match.god else 0
        duplicates = counts[tile]-1
        value += 12*duplicates*(ratio('SHANTEN_PENALTY')+ratio('_DEEP_SHANTEN_UNIT'))/2
        if duplicates == 1 and pairs == 1: value += 8*ratio('_JANTOU_BREAK_PENALTY')
        if len(face) == 2:
            rank,suit = int(face[0]),face[1]
            value += 4-abs(5-rank)
            for d in (-2,-1,1,2):
                near = f'{rank+d}{suit}'
                value += counts[near]*(5 if abs(d)==1 else 2)*ratio('SHANTEN_PENALTY')
                if 1 <= rank+d <= 9 and counts[near]:
                    value += .3*max(0,4-counts[near]-public[near]-(near==match.god))*ratio('_UKEIRE_QUALITY_WEIGHT')
            if counts[match.god] and rank in (4,5,6): value += 3*ratio('_JOKER_MID_CUT_PENALTY')
            danger = .18 if rank in (4,5,6) else .08 if rank in (1,9) else .12
        else:
            if face in (seat,'C','F','P'):
                value += 2*ratio('_YAKUHAI_PAIR_POTENTIAL' if duplicates else '_YAKUHAI_SINGLE_POTENTIAL')
            danger = .02 if public[tile] >= 2 else .16
        # Kept danger is expensive to discard; actual EV uses the richer public model.
        if public[tile]+counts[tile]+(tile==match.god) < 4:
            for s in 'ESWN':
                if s == seat or tile in match.rivers[s]: continue
                turn = len(match.rivers[s])
                prior = .028+.52/(1+math.exp(-steep*(turn-center)))
                prior = min(.95,prior+.14*len(match.melds[s]))
                discount = ratio('_GOOD_SHAPE_DEFENSE_SCALE') if pairs >= 2 else 1
                value += 25*danger*prior*discount/ratio('_DEFENSE_RISK_REFERENCE')
        scores.append((a,value))
    return scores

def choose_exploration(match, seat, rows, weights):
    if match.phase == 'response':
        # Claim legality remains authoritative; proxy conservatively uses PvP fast claims.
        return next((a for a in rows if a['action_type'] in ('ming_gang','pong')), next(a for a in rows if a['action_type']=='pass'))
    kong = next((a for a in rows if a['action_type'] in ('an_gang','bu_gang')), None)
    if kong: return kong
    return min(exploration_scores(match,seat,rows,weights),key=lambda item:item[1])[0]
