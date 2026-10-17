"""Restartable evaluations and human-readable validation reports."""
import hashlib,json,time
from pathlib import Path
from tools.arena import evaluate_pool
from tools.weights import fingerprint
from tools.core_search import CORE_KEYS

class CheckpointEvaluator:
    def __init__(self,args,executor,atomic_json):
        self.args=args;self.executor=executor;self.write=atomic_json
        self.root=args.checkpoint_dir/args.output.name
        self.root.mkdir(parents=True,exist_ok=True)
        sources=Path(__file__).parent
        self.version=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(sources.glob('*.py')))+b''.join(p.read_bytes() for p in sorted((sources.parent/'app/core').glob('*.py')))).hexdigest()
    def __call__(self,candidate,hands,seed,workers,mode,pool):
        key=hashlib.sha256(json.dumps([self.version,fingerprint(candidate),hands,seed,mode,[fingerprint(p) for p in pool]]).encode()).hexdigest()
        path=self.root/('evaluation_'+key+'.json');partial=self.root/('partial_'+key+'.json')
        if path.exists():
            print(json.dumps({'event':'checkpoint_reused','mode':mode,'hands':hands,'seed':seed}),flush=True)
            return json.loads(path.read_text())
        saved=json.loads(partial.read_text()) if partial.exists() else {'rows':[],'elapsed':0}
        initial=len(saved['rows']);last=time.monotonic()
        def progress(rows,elapsed):
            nonlocal last
            if time.monotonic()-last<15 and len(rows)!=hands:return
            last=time.monotonic();done=len(rows)-initial;rate=done/max(elapsed,.001)
            self.write(partial,{'rows':rows,'elapsed':saved['elapsed']+elapsed})
            print(json.dumps({'event':'progress','mode':mode,'policy':fingerprint(candidate)[:12],'seed':seed,
                'completed_hands':len(rows),'total_hands':hands,'net_points':sum(r['net'][1] for r in rows),
                'hands_per_second':round(rate,2),'eta_seconds':round((hands-len(rows))/max(rate,.001))}),flush=True)
        report=evaluate_pool(candidate,hands,seed,workers,mode,pool,executor=self.executor,resume_rows=saved['rows'],progress=progress)
        report['elapsed_seconds']+=saved['elapsed'];report['hands_per_second']=hands/max(.001,report['elapsed_seconds'])
        self.write(path,report)
        if partial.exists():partial.unlink()
        return report

def write_report(output,baseline,atomic_json):
    audits=[json.loads(p.read_text()) for p in sorted(output.glob('validation_*.json')) if 'hands' not in p.name]
    if not audits:
        (output/'validation_report.md').write_text('# 麻将 AI 搜索报告\n\n没有候选在快速筛选中超过 V0，未进入完整 EV 验证，未输出 optimized 配置。\n',encoding='utf-8')
        atomic_json(output/'final_status.json',{'accepted_count':0,'evaluated_elites':0,'optimized_exists':False})
        return
    accepted=[a for a in audits if a['accepted']]
    best=accepted[-1] if accepted else max(audits,key=lambda a:a['vs_v0']['mean_gain_per_hand'])
    if accepted:
        optimized=json.loads((output/'ai_weights_optimized.json').read_text())
        best=next(a for a in reversed(accepted) if fingerprint(a['config'])==fingerprint(optimized))
    reference=json.loads((output/f"stage2_baseline_{best['generation']:04}.json").read_text())['v0']
    cand=best['evaluation'];a=reference['seats'][1];b=cand['seats'][1]
    lines=['# 麻将 AI 完整 EV 交叉检验报告','',f"状态：{'通过晋升' if accepted else '未有候选通过晋升；以下为最佳观察候选'}。",'',
        f"第 {best['generation']+1} 轮，精英 {best['rank']+1}；同牌墙、相同历史对手池、四方轮庄，{cand['hands']} 局（{cand['hands']//4} 个独立牌墙块）。",'',
        '| 指标 | V0 | 候选 |','| --- | ---: | ---: |',f"| 总局数 | {reference['hands']} | {cand['hands']} |",
        f"| 平均净分/局 | {a['mean_net_points']:.4f} | {b['mean_net_points']:.4f} |",
        f"| 和牌率 | {a['win_rate']:.2%} | {b['win_rate']:.2%} |",f"| 放铳率 | {a['deal_in_rate']:.2%} | {b['deal_in_rate']:.2%} |",'',
        f"配对净分增益：{best['vs_v0']['mean_gain_per_hand']:.4f}/局；标准误 {best['vs_v0']['standard_error']:.4f}。",'',
        '晋升按预设代数 × 精英数校正单侧显著性，同时检验 V0 与上一个稳定版本；默认 V0 增益下界须超过 1 分/局。', '',
        '| 核心参数 | V0 | 候选 | 倾向解读（仅权重变化，非已证实行为） |','| --- | ---: | ---: | --- |']
    for key in CORE_KEYS:
        old=baseline['weights'][key];new=best['config']['weights'][key]
        direction='提高' if new>old else '降低' if new<old else '保持'
        if 'SIGMOID_CENTER' in key:note='风险上升时点更晚' if new>old else '风险上升时点更早'
        elif 'STEEPNESS' in key:note='巡目风险曲线更陡' if new>old else '巡目风险曲线更平缓'
        elif 'RISK_REFERENCE' in key:note='风险厌恶减弱' if new>old else '风险厌恶增强'
        elif 'DEFENSE_SCALE' in key:note=direction+'好形手牌的防守损失折价系数'
        elif 'SHANTEN' in key:note=direction+'向听推进优先度'
        elif 'UKEIRE' in key:note=direction+'进张广度价值'
        elif 'JOKER' in key:note=direction+'财神相关保留价值'
        else:note=direction+'役牌/雀头保留价值'
        if new==old:note='保持 V0'
        lines.append(f'| `{key}` | {old:g} | {new:g} | {note} |')
    lines+=['','该配置未自动加载到线上。未通过晋升时，best_candidate.json 仍属于实验候选。','']
    path=output/'validation_report.md';tmp=path.with_suffix('.md.tmp');tmp.write_text('\n'.join(lines),encoding='utf-8');tmp.replace(path)
    atomic_json(output/'final_status.json',{'accepted_count':len(accepted),'evaluated_elites':len(audits),'optimized_exists':bool(accepted),'best_observed_gain':best['vs_v0']['mean_gain_per_hand']})
