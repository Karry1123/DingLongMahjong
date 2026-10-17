"""V2 claim-only evolution on frozen V1; one locked independent 2000-hand gate."""
import argparse
import copy
import json
import random
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import NormalDist
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.claim_v2 import DEFAULTS,BOUNDS
from tools.weights import POOL,load_weights,validate_weights,fingerprint
from tools.arena import paired_comparison
from tools.claim_experiment import Evaluation,atomic_json


def make_candidate(v1,weights):
    cfg=copy.deepcopy(v1)
    cfg.update(name='candidate_v2_claims',policy_version='V2-claims',claim_weights=weights)
    return validate_weights(cfg)


def mutate(parent,rng):
    values=dict(parent['claim_weights'])
    for key,(lo,hi) in BOUNDS.items():
        values[key]=min(hi,max(lo,values[key]+rng.gauss(0,.12)*(hi-lo)))
    return make_candidate(parent,values)


def promotion_passes(stats, baseline_seat, candidate_seat, smoke=False, tests_failed=False):
    return (not smoke and not tests_failed and stats['clusters'] >= 500
            and stats['mean_gain_per_hand'] > 0
            and candidate_seat['deal_in_rate'] <= baseline_seat['deal_in_rate'])


def write_report(args,v1,candidate,reference,result,stats,passed,evidence):
    a,b=reference['seats'][1],result['seats'][1]
    lines=['# V2 副露专项验证','',f"状态：{'通过' if passed else '未晋升'}。",'',
        'V1 的全部 165 项旧权重冻结（含 12 项已优化核心权重）；仅搜索 5 项副露权重。历史 V0/V1 使用旧实现，V2 使用独立新机制。',
        '初筛：普通舍牌用快速代理，吃碰杠用真实决策。最终候选在验证前锁定，2000 局新牌墙仅检验一次；不择优复用验证样本。',
        '对手为 V0/V1 混合池，候选物理座位每墙轮转，每墙同时跑四方轮庄。配对差分按四局牌墙块计算标准误。', '',
        '| 指标 | V1 | V2 |','| --- | ---: | ---: |',
        f"| 局数 | {reference['hands']} | {result['hands']} |",f"| 平均净分/局 | {a['mean_net_points']:.6f} | {b['mean_net_points']:.6f} |",
        f"| 和牌率 | {a['win_rate']:.2%} | {b['win_rate']:.2%} |",f"| 放铳率 | {a['deal_in_rate']:.2%} | {b['deal_in_rate']:.2%} |",'',
        f"配对增益 {stats['mean_gain_per_hand']:.6f}；单侧 95% 常态近似下界 {stats['lower_95_percent']:.6f}；独立牌墙块 {stats['clusters']}。",'',
        '本批次按用户新门槛晋升：配对平均净分增益 >0 且放铳率不高于 V1。95% 下界仍报告，但不作为此批次晋升条件；均值为正不等于统计显著。','',
        '| 参数 | V1 | V2 初值 | 搜索结果 | 界限 |','| --- | --- | ---: | ---: | --- |']
    prior={'redundant_chow_penalty':'55','no_advance_chow_penalty':'18',
        'claim_to_tenpai_reward':'60（庄家另加20）','pung_value_incentive':'2.5（旧公式另有附加激励）',
        'kong_risk_reward_factor':'无独立参数；旧逻辑有杠牌保底/强制补杠'}
    for key,value in candidate['claim_weights'].items():lines.append(f'| {key} | {prior[key]} | {DEFAULTS[key]} | {value:.8g} | {BOUNDS[key]} |')
    lines += ['', '## 机制差异', '',
        '- 所有副露与过牌调用同一待摸状态估值：听牌统一 Σ剩余张数×胡牌收益/8；非听牌统一进张/结构近似和向听惩罚。此为启发式评分，非校准后的真实货币期望。',
        '- 删除副露分支专有的“切掉虚构孤张”奖励；冗余、原样打回、向听倒退吃牌严格低于过牌，罚分最小值也不能突破护栏。',
        '- 原样打回且听口/逐张胡数完全相同的吃牌在调参奖励前从 AI 可选动作池硬过滤，审计行记为负无穷；手动规则合法性不改变。',
        '- 过牌只在未听牌时增加摸牌机会补偿；已听牌的 Rem/8 已包含进张机会，避免重复补偿。碰底胡激励收紧至0.8~1.25。',
        '- 明杠/暗杠/补杠枚举全部可见剩余补张并处理岭上和牌；无强制补杠或杠相对碰的保底加分；补杠额外扣公开信息估算的抢杠风险。',
        '- 台州规则不虚构门清役；硬胡、明暗刻及实际番分由原规则计分器计算。', '',
        f"专项测试证据：`{evidence.name}`。V1 指纹：`{fingerprint(v1)}`；候选指纹：`{fingerprint(candidate)}`。",'',
        '通过时写 app/config/ai_weights_v2.json；未通过仅保存实验候选。不会自动替换 ai_weights_optimized.json 或启用线上 V2。未部署、未 git push。','']
    report='\n'.join(lines)
    (args.output/'validation_report.md').write_text(report,encoding='utf-8')
    if not args.smoke_test:
        (Path(__file__).resolve().parents[2]/'docs'/f'{args.output.name}_report.md').write_text(report,encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generations',type=int,default=2);p.add_argument('--population',type=int,default=6)
    p.add_argument('--hands',type=int,default=500);p.add_argument('--validation-hands',type=int,default=2000)
    p.add_argument('--workers',type=int,default=8);p.add_argument('--seed',type=int,default=20291000)
    p.add_argument('--validation-seed',type=int,default=20301000)
    p.add_argument('--output',type=Path,default=Path('data/ai_tuning/v2-claims'))
    p.add_argument('--checkpoint-dir',type=Path,default=Path('data/checkpoints'))
    p.add_argument('--resume',action='store_true');p.add_argument('--smoke-test',action='store_true')
    args=p.parse_args()
    if min(args.generations,args.population,args.workers)<1 or args.hands<4 or args.hands%4 or args.validation_hands%4 or args.validation_hands<(4 if args.smoke_test else 2000):p.error('Invalid sample counts')
    if args.seed+args.generations*(args.hands//4+1)>=args.validation_seed:p.error('Holdout seed overlaps exploration')
    args.output.mkdir(parents=True,exist_ok=True)
    # Gate runs before any simulation and again before promotion.
    evidence=args.output/'invariant_tests.log'
    command=[sys.executable,'-m','pytest','tests/test_claim_invariance.py','-q']
    test=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
    evidence.write_text(test.stdout+test.stderr,encoding='utf-8')
    if test.returncode:raise RuntimeError('Claim invariants failed; see '+str(evidence))
    print(json.dumps(dict(event='invariants_passed',output=test.stdout.strip())),flush=True)
    v1=load_weights(POOL/'baseline_v1.json');live=load_weights(Path('app/config/ai_weights_optimized.json'))
    if fingerprint(v1)!=fingerprint(live):raise ValueError('V1 baseline differs from verified optimized file')
    pool=[load_weights(POOL/'baseline_v0.json'),v1]
    executor=ProcessPoolExecutor(max_workers=args.workers) if args.workers>1 else None
    try:
        evaluate=Evaluation(args,executor)
        signature={k:str(v) for k,v in vars(args).items() if k not in ('resume','workers')}
        initial=dict(arguments=signature,implementation=evaluate.version,pool=[fingerprint(x) for x in pool])
        manifest=evaluate.root/'initial.json'
        if manifest.exists():
            if not args.resume or json.loads(manifest.read_text())!=initial:raise ValueError('Use --resume with identical source/arguments or fresh output')
        else:
            if args.resume:raise ValueError('No checkpoint to resume')
            atomic_json(manifest,initial)
        atomic_json(args.output/'run.json',initial)
        rng=random.Random(args.seed);parent=make_candidate(v1,dict(DEFAULTS));best=None
        for generation in range(args.generations):
            seed=args.seed+generation*(args.hands//4+1)
            reference=evaluate(v1,pool,args.hands,seed,'claim-explore',f'g{generation+1}-v1')
            candidates=[parent]+[mutate(parent,rng) for _ in range(args.population-1)]
            trials=[]
            for index,cfg in enumerate(candidates):
                r=evaluate(cfg,pool,args.hands,seed,'claim-explore',f'g{generation+1}-candidate{index+1}')
                comparison=paired_comparison(r,reference)
                row=dict(generation=generation+1,candidate=index+1,config=cfg,comparison=comparison,metrics=r['seats'][1])
                atomic_json(args.output/f'trial_{generation+1}_{index+1}.json',row)
                print(json.dumps(dict(event='trial_complete',generation=generation+1,candidate=index+1,gain=comparison['mean_gain_per_hand'])),flush=True)
                trials.append(row)
            elite=max(trials,key=lambda r:r['comparison']['mean_gain_per_hand']);parent=elite['config']
            # Rank on the last generation's common walls; do not rank noisy means across seed sets.
            best=elite
            atomic_json(evaluate.root/f'generation_{generation+1}.json',dict(elite=elite,completed=True))
            print(json.dumps(dict(event='generation_complete',generation=generation+1,best_gain=elite['comparison']['mean_gain_per_hand'])),flush=True)
        candidate=best['config'];atomic_json(args.output/'locked_candidate.json',candidate)
        reference=evaluate(v1,pool,args.validation_hands,args.validation_seed,'ev','holdout-v1')
        result=evaluate(candidate,pool,args.validation_hands,args.validation_seed,'ev','holdout-v2')
        stats=paired_comparison(result,reference)
        stats['lower_95_percent']=stats['mean_gain_per_hand']-NormalDist().inv_cdf(.95)*stats['standard_error']
        # Same code fingerprint must still be on disk; prevent mixing live edits into a run.
        if Evaluation(args,executor).version!=evaluate.version:raise RuntimeError('Implementation changed during experiment')
        final_test=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
        (args.output/'final_invariant_tests.log').write_text(final_test.stdout+final_test.stderr,encoding='utf-8')
        passed=promotion_passes(stats, reference['seats'][1], result['seats'][1], args.smoke_test, bool(final_test.returncode))
        atomic_json(args.output/'validation_v1.json',reference);atomic_json(args.output/'validation_v2.json',result)
        atomic_json(args.output/'comparison.json',stats)
        if passed:
            destination=Path('app/config/ai_weights_v2.json')
            if destination.exists() and load_weights(destination)!=candidate:raise ValueError('Existing V2 config differs; preserved existing file')
            atomic_json(destination,candidate);atomic_json(args.output/'ai_weights_v2.json',candidate)
        write_report(args,v1,candidate,reference,result,stats,passed,evidence)
        status=dict(completed=True,promoted=passed,smoke_test=args.smoke_test,comparison=stats,
                    config_written=passed,policy=fingerprint(candidate),production_activated=False,
                    gate='mean_gain>0 and deal_in_rate<=V1; invariants pass; >=2000 hands',
                    statistically_significant=stats['lower_95_percent']>0)
        atomic_json(args.output/'final_status.json',status)
        print(json.dumps(status),flush=True)
    finally:
        if executor:executor.shutdown(wait=True,cancel_futures=True)


if __name__=='__main__':main()
