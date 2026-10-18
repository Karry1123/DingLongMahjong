"""Predeclared first V3 round: exact EV screening, lock, independent validation."""
import argparse
import copy
import hashlib
import json
import math
import random
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.claim_experiment import atomic_json
from tools.arena import summarize
from tools.weights import load_weights, fingerprint, POOL
from tools.v3_experiment import (ROOT, KEYS, MANIFEST, CLAIMS, baseline, candidates,
    quota_schedule, block, compare, aggregate, gates, interval)


SEEDS = dict(pilot=21600100,screen=21610000,lock=21710000,main=21810000,
             A=21910000,B=21920000,C=21930000,D=21940000,E=21950000)


def implementation_hash():
    paths = sorted((ROOT/'tools').glob('*.py'))+sorted((ROOT/'app/core').glob('*.py'))
    paths += sorted((ROOT/'tools/policy_sources').rglob('*.*'))
    paths += [Path(__file__),ROOT/'app/config/ai_core_bounds.json',ROOT/'tools/weights_schema.json']
    return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+p.read_bytes() for p in paths if p.suffix in ('.py','.json'))).hexdigest()


class Evaluator:
    def __init__(self, output, executor):
        self.output,self.executor=output,executor
        self.version=implementation_hash()
        self.pool=[load_weights(POOL/'baseline_v0.json'),load_weights(POOL/'baseline_v1.json'),baseline()]

    def evaluate(self,cfg,hands,seed,label,cell=None,probes=None):
        if hands%4 or hands<4: raise ValueError('Complete wall blocks required')
        count=hands//4
        schedule=quota_schedule(count,seed) if cell is None else [cell]*count
        jobs=[]
        for i,trio in enumerate(schedule):
            physical=i%4;order=[(physical-1+j)%4 for j in range(4)]
            normalized=[self.pool[trio[0]],cfg,self.pool[trio[1]],self.pool[trio[2]]]
            configs=[None]*4
            for j,s in enumerate(order):configs[s]=normalized[j]
            jobs.append((seed+i,i,configs,physical,probes))
        identity=dict(version=self.version,policy=fingerprint(cfg),hands=hands,seed=seed,label=label,cell=cell,
                      schedule=schedule,probes=[(k,fingerprint(c)) for k,c in (probes or [])])
        signature=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        path=self.output/(label+'.json');partial=self.output/(label+'.partial.json')
        if path.exists():
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved['signature']!=signature:raise ValueError('Checkpoint implementation/arguments mismatch: '+label)
            return saved
        rows=[];elapsed=0
        if partial.exists():
            saved=json.loads(partial.read_text(encoding='utf-8'))
            if saved['signature']!=signature:raise ValueError('Partial signature mismatch')
            rows,elapsed=saved['rows'],saved['elapsed']
            if len(rows)%4 or len(rows)>hands:raise ValueError('Partial block')
            for i,row in enumerate(rows):
                job=jobs[i//4];physical=job[3];order=[(physical-1+j)%4 for j in range(4)]
                if (row['seed'],row['dealer'],row['physical_candidate_seat'],row['policies'])!=(job[0],i%4,physical,[fingerprint(job[2][s]) for s in order]):
                    raise ValueError('Partial schedule differs')
        atomic_json(self.output/(label+'_schedule.json'),dict(signature=signature,**identity))
        initial=len(rows);start=last=time.monotonic()
        print(json.dumps(dict(event='start',label=label,hands=hands,resumed=initial)),flush=True)
        for result in self.executor.map(block,jobs[initial//4:],chunksize=1):
            rows.extend(result);now=time.monotonic()
            if now-last>=15 or len(rows)==hands:
                atomic_json(partial,dict(signature=signature,rows=rows,elapsed=elapsed+now-start))
                print(json.dumps(dict(event='progress',label=label,hands=len(rows),total=hands,seconds=round(elapsed+now-start,2))),flush=True)
                last=now
        report=summarize(rows,elapsed+time.monotonic()-start,'ev')
        report.update(candidate_seat=1,signature=signature,implementation=self.version)
        atomic_json(path,report)
        if partial.exists():partial.unlink()
        return report


TESTS = ['test_ai_weights_loading','test_offline_ai_tools','test_focused_validation',
    'test_v3_tuning','test_v1_chow_guard','test_claim_invariance','test_call_decision',
    'test_ev_engine','test_danger_model','test_tenpai_model','test_action_generator',
    'test_self_gang','test_payment_cap','test_settlement','test_physical_white_dragon','test_no_round_wind_fan']


def regression(output,label):
    cmd=[sys.executable,'-m','pytest',*[f'tests/{t}.py' for t in TESTS],'-q']
    result=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8')
    (output/(label+'.log')).write_text(result.stdout,encoding='utf-8')
    print(json.dumps(dict(event='tests',label=label,returncode=result.returncode,tail=result.stdout[-600:])),flush=True)
    return result.returncode==0


def probes():
    result=[]
    for key in KEYS:
        for scale in (.9,.95,1.05,1.1):
            cfg=copy.deepcopy(baseline());v=cfg['weights'][key]*scale
            cfg['weights'][key]=round(v) if key==KEYS[0] else v
            result.append((key.split('.')[-1]+'_'+str(scale),cfg))
    return result


def seed_audit(output, scales):
    """Scan existing experiment metadata, including expanded seed intervals."""
    findings=[]
    for p in (ROOT/'data').rglob('*.json'):
        if output in p.parents:continue
        # Reports can be several MB; only inspect metadata and recorded row seeds.
        try:data=json.loads(p.read_text(encoding='utf-8'))
        except (ValueError,OSError):continue
        if not isinstance(data,dict):continue
        if data.get('rows'):
            seeds=[r['seed'] for r in data['rows'] if 'seed' in r]
            if seeds:findings.append((str(p.relative_to(ROOT)),min(seeds),max(seeds)+1))
        args=data.get('arguments',{})
        for k in ('seed','validation_seed'):
            if k in args:
                try:
                    start=int(args[k]);hands=max(int(args.get('hands',0)),int(args.get('validation_hands',0)))
                    # Conservative expansion covers generations and selection stages.
                    end=start+(hands//4+1)*(2*int(args.get('generations',1))+2)
                    findings.append((str(p.relative_to(ROOT)),start,end))
                except (ValueError,TypeError):continue
    for label,start in SEEDS.items():
        end=start+max(scales.values())//4
        for path,lo,hi in findings:
            if max(start,lo)<min(end,hi):raise ValueError('Seed collision: '+label+' '+path)
    return findings


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--workers',type=int,default=8)
    ap.add_argument('--output',type=Path,default=ROOT/'data/ai_tuning/v3-round1')
    ap.add_argument('--pilot-only',action='store_true')
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        ev=Evaluator(out,ex)
        # Exactly twenty representative throughput hands, no sensitivity overhead.
        pilot_path=out/'pilot.json'
        if pilot_path.exists() and not args.pilot_only:
            pilot=json.loads(pilot_path.read_text(encoding='utf-8'))
            if len(pilot['rows'])!=20 or any(r['seed']!=SEEDS['pilot']+i//4 for i,r in enumerate(pilot['rows'])):
                raise ValueError('Invalid throughput pilot')
        else:
            pilot=ev.evaluate(baseline(),20,SEEDS['pilot'],'pilot')
        rate=20/pilot['elapsed_seconds']
        desired=dict(screen=300,lock=300,main=1000,pressure=252,anchor=300)
        total=6*desired['screen']+2*desired['lock']+2*desired['main']+8*desired['pressure']+desired['anchor']
        estimate=total/rate
        # Reserve 10% for tests/bootstrap/report. This is fixed before screening.
        scale=min(1,9720/max(estimate,1))
        sizes={k:max(8,4*int(v*scale/4)) for k,v in desired.items()}
        metadata=dict(implementation=ev.version,seeds=SEEDS,desired=desired,sizes=sizes,
            pilot_seconds=pilot['elapsed_seconds'],estimated_seconds=estimate,scale=scale,
            workers=args.workers,alpha=.05,attempts=1,bootstrap_seed=61017,bootstrap_repeats=10000,
            runtime=MANIFEST,pilot_implementation=pilot['implementation'],pool=[dict(version=n,fingerprint=fingerprint(c)) for n,c in zip(('V0','historical-V1','V1+guard'),ev.pool)],
            pool_fractions=[.2,.4,.4],v2_recovery='Full historical implementation fingerprint unavailable; 10% reassigned to V1+guard',
            low_risk='max public tenpai probability < 0.30',pressure_noninferiority=-1,
            reduced_scale_is_not_original_plan_power=True,
            thresholds=dict(net_lower=0,dealin_delta=0,dealin_upper=.005,claim_ratio=[.75,1.25],minimum_opportunities=200,
                progress_lower=-.05,zimo_lower=-.01,low_risk_tenpai_delta=.02,elo_lower=-10),
            timestamp=datetime.now(timezone.utc).isoformat())
        # Pilot-only also writes a reviewable proposed allocation, final run freezes it.
        if args.pilot_only:
            atomic_json(out/'pilot_plan.json',metadata);print(json.dumps(metadata),flush=True);return
        old=out/'run.json'
        if old.exists():
            previous=json.loads(old.read_text(encoding='utf-8'))
            if {k:v for k,v in previous.items() if k not in ('timestamp','seed_audit')}!={k:v for k,v in metadata.items() if k!='timestamp'}:
                raise ValueError('Frozen run changed')
            metadata=previous
        else:
            metadata['seed_audit']=seed_audit(out,sizes)
            atomic_json(old,metadata)
        configs=candidates()
        for i,cfg in enumerate(configs):atomic_json(out/f'candidate_{i}.json',cfg)
        reports=[ev.evaluate(cfg,sizes['screen'],SEEDS['screen'],f'screen_{i}') for i,cfg in enumerate(configs)]
        comparisons=[compare(r,reports[0]) for r in reports]
        atomic_json(out/'screen_comparisons.json',comparisons)
        # Filter gross collapse at screening; low-frequency sufficiency is final-only.
        eligible=[]
        for i,c in enumerate(comparisons[1:],1):
            a,b=c['candidate'],c['baseline']
            behavior_ok=all(not (b.get(t+'_take',0)>0 and a.get(t+'_take',0)==0) for t in ('chi','pong'))
            behavior_ok &= c['progress'] is not None and c['progress']['mean']>=-.05
            if behavior_ok:eligible.append(i)
        best=max(eligible or range(1,len(configs)),key=lambda i:comparisons[i]['net']['mean'])
        # Separate lock selection set, never used in final confidence bounds.
        lb=ev.evaluate(configs[0],sizes['lock'],SEEDS['lock'],'lock_baseline')
        lc=ev.evaluate(configs[best],sizes['lock'],SEEDS['lock'],'lock_candidate')
        atomic_json(out/'lock_comparison.json',compare(lc,lb))
        tests_ok=regression(out,'lock_tests')
        if not tests_ok:raise RuntimeError('Lock regression failed')
        cfg=configs[best]
        locked=dict(candidate=cfg,id=fingerprint(cfg),implementation=ev.version,screen_index=best,
            timestamp=datetime.now(timezone.utc).isoformat(),parameter_changes={k:[configs[0]['weights'][k],cfg['weights'][k]] for k in KEYS})
        if (out/'locked_candidate.json').exists():
            old_lock=json.loads((out/'locked_candidate.json').read_text(encoding='utf-8'))
            if old_lock['id']!=locked['id'] or old_lock['implementation']!=locked['implementation']:raise ValueError('Locked identity changed')
        else:atomic_json(out/'locked_candidate.json',locked)
        vb=ev.evaluate(configs[0],sizes['main'],SEEDS['main'],'main_baseline')
        vc=ev.evaluate(cfg,sizes['main'],SEEDS['main'],'main_candidate')
        main_comparison=compare(vc,vb)
        atomic_json(out/'main_comparison.json',main_comparison)
        pressure={}
        for label,cell in dict(A=[0,0,0],B=[1,1,1],C=[0,1,2],D=[2,2,2]).items():
            pb=ev.evaluate(configs[0],sizes['pressure'],SEEDS[label],label+'_baseline',cell)
            pc=ev.evaluate(cfg,sizes['pressure'],SEEDS[label],label+'_candidate',cell)
            pressure[label]=compare(pc,pb)
            atomic_json(out/(label+'_comparison.json'),pressure[label])
        # Fixed four-version anchor: guard candidate occupies the rotating target,
        # with V0/historical V1/guard incumbent in the other seats.
        anchor=ev.evaluate(cfg,sizes['anchor'],SEEDS['E'],'E_anchor',[0,1,2])
        tests_ok=regression(out,'final_tests')
        # Full BT Elo/bootstrap diagnostics are generated from the frozen rows.
        from tools.v3_reporting import elo_diagnostics, write_report
        elo=elo_diagnostics(anchor)
        atomic_json(out/'elo.json',elo)
        verdict=gates(main_comparison,pressure,tests_ok,elo.get('gain_bootstrap_lower'))
        # Throughput scaling may reduce the explicit user minimum; report as insufficient.
        verdict['minimum_main_walls']=sizes['main']>=1000
        passed=all(verdict.values())
        if passed:atomic_json(ROOT/'app/config/ai_weights_v3.json',cfg)
        preflight=[]
        for p in (out/'preflight').glob('*.json'):
            old_data=json.loads(p.read_text(encoding='utf-8'))
            if isinstance(old_data,dict) and old_data.get('rows'):
                preflight.append(dict(file=p.name,hands=len(old_data['rows']),seconds=old_data.get('elapsed_seconds',old_data.get('elapsed',0))))
        result=dict(promoted=passed,gates=verdict,elapsed_seconds=time.monotonic()-started,
            simulated_hands=20+6*sizes['screen']+2*sizes['lock']+2*sizes['main']+8*sizes['pressure']+sizes['anchor'],
            preflight=preflight,
            candidate_id=fingerprint(cfg),metadata=metadata,main=main_comparison,pressure=pressure,elo=elo)
        atomic_json(out/'result.json',result)
        write_report(out,result,comparisons)
        print(json.dumps(dict(event='complete',promoted=passed,hands=result['simulated_hands'],seconds=result['elapsed_seconds'],net=main_comparison['net'],gates=verdict)),flush=True)


if __name__=='__main__':main()
