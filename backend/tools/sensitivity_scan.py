"""R1 offline sensitivity, fixed training states and kong enrichment."""
import copy
import math
import json
import random
from collections import Counter
from tools import v3_experiment as v3
from tools.weights import PARAMETERS

KEYS = (
 'ev_engine.SHANTEN_PENALTY','ev_engine._UKEIRE_QUALITY_WEIGHT',
 'ev_engine._GOOD_SHAPE_DEFENSE_SCALE','tenpai_model._SIGMOID_CENTER',
 'ev_engine._GUEST_WIND_SINGLE_PENALTY','ev_engine._ORPHAN_TERMINAL_UKEIRE_SCALE',
 *('danger_model.'+s for s in ('BASE_HONOR_LIVE','BASE_HONOR_DEAD','BASE_MID_456','BASE_NEAR_MID','BASE_TERMINAL','WALL_BOTH_SIDES_FACTOR','WALL_ONE_SIDE_EDGE_FACTOR')),
 *('tenpai_model.'+s for s in ('_SIGMOID_STEEPNESS','_P_SPAN','_MELD_ADD.1','_MELD_ADD.2')),
 *('ev_engine.'+s for s in ('_SHAPE_RYANMEN','_SHAPE_KANCHAN','_SHAPE_PENCHAN','_YAKUHAI_SINGLE_POTENTIAL','_YAKUHAI_PAIR_POTENTIAL','_JANTOU_BREAK_PENALTY')))
KONGS=('ming_gang','an_gang','bu_gang')
ORDERS=(('danger_model.BASE_HONOR_DEAD','danger_model.BASE_HONOR_LIVE'),
 ('danger_model.BASE_TERMINAL','danger_model.BASE_NEAR_MID','danger_model.BASE_MID_456'),
 ('danger_model.WALL_BOTH_SIDES_FACTOR','danger_model.WALL_ONE_SIDE_EDGE_FACTOR'),
 ('ev_engine._SHAPE_PENCHAN','ev_engine._SHAPE_KANCHAN','ev_engine._SHAPE_RYANMEN'),
 ('ev_engine._YAKUHAI_SINGLE_POTENTIAL','ev_engine._YAKUHAI_PAIR_POTENTIAL','ev_engine._YAKUHAI_PUNG_POTENTIAL'),
 ('tenpai_model._MELD_ADD.1','tenpai_model._MELD_ADD.2','tenpai_model._MELD_ADD.3','tenpai_model._MELD_ADD.4'))

def baseline():
    cfg=v3.baseline();cfg.update(policy_version='V4-R1',name='v4_round2_parent')
    return cfg

def bounds(key):
    w=baseline()['weights'];p=w[key];s=PARAMETERS[key]
    lo,hi=max(.6*p,s['min']),min(1.4*p,s['max'])
    for order in ORDERS:
        if key in order:
            i=order.index(key)
            if i:lo=max(lo,w[order[i-1]])
            if i+1<len(order):hi=min(hi,w[order[i+1]])
    if key=='tenpai_model._P_SPAN':hi=min(hi,.95-w['tenpai_model._P_FLOOR'])
    if s['integer']:lo,hi=math.ceil(lo),math.floor(hi)
    return lo,hi

def validate_r1(cfg):
    p=baseline()
    if cfg.get('runtime_hashes')!=v3.MANIFEST['source_hashes'] or 'claim_weights' in cfg:raise ValueError('R1 provenance')
    changed=[k for k in p['weights'] if cfg['weights'][k]!=p['weights'][k]]
    if len(changed)>1:raise ValueError('R1 single parameter candidates only')
    for k in changed:
        if k not in KEYS:raise ValueError('R1 frozen parameter '+k)
        lo,hi=bounds(k)
        if not lo<=cfg['weights'][k]<=hi:raise ValueError('R1 bounds '+k)
    return cfg

def perturb(key,scale):
    cfg=baseline();lo,hi=bounds(key);x=cfg['weights'][key]*scale
    if PARAMETERS[key]['integer']:x=round(x)
    cfg['weights'][key]=max(lo,min(hi,x));cfg['name']=key+'_'+str(scale)
    return validate_r1(cfg)

def guard_runtime(cfg,accelerated=True):return v3.guard_runtime(cfg,accelerated,KEYS)

class State:
    def __init__(self,m,seat):
        self.seat=seat
        for k in ('god','phase','turns','hands','rivers','melds','last_discard','options'):
            setattr(self,k,copy.deepcopy(getattr(m,k)))
    def _models(self,s):
        from app.schemas import Meld
        return [Meld.model_validate(m) for m in self.melds[s]]

class StateCollector:
    def __init__(self,seed):self.states=[];self.kongs=[];self.metrics=Counter();self.rng=random.Random(seed);self.n=0
    def before(self,m,seat,physical,action,policy):
        legal={a['action_type'] for a in m.options[seat]}
        if any(t in legal for t in KONGS):self.kongs.append(State(m,seat))
        if action['action_type'] in ('hu','self_draw_win'):return
        self.n+=1
        if len(self.states)<8:self.states.append(State(m,seat))
        else:
            j=self.rng.randrange(self.n)
            if j<8:self.states[j]=State(m,seat)
    def after(self,*args):pass

def collect_wall(job):
    from tools.arena import play_hand
    seed,mode=job;cfg=baseline();states=[];kongs=[]
    for d in range(4 if mode=='ev' else 1):
        obs=StateCollector(seed*4+d);play_hand(seed,d,[cfg]*4,mode,obs)
        states.extend(obs.states);kongs.extend(obs.kongs)
    return states,kongs

def descriptor(a):return a['action_type'],tuple(a.get('tiles',[]))

def state_signature(s):
    """Observable decision identity; exclude random game/action identifiers."""
    return json.dumps([s.seat,s.god,s.phase,s.turns,s.hands[s.seat],s.rivers,s.melds,s.last_discard,
                       [descriptor(a) for a in s.options[s.seat]]],sort_keys=True)

def action_scores(policy,s):
    from tools.arena import WINDS, Action, ActionType, PlayerState
    seat=s.seat;rows=s.options[seat]
    opponents=[PlayerState(seat_wind=w,is_dealer=w=='E',melds=s._models(w),discards=s.rivers[w]) for w in WINDS if w!=seat]
    public=[t for w in WINDS for t in s.rivers[w]]
    if s.phase=='response':
        actions=[Action(ActionType(a['action_type']),list(a.get('tiles',[])),s.last_discard['seat']) for a in rows]
        r=policy.modules['call_decision'].evaluate_call_decision(actions,s.hands[seat],s._models(seat),opponents,s.god,seat,'E',seat=='E',discarded_tile=s.last_discard['tile'],discarded_tiles=public,turn_count=s.turns)
        return {descriptor(x.action.to_dict()):x.net_ev for x in r.candidates}
    r=policy.modules['ev_engine'].calculate_best_discards(s.hands[seat],s.god,seat=='E',seat,discarded_tiles=public,melds=s._models(seat),opponents=opponents,include_self_gang=any(a['action_type'] in KONGS for a in rows))
    scores={('discard',(a['tile'],)):a['ev_score'] for a in r['candidates']}
    scores.update({(a['action_type'],(a['tile'],)* (4 if a['action_type']=='an_gang' else 1)):a['ev_score'] for a in r['self_gang_candidates']})
    # Legal descriptors are authoritative (self kong tile arrays vary by type).
    for a in rows:
        if a['action_type'] in KONGS:
            z=next((x for x in r['self_gang_candidates'] if x['action_type']==a['action_type'] and x['tile'] in a['tiles']),None)
            if z:scores[descriptor(a)]=z['ev_score']
    return scores

def scan_key(job):
    from tools.arena import Policy
    key,states=job;parent=Policy(baseline(),'ev');variants=[Policy(perturb(key,s),'ev') for s in (.6,.8,1.2,1.4)]
    counts=[0]*4;deltas=[0.]*4;missing=[0]*4
    for state in states:
        base=descriptor(parent.choose(state,state.seat));scores=None
        for i,p in enumerate(variants):
            a=descriptor(p.choose(state,state.seat))
            if a!=base:
                counts[i]+=1
                if scores is None:scores=action_scores(parent,state)
                if a in scores and base in scores and math.isfinite(scores[a]-scores[base]):deltas[i]+=scores[a]-scores[base]
                else:missing[i]+=1
    n=len(states)*4;flips=sum(counts)
    return dict(key=key,states=len(states),replays=n,flips=flips,rate=flips/n,local_ev_delta=deltas,missing_ev=missing,directions=[dict(scale=s,flips=c,rate=c/len(states),value=p.cfg['weights'][key]) for s,c,p in zip((.6,.8,1.2,1.4),counts,variants)],bounds=bounds(key),mean_flip_ev=sum(deltas)/(flips-sum(missing)) if flips>sum(missing) else None)

def select_candidates(ranking):
    selected=[r for r in ranking if r['rate']>=.01][:3]
    cfgs=[baseline()]
    for r in selected:
        for d in sorted(r['directions'],key=lambda d:(-d['flips'],d['scale']))[:2]:
            cfgs.append(perturb(r['key'],d['scale']))
    return selected,cfgs

def kong_compare(job):
    from tools.arena import Policy
    cfg,states=job;p=Policy(baseline(),'ev');c=Policy(cfg,'ev');counts={t:Counter() for t in KONGS}
    for s in states:
        pa=p.choose(s,s.seat)['action_type'];ca=c.choose(s,s.seat)['action_type']
        winning=any(a['action_type'] in ('hu','self_draw_win') for a in s.options[s.seat])
        scores={} if winning else action_scores(p,s)
        for t in KONGS:
            if not any(a['action_type']==t for a in s.options[s.seat]):continue
            x=counts[t];x['states']+=1;x['parent_take']+=pa==t;x['candidate_take']+=ca==t
            other=max((v for a,v in scores.items() if a[0]!=t),default=-math.inf)
            benefit=max((v for a,v in scores.items() if a[0]==t),default=-math.inf)>other
            x['benefit']+=benefit;x['benefit_parent_take']+=benefit and pa==t;x['benefit_candidate_take']+=benefit and ca==t
    return counts
