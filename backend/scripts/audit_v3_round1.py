"""Read-only replay audit of recorded V3 schedules; never runs policy decisions."""
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.deck_engine import setup_new_game
from tools.claim_experiment import atomic_json
from tools.v3_experiment import ROOT, ratio_interval


def wall_identity(seed):
    deal=setup_new_game('E',rng=random.Random(seed))
    return dict(seed=seed,god=deal['dealer_tile'],
        sha256=hashlib.sha256(json.dumps(deal,sort_keys=True,separators=(',',':')).encode()).hexdigest())


def audit(output):
    records={}
    for path in output.glob('*_schedule.json'):
        schedule=json.loads(path.read_text(encoding='utf-8'))
        count=schedule['hands']//4
        records[schedule['label']]=[wall_identity(schedule['seed']+i) for i in range(count)]
    # Paired arms deliberately share identities. Distinct stages must be disjoint.
    seen={};collisions=[]
    for label,walls in records.items():
        stage=label.replace('_baseline','').replace('_candidate','')
        if stage.startswith('screen_'):stage='screen'
        for wall in walls:
            prior=seen.setdefault(wall['sha256'],stage)
            if prior!=stage:collisions.append((prior,stage,wall['seed']))
    historical={}
    for path in (ROOT/'data').rglob('*.json'):
        if output in path.parents:continue
        try:data=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):continue
        if not isinstance(data,dict):continue
        for row in data.get('rows',[]):
            if 'seed' in row:historical[row['seed']]=None
    old_hashes={wall_identity(seed)['sha256'] for seed in historical}
    historical_collisions=[(label,wall['seed']) for label,walls in records.items() for wall in walls if wall['sha256'] in old_hashes]
    implementation={}
    for path in output.glob('*.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data,dict) and data.get('rows'):
            implementation[path.name]=dict(kernel=data['kernel_sha256'],policy=data['policy_sha256'],implementation=data.get('implementation'))
    candidate=json.loads((output/'main_candidate.json').read_text(encoding='utf-8'))['rows']
    same_state=ratio_interval(candidate,candidate,'audit_low_tenpai_break','audit_low_tenpai_opp',other_num='audit_parent_low_tenpai_break')
    result=dict(walls=records,stage_collisions=collisions,historical_wall_count=len(historical),historical_collisions=historical_collisions,
        implementations=implementation,fixed_state_low_risk_tenpai=same_state)
    atomic_json(output/'wall_audit.json',result)
    if collisions or historical_collisions:raise ValueError('Wall identity collision')
    return result


if __name__=='__main__':
    out=ROOT/'data/ai_tuning/v3-round1'
    result=audit(out)
    print(json.dumps(dict(stages=len(result['walls']),historical_walls=result['historical_wall_count'],collisions=0,fixed_state_low_risk_tenpai=result['fixed_state_low_risk_tenpai']),ensure_ascii=False))
