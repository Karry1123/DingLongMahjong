"""Third V4 attempt: frozen candidate, new walls, R2 sequential preregistration."""
import argparse
import copy
import hashlib
import json
import math
import pickle
import random
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.claim_experiment import atomic_json
from tools.sensitivity_scan import baseline,perturb,KONGS,kong_compare,state_signature
from tools.v3_experiment import ROOT,compare,gates,interval,quantile
from tools.v4_round3 import ALPHA,NORMAL,required_walls,achieved_power,spending,kong_gates,allocate
from tools.arena import summarize
from tools.weights import fingerprint,validate_weights
from scripts.tune_ai_weights_v4 import Evaluator,seed_audit
from scripts.scan_sensitivity import enrich
from tools.v4_reporting import elo_diagnostics
from tools.report_common import table

SEEDS=dict(pilot=42600100,training=42610000,screen=42710000,main=42810000,A=42910000,B=42920000,C=42930000,D=42940000,E=42950000)
TESTS=['test_ai_weights_loading','test_offline_ai_tools','test_focused_validation','test_v3_tuning','test_v4_tuning','test_sensitivity_scan','test_v4_round3']

def net_bounds(a,b,alpha):
    from tools.arena import paired_comparison
    paired_comparison(a,b)
    x=[sum(c['net'][1]-p['net'][1] for c,p in zip(a['rows'][i:i+4],b['rows'][i:i+4]))/4 for i in range(0,len(a['rows']),4)]
    ci=interval(x)
    rng=random.Random(61017)
    draws=sorted(sum(rng.choices(x,k=len(x)))/len(x) for _ in range(10000))
    ci.update(corrected_normal_lower=ci['mean']-NORMAL.inv_cdf(1-alpha)*ci['se'],corrected_bootstrap_lower=quantile(draws,alpha),alpha=alpha)
    return ci

def verdict(main,pressure,elo,kong,bounds):
    g=gates(main,pressure,True,elo['gain_bootstrap_lower'])
    # R1 replaces all natural-distribution kong sufficiency/rate/noncollapse with fixed-state tests.
    for t in KONGS:
        for prefix in ('opportunities_','rate_','noncollapse_'):g.pop(prefix+t,None)
    g.update(kong_gates(kong))
    g['net']=min(bounds['corrected_normal_lower'],bounds['corrected_bootstrap_lower'])>0
    g['pressure_complete']=set(pressure)==set('ABCD')
    return g

def report(out,r):
    m=r['main'];n=r['bounds'];meta=r['metadata']
    lines=['# V4 第三小轮报告','','## 方法修订 R2 摘要','',
      '锁定 _UKEIRE_QUALITY_WEIGHT=1.246728，仅修改这一项；不重筛、不使用旧主验证调整候选。现任 V1+guard，生产加载保持原样。',
      '第三次确认性尝试 α=0.05/3；三节点采用 O’Brien–Fleming 形状累计支出，其差额作为各节点局部 α，使用并集界保证总 α 不超过 0.05/3（比经典相关边界更保守）。正态与墙块 bootstrap 下界同时大于零才过主净分门槛；未校正 95% 区间仅描述。',
      '每类杠至少200个固定状态，有收益杠接受率不得低于现任减2pp；1/125的偶然差异不再一票否决。仍保留选择率比[0.75,1.25]及非杠选择。',
      '放铳沿用差值点估计≤0且单侧95%上界≤+0.5pp；压力非劣下界≥−1；Elo下界≥−10；其余吃碰、推进、自摸及低风险弃听门槛沿用。','',
      '## 功效表','', '按上一轮配对墙块标准差9.2，n=ceil(((z(1−α)+z(0.8))*9.2/δ)^2)，不是把四庄或两臂当独立样本。']
    lines+=table(('目标分/局','未校正α=.05墙块','α=.05/3墙块','两臂合计局数'),[(d,required_walls(d,alpha=.05),required_walls(d),8*required_walls(d)) for d in (.3,.4,.5)])
    lines+=['',f"+0.4、80%目标按序贯末节点局部α迭代定为每臂 {meta['desired_main']} 局；约1500墙块的原估计不足。实配每臂 {meta['sizes']['main']} 局；固定末节点近似功效 {meta['actual_power']:.2%}（保守值，不包含早停增益）。",
      '预算按主验证>压力>E排序缩减，20%预留富集、统计和测试，训练快筛预留1500局；压力目标每臂1000局，E目标1000局。缩减只由吞吐决定，未查看验证结果。',
      '', '## 实际规模与耗时','',f"20局试跑 {meta['pilot_seconds']:.2f} 秒，workers=8。自然对局总数 {r['simulated_hands']}；另有杠训练 {r['kong_training']['hands']} 局。累计耗时 {r['elapsed_seconds']:.2f} 秒。各阶段耗时及赛程见数据目录。",
      '```json',json.dumps({k:meta[k] for k in ('sizes','seeds','nodes','actual_power','desired_main','runtime_limit_seconds')},ensure_ascii=False,indent=2),'```',
      '全新种子与既往全部数据范围已审计；audit含实际rows和预登记seed元数据的保守区间。共同随机数只在本轮相同对照配对内复用。检查点绑定实现、候选、赛程与规模。',
      '', '## 主验证（含序贯节点）','',f"提前停止：{r['early_stop']}。只有节点净分及其他全部门槛同时满足才提前停止；否则跑满。"]
    lines+=table(('墙块/臂','局部α','净分增益','校正正态下界','校正bootstrap下界','未校正正态下界','未校正bootstrap下界'),[(x['clusters'],x['alpha'],x['mean'],x['corrected_normal_lower'],x['corrected_bootstrap_lower'],x['normal_lower'],x['bootstrap_lower']) for x in r['nodes']])
    lines+=['',f"主验证净分 {n['mean']:+.6f}/局；SE={n['se']:.6f}；按轮次α单独校正、未计序贯的正态下界 {n['mean']-NORMAL.inv_cdf(1-ALPHA)*n['se']:.6f}。实际晋升使用表中序贯下界。",
       '', '## 放铳','', f"差值 {m['dealin']['mean']*100:+.4f}pp；正态上界 {m['dealin']['normal_upper']*100:+.4f}pp，bootstrap上界 {m['dealin']['bootstrap_upper']*100:+.4f}pp。取较高上界判定。",
       '', '## 杠专项','', '训练集独立、去重；完整EV重放，有收益标签排除可立即和牌状态；专项不并入自然分布净分。']
    lines+=table(('类型','状态','现任/候选选择','有收益数','有收益现任/候选选择','接受率差pp'),[(t,x['states'],f"{x.get('parent_take',0)}/{x.get('candidate_take',0)}",x.get('benefit',0),f"{x.get('benefit_parent_take',0)}/{x.get('benefit_candidate_take',0)}",100*(x.get('benefit_candidate_take',0)-x.get('benefit_parent_take',0))/x['benefit'] if x.get('benefit') else '无分母') for t,x in r['kong'].items()])
    lines+=['','```json',json.dumps(r['kong_training'],ensure_ascii=False,indent=2),'```','','## 压力 A~D','','A=V0×3；B=历史V1×3；C=V0/历史V1/guard；D=guard×3。非劣界−1；缩减造成的功效下降见实际局数。']
    lines+=table(('单元','每臂局数','净分差','正态下界','bootstrap下界'),[(k,4*v['net']['clusters'],v['net']['mean'],v['net']['normal_lower'],v['net']['bootstrap_lower']) for k,v in r['pressure'].items()])
    lines+=['','## Elo','',f"E锚点 {r['elo']['hands']} 局；Elo增益 {r['elo']['gain']:.6f}，墙块bootstrap下界 {r['elo']['gain_bootstrap_lower']:.6f}。门槛≥−10。",'','## 门槛逐项','']
    lines+=table(('门槛','结果'),[(k,'通过' if v else '未通过') for k,v in r['gates'].items()])
    lines+=['','## 下一轮候选：役牌孤张快筛','','仅独立训练墙、非确认性；不参与本轮锁定和门槛；最多5组×300局，其他参数冻结于现任。']
    lines+=table(('组','孤张权重','局数','相对现任净分/局'),[(x['label'],x['value'],x['hands'],x['net']) for x in r['screen']])
    lines+=['','## 结论与下一轮建议','', '全部通过，生成独立V4配置。' if r['promoted'] else '未晋升；不生成V4配置，候选仅保存在data/ai_tuning/v4-round3/。',
       '保持现任。样本缩减或区间跨零代表证据不足，不代表已证明候选更差；下一轮应在独立训练集锁定候选后，用新墙预登记新的尝试数与更高预算。役牌快筛均值只用于下一轮训练候选排序。',
       '', '复现：`.\\.venv\\Scripts\\python.exe scripts/tune_ai_weights_v4_round3.py --workers 8 --resume`；后台输出 `data/ai_tuning/v4-round3/console.log`。',
       f"回归命令：`{r['test_command']}`；结果见pytest.log（本报告在最终pytest之前写入，测试后只更新验收状态）。"]
    (ROOT.parent/'docs/ai_weights_v4_round3_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def audit_registered_seeds(out):
    findings=[]
    def walk(x,path):
        if isinstance(x,dict):
            seeds=x.get('seeds')
            if isinstance(seeds,dict):
                for label,seed in seeds.items():
                    if isinstance(seed,int):findings.append((str(path),seed,seed+20000))
            for value in x.values():walk(value,path)
        elif isinstance(x,list):
            for value in x:walk(value,path)
    for path in (ROOT/'data').rglob('*.json'):
        if out in path.parents:continue
        try:walk(json.loads(path.read_text(encoding='utf-8')),path.relative_to(ROOT))
        except (ValueError,OSError):continue
    for label,start in SEEDS.items():
        for path,lo,hi in findings:
            if max(start,lo)<min(start+20000,hi):raise ValueError('Registered seed collision: '+label+' '+path)
    # Slots separated by 10000 for pressures; each needs only 250 walls.
    ranges={k:(v,v+(20000 if k=='training' else 8000 if k=='main' else 250)) for k,v in SEEDS.items()}
    items=list(ranges.items())
    for i,(label,(lo,hi)) in enumerate(items):
        for other,(a,b) in items[i+1:]:
            if max(lo,a)<min(hi,b):raise ValueError('Internal seed overlap: '+label+' '+other)
    return findings

def execute(args):
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'run.json').exists() and not args.resume:raise ValueError('Use --resume for existing run')
    parent=baseline();cfg=copy.deepcopy(parent);cfg['weights']['ev_engine._UKEIRE_QUALITY_WEIGHT']=parent['weights']['ev_engine._UKEIRE_QUALITY_WEIGHT']*1.4;cfg['name']='v4_round3_locked';validate_weights(cfg)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        ev=Evaluator(out,ex);ev.version=hashlib.sha256((ev.version+Path(__file__).read_text(encoding='utf-8')).encode()).hexdigest()
        pilot=json.loads((out/'pilot.json').read_text(encoding='utf-8')) if args.resume and (out/'pilot.json').exists() else ev.evaluate(parent,20,SEEDS['pilot'],'pilot')
        if (out/'run.json').exists():
            meta=json.loads((out/'run.json').read_text(encoding='utf-8'))
            if meta['implementation']!=ev.version or meta['candidate_id']!=fingerprint(cfg):raise ValueError('Frozen run mismatch')
        else:
            target=required_walls(.4)
            for _ in range(8):target=required_walls(.4,alpha=spending(target)[-1]['alpha'])
            desired=4*target;sizes=allocate(pilot['elapsed_seconds']/20,desired,args.timeout)
            import scripts.tune_ai_weights_v4 as old
            old.SEEDS=SEEDS
            audit=seed_audit(out,dict(maximum=80000))
            audit.extend(audit_registered_seeds(out))
            meta=dict(started=time.time()-pilot['elapsed_seconds'],implementation=ev.version,candidate_id=fingerprint(cfg),candidate=cfg,
                seeds=SEEDS,seed_audit=audit,desired_main=desired,sizes=sizes,nodes=spending(sizes['main']//4),alpha=ALPHA,
                actual_power=achieved_power(sizes['main']//4,alpha=spending(sizes['main']//4)[-1]['alpha']),workers=args.workers,pilot_seconds=pilot['elapsed_seconds'],runtime_limit_seconds=args.timeout,
                thresholds=dict(dealin_point_max=0,dealin_upper_max=.005,pressure_lower=-1,elo_lower=-10,kong_tolerance=.02),
                auxiliary_before_main='Frozen allocation by main > pressure > E priority; auxiliary gates available for early stopping')
            atomic_json(out/'run.json',meta);atomic_json(out/'locked_candidate.json',dict(candidate=cfg,id=fingerprint(cfg)))
        s=meta['sizes'];print(json.dumps(dict(event='preregistered',sizes=s,nodes=meta['nodes'],power=meta['actual_power'])),flush=True)
        # Fresh independent training enrichment; resume cached states and replay shards.
        states=enrich(out,ex,[],SEEDS['training'])
        path=out/'kong_comparison.json'
        if path.exists():kong=json.loads(path.read_text(encoding='utf-8'))
        else:
            from collections import Counter
            partial=out/'kong_comparison.partial.json';ident=hashlib.sha256((fingerprint(cfg)+''.join(state_signature(s) for s in states)).encode()).hexdigest()
            saved=json.loads(partial.read_text(encoding='utf-8')) if partial.exists() else dict(identity=ident,completed=0,counts={t:{} for t in KONGS})
            if saved['identity']!=ident:raise ValueError('Kong identity mismatch')
            counts={t:Counter(saved['counts'][t]) for t in KONGS};done=saved['completed']
            chunks=[states[i:i+32] for i in range(done,len(states),32)]
            for chunk,part in zip(chunks,ex.map(kong_compare,[(cfg,x) for x in chunks])):
                for t in KONGS:counts[t].update(part[t])
                done+=len(chunk);atomic_json(partial,dict(identity=ident,completed=done,counts=counts))
                print(json.dumps(dict(event='kong',completed=done,total=len(states))),flush=True)
            kong={t:dict(counts[t]) for t in KONGS};atomic_json(path,kong)
        pressure={}
        for label,cell in dict(A=[0,0,0],B=[1,1,1],C=[0,1,2],D=[2,2,2]).items():
            b=ev.evaluate(parent,s['pressure'],SEEDS[label],label+'_baseline',cell)
            c=ev.evaluate(cfg,s['pressure'],SEEDS[label],label+'_candidate',cell)
            path=out/(label+'_comparison.json')
            pressure[label]=json.loads(path.read_text(encoding='utf-8')) if path.exists() else compare(c,b)
            atomic_json(path,pressure[label])
        anchor=ev.evaluate(cfg,s['anchor'],SEEDS['E'],'E_anchor',[0,1,2])
        path=out/'elo.json';elo=json.loads(path.read_text(encoding='utf-8')) if path.exists() else elo_diagnostics(anchor);atomic_json(path,elo)
        rows_b=[];rows_c=[];previous=0;nodes=[];early=False
        for i,node in enumerate(meta['nodes']):
            count=node['walls']-previous;seed=SEEDS['main']+previous
            b=ev.evaluate(parent,4*count,seed,f'main_{i}_baseline')
            c=ev.evaluate(cfg,4*count,seed,f'main_{i}_candidate')
            rows_b.extend(b['rows']);rows_c.extend(c['rows']);previous=node['walls']
            vb=summarize(rows_b,1,'ev');vc=summarize(rows_c,1,'ev');vb['candidate_seat']=vc['candidate_seat']=1
            bounds=net_bounds(vc,vb,node['alpha']);nodes.append(bounds);atomic_json(out/'sequential.json',nodes)
            print(json.dumps(dict(event='node',index=i,**bounds)),flush=True)
            if min(bounds['corrected_normal_lower'],bounds['corrected_bootstrap_lower'])>0 or i==len(meta['nodes'])-1:
                path=out/f'main_comparison_{i}.json'
                main=json.loads(path.read_text(encoding='utf-8')) if path.exists() else compare(vc,vb);atomic_json(path,main)
                g=verdict(main,pressure,elo,kong,bounds)
                if all(g.values()):early=i<len(meta['nodes'])-1;break
        atomic_json(out/'main_comparison.json',main)
        # Training-only next-round screen, never consulted by the current verdict.
        screen=[];key='ev_engine._YAKUHAI_SINGLE_POTENTIAL'
        configs=[parent]+[perturb(key,x) for x in (.6,.8,1.2,1.4)]
        reports=[ev.evaluate(c,300,SEEDS['screen'],f'yakuhai_{i}') for i,c in enumerate(configs)]
        for i,(c,r) in enumerate(zip(configs,reports)):
            screen.append(dict(label=i,value=c['weights'][key],hands=300,net=sum(x['net'][1]-y['net'][1] for x,y in zip(r['rows'],reports[0]['rows']))/300))
        atomic_json(out/'yakuhai_screen.json',screen)
    r=dict(metadata=meta,main=main,bounds=bounds,nodes=nodes,pressure=pressure,elo=elo,kong=kong,kong_training=json.loads((out/'kong_training.json').read_text(encoding='utf-8')),
        screen=screen,gates=g,early_stop=early,promoted=False,elapsed_seconds=time.time()-meta['started'],simulated_hands=20+2*len(rows_b)+8*s['pressure']+s['anchor']+1500,
        test_command=' '.join([sys.executable,'-m','pytest',*[f'tests/{t}.py' for t in TESTS],'-q']))
    # Reviewable complete report precedes final regression; no further simulation after tests.
    report(out,r)
    cmd=[sys.executable,'-m','pytest',*[f'tests/{t}.py' for t in TESTS],'-q']
    test=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8')
    (out/'pytest.log').write_text(test.stdout,encoding='utf-8');r['gates']['invariants']=test.returncode==0
    r['promoted']=all(r['gates'].values());r['elapsed_seconds']=time.time()-meta['started']
    if r['promoted']:atomic_json(ROOT/'app/config/ai_weights_v4.json',cfg)
    atomic_json(out/'result.json',r);report(out,r)
    print(json.dumps(dict(event='complete',seconds=r['elapsed_seconds'],hands=r['simulated_hands'],sizes=s,bounds=bounds,gates=g,elo=elo['gain_bootstrap_lower'],kong=kong,screen=screen,tests=test.stdout),ensure_ascii=False),flush=True)
    return test.returncode

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=8);ap.add_argument('--resume',action='store_true');ap.add_argument('--timeout',type=int,default=14400);ap.add_argument('--output',type=Path,default=ROOT/'data/ai_tuning/v4-round3');sys.exit(execute(ap.parse_args()))
