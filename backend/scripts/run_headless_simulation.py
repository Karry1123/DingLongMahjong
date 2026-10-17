"""Offline four-AI arena. Run from any cwd; never starts FastAPI."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.weights import load_weights,POOL
from tools.arena import simulate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hands',type=int,default=1000)
    p.add_argument('--workers',type=int,default=max(1,(os.cpu_count() or 2)-1))
    p.add_argument('--seed',type=int,default=20261011)
    p.add_argument('--mode',choices=['ev','fast','explore'],default='ev')
    p.add_argument('--policies',nargs=4,type=Path,default=[POOL/'baseline_v0.json']*4)
    p.add_argument('--output',type=Path,default=Path('data/headless/report.json'))
    args=p.parse_args()
    # A 50-hand smoke run rounds UP to 52, keeping four-dealer balance.
    hands=((args.hands+3)//4)*4
    report=simulate([load_weights(x) for x in args.policies],hands,args.seed,args.workers,args.mode)
    report['requested_hands']=args.hands
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
if __name__=='__main__': main()
