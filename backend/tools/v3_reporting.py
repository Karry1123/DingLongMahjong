"""Frozen-wall ranking diagnostics and Chinese round-one evidence report."""
import json
import math
import random
from pathlib import Path
from tools.v3_experiment import ROOT, KEYS, CLAIMS, aggregate, ratio, quantile


def bt_fit(wins):
    """Bradley--Terry MM with V0=1500; ties count half a win."""
    strength=[1.]*4
    for _ in range(100):
        updated=[]
        for i in range(4):
            numerator=sum(wins[i][j] for j in range(4) if j!=i)+1e-8
            denominator=sum((wins[i][j]+wins[j][i]+2e-8)/(strength[i]+strength[j]) for j in range(4) if j!=i)
            updated.append(numerator/denominator)
        updated=[x/updated[0] for x in updated]
        error=max(abs(math.log(updated[i]/strength[i])) for i in range(4))
        strength=updated
        if error<1e-9:break
    return [1500+400*math.log10(x) for x in strength]


def elo_diagnostics(report):
    blocks=[]
    for i in range(0,len(report['rows']),4):
        matrix=[[0.]*4 for _ in range(4)]
        for row in report['rows'][i:i+4]:
            for a in range(4):
                for b in range(a+1,4):
                    x=.5 if row['net'][a]==row['net'][b] else float(row['net'][a]>row['net'][b])
                    matrix[a][b]+=x;matrix[b][a]+=1-x
        blocks.append(tuple(v for row in matrix for v in row))
    def fit(sample):
        flat=list(map(sum,zip(*sample)))
        return bt_fit([flat[i*4:i*4+4] for i in range(4)])
    ratings=fit(blocks)
    rng=random.Random(61017)
    draws=[]
    for _ in range(10000):
        e=fit(rng.choices(blocks,k=len(blocks)))
        draws.append(e[1]-e[3])
    draws.sort()
    totals=list(map(sum,zip(*blocks)))
    return dict(versions=['V0','candidate','historical-V1','V1+guard'],ratings=ratings,
        gain=ratings[1]-ratings[3],gain_bootstrap_lower=quantile(draws,.05),
        pairwise_ranking_win_rates=[[None if i==j else totals[4*i+j]/report['hands'] for j in range(4)] for i in range(4)],
        blocks=len(blocks),hands=report['hands'],bootstrap_repeats=10000,bootstrap_seed=61017,
        net_per_hand=[sum(r['net'][i] for r in report['rows'])/report['hands'] for i in range(4)])


def f(value,digits=6):
    return '无有效分母' if value is None else f'{value:.{digits}f}'


def ci(x,percent=False):
    if x is None:return '证据不足（无分母）'
    m=100 if percent else 1
    return ' / '.join(f(x[k]*m) for k in ('mean','normal_lower','bootstrap_lower','normal_upper','bootstrap_upper'))


def write_report(output,result,screen):
    meta=result['metadata'];c=result['main'];a,b=c['candidate'],c['baseline']
    locked=json.loads((output/'locked_candidate.json').read_text(encoding='utf-8'))
    lines=['# V3 第一小轮：推进子组调优报告','',
        '状态：'+('全部门槛通过，生成独立 V3 配置。' if result['promoted'] else '未晋升；仅保留实验候选，未生成 app/config/ai_weights_v3.json。'),'',
        '本轮只调整 `ev_engine.SHANTEN_PENALTY` 与 `ev_engine._UKEIRE_QUALITY_WEIGHT`；其余165项表内参数冻结在当前 V1。'
        '当前 V1+guard 使用独立源码快照，历史 V0/V1 使用原冻结源码；所有阶段均为完整 EV，收益来自真实 settlement。'
        '未改变生产默认加载或生产决策/计分文件。','',
        '## 预登记、命令与规模','',
        '在 `F:\\mahjong\\backend` 执行：','', '```powershell',
        '.\\.venv\\Scripts\\python.exe scripts/tune_ai_weights_v3.py --workers 8 --pilot-only',
        '.\\.venv\\Scripts\\python.exe scripts/tune_ai_weights_v3.py --workers 8',
        '.\\.venv\\Scripts\\python.exe -m pytest tests/test_ai_weights_loading.py tests/test_offline_ai_tools.py tests/test_focused_validation.py -q',
        '```','',
        f"20局代表性吞吐试跑耗时 {f(meta['pilot_seconds'],2)} 秒；不包含敏感度探针开销。按试跑吞吐估算预定全流程 {f(meta['estimated_seconds']/3600,3)} 小时，"
        f"预登记缩放系数 {f(meta['scale'])}（3小时预算预留10%统计/测试）。实际完成 {result['simulated_hands']} 局，阶段运行耗时 {f(result['elapsed_seconds'],2)} 秒。",
        '试跑牌墙与全部正式阶段隔离，验证开始前冻结候选与所有门槛。快筛保留父代；先单参数±10%，再固定2维局部复核。'
        '独立锁定选择集只审计筛选优胜者，不进入晋升区间。主验证与各压力单元只打开一次，不按中途均值追加或停止。','',
        '| 阶段 | 每策略局数 | 策略/臂数 | 每策略墙块 | 起始种子 |','|---|---:|---:|---:|---:|']
    s=meta['sizes'];seeds=meta['seeds']
    for label,n,arms,key in [('试跑',20,1,'pilot'),('完整EV快筛',s['screen'],6,'screen'),('锁定选择',s['lock'],2,'lock'),
                           ('M主盲验证',s['main'],2,'main'),*[(x+'压力',s['pressure'],2,x) for x in 'ABCD'],('E固定阵容锚点',s['anchor'],1,'E')]:
        lines.append(f'| {label} | {n} | {arms} | {n//4} | {seeds[key]} |')
    preflight=result.get('preflight',[])
    lines += ['', f"额外仪器预运行完成 {sum(p['hands'] for p in preflight)} 局，累计记录模拟耗时 {f(sum(p['seconds'] for p in preflight),2)} 秒；"
        f"全任务已记录完成局数 {result['simulated_hands']+sum(p['hands'] for p in preflight)}。"
        '初次20局包含8组敏感度探针和冷启动，外推5.52小时而过度缩减；在打开任何留出集前，因实际缓存吞吐差异中止初始快筛，'
        '保留 preflight/ 原始记录，再以不带探针的独立20局测量重定预算。初始两组各144局快筛数据仅作仪器检查，未择优、未混入正式确认统计。', '',
        '四局共享同一物理牌墙；墙块独立、四方轮庄；候选座位按墙索引 mod 4 轮换。'
        '候选与现任共享墙、座位、庄家和三个对手。局数不能把两臂相加当独立样本。'
        '已扫描已有实验元数据与实际 rows 的种子范围，扩展区间不交叠，详见 run.json 的 seed_audit。'
        '逐阶段 schedule 保存对手席位配额；checkpoint 绑定实现/配置/源码/schema/bounds/赛程/上限，整墙恢复。', '',
        '## 版本隔离与基准池','',
        'V2-tight 的 locked_candidate 权重与配置指纹可读，但旧实验未保存逐文件完整运行时快照，无法核验历史完整实现指纹；'
        '按计划5.1将其10%合并给当前V1+guard，未把当前 claim_v2 冒充历史已恢复版本。实际固定比例 V0 20%、历史V1 40%、当前V1+guard 40%。'
        '先保证每墙至少两个版本谱系，再确定性打乱；席位总数不能整除配额时用最大余数取整，误差少于一个席位。', '',
        '| 版本 | 配置/实现指纹 | 配额 |','|---|---|---:|']
    for p,fraction in zip(meta['pool'],meta['pool_fractions']):lines.append(f"| {p['version']} | `{p['fingerprint']}` | {fraction:.0%} |")
    lines += ['',f"整体实现哈希：`{meta['implementation']}`；锁定ID：`{locked['id']}`；锁定时间：{locked['timestamp']}。",
        '运行时4模块哈希见 tools/policy_sources/v3_guard/manifest.json；规则内核哈希和各臂策略指纹见逐局结果。'
        'V3 schema 是独立 `V3-guard` 白名单，只允许本轮两项；相对步幅≤15%、累计≤25%，同时取计划窄界与核心硬界交集。', '',
        '## 参数与快筛','', '| 参数 | 当前V1 | 锁定候选 | 相对变化 |','|---|---:|---:|---:|']
    for k,(v,w) in locked['parameter_changes'].items():lines.append(f'| `{k}` | {f(v,9)} | {f(w,9)} | {(w/v-1)*100:.3f}% |')
    lines += ['', '| 候选 | SHANTEN | UKEIRE | 配对净分/局 | 放铳差pp | 副露机会(吃/碰/明杠) |','|---|---:|---:|---:|---:|---|']
    for i,x in enumerate(screen):
        cfg=json.loads((output/f'candidate_{i}.json').read_text(encoding='utf-8'))
        counts='/'.join(str(x['candidate'].get(t+'_opp',0)) for t in ('chi','pong','ming_gang'))
        lines.append(f"| {i}{'（锁定）' if i==locked['screen_index'] else ''} | {f(cfg['weights'][KEYS[0]],0)} | {f(cfg['weights'][KEYS[1]],9)} | {f(x['net']['mean'])} | {f(100*x['dealin']['mean'])} | {counts} |")
    pilot=json.loads((output/'sensitivity_pilot.json').read_text(encoding='utf-8'))
    probe=aggregate(pilot['rows'])
    lines += ['', '探针在试跑正常弃牌局面上重放，每局最多8个状态；计数为固定状态上的动作翻转，不把重放当独立牌墙。', '',
        '| 扰动 | 翻转次数 | 状态分母 |','|---|---:|---:|']
    for k in KEYS:
        for scale in (.9,.95,1.05,1.1):
            label=k.split('.')[-1]+'_'+str(scale)
            lines.append(f"| {label} | {probe.get('probe_'+label+'_flips',0)} | {probe.get('probe_states',0)} |")
    lines += ['', '实际模块值、SHANTEN导入副本同步、完整评分对参数扰动的响应由新增测试覆盖。'
        '本轮将计划256块探针随本机预算缩为试跑5块，不声称达到原计划灵敏度覆盖。','',
        '## 主盲验证关键数字','',
        '以下区间均为单侧95%；正态按墙块影响函数/均值计算，bootstrap为固定种子61017、10000次整墙重采样。'
        '比率指标在每次重采样中重算总分子/总分母，不对逐动作作独立二项检验。', '',
        '| 指标 | 当前V1+guard | 候选 | 差/正态下界/bootstrap下界/正态上界/bootstrap上界 |',
        '|---|---:|---:|---|']
    for label,num,den,key,pct in [('净分/局','net_sum','hands','net',False),('放铳率%','dealin','hands','dealin',True),
        ('自摸率%','zimo','hands','zimo',True),('向听推进/窗口','progress_sum','progress_windows','progress',False),
        ('低风险弃听率%','low_tenpai_break','low_tenpai_opp','low_tenpai',True)]:
        m=100 if pct else 1
        lines.append(f"| {label} | {f((ratio(b,num,den) or 0)*m)} | {f((ratio(a,num,den) or 0)*m)} | {ci(c[key],pct)} |")
    lines += ['', '| 行为分母/分类 | 当前V1+guard | 候选 |','|---|---:|---:|']
    for k in ('hands','progress_windows','low_tenpai_opp','tenpai_opp','tenpai_break','zimo','ron','rob_kong','rob_kong_dealin'):
        lines.append(f"| {k} | {b.get(k,0)} | {a.get(k,0)} |")
    for label,x in [('当前V1+guard',b),('候选',a)]:
        wins=sum(x.get(k,0) for k in ('zimo','ron','rob_kong'))
        lines.append(f"| {label} 自摸/和牌 | {f(x.get('zimo',0)/wins if wins else None)} | — |")
    lines += ['', '| 动作 | 现任选/合法机会 | 候选选/合法机会 | 候选/现任机会率比 | 候选每局次数 | 轨迹差区间(pp) | 同局面差区间(pp) |',
        '|---|---:|---:|---:|---:|---|---|']
    for t in CLAIMS:
        x=c['claims'][t];ar=x['candidate'];br=x['baseline']
        lines.append(f"| {t} | {b.get(t+'_take',0)}/{b.get(t+'_opp',0)} | {a.get(t+'_take',0)}/{a.get(t+'_opp',0)} | {f(ar/br if ar is not None and br else None)} | {f(a.get(t+'_take',0)/a['hands'])} | {ci(x['difference'],True)} | {ci(x['fixed_state'],True)} |")
    lines += ['', '| 有收益标签 | 当前选择/机会 | 候选选择/机会 |','|---|---:|---:|']
    for t in ('chi','pong','ming_gang'):
        lines.append(f"| {t} | {b.get(t+'_benefit_take',0)}/{b.get(t+'_benefit_opp',0)} | {a.get(t+'_benefit_take',0)}/{a.get(t+'_benefit_opp',0)} |")
    lines += ['', '“有收益”在采集中操作化为副露后最佳合法弃牌使向听下降；不把此标签当优化奖励。'
        '未把它解释为完整货币收益标签；其他正收益形态依赖专项回归。合法机会按决策时点计一次动作类型，多个吃法不重复计分母。'
        '向听窗口为正常弃牌后到下次正常弃牌后，剔除副露后弃牌及终局不成对窗口。'
        '低风险桶固定为对手公开听牌概率最大值<0.30，可保持听牌机会按所有合法弃牌的最小向听=0判定。', '',
        '| 起始向听 | 现任推进总和/窗口 | 候选推进总和/窗口 |','|---|---:|---:|']
    for i in range(7):
        n='progress_'+str(i)
        if a.get(n+'_windows',0)+b.get(n+'_windows',0):
            lines.append(f"| {i} | {b.get(n+'_sum',0)}/{b.get(n+'_windows',0)} | {a.get(n+'_sum',0)}/{a.get(n+'_windows',0)} |")
    lines += ['', '## 压力单元、座位与Elo','',
        'A=三家V0，B=三家历史V1，C=V0/历史V1/当前guard（V2恢复失败替代），D=三家当前guard。'
        '压力单元与主池和彼此使用独立墙；非劣阈值事前固定为−1分/局。', '',
        '| 单元 | 配对净分差 | 正态95%下界 | bootstrap95%下界 | 放铳差pp |','|---|---:|---:|---:|---:|']
    for label,p in result['pressure'].items():lines.append(f"| {label} | {f(p['net']['mean'])} | {f(p['net']['normal_lower'])} | {f(p['net']['bootstrap_lower'])} | {f(100*p['dealin']['mean'])} |")
    lines += ['', '| 主池分层 | 局数 | 配对净分差/局 |','|---|---:|---:|']
    ca=json.loads((output/'main_candidate.json').read_text(encoding='utf-8'))['rows']
    cb=json.loads((output/'main_baseline.json').read_text(encoding='utf-8'))['rows']
    for seat in range(4):
        pairs=[(x,y) for x,y in zip(ca,cb) if x['physical_candidate_seat']==seat]
        lines.append(f"| 物理座位{seat} | {len(pairs)} | {f(sum(x['net'][1]-y['net'][1] for x,y in pairs)/len(pairs))} |")
    for dealer in (True,False):
        pairs=[(x,y) for x,y in zip(ca,cb) if (x['dealer']==x['physical_candidate_seat'])==dealer]
        lines.append(f"| {'庄' if dealer else '闲'} | {len(pairs)} | {f(sum(x['net'][1]-y['net'][1] for x,y in pairs)/len(pairs))} |")
    e=result['elo']
    lines += ['', f"E固定阵容 {e['hands']}局/{e['blocks']}块，互结净分排名，平局0.5，Bradley–Terry拟合，V0固定1500。"
        f"候选相对guard Elo差 {f(e['gain'],3)}，10000次墙bootstrap单侧95%下界 {f(e['gain_bootstrap_lower'],3)}（门槛≥−10）。", '',
        '| 版本 | Elo | 净分/局 |','|---|---:|---:|']
    for name,rating,net in zip(e['versions'],e['ratings'],e['net_per_hand']):lines.append(f'| {name} | {f(rating,3)} | {f(net)} |')
    lines += ['', '排名两两胜率/循环克制矩阵（行对列，含平局0.5）：', '',
        '| 版本 | V0 | candidate | historical-V1 | V1+guard |','|---|---:|---:|---:|---:|']
    for name,row in zip(e['versions'],e['pairwise_ranking_win_rates']):lines.append('| '+name+' | '+' | '.join('—' if v is None else f(v,4) for v in row)+' |')
    lines += ['', '## 门槛逐项判定','',
        '单次锁定候选、一次主检验，α=0.05；未把选择集并入确认区间。'
        '正态与bootstrap均须满足；低频样本不足不能判通过，尤其任何杠类不足200机会时本轮不能晋升。', '',
        '| 门槛 | 通过/未通过 |','|---|---|']
    for k,v in result['gates'].items():lines.append(f"| {k} | {'通过' if v else '未通过（含证据不足）'} |")
    lines += ['', '专项回归在锁定前和最终判定前各运行一次，命令及完整结果见 lock_tests.log / final_tests.log。'
        '涵盖财神实体、唯一雀头、正常吃碰杠、原样吃回守护、直接生产HU/PASS、支付封顶、零和、合法动作与运行时隔离。'
        '每局内核硬断言实体牌136张且每种4张、结算零和、1200动作内终止；异常不丢弃。', '',
        '## 结论与下一轮建议','',
        ('本轮通过全部预登记门槛；写出独立V3配置，生产仍使用原默认V1。' if result['promoted'] else
         '本轮未满足全部门槛，不晋升；候选与完整证据留在 backend/data/ai_tuning/v3-round1/。均值为正也不能替代置信下界、行为和压力门槛。'),
        '本机缩减实验不等同计划原样本量的统计功效；关键分层或稀有杠不足须明确保留为证据不足。'
        '下一轮先补足低频专项固定状态与有收益/被支配分类，完成V2历史实现可核验快照；再用新的锁定ID与全新留出墙重试。'
        '若本轮净分区间跨零，保持现任并先扩大训练敏感度探针，不按留出结果反向调参或复用验证墙。','']
    (ROOT.parent/'docs/ai_weights_v3_round1_report.md').write_text('\n'.join(lines),encoding='utf-8')
