"""Restartable paired V2 experiment with physical seat and dealer rotation."""
import hashlib
import json
import random
import time
from pathlib import Path
from tools.arena import _block, summarize
from tools.weights import fingerprint


def atomic_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)


def schedule(candidate,pool,seed,index,mode):
    rng=random.Random(seed)
    opponents=[rng.choice(pool) for _ in range(3)]
    if len({fingerprint(p) for p in opponents})==1:
        opponents[-1]=next(p for p in pool if fingerprint(p)!=fingerprint(opponents[0]))
    physical=index%4
    order=[(physical-1+i)%4 for i in range(4)]
    normalized=[opponents[0],candidate,opponents[1],opponents[2]]
    configs=[None]*4
    for i,s in enumerate(order):configs[s]=normalized[i]
    return seed,configs,mode,physical


def rotating_block(job):
    seed,configs,mode,physical=job
    order=[(physical-1+i)%4 for i in range(4)]
    rows=_block((seed,configs,mode))
    for r in rows:
        r['physical_candidate_seat']=physical
        r['net']=[r['net'][s] for s in order]
        r['policies']=[r['policies'][s] for s in order]
        for key in ('winner','dealin'):
            if r[key] is not None:r[key]=order.index(r[key])
    return rows


class Evaluation:
    def __init__(self,args,executor):
        self.args,self.executor=args,executor
        self.root=args.checkpoint_dir/args.output.name
        self.root.mkdir(parents=True,exist_ok=True)
        backend=Path(__file__).resolve().parents[1]
        paths=sorted((backend/'tools').glob('*.py'))+sorted((backend/'app/core').glob('*.py'))
        paths += [backend/'scripts/tune_claim_weights.py']
        self.version=hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()

    def __call__(self,candidate,pool,hands,seed,mode,label):
        key=hashlib.sha256(json.dumps([self.version,fingerprint(candidate),[fingerprint(p) for p in pool],hands,seed,mode]).encode()).hexdigest()
        complete=self.root/(key+'.json');partial=self.root/(key+'.partial.json')
        if complete.exists():
            print(json.dumps(dict(event='checkpoint_reused',label=label)),flush=True)
            return json.loads(complete.read_text(encoding='utf-8'))
        saved=json.loads(partial.read_text(encoding='utf-8')) if partial.exists() else {'rows':[],'elapsed':0}
        rows=saved['rows'];initial=len(rows)
        if initial%4 or initial>hands:raise ValueError('Invalid checkpoint block')
        jobs=[schedule(candidate,pool,seed+i,i,mode) for i in range(hands//4)]
        for i,r in enumerate(rows):
            job=jobs[i//4];order=[(job[3]-1+j)%4 for j in range(4)]
            if (r['seed'],r['dealer'],r['physical_candidate_seat'],r['policies'])!=(job[0],i%4,job[3],[fingerprint(job[1][s]) for s in order]):
                raise ValueError('Checkpoint schedule mismatch')
        start=last=time.monotonic()
        print(json.dumps(dict(event='evaluation_start',label=label,hands=hands,mode=mode)),flush=True)
        blocks=self.executor.map(rotating_block,jobs[initial//4:],chunksize=1) if self.executor else map(rotating_block,jobs[initial//4:])
        for block in blocks:
            rows.extend(block);now=time.monotonic()
            if now-last>=15 or len(rows)==hands:
                elapsed=now-start;rate=(len(rows)-initial)/max(elapsed,.001)
                atomic_json(partial,dict(rows=rows,elapsed=saved['elapsed']+elapsed))
                print(json.dumps(dict(event='progress',label=label,completed_hands=len(rows),total_hands=hands,
                    net_points=sum(r['net'][1] for r in rows),hands_per_second=round(rate,2),eta_seconds=round((hands-len(rows))/max(rate,.001)))),flush=True)
                last=now
        report=summarize(rows,max(.001,saved['elapsed']+time.monotonic()-start),mode)
        report.update(candidate_seat=1,seat_normalization='candidate=1; actual physical seat rotates each wall; all four dealers per wall')
        atomic_json(complete,report)
        if partial.exists():partial.unlink()
        return report
