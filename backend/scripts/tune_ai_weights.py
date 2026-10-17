"""Offline (1+lambda) evolution; only independent full-EV validation can promote."""
import argparse,copy,json,math,os,random,sys,time
from pathlib import Path
from statistics import NormalDist
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.weights import PARAMETERS,POOL,load_weights,validate_weights,fingerprint
from tools.arena import evaluate_pool,paired_comparison

DEFAULT_KEYS=['ev_engine.SHANTEN_PENALTY','ev_engine._UKEIRE_QUALITY_WEIGHT','ev_engine._DEEP_SHANTEN_UNIT','ev_engine._YAKUHAI_SINGLE_POTENTIAL','ev_engine._YAKUHAI_PAIR_POTENTIAL','ev_engine._GUEST_WIND_SINGLE_PENALTY','ev_engine._SHAPE_JOKER','ev_engine._JANTOU_BREAK_PENALTY','ev_engine._GOOD_SHAPE_DEFENSE_SCALE','ev_engine._DEFENSE_RISK_REFERENCE','call_decision._CALL_TENPAI_TEMPO_BONUS','call_decision._PONG_HU_EV_SCALE']

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2),encoding='utf-8');temp.replace(path)

def mutate(parent,rng,keys,sigma):
    for _ in range(100):
        child=copy.deepcopy(parent);child['name']='candidate'
        for key in rng.sample(keys,min(6,len(keys))):
            spec=PARAMETERS[key];v=child['weights'][key]+rng.gauss(0,sigma)*(spec['max']-spec['min'])
            v=max(spec['min'],min(spec['max'],v))
            if spec['integer']:v=max(math.ceil(spec['min']),min(math.floor(spec['max']),round(v)))
            child['weights'][key]=v
        try:return validate_weights(child)
        except ValueError:pass
    raise RuntimeError('Unable to sample feasible parameters')

def promotion_gate(stats,hands,mode,minimum_gain,z):
    return mode=='ev' and hands>=2000 and stats['clusters']>=500 and stats['mean_gain_per_hand']-z*stats['standard_error']>minimum_gain

def compact(report):return {k:v for k,v in report.items() if k!='rows'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generations',type=int,default=10);p.add_argument('--population',type=int,default=4)
    p.add_argument('--hands',type=int,default=1000);p.add_argument('--validation-hands',type=int,default=2000)
    p.add_argument('--workers',type=int,default=max(1,(os.cpu_count() or 2)-1));p.add_argument('--seed',type=int,default=20261011)
    p.add_argument('--sigma',type=float,default=.08);p.add_argument('--minimum-gain',type=float,default=1.0)
    p.add_argument('--screen-only',action='store_true',help='Smoke-test full EV evolution without validation or promotion')
    p.add_argument('--pipeline',choices=['two-stage','single-stage'],default='two-stage')
    p.add_argument('--focus-core',action='store_true',help='Freeze V0 noncore weights; search only the shared 12 core weights')
    p.add_argument('--elites',type=int,default=3)
    p.add_argument('--smoke-test',action='store_true',help='Allow small EV validation; NEVER promotes an optimized policy')
    p.add_argument('--mode',choices=['ev','fast'],default='ev');p.add_argument('--parameters',nargs='+')
    p.add_argument('--history-dir',type=Path,default=Path('data/ai_tuning/stable_pool'),help='Persistent local history of previously validated policies')
    p.add_argument('--all-weights',action='store_true',help='Evolve all exposed weights for the selected mode')
    p.add_argument('--output',type=Path,default=Path('data/ai_tuning'))
    p.add_argument('--checkpoint-dir',type=Path,default=Path('data/checkpoints'))
    p.add_argument('--resume',action='store_true',help='Replay deterministic search using saved completed/partial evaluations')
    args=p.parse_args()
    if args.smoke_test:
        args.validation_hands=((args.validation_hands+3)//4)*4
    if args.generations<1 or args.population<1 or args.hands<4 or args.hands%4 or args.validation_hands<(4 if args.smoke_test else 2000) or args.validation_hands%4 or not 0<args.sigma<=.5 or args.minimum_gain<0 or not 1<=args.elites<=3 or args.workers<1:p.error('Invalid counts, bounds or validation budget')
    if args.smoke_test and args.pipeline!='two-stage':p.error('--smoke-test requires the two-stage pipeline')
    if args.focus_core and (args.all_weights or args.parameters or args.mode!='ev'):p.error('--focus-core requires EV and cannot override the core parameter list')
    if args.pipeline=='two-stage' and (args.mode!='ev' or args.all_weights or args.parameters or args.screen_only):p.error('Two-stage searches shared core EV weights. Use --pipeline single-stage for legacy modes/options')
    if args.all_weights and args.parameters:p.error('Choose --all-weights or --parameters')
    from tools.core_search import CORE_KEYS
    keys=CORE_KEYS if args.focus_core else (([k for k in PARAMETERS if k.startswith('screen.') == (args.mode=='fast')] if args.all_weights else args.parameters) or ([k for k in PARAMETERS if k.startswith('screen.')] if args.mode=='fast' else DEFAULT_KEYS))
    if any(k not in PARAMETERS or (args.mode=='ev' and k.startswith('screen.')) or (args.mode=='fast' and not k.startswith('screen.')) for k in keys):p.error('Parameter is unknown or ineffective in selected mode')
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'trials.jsonl').exists() and not args.resume:p.error('Use a fresh output directory or --resume')
    baseline=load_weights(POOL/'baseline_v0.json');champion=copy.deepcopy(baseline)
    pool=[load_weights(POOL/(n+'.json')) for n in ('baseline_v0','conservative','aggressive')]
    if args.history_dir.exists():
        pool.extend(load_weights(path) for path in sorted(args.history_dir.glob('stable_*.json')))
    pool=list({fingerprint(c):c for c in pool}.values())
    if args.pipeline=='two-stage':
        from tools.two_stage import run
        return run(args,baseline,pool,atomic_json,mutate,promotion_gate,compact)
    rng=random.Random(args.seed)
    # Family-wise false promotion probability <= 1% across scheduled generations.
    z=NormalDist().inv_cdf(1-.01/args.generations)
    atomic_json(args.output/'run.json',{'arguments':{k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},'parameters':keys,'promotion_z':z,'source_hashes':baseline['source_hashes'],'pool':[fingerprint(c) for c in pool]})
    stride=max(args.hands,args.validation_hands)//4+1
    for generation in range(args.generations):
        seed=args.seed+generation*stride
        incumbent=copy.deepcopy(champion)
        incumbent_report=evaluate_pool(incumbent,args.hands,seed,args.workers,args.mode,pool)
        best=incumbent_report
        for trial in range(args.population):
            candidate=mutate(incumbent,rng,keys,args.sigma)
            report=evaluate_pool(candidate,args.hands,seed,args.workers,args.mode,pool)
            comparison=paired_comparison(report,incumbent_report)
            log={'generation':generation,'trial':trial,'config':candidate,'comparison':comparison,'evaluation':compact(report),'status':'screened_unvalidated'}
            with (args.output/'trials.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(log)+'\n')
            if report['seats'][1]['net_points']>best['seats'][1]['net_points']:champion,best=candidate,report
            print(json.dumps({'generation':generation,'trial':trial,'fitness_net_points':report['seats'][1]['net_points'],'mean_gain':comparison['mean_gain_per_hand']}),flush=True)
        atomic_json(args.output/'best_candidate.json',champion)
        if fingerprint(champion)==fingerprint(incumbent) or args.mode!='ev' or args.screen_only:continue
        # Independent fresh walls for each generation, never reused for training.
        holdout_seed=args.seed+(args.generations+generation)*stride
        validated=evaluate_pool(champion,args.validation_hands,holdout_seed,args.workers,'ev',pool)
        v0_report=evaluate_pool(baseline,args.validation_hands,holdout_seed,args.workers,'ev',pool)
        incumbent_validation=evaluate_pool(incumbent,args.validation_hands,holdout_seed,args.workers,'ev',pool)
        vs_v0=paired_comparison(validated,v0_report);vs_incumbent=paired_comparison(validated,incumbent_validation)
        # Both original V0 and last stable incumbent must improve significantly.
        accepted=promotion_gate(vs_v0,args.validation_hands,'ev',args.minimum_gain,z) and promotion_gate(vs_incumbent,args.validation_hands,'ev',0,z)
        audit={'generation':generation,'accepted':accepted,'vs_v0':vs_v0,'vs_incumbent':vs_incumbent,'candidate':compact(validated),'baseline':compact(v0_report),'config':champion}
        atomic_json(args.output/f'validation_{generation:04}.json',audit)
        atomic_json(args.output/f'validation_hands_{generation:04}.json',{'candidate':validated,'baseline':v0_report,'incumbent':incumbent_validation})
        if accepted:
            atomic_json(args.output/'ai_weights_optimized.json',champion)
            atomic_json(args.output/f'stable_{generation:04}.json',champion)
            atomic_json(args.history_dir/('stable_'+fingerprint(champion)+'.json'),champion)
            pool.append(copy.deepcopy(champion))
        else:champion=incumbent
    print(json.dumps({'status':'complete','optimized_exists':(args.output/'ai_weights_optimized.json').exists(),'mode':args.mode}),flush=True)
if __name__=='__main__':main()
