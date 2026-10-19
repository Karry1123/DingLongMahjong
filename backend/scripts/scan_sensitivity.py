"""Reusable fixed-state scan CLI; training seeds only."""
import argparse
import json
import pickle
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.sensitivity_scan import KEYS,KONGS,collect_wall,scan_key,state_signature
from tools.claim_experiment import atomic_json

def run_scan(out,ex,seed=32610000,walls=40):
    started=time.monotonic();out.mkdir(parents=True,exist_ok=True)
    training=out/'training_states.pkl'
    if training.exists():
        states,kongs=pickle.loads(training.read_bytes())
    else:
        states=[];kongs=[]
        for a,b in ex.map(collect_wall,[(seed+i,'ev') for i in range(walls)]):
            states.extend(a);kongs.extend(b)
        training.write_bytes(pickle.dumps((states,kongs)))
    assert walls>=40 and len(states)>=1000
    ranking=[]
    for r in ex.map(scan_key,[(k,states) for k in KEYS],chunksize=1):
        ranking.append(r);print(json.dumps(dict(event='sensitivity',**r)),flush=True)
        atomic_json(out/'sensitivity.partial.json',ranking)
    ranking.sort(key=lambda r:(-r['rate'],r['key']))
    result=dict(seed=seed,walls=walls,states=len(states),ranking=ranking,seconds=time.monotonic()-started)
    atomic_json(out/'sensitivity.json',result)
    return result,kongs

def enrich(out,ex,kongs,seed=32620000):
    path=out/'kong_states.pkl'
    if path.exists():return pickle.loads(path.read_bytes())
    unique={state_signature(s):s for s in kongs};kongs=list(unique.values())
    def counts():return {t:sum(any(a['action_type']==t for a in s.options[s.seat]) for s in kongs) for t in KONGS}
    walls=0
    while min(counts().values())<200:
        for _,b in ex.map(collect_wall,[(seed+walls+i,'fast') for i in range(40)]):
            for s in b:unique.setdefault(state_signature(s),s)
        kongs=list(unique.values())
        walls+=40
        print(json.dumps(dict(event='kong_enrichment',walls=walls,counts=counts())),flush=True)
        if walls>=20000:raise RuntimeError('Kong training budget exhausted')
    path.write_bytes(pickle.dumps(kongs))
    atomic_json(out/'kong_training.json',dict(seed=seed,walls=walls,hands=walls,counts=counts(),deduplicated=True,trajectory='EV scan walls plus one fast hand per additional training wall; evaluated with full EV'))
    return kongs

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=8);ap.add_argument('--output',type=Path,default=Path('data/ai_tuning/v4-round2'));args=ap.parse_args()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:run_scan(args.output,ex)
