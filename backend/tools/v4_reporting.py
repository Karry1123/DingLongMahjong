"""Function based V4 reporting; shared metric formatting, no dynamic source edits."""
import json
from tools.v3_reporting import elo_diagnostics
from tools.v3_experiment import ROOT, CLAIMS
from tools.report_common import table, intervals, number


def write_report(output,result,screen):
    r1='sensitivity' in result
    title='V4 第二小轮' if r1 else 'V4 第一小轮'
    lines=['# '+title+'调优报告','', '结论：'+('全部门槛通过，生成独立 V4 配置。' if result['promoted'] else '未晋升，不生成 V4 配置。'),'',
           '现任基准为 V1+guard；生产默认加载及 optimized 配置保持原样。', '', '## 方法修订摘要','',
           'R1：40 墙、每局最多 8 个固定状态；23 项单参数 ±20%/±40%，取 schema 硬界及次序约束交集。翻转率按四方向总翻转/总重放统计，≥1% 排名前三入选；每个候选只动一个参数，避免强耦合乘数同动。局部 EV 差以现任同一局面的评分为尺度，仅为诊断，不是真实收益。',
           '训练局面采用确定种子的全局面蓄水抽样；局部 EV 覆盖不到的动作单列 missing_ev，不按零值解释。杠富集集包含 EV 训练轨迹和额外 fast 训练轨迹，后者仅用于获得合法状态，专项比较全部使用完整 EV。专项不进入自然分布胜率。',
           '候选快筛使用同墙共同随机数；对独立主验证墙做单侧 95% 正态与墙块 bootstrap（10000次）。基准池 V0/历史V1/V1+guard=20%/40%/40%。报告使用普通函数与共用表格函数。','', '## 实际规模与耗时','',
           '```json',json.dumps(result['metadata'],ensure_ascii=False,indent=2),'```',
           f"实际自然对局 {result['simulated_hands']} 局；从吞吐试跑开始累计经过 {result['elapsed_seconds']:.2f} 秒（含中断等待、扫描、富集、统计及最终 pytest）。workers=8；续跑命令设超时 10800 秒，输出 data/ai_tuning/v4-round2/console.log。扫描、快筛及锁定结果从检查点恢复，没有重跑或重新选参。", '', '## 敏感度排序全表','']
    if r1:
        s=result['sensitivity']
        lines += [f"训练种子 {s['seed']} 起，共 {s['walls']} 墙、{s['states']} 状态；所有验证种子独立。扫描耗时 {s['seconds']:.2f} 秒。"]
        lines += table(('排名','参数','翻转/重放','翻转率','翻转后局部EV差均值','缺失EV数','结论'),
           [(i+1,r['key'],f"{r['flips']}/{r['replays']}",f"{r['rate']*100:.4f}%",number(r['mean_flip_ev']),sum(r['missing_ev']), '当前幅度内不敏感，继续冻结' if not r['flips'] else ('入选' if r['key'] in result['selected'] else '未入选')) for i,r in enumerate(s['ranking'])])
        lines += ['', '### 入选理由与区间','', '≥1% 且全表前三；候选均为单参数，不同时改变耦合乘数。方向按训练翻转数排序，最多各取两个方向。']
        lines += table(('参数','有效区间'),[(r['key'],r['bounds']) for r in s['ranking'] if r['key'] in result['selected']])
        lines += ['', '逐方向完整统计（含硬界/次序截断后的实际值）：','```json',json.dumps(s['ranking'],ensure_ascii=False,indent=2),'```']
    lines += ['', '## 快筛与锁定','']
    changes=result.get('candidate_changes',[{} for _ in screen])
    lines += table(('候选','参数实际值（空为基准）','净分差/局','放铳差','锁定'),[(i,json.dumps(changes[i],ensure_ascii=False),number(c['net']['mean']),number(c['dealin']['mean']),i==result.get('screen_index')) for i,c in enumerate(screen)])
    lines += ['', '## 主验证','']+intervals(result['main'])
    lines += ['', '### 自然分布吃碰杠（专项不混入本表）','']
    a,b=result['main']['candidate'],result['main']['baseline']
    lines += table(('类型','候选机会/选择','现任机会/选择','候选率','现任率'),[(t,f"{a.get(t+'_opp',0)}/{a.get(t+'_take',0)}",f"{b.get(t+'_opp',0)}/{b.get(t+'_take',0)}",number(result['main']['claims'][t]['candidate']),number(result['main']['claims'][t]['baseline'])) for t in CLAIMS])
    lines += ['', '## 杠专项','', '有收益定义：现任完整局部 EV 中该杠最佳分高于其他合法动作最佳分；比较同一固定状态。可立即和牌的状态仍计合法机会，但和牌优先，不标成有收益杠、不将选择和牌计作拒绝杠。要求每类≥200、选择率比在[0.75,1.25]、存在有收益状态且候选全部选择，并保留非杠选择。']
    if r1:
        lines += table(('类型','状态','现任选择','候选选择','有收益状态','有收益现任选择','有收益候选选择'),[(t,*[result['kong'][t].get(k,0) for k in ('states','parent_take','candidate_take','benefit','benefit_parent_take','benefit_candidate_take')]) for t in result['kong']])
        lines += ['```json',json.dumps(result['kong_training'],ensure_ascii=False,indent=2),'```']
    lines += ['', '## 压力单元 A–D','', 'A=V0×3；B=历史V1×3；C=V0/历史V1/guard；D=guard×3。非劣界 −1。']
    for label,c in result['pressure'].items():lines += ['', '### '+label,'']+intervals(c,('net',))
    lines += ['', '## E 锚点赛与 Elo','', 'E 固定 V0/候选/历史V1/guard 阵容，墙块 bootstrap，Elo 下界要求 ≥−10。','```json',json.dumps(result['elo'],ensure_ascii=False,indent=2),'```', '', '## 门槛逐项','']
    lines += table(('门槛','通过'),[(k,'通过' if v else '未通过') for k,v in result['gates'].items()])
    lines += ['', '## 结论与下一轮建议','', '仅全部通过才生成 app/config/ai_weights_v4.json；本轮'+('通过。' if result['promoted'] else '未通过，候选仅保存在 data/ai_tuning/v4-round2/。'),
              '下一轮优先复测显著敏感参数的独立局部区间；零翻转项继续冻结。若置信区间不足，应增加独立墙块，避免查看验证结果后再选参数。杠专项继续单独富集，不用自然稀少机会作否决。']
    path=ROOT.parent/'docs'/('ai_weights_v4_round2_report.md' if r1 else 'ai_weights_v4_round1_report.md')
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
