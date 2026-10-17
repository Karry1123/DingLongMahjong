"""Pure-memory authoritative hands, no service, broadcasts, sleeps or archive writes."""
import hashlib
import json
import math
import random
import time
import types
from collections import Counter
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from app.core import pvp_match
from app.core.pvp_match import PvpMatch, WINDS
from app.core.deck_engine import setup_new_game
from app.core.action_generator import Action, ActionType
from app.core.evaluator import check_self_drawn_win, check_ron_win, is_complete_win
from app.core.mapper import normalize_hand_for_eval
from app.core import action_generator
from app.schemas import Meld
from app.schemas import PlayerState
from tools.weights import load_weights, runtime, fingerprint, POOL
from tools.core_search import choose_exploration

# Bounded exact decision reuse across physical dealer rotations / paired trials.
# Keys contain every observable input and the complete policy fingerprint.
_DECISIONS = {}
_DECISION_LIMIT = 4096

class NullHistory(list):
    def append(self, value): pass

@lru_cache(maxsize=8192)
def _win_info_cached(hand, melds, god, seat, zimo, tile):
    models=[Meld.model_validate(json.loads(m)) for m in melds]
    trial=list(hand) if zimo else list(hand)+[tile]
    if not is_complete_win(normalize_hand_for_eval(trial,god),needed_melds=4-len(models)):return None
    if zimo:return check_self_drawn_win(list(hand),models,god,seat,is_dealer=seat=='E',win_tile=tile)
    return check_ron_win(list(hand),models,tile,god,seat,is_dealer=seat=='E')

def _win_only(tiles, joker_count=0, needed_melds=4):
    # Call legality only asks whether shanten == -1. Skip nonwinning shanten search.
    return -1 if is_complete_win(tiles,joker_count,needed_melds) else 1

_ron_globals=dict(action_generator._can_ron.__globals__,check_win_or_shanten=_win_only)
_fast_ron=types.FunctionType(action_generator._can_ron.__code__,_ron_globals)
_action_globals=dict(action_generator.get_available_actions.__globals__,_can_ron=_fast_ron)
fast_available_actions=types.FunctionType(action_generator.get_available_actions.__code__,_action_globals)
_response_globals=dict(PvpMatch._responses.__globals__,get_available_actions=fast_available_actions)
_fast_responses=types.FunctionType(PvpMatch._responses.__code__,_response_globals,argdefs=PvpMatch._responses.__defaults__)

class HeadlessMatch(PvpMatch):
    _responses=_fast_responses
    def _win_info(self, seat, tile=None, zimo=False):
        return _win_info_cached(tuple(self.hands[seat]),tuple(json.dumps(m,sort_keys=True) for m in self.melds[seat]),self.god,seat,zimo,self.drawn[seat] if zimo else tile)
    def _refresh_clocks(self): pass
    def _event(self, *args, **kwargs): pass

class Policy:
    def __init__(self, cfg, mode):
        self.cfg, self.mode = cfg, mode
        self.fingerprint = fingerprint(cfg)
        self.modules = runtime(cfg)
    def choose(self, match, seat):
        if self.mode != 'ev': return self._choose(match,seat)
        rows=match.options[seat]
        key=(self.fingerprint,seat,match.god,match.phase,match.turns,
             tuple(match.hands[seat]),
             tuple((s,tuple(match.rivers[s]),json.dumps(match.melds[s],sort_keys=True)) for s in WINDS),
             json.dumps(match.last_discard,sort_keys=True),
             tuple((a['action_type'],tuple(a.get('tiles',[]))) for a in rows))
        descriptor=_DECISIONS.get(key)
        if descriptor is None:
            action=self._choose(match,seat)
            descriptor=(action['action_type'],tuple(action.get('tiles',[])))
            if len(_DECISIONS)>=_DECISION_LIMIT: _DECISIONS.pop(next(iter(_DECISIONS)))
            _DECISIONS[key]=descriptor
        return next(a for a in rows if (a['action_type'],tuple(a.get('tiles',[])))==descriptor)
    def _choose(self, match, seat):
        rows = match.options[seat]
        # A legal win always wins immediately; no deliberate win refusal allowed.
        win = next((a for a in rows if a['action_type'] in ('hu', 'self_draw_win')), None)
        if win: return win
        if self.mode == 'fast': return self.fast(match, seat, rows)
        if self.mode == 'explore': return choose_exploration(match,seat,rows,self.cfg['weights'])
        if self.mode == 'claim-explore' and match.phase != 'response':
            # Real claim evaluation; only ordinary discard selection is proxied.
            # The old explore mode ignores claim weights and cannot screen V2.
            if not any(a['action_type'] in ('an_gang','bu_gang') for a in rows):
                return choose_exploration(match,seat,rows,self.cfg['weights'])
        opponents = [PlayerState(seat_wind=s, is_dealer=s == 'E', melds=match._models(s), discards=match.rivers[s]) for s in WINDS if s != seat]
        public = [t for s in WINDS for t in match.rivers[s]]
        if match.phase == 'response':
            actions = [Action(ActionType(a['action_type']), list(a.get('tiles', [])), match.last_discard['seat']) for a in rows]
            result = self.modules['call_decision'].evaluate_call_decision(actions, match.hands[seat], match._models(seat), opponents, match.god, seat, 'E', seat == 'E', discarded_tile=match.last_discard['tile'], discarded_tiles=public, turn_count=match.turns)
            desired = result.recommended_action.to_dict()
            return next(a for a in rows if a['action_type'] == desired['action_type'] and a.get('tiles', []) == desired['tiles'])
        result = self.modules['ev_engine'].calculate_best_discards(match.hands[seat], match.god, seat == 'E', seat, discarded_tiles=public, melds=match._models(seat), opponents=opponents, include_self_gang=any(a['action_type'] in ('an_gang','bu_gang') for a in rows))
        chosen = result['best_action']
        return next(a for a in rows if a['action_type'] == chosen['action_type'] and chosen['tile'] in a['tiles'])
    def fast(self, match, seat, rows):
        w = self.cfg['weights']
        if match.phase == 'response':
            claim = next((a for a in rows if a['action_type'] in ('ming_gang','pong')), None)
            return claim if claim and w['screen.call_bonus'] >= 1 else next(a for a in rows if a['action_type'] == 'pass')
        kong = next((a for a in rows if a['action_type'] in ('an_gang','bu_gang')), None)
        if kong: return kong
        counts = Counter(match.hands[seat])
        public = Counter(t for s in WINDS for t in match.rivers[s])
        public.update(t for s in WINDS for m in match.melds[s] for t in m['tiles'])
        rem = {t: max(0,4-counts[t]-public[t]-(t==match.god)) for t in counts}
        def score(a):
            tile = a['tiles'][0]
            if tile == match.god: return w['screen.joker_keep']
            value = (counts[tile]-1)*w['screen.duplicate_keep']
            face = match.god if tile == 'P' and match.god != 'P' else tile
            if len(face)==2:
                rank,suit=int(face[0]),face[1]
                value += (4-abs(5-rank))*w['screen.central_keep']
                for d in (-2,-1,1,2): value += counts.get(f'{rank+d}{suit}',0)*w['screen.'+('neighbor_keep' if abs(d)==1 else 'gap_keep')]
            elif face in (seat,'C','F','P'): value += w['screen.honor_keep']
            if w['screen.danger_penalty']:
                for s in WINDS:
                    if s!=seat:
                        opp=PlayerState(seat_wind=s,is_dealer=s=='E',melds=match._models(s),discards=match.rivers[s])
                        value += w['screen.danger_penalty']*self.modules['danger_model'].estimate_tile_danger(tile,opp,rem,match.god,hand_tiles=match.hands[seat])
            return value
        return min((a for a in rows if a['action_type']=='discard'),key=score)

def play_hand(seed, dealer, configs, mode='ev'):
    policies=[Policy(c,mode) for c in configs]
    players=[{'seat':i,'is_ai':True,'name':f'AI-{i}'} for i in range(4)]
    match=HeadlessMatch(players,opening_seconds=0,deal=setup_new_game('E',rng=random.Random(seed)),dealer_seat=WINDS[dealer],now_ms=lambda:0)
    match.history=NullHistory();match.begin()
    for steps in range(1200):
        if match.phase=='finished': break
        seat=next((s for s in WINDS if match.options[s]),None)
        if seat is None: raise RuntimeError(f'No legal actor: seed={seed}, phase={match.phase}')
        physical=WINDS.index(match.players[seat]['room_seat'])
        action=policies[physical].choose(match,seat)
        match.act(seat,{'game_id':match.game_id,'revision':match.revision,'action_id':action['action_id']},automatic=True)
    else: raise RuntimeError(f'Nonterminating hand: seed={seed}')
    physical_tiles=Counter([match.god]+match.wall)
    for wind in WINDS:
        physical_tiles.update(match.hands[wind]);physical_tiles.update(match.rivers[wind])
        for meld in match.melds[wind]:physical_tiles.update(meld['tiles'])
    if sum(physical_tiles.values())!=136 or any(n!=4 for n in physical_tiles.values()): raise AssertionError(f'Physical tile conservation failed: seed={seed}')
    result=match.full_settlement
    net=[result['net_by_seat'][match.wind_for_room_seat(s)] for s in WINDS]
    if sum(net)!=0: raise AssertionError('Settlement is not zero sum')
    winner=result.get('winner_seat')
    winner=WINDS.index(match.players[winner]['room_seat']) if winner else None
    provider=result.get('discarder_seat')
    if winner is not None and result.get('win_type') in ('ron','rob_kong'):
        provider=match.last_discard['seat']
    dealin=WINDS.index(match.players[provider]['room_seat']) if provider else None
    return {'seed':seed,'dealer':dealer,'net':net,'winner':winner,'dealin':dealin,'draw':winner is None,'actions':steps,'policies':[fingerprint(c) for c in configs]}

def _block(job):
    seed, configs, mode = job
    # Same wall, all four physical dealers: one statistical cluster.
    try:return [play_hand(seed,d,configs,mode) for d in range(4)]
    except Exception as exc:raise RuntimeError(f'Arena failed: seed={seed}, mode={mode}: {exc}') from exc

def summarize(rows, elapsed, mode):
    n=len(rows);seats=[]
    for s in range(4):
        points=[r['net'][s] for r in rows];wins=sum(r['winner']==s for r in rows)
        seats.append({'seat':s,'wins':wins,'win_rate':wins/n,'hu_rate':wins/n,'positive_net_rate':sum(v>0 for v in points)/n,'deal_in_rate':sum(r['dealin']==s for r in rows)/n,'net_points':sum(points),'mean_net_points':sum(points)/n})
    return {'hands':n,'draw_rate':sum(r['draw'] for r in rows)/n,'elapsed_seconds':elapsed,'hands_per_second':n/elapsed,'mode':mode,'seats':seats,'rows':rows,'kernel_sha256':hashlib.sha256(b''.join((Path(pvp_match.__file__).parent/(name+'.py')).read_bytes() for name in ('pvp_match','deck_engine','action_generator','evaluator','mapper','scoring','settlement','constants'))).hexdigest(),
        'policy_sha256':hashlib.sha256(b''.join((Path(__file__).parent/(name+'.py')).read_bytes() for name in ('arena','weights','core_search','ev_acceleration','shanten_kernel'))+(Path(pvp_match.__file__).parent/'claim_v2.py').read_bytes()).hexdigest()}

def simulate(configs, hands=1000, seed=20261011, workers=1, mode='ev'):
    if hands<=0 or hands%4: raise ValueError('Hands must be a positive multiple of 4 (balanced dealers)')
    if not 1<=workers or mode not in ('ev','fast','explore') or len(configs)!=4: raise ValueError('Invalid arena settings')
    jobs=[(seed+i,configs,mode) for i in range(hands//4)];start=time.perf_counter()
    if workers==1: blocks=map(_block,jobs);rows=[r for block in blocks for r in block]
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor: rows=[r for block in executor.map(_block,jobs,chunksize=1) for r in block]
    return summarize(rows,time.perf_counter()-start,mode)

def evaluate_pool(candidate, hands=1000, seed=20261011, workers=1, mode='ev', pool=None, executor=None, resume_rows=None, progress=None):
    pool=pool or [load_weights(POOL/(n+'.json')) for n in ('baseline_v0','conservative','aggressive')]
    if len({fingerprint(p) for p in pool}) < 2: raise ValueError('Pool needs two distinct stable policies')
    jobs=[]
    for i in range(hands//4):
        rng=random.Random(seed+i);opponents=[rng.choice(pool) for _ in range(3)]
        # Fixed schedule independent of candidate: paired common random numbers.
        # At least two historical policies in every opponent trio prevents self-play.
        if len({fingerprint(p) for p in opponents}) == 1:
            opponents[-1]=next(p for p in pool if fingerprint(p)!=fingerprint(opponents[0]))
        jobs.append((seed+i,[opponents[0],candidate,opponents[1],opponents[2]],mode))
    if hands<=0 or hands%4: raise ValueError('Pool evaluation needs complete four-dealer blocks')
    rows=list(resume_rows or [])
    if len(rows)%4 or len(rows)>hands: raise ValueError('Invalid partial checkpoint')
    for i,row in enumerate(rows):
        job=jobs[i//4]
        if row['seed']!=job[0] or row['dealer']!=i%4 or row['policies']!=[fingerprint(c) for c in job[1]]:raise ValueError('Checkpoint schedule mismatch')
    jobs=jobs[len(rows)//4:]
    start=time.perf_counter()
    def collect(blocks):
        for block in blocks:
            rows.extend(block)
            if progress:progress(rows,time.perf_counter()-start)
    if executor is not None: collect(executor.map(_block,jobs,chunksize=1))
    elif workers==1: collect(map(_block,jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex: collect(ex.map(_block,jobs,chunksize=1))
    report=summarize(rows,time.perf_counter()-start,mode)
    report['candidate_seat']=1
    return report

def paired_comparison(candidate, baseline):
    if candidate['kernel_sha256'] != baseline['kernel_sha256'] or candidate['mode'] != baseline['mode']: raise ValueError('Different kernel or policy mode')
    if candidate.get('policy_sha256') != baseline.get('policy_sha256'): raise ValueError('Different offline policy implementation')
    if len(candidate['rows'])!=len(baseline['rows']): raise ValueError('Unpaired evaluations')
    candidate_seat=candidate.get('candidate_seat',0)
    if candidate_seat!=baseline.get('candidate_seat',0):raise ValueError('Different candidate seats')
    def schedule(r):return (r['seed'],r['dealer'],[p for i,p in enumerate(r['policies']) if i!=candidate_seat])
    deltas=[]
    for i in range(0,len(candidate['rows']),4):
        a,b=candidate['rows'][i:i+4],baseline['rows'][i:i+4]
        if [schedule(r) for r in a]!=[schedule(r) for r in b]: raise ValueError('Walls/dealers/opponents differ')
        deltas.append(sum(x['net'][candidate_seat]-y['net'][candidate_seat] for x,y in zip(a,b))/4)
    mean=sum(deltas)/len(deltas)
    se=math.sqrt(sum((x-mean)**2 for x in deltas)/(len(deltas)-1)/len(deltas)) if len(deltas)>1 else math.inf
    return {'mean_gain_per_hand':mean,'standard_error':se,'clusters':len(deltas),'lower_99_percent':mean-2.576*se}
