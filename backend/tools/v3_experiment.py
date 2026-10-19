"""Isolated current V1+guard policies, deterministic quotas and behavioral telemetry.

This module is offline only. The round-one schema permits precisely two changes.
"""
import ast
import copy
import hashlib
import importlib
import json
import math
import random
import sys
import types
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT/'tools/policy_sources/v3_guard'
KEYS = ('ev_engine.SHANTEN_PENALTY', 'ev_engine._UKEIRE_QUALITY_WEIGHT')
LIMITS = ((112, 150), (.76, 1.02))
MANIFEST = json.loads((SNAPSHOT/'manifest.json').read_text(encoding='utf-8'))
BOUNDS = json.loads((ROOT/'app/config/ai_core_bounds.json').read_text(encoding='utf-8'))


def baseline():
    cfg = json.loads((ROOT/'app/config/ai_weights_optimized.json').read_text(encoding='utf-8'))
    cfg.update(policy_version='V3-guard', runtime_hashes=MANIFEST['source_hashes'], name='v3_round1_parent')
    return cfg


def validate_v3(cfg):
    parent = baseline()
    if cfg.get('runtime_hashes') != MANIFEST['source_hashes'] or 'claim_weights' in cfg:
        raise ValueError('V3 runtime provenance mismatch')
    for key, value in cfg['weights'].items():
        if key not in KEYS and value != parent['weights'][key]:
            raise ValueError('V3 round one must freeze ' + key)
    for key, (lo, hi) in zip(KEYS, LIMITS):
        value, initial = cfg['weights'][key], parent['weights'][key]
        hard = BOUNDS[key]
        if not max(lo, hard['min'], .85*initial) <= value <= min(hi, hard['max'], 1.15*initial):
            raise ValueError('V3 step/bounds violation: ' + key)
        if abs(value/initial-1) > .25:
            raise ValueError('V3 cumulative change exceeds 25%')
    return cfg


def guard_runtime(cfg, accelerated=True, extra_keys=()):
    """Compile private snapshot modules, overriding named assignments before imports."""
    from tools.weights import fingerprint
    name = 'app.core._v3_' + fingerprint(cfg)[:16]
    package = types.ModuleType(name)
    package.__path__ = [str(SNAPSHOT)]
    package.__package__ = name
    sys.modules[name] = package
    modules = {}
    try:
        for dependency in ('constants','evaluator','mapper','pool_tracker','scoring','action_generator'):
            sys.modules[name+'.'+dependency] = importlib.import_module('app.core.'+dependency)
        for module in ('danger_model','tenpai_model','ev_engine','call_decision'):
            path = SNAPSHOT/(module+'.py')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != cfg['runtime_hashes'][module]:
                raise ValueError('V3 snapshot modified: '+module)
            tree = ast.parse(data.decode('utf-8'))
            found = set()
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                    key = module+'.'+node.targets[0].id
                    dict_keys = [k for k in extra_keys if k.startswith(key+'.')]
                    if dict_keys and isinstance(node.value, ast.Dict):
                        for dk, dv in zip(node.value.keys, node.value.values):
                            full = key+'.'+str(dk.value)
                            if full in dict_keys:
                                dv.value = cfg['weights'][full]
                                found.add(full)
                    if key in BOUNDS or key in extra_keys:
                        node.value = ast.copy_location(ast.Constant(cfg['weights'][key]),node.value)
                        found.add(key)
            expected = {k for k in (*BOUNDS, *extra_keys) if k.startswith(module+'.')}
            if found != expected:
                raise ValueError('Named V3 loading mismatch')
            obj = types.ModuleType(name+'.'+module)
            obj.__package__, obj.__file__ = name, str(path)
            sys.modules[obj.__name__] = obj
            exec(compile(ast.fix_missing_locations(tree),str(path),'exec'),obj.__dict__)
            modules[module] = obj
        if accelerated:
            from tools.ev_acceleration import install
            # Current snapshot already maps overlap choices back to physical P.
            original = modules['ev_engine']._overlap_pair_ryanmen_shape
            install(modules)
            modules['ev_engine']._overlap_pair_ryanmen_shape = original
        for obj in modules.values(): obj.__package__ = 'app.core'
        assert modules['call_decision'].SHANTEN_PENALTY == modules['ev_engine'].SHANTEN_PENALTY
        return modules
    finally:
        for key in list(sys.modules):
            if key == name or key.startswith(name+'.'): del sys.modules[key]


def candidates():
    parent = baseline()
    result = [parent]
    for key in KEYS:
        for scale in (.9, 1.1):
            cfg = copy.deepcopy(parent)
            cfg['weights'][key] = round(cfg['weights'][key]*scale) if key==KEYS[0] else cfg['weights'][key]*scale
            cfg['name'] = key.split('.')[-1]+str(scale)
            result.append(validate_v3(cfg))
    # Fixed, predeclared two-dimensional local cross-check, not validation-adaptive.
    cfg = copy.deepcopy(parent)
    cfg['weights'][KEYS[0]] = 144
    cfg['weights'][KEYS[1]] *= .9
    cfg['name'] = 'push_up_quality_down'
    result.append(validate_v3(cfg))
    return result


def quota_schedule(blocks, seed):
    """V2 recovery fallback: V0 20%, historical V1 40%, current guard 40%.

    Put a historical V1 in every trio, then shuffle the exact remaining quota.
    Largest remainders handle sample sizes whose opponent slots are not /10.
    """
    if blocks < 1: raise ValueError('Need complete blocks')
    fractions = (.2,.4,.4)
    quota = [int(3*blocks*p) for p in fractions]
    for i in sorted(range(3),key=lambda i: (3*blocks*fractions[i]-quota[i],-i),reverse=True)[:3*blocks-sum(quota)]:
        quota[i] += 1
    remainder = [0]*quota[0]+[1]*(quota[1]-blocks)+[2]*quota[2]
    rng = random.Random(seed ^ 0x53A91)
    rng.shuffle(remainder)
    result = []
    for i in range(blocks):
        trio = [1]+remainder[2*i:2*i+2]
        # If all three are historical V1, swap one with a later non-V1 slot.
        if len(set(trio))==1:
            j = next((j for j in range(2*i+2,len(remainder)) if remainder[j]!=1),None)
            if j is not None:
                trio[2], remainder[j] = remainder[j], trio[2]
            else:
                prior=next(s for s in result if sum(t!=1 for t in s)>=2)
                j=next(j for j,t in enumerate(prior) if t!=1)
                trio[2],prior[j]=prior[j],trio[2]
        rng.shuffle(trio)
        result.append(trio)
    return result


def shanten(hand, god, meld_count):
    from app.core.mapper import preprocess_hand
    from tools.ev_acceleration import cached_shanten
    return cached_shanten(preprocess_hand(hand,god),0,4-meld_count)


CLAIMS = ('chi','pong','ming_gang','an_gang','bu_gang')


class Collector:
    """One physical candidate seat; opportunity is a decision with that legal type.

    Fixed-state audit replays the parent on every candidate opportunity. Benefit
    labels mean structural shanten improvement after the best legal discard;
    they are diagnostics, never used to choose an action or compute fitness.
    """
    def __init__(self, physical, audit=True, probes=None):
        self.physical = physical
        self.metrics = Counter()
        self.previous = None
        self.pending = None
        self.after_claim = False
        self.audit = audit
        self.probes = probes or []

    def before(self, match, seat, physical, action, policy):
        if physical != self.physical: return
        rows = match.options[seat]
        kind = action['action_type']
        legal = {a['action_type'] for a in rows}
        for t in CLAIMS:
            self.metrics[t+'_opp'] += t in legal
            self.metrics[t+'_take'] += kind == t
        if self.audit and (any(t in legal for t in CLAIMS) or kind=='discard'):
            from tools.arena import Policy
            parent = Policy(baseline(),'ev').choose(match,seat)
            for t in CLAIMS:
                if t in legal:
                    self.metrics['audit_'+t+'_opp'] += 1
                    self.metrics['audit_'+t+'_take'] += kind==t
                    self.metrics['audit_parent_'+t+'_take'] += parent['action_type']==t
            self.metrics['audit_actions'] += 1
            self.metrics['audit_flips'] += (kind,action.get('tiles'))!=(parent['action_type'],parent.get('tiles'))
        if match.phase=='response':
            start = shanten(match.hands[seat],match.god,len(match.melds[seat]))
            for t in ('chi','pong','ming_gang'):
                beneficial = False
                for a in rows:
                    if a['action_type'] != t: continue
                    hand = list(match.hands[seat])
                    tiles = list(a['tiles'])
                    # Action tiles include the public discarded tile.
                    tiles.remove(match.last_discard['tile'])
                    for tile in tiles: hand.remove(tile)
                    n = len(match.melds[seat])+1
                    if t == 'ming_gang':
                        # A kong waits for a replacement draw; compare waiting states.
                        best = shanten(hand,match.god,n)
                    else:
                        best = min(shanten(hand[:j]+hand[j+1:],match.god,n) for j in range(len(hand)))
                    beneficial |= best < start
                if beneficial:
                    self.metrics[t+'_benefit_opp'] += 1
                    self.metrics[t+'_benefit_take'] += kind==t
        if kind=='discard':
            hand = match.hands[seat]
            n = len(match.melds[seat])
            options = []
            for a in rows:
                if a['action_type']=='discard':
                    after = list(hand);after.remove(a['tiles'][0])
                    options.append(shanten(after,match.god,n))
            chosen = list(hand);chosen.remove(action['tiles'][0])
            s = shanten(chosen,match.god,n)
            can_keep = min(options)==0
            if can_keep:
                from app.schemas import PlayerState
                opponents = [PlayerState(seat_wind=w,is_dealer=w=='E',melds=match._models(w),discards=match.rivers[w]) for w in 'ESWN' if w!=seat]
                threats = policy.modules['tenpai_model'].estimate_opponents_tenpai(opponents,dealer_tile=match.god)
                low = max(threats.values(),default=0) < .3
                self.metrics['tenpai_opp'] += 1
                self.metrics['tenpai_break'] += s>0
                if low:
                    self.metrics['low_tenpai_opp'] += 1
                    self.metrics['low_tenpai_break'] += s>0
                if self.audit:
                    ph=list(hand);ph.remove(parent['tiles'][0]) if parent['action_type']=='discard' else None
                    if parent['action_type']=='discard':
                        ps=shanten(ph,match.god,n)
                        self.metrics['audit_low_tenpai_opp'] += low
                        self.metrics['audit_low_tenpai_break'] += low and s>0
                        self.metrics['audit_parent_low_tenpai_break'] += low and ps>0
            normal = not self.after_claim
            self.pending = (s,normal)
            if self.probes and self.metrics['probe_states'] < 8:
                from tools.arena import Policy
                for label,cfg in self.probes:
                    pp=Policy(cfg,'ev')
                    a=pp.choose(match,seat)
                    self.metrics['probe_'+label+'_flips'] += (kind,action.get('tiles'))!=(a['action_type'],a.get('tiles'))
                self.metrics['probe_states'] += 1
        elif kind in CLAIMS:
            self.after_claim = True

    def after(self, match, seat, physical, action):
        if physical != self.physical or action['action_type']!='discard': return
        s,normal = self.pending
        if normal and self.previous is not None:
            self.metrics['progress_sum'] += self.previous-s
            self.metrics['progress_windows'] += 1
            bucket = str(self.previous)
            self.metrics['progress_'+bucket+'_sum'] += self.previous-s
            self.metrics['progress_'+bucket+'_windows'] += 1
        self.previous = s if normal else None
        self.after_claim = False


def block(job):
    from tools.arena import play_hand
    from tools.weights import fingerprint
    seed,index,configs,physical,probes = job
    order = [(physical-1+i)%4 for i in range(4)]
    result = []
    for dealer in range(4):
        c = Collector(physical,probes=probes)
        row = play_hand(seed,dealer,configs,'ev',c)
        row['physical_candidate_seat'] = physical
        row['net'] = [row['net'][s] for s in order]
        row['policies'] = [row['policies'][s] for s in order]
        for key in ('winner','dealin'):
            if row[key] is not None: row[key] = order.index(row[key])
        result.append(row)
    return result


def interval(values, seed=61017, repeats=10000):
    """Independent wall units only; fixed-seed wall bootstrap, one-sided 95%."""
    a = list(values);n=len(a)
    if n<2: raise ValueError('Need at least two walls')
    mean = sum(a)/n; se = math.sqrt(sum((v-mean)**2 for v in a)/(n-1)/n)
    rng = random.Random(seed)
    draws = sorted(sum(rng.choices(a,k=n))/n for _ in range(repeats))
    return dict(mean=mean,se=se,normal_lower=mean-NormalDist().inv_cdf(.95)*se,
                normal_upper=mean+NormalDist().inv_cdf(.95)*se,
                bootstrap_lower=quantile(draws,.05),bootstrap_upper=quantile(draws,.95),clusters=n)


def quantile(sorted_values, p):
    position=(len(sorted_values)-1)*p;lo=int(position);hi=math.ceil(position)
    return sorted_values[lo]+(sorted_values[hi]-sorted_values[lo])*(position-lo)


def aggregate(rows):
    result = Counter()
    for r in rows:
        result.update(r['behavior'])
        result['hands'] += 1
        result['net_sum'] += r['net'][1]
        result['dealin'] += r['dealin']==1
        result['zimo'] += r['winner']==1 and r['win_type']=='zimo'
        result['ron'] += r['winner']==1 and r['win_type']=='ron'
        result['rob_kong'] += r['winner']==1 and r['win_type']=='rob_kong'
        result['rob_kong_dealin'] += r['dealin']==1 and r['win_type']=='rob_kong'
    return dict(result)


def ratio(c, numerator, denominator):
    return c.get(numerator,0)/c.get(denominator,0) if c.get(denominator,0) else None


def compare(a, b):
    from tools.arena import paired_comparison
    paired_comparison(a,b)  # Reject mismatched walls, opponents and kernel.
    aa,bb=a['rows'],b['rows']
    data={k:[] for k in ('net','dealin','zimo','progress','low_tenpai')}
    for i in range(0,len(aa),4):
        x,y=aggregate(aa[i:i+4]),aggregate(bb[i:i+4])
        data['net'].append((x['net_sum']-y['net_sum'])/4)
        for key in ('dealin','zimo'): data[key].append((x[key]-y[key])/4)
        # Ratio metrics require a joint numerator/denominator bootstrap below.
    result={k:interval(v) for k,v in data.items() if v}
    x,y=aggregate(aa),aggregate(bb)
    result['candidate'],result['baseline']=x,y
    for name,num,den in (('progress','progress_sum','progress_windows'),('low_tenpai','low_tenpai_break','low_tenpai_opp')):
        result[name]=ratio_interval(aa,bb,num,den)
    result['claims']={}
    for t in CLAIMS:
        result['claims'][t] = dict(candidate=ratio(x,t+'_take',t+'_opp'),baseline=ratio(y,t+'_take',t+'_opp'),
            difference=ratio_interval(aa,bb,t+'_take',t+'_opp'),
            fixed_state=ratio_interval(aa,aa,'audit_'+t+'_take','audit_'+t+'_opp',other_num='audit_parent_'+t+'_take'))
    return result


def ratio_interval(aa,bb,num,den,other_num=None):
    av=[aggregate(aa[i:i+4]) for i in range(0,len(aa),4)]
    bv=[aggregate(bb[i:i+4]) for i in range(0,len(bb),4)]
    units=[(a.get(num,0),a.get(den,0),b.get(other_num or num,0),b.get(den,0)) for a,b in zip(av,bv)]
    n=len(units);ad=sum(v[1] for v in units);bd=sum(v[3] for v in units)
    if min(ad,bd)==0: return None
    am=sum(v[0] for v in units)/ad;bm=sum(v[2] for v in units)/bd
    influence=[(v[0]-am*v[1])/(ad/n)-(v[2]-bm*v[3])/(bd/n) for v in units]
    se=math.sqrt(sum(v*v for v in influence)/(n-1)/n)
    rng=random.Random(61017);draws=[]
    for _ in range(10000):
        sample=rng.choices(units,k=n)
        ax,ay,bx,by=map(sum,zip(*sample))
        if ay and by: draws.append(ax/ay-bx/by)
    draws.sort()
    return dict(mean=float(am-bm),normal_lower=float(am-bm-1.6448536269514722*se),normal_upper=float(am-bm+1.6448536269514722*se),
        bootstrap_lower=quantile(draws,.05),bootstrap_upper=quantile(draws,.95),candidate=float(am),baseline=float(bm))


def gates(comparison, pressure, invariants, elo_lower=None):
    c=comparison; a,b=c['candidate'],c['baseline']
    lower=lambda x: min(x['normal_lower'],x['bootstrap_lower'])
    upper=lambda x: max(x['normal_upper'],x['bootstrap_upper'])
    g={
        'main_sample':c['net']['clusters']>=250,
        'net':lower(c['net'])>0,
        'dealin':c['dealin']['mean']<=0 and upper(c['dealin'])<=.005,
        'progress':c['progress'] is not None and lower(c['progress'])>=-.05,
        'zimo':lower(c['zimo'])>=-.01,
        'low_risk_tenpai':c['low_tenpai'] is not None and upper(c['low_tenpai'])<=.02 and a.get('tenpai_opp',0)>a.get('tenpai_break',0),
        'invariants':bool(invariants),
        'elo':elo_lower is not None and elo_lower>=-10,
    }
    for t in CLAIMS:
        ar,br=c['claims'][t]['candidate'],c['claims'][t]['baseline']
        g['rate_'+t]= ar is not None and br is not None and br>0 and .75<=ar/br<=1.25
        g['opportunities_'+t]=min(a.get(t+'_opp',0),b.get(t+'_opp',0))>=200
        if t in ('chi','pong','ming_gang'):
            g['noncollapse_'+t]=a.get(t+'_benefit_opp',0)>=200 and a.get(t+'_benefit_take',0)>0 and a.get(t+'_take',0)<a.get(t+'_opp',0)
    for label,p in pressure.items():g['pressure_'+label]=lower(p['net'])>=-1
    return g
