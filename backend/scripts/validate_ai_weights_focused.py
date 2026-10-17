"""Lock the best observed candidate; append fresh paired EV evidence, no search."""
import argparse,copy,json,math,sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from statistics import NormalDist
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.tune_ai_weights import atomic_json
from tools.weights import load_weights,validate_weights,fingerprint,POOL
from tools.core_search import CORE_KEYS
from tools.experiment_io import CheckpointEvaluator
from tools.arena import paired_comparison,summarize

def combine(old,new):
    if old['mode']!='ev' or new['mode']!='ev':raise ValueError('Only full EV evidence may be pooled')
    if (old['kernel_sha256'],old.get('policy_sha256'),old['mode'])!=(new['kernel_sha256'],new.get('policy_sha256'),new['mode']):
        raise ValueError('Cannot combine different rule/policy implementations')
    if {r['seed'] for r in old['rows']} & {r['seed'] for r in new['rows']}:raise ValueError('Holdout walls overlap')
    result=summarize(old['rows']+new['rows'],old['elapsed_seconds']+new['elapsed_seconds'],'ev')
    result['candidate_seat']=1
    return result

def gate(stats,hands):
    # Single prespecified contrast, one-sided 95% large-sample cluster CI.
    lower=stats['mean_gain_per_hand']-NormalDist().inv_cdf(.95)*stats['standard_error']
    return hands>=4000 and stats['clusters']>=1000 and lower>0,lower

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=Path('data/ai_tuning/formal-core-3g-v2'))
    p.add_argument('--output',type=Path,default=Path('data/ai_tuning/focused-best-4000'))
    p.add_argument('--checkpoint-dir',type=Path,default=Path('data/checkpoints'))
    p.add_argument('--workers',type=int,default=8);p.add_argument('--seed',type=int,default=20280000)
    p.add_argument('--resume',action='store_true')
    args=p.parse_args()
    if args.workers<1:p.error('workers must be positive')
    audits=[json.loads(f.read_text()) for f in sorted(args.source.glob('validation_*.json')) if 'hands' not in f.name]
    if not audits:p.error('No original validations')
    best=max(audits,key=lambda a:a['vs_v0']['mean_gain_per_hand'])
    candidate=validate_weights(copy.deepcopy(best['config']));baseline=load_weights(POOL/'baseline_v0.json')
    original=json.loads((args.source/f"validation_hands_{best['generation']:04}_{best['rank']}.json").read_text())
    reference=json.loads((args.source/f"stage2_baseline_{best['generation']:04}.json").read_text())['v0']
    if original['hands']!=2000 or reference['hands']!=2000:p.error('Exactly 2000 original hands required')
    if any(r['policies'][1]!=fingerprint(candidate) for r in original['rows']):p.error('Candidate fingerprint mismatch')
    if any(r['policies'][1]!=fingerprint(baseline) for r in reference['rows']):p.error('V0 fingerprint mismatch')
    paired_comparison(original,reference)
    oldrun=json.loads((args.source/'run.json').read_text())['arguments']
    initial=json.loads((args.checkpoint_dir/args.source.name/'initial.json').read_text())
    pool=[validate_weights(c) for c in initial['pool']]
    # Exclude ALL previous training and validation walls, not only winner's walls.
    g=int(oldrun['generations']);train=int(oldrun['hands']);holdout=int(oldrun['validation_hands']);start=int(oldrun['seed'])
    stride=max(train,holdout)//4+1
    seen={start+gen*stride+i for gen in range(g) for i in range(train//4)}
    seen|={start+(g+gen)*stride+i for gen in range(g) for i in range(holdout//4)}
    if seen & set(range(args.seed,args.seed+500)):p.error('Fresh seeds overlap prior search')
    args.output.mkdir(parents=True,exist_ok=True)
    lockpath=args.output/'locked_candidate.json'
    if lockpath.exists():
        if not args.resume:p.error('Output already exists; use --resume')
        if fingerprint(load_weights(lockpath))!=fingerprint(candidate):p.error('Locked candidate changed')
    else:atomic_json(lockpath,candidate)
    executor=ProcessPoolExecutor(max_workers=args.workers) if args.workers>1 else None
    try:
        evaluate=CheckpointEvaluator(args,executor,atomic_json)
        manifest={'candidate':fingerprint(candidate),'baseline':fingerprint(baseline),'seed':args.seed,
            'old_source':str(args.source.resolve()),'version':evaluate.version,'pool':[fingerprint(c) for c in pool]}
        manifest_path=args.output/'run.json'
        if manifest_path.exists() and json.loads(manifest_path.read_text())!=manifest:raise ValueError('Resume manifest changed')
        atomic_json(manifest_path,manifest)
        print(json.dumps({'event':'candidate_locked','source_generation':best['generation']+1,'source_elite':best['rank']+1,
            'fingerprint':fingerprint(candidate),'fresh_hands':2000,'combined_hands':4000,'seed':args.seed}),flush=True)
        fresh_v0=evaluate(baseline,2000,args.seed,args.workers,'ev',pool)
        fresh=evaluate(candidate,2000,args.seed,args.workers,'ev',pool)
        combined=combine(original,fresh);combined_v0=combine(reference,fresh_v0)
        combined_stats=paired_comparison(combined,combined_v0);fresh_stats=paired_comparison(fresh,fresh_v0)
        passed,lower=gate(combined_stats,combined['hands'])
        _,fresh_lower=gate(fresh_stats,4000) # interval only; fresh has 500 clusters, cannot promote alone here.
        atomic_json(args.output/'fresh_2000.json',{'candidate':fresh,'v0':fresh_v0})
        atomic_json(args.output/'combined_4000.json',{'candidate':combined,'v0':combined_v0})
        result={'accepted':passed,'combined':combined_stats,'combined_lower_95':lower,'fresh':fresh_stats,'fresh_lower_95':fresh_lower,
            'criterion':'single one-sided 95% normal-approximation cluster CI; combined lower > 0',
            'selection_bias':'Original 2000 selected from 9 candidates; pooled interval is not a selection-adjusted confirmatory CI.'}
        atomic_json(args.output/'final_status.json',result)
        destination=Path(__file__).resolve().parents[1]/'app/config/ai_weights_optimized.json'
        if passed:
            if destination.exists() and fingerprint(load_weights(destination))!=fingerprint(candidate):
                atomic_json(args.output/'previous_optimized_backup.json',load_weights(destination))
            atomic_json(destination,candidate)
            atomic_json(args.output/'ai_weights_optimized.json',candidate)
        lines=['# 最佳候选单独深度验证（4000 局）','',f"用户指定晋升门槛：{'通过' if passed else '未通过'}。",'',
            '候选在追加样本前锁定。新增 2000 局使用全新随机牌墙，物理座位 1 对抗固定历史池、每墙四方轮庄；两组参数均不再搜索。', '',
            '| 样本 | 净分增益/局 | 标准误 | 单侧 95% 下界（常态近似） |','| --- | ---: | ---: | ---: |',
            f"| 新增独立 2000 局 | {fresh_stats['mean_gain_per_hand']:.6f} | {fresh_stats['standard_error']:.6f} | {fresh_lower:.6f} |",
            f"| 累计 4000 局 | {combined_stats['mean_gain_per_hand']:.6f} | {combined_stats['standard_error']:.6f} | {lower:.6f} |",'',
            '置信区间以四局牌墙块为独立统计单位。旧 2000 局用于从 9 组候选中择优，因此合并结果仍有选择偏差；本报告按用户指定的合并门槛决定写出配置，同时单独报告新增样本，不将合并区间解释为消除了择优偏差。', '',
            '| 累计战绩 | V0 | 锁定候选 |','| --- | ---: | ---: |','| 局数 | 4000 | 4000 |']
        a=combined_v0['seats'][1];b=combined['seats'][1]
        lines += [f"| 平均净分/局 | {a['mean_net_points']:.6f} | {b['mean_net_points']:.6f} |",
            f"| 和牌率 | {a['win_rate']:.2%} | {b['win_rate']:.2%} |",f"| 放铳率 | {a['deal_in_rate']:.2%} | {b['deal_in_rate']:.2%} |",'',
            '| 核心权重 | V0 | 固化候选 |','| --- | ---: | ---: |']
        lines += [f"| `{key}` | {baseline['weights'][key]:.8g} | {candidate['weights'][key]:.8g} |" for key in CORE_KEYS]
        lines += ['',f"正式配置：{destination if passed else '未生成'}。仅写配置文件，未修改生产加载逻辑、未部署、未 git push。",'']
        (args.output/'validation_report.md').write_text('\n'.join(lines),encoding='utf-8')
        print(json.dumps({'event':'complete',**result,'optimized_written':passed}),flush=True)
    finally:
        if executor is not None:executor.shutdown(wait=True,cancel_futures=True)

if __name__=='__main__':main()
