"""Cheap core-weight exploration followed by independent exact-EV gates."""
import copy
import json
import random
from statistics import NormalDist
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from functools import partial
from tools.arena import evaluate_pool, paired_comparison
from tools.weights import fingerprint
from tools.core_search import CORE_KEYS

def select_elites(trials, baseline, count=3):
    # Net income is primary fitness. Win rate breaks ties, never overrides losses.
    survivors=[t for t in trials if t['report']['seats'][1]['net_points'] > baseline['seats'][1]['net_points']]
    unique={fingerprint(t['config']):t for t in survivors}
    return sorted(unique.values(),key=lambda t:(t['report']['seats'][1]['net_points'],t['report']['seats'][1]['win_rate']),reverse=True)[:count]

def run(args, baseline, pool, atomic_json, mutate, promotion_gate, compact):
    # Retain workers and their bounded hand caches through both stages/generations.
    # Restarting Windows workers per policy wasted time and all pure-hand caches.
    executor=ProcessPoolExecutor(max_workers=args.workers) if args.workers>1 else None
    try:
        from tools.experiment_io import CheckpointEvaluator,write_report
        evaluate=CheckpointEvaluator(args,executor,atomic_json)
        initial=evaluate.root/'initial.json'
        signature={k:str(v) for k,v in vars(args).items() if k not in ('resume','workers','output','checkpoint_dir')}
        if args.resume:
            saved=json.loads(initial.read_text())
            if saved['arguments']!=signature or saved['version']!=evaluate.version:raise ValueError('Resume arguments or implementation differ from checkpoint')
            pool=saved['pool']
            if (args.output/'trials.jsonl').exists():(args.output/'trials.jsonl').unlink()
        elif initial.exists():raise ValueError('Checkpoint directory already belongs to another run; use --resume or a fresh output name')
        else:atomic_json(initial,{'arguments':signature,'version':evaluate.version,'pool':pool})
        result=_run(args,baseline,pool,atomic_json,mutate,promotion_gate,compact,evaluate)
        write_report(args.output,baseline,atomic_json)
        return result
    finally:
        if executor is not None:executor.shutdown(wait=True,cancel_futures=True)

def _run(args, baseline, pool, atomic_json, mutate, promotion_gate, compact, evaluate):
    rng=random.Random(args.seed)
    parent=copy.deepcopy(baseline)
    stable=copy.deepcopy(baseline)
    # Every elite is a possible promotion attempt. Allocate the 1% family budget.
    z=NormalDist().inv_cdf(1-.01/(args.generations*args.elites))
    stride=max(args.hands,args.validation_hands)//4+1
    keys=CORE_KEYS
    atomic_json(args.output/'run.json',{'arguments':{k:str(v) for k,v in vars(args).items()},
        'parameters':keys,'frozen_parameters':sorted(set(baseline['weights'])-set(keys)),
        'stage1_policy':'explore (approximate EV core projection)', 'stage2_policy':'ev',
        'promotion_z':z,'source_hashes':baseline['source_hashes'],'pool':[fingerprint(c) for c in pool]})
    for generation in range(args.generations):
        checkpoint=getattr(args,'checkpoint_dir',args.output/'checkpoints')/args.output.name
        print(json.dumps({'event':'generation_start','generation':generation+1,'generations':args.generations}),flush=True)
        train_seed=args.seed+generation*stride
        v0_fast=evaluate(baseline,args.hands,train_seed,args.workers,'explore',pool)
        trials=[]
        for trial in range(args.population):
            candidate=mutate(parent,rng,keys,args.sigma)
            assert all(candidate['weights'][k]==v for k,v in baseline['weights'].items() if k not in keys)
            report=evaluate(candidate,args.hands,train_seed,args.workers,'explore',pool)
            comparison=paired_comparison(report,v0_fast)
            trials.append({'config':candidate,'report':report,'trial':trial})
            atomic_json(checkpoint/'latest.json',{'generation':generation,'stage':1,'trial':trial,'parent':parent,'stable':stable,'rng_state':rng.getstate(),'pool':pool})
            entry={'generation':generation,'trial':trial,'stage':1,'status':'proxy_only',
                   'config':candidate,'vs_v0':comparison,'evaluation':compact(report)}
            with (args.output/'trials.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(entry)+'\n')
            print(json.dumps({'generation':generation,'stage':1,'trial':trial,
                'net_points':report['seats'][1]['net_points'],'win_rate':report['seats'][1]['win_rate'],
                'gain_vs_v0':comparison['mean_gain_per_hand']}),flush=True)
        elites=select_elites(trials,v0_fast,args.elites)
        atomic_json(checkpoint/f'elites_{generation:04}.json',{'generation':generation,'elites':[e['config'] for e in elites],'parent':parent,'stable':stable,'rng_state':rng.getstate(),'pool':pool})
        atomic_json(args.output/f'stage1_{generation:04}.json',{'baseline':compact(v0_fast),
            'survivors':len(elites),'elites':[{'trial':e['trial'],'config':e['config'],'report':compact(e['report'])} for e in elites]})
        if not elites:
            # Preserve a concrete, explicitly unvalidated result even if all mutants lose.
            atomic_json(args.output/'best_candidate.json',parent)
            print(json.dumps({'generation':generation,'stage':2,'status':'skipped_no_survivors'}),flush=True)
            continue
        parent=copy.deepcopy(elites[0]['config'])
        atomic_json(args.output/'best_candidate.json',parent)
        holdout_seed=args.seed+(args.generations+generation)*stride
        v0_ev=evaluate(baseline,args.validation_hands,holdout_seed,args.workers,'ev',pool)
        stable_ev=v0_ev if fingerprint(stable)==fingerprint(baseline) else evaluate(stable,args.validation_hands,holdout_seed,args.workers,'ev',pool)
        atomic_json(args.output/f'stage2_baseline_{generation:04}.json',{'v0':v0_ev,'incumbent':stable_ev})
        verified=[]
        accepted=[]
        for rank,elite in enumerate(elites):
            print(json.dumps({'event':'elite_validation_start','generation':generation+1,'elite':rank+1,'hands':args.validation_hands}),flush=True)
            report=evaluate(elite['config'],args.validation_hands,holdout_seed,args.workers,'ev',pool)
            vs_v0=paired_comparison(report,v0_ev);vs_stable=paired_comparison(report,stable_ev)
            passed=(not args.smoke_test and promotion_gate(vs_v0,args.validation_hands,'ev',args.minimum_gain,z)
                    and promotion_gate(vs_stable,args.validation_hands,'ev',0,z))
            audit={'generation':generation,'stage':2,'rank':rank,'accepted':passed,
                'status':'smoke_unvalidated' if args.smoke_test else 'accepted' if passed else 'rejected',
                'vs_v0':vs_v0,'vs_incumbent':vs_stable,'config':elite['config'],'evaluation':compact(report),
                'win_rate_gain_vs_v0':report['seats'][1]['win_rate']-v0_ev['seats'][1]['win_rate'],
                'deal_in_rate_gain_vs_v0':report['seats'][1]['deal_in_rate']-v0_ev['seats'][1]['deal_in_rate']}
            atomic_json(args.output/f'validation_{generation:04}_{rank}.json',audit)
            atomic_json(args.output/f'validation_hands_{generation:04}_{rank}.json',report)
            atomic_json(checkpoint/f'validated_{generation:04}_{rank}.json',audit)
            with (args.output/'trials.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(audit)+'\n')
            print(json.dumps({k:audit[k] for k in ('generation','stage','rank','status','vs_v0')}),flush=True)
            verified.append((report['seats'][1]['net_points'],elite['config']))
            if passed: accepted.append((report['seats'][1]['net_points'],elite['config']))
        # Full EV picks the next exploration parent; rejected parents remain unvalidated.
        parent=copy.deepcopy(max(verified,key=lambda item:item[0])[1])
        atomic_json(args.output/'best_candidate.json',parent)
        if accepted:
            stable=copy.deepcopy(max(accepted,key=lambda item:item[0])[1])
            atomic_json(args.output/'ai_weights_optimized.json',stable)
            atomic_json(args.history_dir/('stable_'+fingerprint(stable)+'.json'),stable)
            pool.append(stable)
        atomic_json(checkpoint/f'generation_{generation:04}.json',{'completed':True,'parent':parent,'stable':stable,'pool':pool,'rng_state':rng.getstate()})
    print(json.dumps({'status':'complete','pipeline':'two-stage','smoke_test':args.smoke_test,
        'optimized_exists':(args.output/'ai_weights_optimized.json').exists()}),flush=True)
