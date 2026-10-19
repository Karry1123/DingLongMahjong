"""V4 danger-only whitelist, fixed-state probes and discard calibration."""
import copy
import math
from collections import Counter
from tools import v3_experiment as v3
from tools.v3_experiment import ROOT, MANIFEST, CLAIMS, quota_schedule, compare, aggregate, gates, interval

GROUPS = dict(A=('danger_model.BASE_HONOR_LIVE','danger_model.BASE_HONOR_DEAD'),
              B=('danger_model.BASE_MID_456','danger_model.BASE_NEAR_MID','danger_model.BASE_TERMINAL'))
LIMITS = dict(zip(GROUPS['A']+GROUPS['B'], ((.136,.184),(.017,.023),(.153,.207),(.102,.138),(.068,.092))))
KEYS = tuple(LIMITS)

def baseline(group='B'):
    cfg=v3.baseline()
    cfg.update(policy_version='V4-guard', parameter_group=group, name='v4_round1_parent')
    return cfg

def bounds(key):
    from tools.weights import PARAMETERS
    p=baseline()['weights'][key]; lo,hi=LIMITS[key]
    hard=v3.BOUNDS.get(key, PARAMETERS[key])
    return max(lo,hard['min'],PARAMETERS[key]['min'],p*.85,p*.75), min(hi,hard['max'],PARAMETERS[key]['max'],p*1.15,p*1.25)

def validate_v4(cfg):
    parent=baseline(); group=cfg.get('parameter_group')
    if group not in GROUPS or cfg.get('runtime_hashes')!=MANIFEST['source_hashes'] or 'claim_weights' in cfg:
        raise ValueError('V4 provenance/group mismatch')
    for k,v in cfg['weights'].items():
        if k not in GROUPS[group] and v!=parent['weights'][k]: raise ValueError('V4 frozen parameter: '+k)
        if k in GROUPS[group]:
            lo,hi=bounds(k)
            if not lo<=v<=hi:raise ValueError('V4 step/bounds violation: '+k)
    w=cfg['weights']
    if not w[KEYS[1]]<=w[KEYS[0]] or not w[KEYS[2]]>=w[KEYS[3]]>=w[KEYS[4]]:
        raise ValueError('V4 danger ordering violation')
    return cfg

def guard_runtime(cfg, accelerated=True):
    return v3.guard_runtime(cfg,accelerated,KEYS)

def perturb(group,key,scale):
    cfg=baseline(group); cfg['weights'][key]*=scale
    cfg['name']=key.split('.')[-1]+'_'+str(scale)
    return validate_v4(cfg)

def probes():
    return [(g+'_'+k.split('.')[-1]+'_'+str(s),perturb(g,k,s))
            for g,keys in GROUPS.items() for k in keys for s in (.9,.95,1.05,1.1)]

def select_group(probe):
    # Compare flip rates over all key/scale replays. Near-zero means <=1%.
    n=probe['probe_states']
    rates={g:sum(probe.get('probe_'+label+'_flips',0) for label,c in probes() if label.startswith(g+'_'))/(n*4*len(keys)) for g,keys in GROUPS.items()}
    return ('B' if max(rates.values())<=.01 else max(rates,key=rates.get)),rates

def candidates(group,probe):
    # Rank only nonzero probe directions; do not spend screening on zero flips.
    ranked=sorted([(probe.get('probe_'+label+'_flips',0),label,c) for label,c in probes() if label.startswith(group+'_')],key=lambda x:(-x[0],x[1]))
    chosen=[c for flips,label,c in ranked if flips>0][:5]
    if not chosen:chosen=[perturb(group,GROUPS[group][0],.9)]
    return [baseline(group)]+chosen

class Collector(v3.Collector):
    def before(self,match,seat,physical,action,policy):
        super().before(match,seat,physical,action,policy)
        if physical!=self.physical or action['action_type']!='discard':return
        from app.schemas import PlayerState
        from app.core.constants import ALL_TILES
        hand=match.hands[seat]
        public=Counter([match.god]+[t for s in 'ESWN' for t in match.rivers[s]]+[t for s in 'ESWN' for m in match.melds[s] for t in m['tiles']]+list(hand))
        rem={t:max(0,4-public[t]) for t in ALL_TILES}
        opponents=[PlayerState(seat_wind=s,is_dealer=s=='E',melds=match._models(s),discards=match.rivers[s]) for s in 'ESWN' if s!=seat]
        tenpai=policy.modules['tenpai_model'].estimate_opponents_tenpai(opponents,dealer_tile=match.god)
        p=1-math.prod(1-tenpai[o.seat_wind]*policy.modules['danger_model'].estimate_tile_danger(action['tiles'][0],o,rem,match.god,hand_tiles=hand) for o in opponents)
        bucket=min(int(p*10),9)
        self.metrics['cal_n']+=1;self.metrics['cal_brier_sum']+=p*p
        self.metrics[f'cal_{bucket}_n']+=1;self.metrics[f'cal_{bucket}_p']+=p
        self.last_prediction=(p,bucket)

    def finish(self,row,target):
        if row['dealin']==target and row['win_type']=='ron':
            p,bucket=self.last_prediction
            self.metrics['cal_brier_sum']+=1-2*p
            self.metrics[f'cal_{bucket}_y']+=1
            self.metrics['cal_y']+=1

def block(job):
    from tools.arena import play_hand
    seed,index,configs,physical,probes=job
    order=[(physical-1+i)%4 for i in range(4)];result=[]
    for dealer in range(4):
        c=Collector(physical,probes=probes)
        row=play_hand(seed,dealer,configs,'ev',c);c.finish(row,physical)
        row['physical_candidate_seat']=physical
        row['net']=[row['net'][s] for s in order];row['policies']=[row['policies'][s] for s in order]
        for k in ('winner','dealin'):
            if row[k] is not None:row[k]=order.index(row[k])
        result.append(row)
    return result

def calibration(report):
    a=aggregate(report['rows'])
    return dict(n=a['cal_n'],positives=a.get('cal_y',0),brier=a['cal_brier_sum']/a['cal_n'],
                buckets=[dict(range=[i/10,(i+1)/10],n=a.get(f'cal_{i}_n',0),mean_prediction=a.get(f'cal_{i}_p',0)/a[f'cal_{i}_n'] if a.get(f'cal_{i}_n') else None,observed=a.get(f'cal_{i}_y',0)/a[f'cal_{i}_n'] if a.get(f'cal_{i}_n') else None) for i in range(10)])
