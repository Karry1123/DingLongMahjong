"""R1 single-parameter screen and one untouched validation, bounded runtime."""
import argparse
import hashlib
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.sensitivity_scan import baseline,select_candidates,kong_compare,KONGS,state_signature
from tools.v3_experiment import compare,gates,ROOT
from tools.weights import fingerprint
from tools.claim_experiment import atomic_json
from scripts import tune_ai_weights_v4 as old
from scripts.scan_sensitivity import run_scan,enrich

SEEDS=dict(pilot=32600100,sensitivity=32610000,enrichment=32620000,screen=32710000,main=32810000,A=32910000,B=32920000,C=32930000,D=32940000,E=32950000)

def kong_gates(counts):
    result={}
    for t in KONGS:
        x=counts[t];n=x.get('states',0);p=x.get('parent_take',0);c=x.get('candidate_take',0)
        result['opportunities_'+t]=n>=200
        result['rate_'+t]=p>0 and .75<=c/p<=1.25
        result['noncollapse_'+t]=x.get('benefit',0)>0 and x.get('benefit_candidate_take',0)==x['benefit'] and c<n
    return result

def execute(out,workers):
    start=time.monotonic();out.mkdir(parents=True,exist_ok=True)
    saved_pilot=(out/'pilot.json').exists();saved_scan=(out/'sensitivity.json').exists()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        pilot=json.loads((out/'pilot.json').read_text(encoding='utf-8')) if (out/'pilot.json').exists() else old.Evaluator(out,ex).evaluate(baseline(),20,SEEDS['pilot'],'pilot')
        desired=dict(screen=300,main=1000,pressure=252,anchor=300)
        estimate=(7*300+2*1000+8*252+300)*pilot['elapsed_seconds']/20
        scale=min(1,9720/max(estimate,1))
        sizes={k:max(8,4*int(v*scale/4)) for k,v in desired.items()}
        old.SEEDS=SEEDS
        audit=old.seed_audit(out,dict(maximum=80000))
        atomic_json(out/'allocation.json',dict(desired=desired,sizes=sizes,scale=scale,estimate=estimate,seeds=SEEDS,seed_audit=audit))
        if (out/'sensitivity.json').exists():
            sensitivity=json.loads((out/'sensitivity.json').read_text(encoding='utf-8'))
            _,kongs=pickle.loads((out/'training_states.pkl').read_bytes())
        else:sensitivity,kongs=run_scan(out,ex,SEEDS['sensitivity'])
        locked_path=out/'locked_candidate.json'
        archived=out/'preflight_before_kong_label_fix'
        if not locked_path.exists() and (archived/'locked_candidate.json').exists():
            import shutil
            for path in archived.glob('*.json'):shutil.copy2(path,out/path.name)
        resume_lock=locked_path.exists()
        if resume_lock:
            locked=json.loads(locked_path.read_text(encoding='utf-8'))
            cfg=locked['candidate'];best=locked['screen_index']
            if fingerprint(cfg)!=locked['id'] or cfg['weights']['ev_engine._UKEIRE_QUALITY_WEIGHT']!=1.246727620234373:
                raise ValueError('Frozen candidate differs from authorized checkpoint')
            cfgs=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(out.glob('candidate_[0-9].json'))]
            comparisons=json.loads((out/'screen_comparisons.json').read_text(encoding='utf-8'))
            selected=[r for r in sensitivity['ranking'] if r['rate']>=.01][:3]
            print(json.dumps(dict(event='resume_locked',screen_index=best,id=locked['id'],no_screen_or_selection=True)),flush=True)
        else:
            selected,cfgs=select_candidates(sensitivity['ranking'])
            if len(cfgs)<2:raise RuntimeError('No sensitive parameter: do not waste validation budget')
            for i,cfg in enumerate(cfgs):atomic_json(out/f'candidate_{i}.json',cfg)
        ev=old.Evaluator(out,ex)
        ev.version=hashlib.sha256(ev.version.encode()+Path(__file__).read_bytes()+(ROOT/'scripts/scan_sensitivity.py').read_bytes()).hexdigest()
        if not resume_lock:
            reports=[ev.evaluate(c,sizes['screen'],SEEDS['screen'],f'screen_{i}') for i,c in enumerate(cfgs)]
            comparisons=[compare(r,reports[0]) for r in reports]
            atomic_json(out/'screen_comparisons.json',comparisons)
            eligible=[i for i,c in enumerate(comparisons[1:],1) if c['progress'] and c['progress']['mean']>=-.05 and all(not(c['baseline'].get(t+'_take',0)>0 and c['candidate'].get(t+'_take',0)==0) for t in ('chi','pong'))]
            best=max(eligible or range(1,len(cfgs)),key=lambda i:comparisons[i]['net']['mean'])
            cfg=cfgs[best]
            atomic_json(locked_path,dict(candidate=cfg,id=fingerprint(cfg),implementation=ev.version,screen_index=best,parameter_changes={k:[cfgs[0]['weights'][k],v] for k,v in cfg['weights'].items() if v!=cfgs[0]['weights'][k]}))
        kongs=enrich(out,ex,kongs,SEEDS['enrichment'])
        # Wall data remain independent; replay enriched states in parallel shards.
        from collections import Counter
        identity=hashlib.sha256(('win-priority-v1'+fingerprint(cfg)+''.join(state_signature(s) for s in kongs)).encode()).hexdigest()
        partial=out/'kong_comparison.partial.json'
        saved=json.loads(partial.read_text(encoding='utf-8')) if partial.exists() else dict(identity=identity,completed=0,counts={t:{} for t in KONGS})
        if saved['identity']!=identity:raise ValueError('Kong checkpoint identity mismatch')
        counts={t:Counter(saved['counts'][t]) for t in KONGS};done=saved['completed']
        chunks=[kongs[i:i+32] for i in range(done,len(kongs),32)]
        for chunk,part in zip(chunks,ex.map(kong_compare,[(cfg,s) for s in chunks])):
            for t in KONGS:counts[t].update(part[t])
            done+=len(chunk)
            atomic_json(partial,dict(identity=identity,completed=done,counts=counts))
            print(json.dumps(dict(event='kong_replay',completed=done,total=len(kongs))),flush=True)
        kong={t:dict(counts[t]) for t in KONGS}
        atomic_json(out/'kong_comparison.json',kong)
        vb=ev.evaluate(cfgs[0],sizes['main'],SEEDS['main'],'main_baseline')
        vc=ev.evaluate(cfg,sizes['main'],SEEDS['main'],'main_candidate')
        main=compare(vc,vb);atomic_json(out/'main_comparison.json',main)
        pressure={}
        for label,cell in dict(A=[0,0,0],B=[1,1,1],C=[0,1,2],D=[2,2,2]).items():
            b=ev.evaluate(cfgs[0],sizes['pressure'],SEEDS[label],label+'_baseline',cell)
            c=ev.evaluate(cfg,sizes['pressure'],SEEDS[label],label+'_candidate',cell)
            pressure[label]=compare(c,b);atomic_json(out/(label+'_comparison.json'),pressure[label])
        anchor=ev.evaluate(cfg,sizes['anchor'],SEEDS['E'],'E_anchor',[0,1,2])
    from tools.v4_reporting import elo_diagnostics,write_report
    elo=elo_diagnostics(anchor);atomic_json(out/'elo.json',elo)
    verdict=gates(main,pressure,True,elo['gain_bootstrap_lower'])
    verdict.update(kong_gates(kong))
    verdict['minimum_main_walls']=sizes['main']>=1000
    # Regression must pass before a standalone config can be emitted.
    tests=['test_ai_weights_loading','test_offline_ai_tools','test_focused_validation','test_v3_tuning','test_v4_tuning','test_sensitivity_scan']
    specialist=[t for t in old.TESTS if t not in tests]
    specialist_cmd=[sys.executable,'-m','pytest',*[f'tests/{t}.py' for t in specialist],'-q']
    special=subprocess.run(specialist_cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=600)
    (out/'specialist_pytest.log').write_text(special.stdout,encoding='utf-8');print(special.stdout,flush=True)
    cmd=[sys.executable,'-m','pytest',*[f'tests/{t}.py' for t in tests],'-q']
    completed=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=600)
    (out/'pytest.log').write_text(completed.stdout,encoding='utf-8');print(completed.stdout,flush=True)
    verdict['invariants']=completed.returncode==0 and special.returncode==0
    result=dict(promoted=all(verdict.values()),gates=verdict,main=main,pressure=pressure,elo=elo,kong=kong,
        kong_training=json.loads((out/'kong_training.json').read_text(encoding='utf-8')),sensitivity=sensitivity,
        selected=[r['key'] for r in selected],screen_index=best,candidate_id=fingerprint(cfg),
        candidate_changes=[{k:v for k,v in c['weights'].items() if v!=cfgs[0]['weights'][k]} for c in cfgs],
        simulated_hands=20+len(cfgs)*sizes['screen']+2*sizes['main']+8*sizes['pressure']+sizes['anchor'],
        elapsed_seconds=time.time()-( (out/'pilot.json').stat().st_mtime-pilot['elapsed_seconds']),
        metadata=dict(sizes=sizes,desired=desired,scale=scale,pilot_seconds=pilot['elapsed_seconds'],estimated_seconds=estimate,
                      seeds=SEEDS,workers=workers,pool_fractions=[.2,.4,.4],training_hands=160,kong_training_in_natural_sample=False,
                      scan_elapsed_already_completed=saved_scan,resumed_locked_candidate=resume_lock,elapsed_includes_interruptions=True,
                      win_priority='Immediate legal win states are opportunities but never beneficial-kong refusals',
                      specialist_command=' '.join(specialist_cmd),specialist_returncode=special.returncode,
                      regression_command=' '.join(cmd),regression_returncode=completed.returncode))
    atomic_json(out/'result.json',result)
    if result['promoted']:atomic_json(ROOT/'app/config/ai_weights_v4.json',cfg)
    write_report(out,result,comparisons)
    print(json.dumps(dict(event='complete',promoted=result['promoted'],net=main['net'],dealin=main['dealin'],gates=verdict,seconds=result['elapsed_seconds'],sizes=sizes,hands=result['simulated_hands'],top5=[{k:r[k] for k in ('key','rate','flips','replays')} for r in sensitivity['ranking'][:5]],selected=[dict(key=r['key'],bounds=r['bounds']) for r in selected],kong=kong,kong_training=result['kong_training'],elo=elo['gain_bootstrap_lower'],pytest=completed.stdout),ensure_ascii=False),flush=True)
    return completed.returncode or special.returncode

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=8);ap.add_argument('--output',type=Path,default=ROOT/'data/ai_tuning/v4-round2');ap.add_argument('--execute',action='store_true');ap.add_argument('--timeout',type=int,default=10800);args=ap.parse_args()
    if args.execute:sys.exit(execute(args.output,args.workers))
    else:
        with (args.output/'console.log').open('a',encoding='utf-8') as log:
            rc=subprocess.run([sys.executable,__file__,'--execute','--workers',str(args.workers),'--output',str(args.output)],stdout=log,stderr=subprocess.STDOUT,timeout=args.timeout).returncode
        print('\n'.join((args.output/'console.log').read_text(encoding='utf-8',errors='replace').splitlines()[-3:]),flush=True)
        sys.exit(rc)
