import math
import pytest
from tools.v4_round3 import required_walls,achieved_power,spending,kong_gates,allocate,ALPHA
from tools.sensitivity_scan import KONGS

def test_power_and_spending():
    n=required_walls(.4)
    assert 4600<n<4800
    assert achieved_power(n)>=.8
    assert required_walls(.3)>n>required_walls(.5)
    s=spending(n)
    assert [x['walls'] for x in s]==sorted(set(x['walls'] for x in s))
    assert sum(x['alpha'] for x in s)==pytest.approx(ALPHA)
    assert s[0]['z']>s[1]['z']>s[2]['z']
    assert all(x['alpha']>0 for x in s)

def test_kong_tolerance_and_denominators():
    c={t:dict(states=200,parent_take=125,candidate_take=124,benefit=125,benefit_parent_take=125,benefit_candidate_take=124) for t in KONGS}
    assert all(kong_gates(c).values())
    c['an_gang']['benefit_candidate_take']=122
    assert not kong_gates(c)['noncollapse_an_gang']
    c['an_gang']['states']=199
    assert not kong_gates(c)['opportunities_an_gang']

def test_allocation_priority():
    s=allocate(.5,20000)
    assert s['anchor']==s['pressure']==8 and s['main']<20000
    assert all(n%4==0 for n in s.values())
    assert allocate(.01,6000)==dict(main=6000,pressure=1000,anchor=1000)

def test_net_bounds_use_target_seat_and_reject_unpaired():
    from scripts.tune_ai_weights_v4_round3 import net_bounds
    def arm(candidate):
        return dict(kernel_sha256='k',policy_sha256='p',mode='ev',candidate_seat=1,rows=[
            dict(seed=100+i//4,dealer=i%4,policies=['v0',candidate,'v1','guard'],net=[0,(i//4+1) if candidate=='c' else 0,0,0]) for i in range(12)])
    a,b=arm('c'),arm('b')
    ci=net_bounds(a,b,.01)
    assert ci['clusters']==3 and ci['mean']==2
    assert ci['corrected_normal_lower']<ci['normal_lower']
    b['rows'][0]['seed']=999
    with pytest.raises(ValueError,match='Walls'):
        net_bounds(a,b,.01)

def test_report_contains_all_required_evidence(tmp_path,monkeypatch):
    from scripts import tune_ai_weights_v4_round3 as r
    (tmp_path/'docs').mkdir();monkeypatch.setattr(r,'ROOT',tmp_path/'backend')
    ci=dict(mean=.1,se=.2,normal_lower=-.2,bootstrap_lower=-.3,normal_upper=.4,bootstrap_upper=.5,clusters=3,corrected_normal_lower=-.4,corrected_bootstrap_lower=-.5,alpha=.01)
    kong={t:dict(states=200,benefit=125,parent_take=125,candidate_take=124,benefit_parent_take=125,benefit_candidate_take=124) for t in KONGS}
    result=dict(main=dict(dealin=ci),bounds=ci,metadata=dict(desired_main=20000,sizes=dict(main=12),actual_power=.1,pilot_seconds=9,seeds={},nodes=[],runtime_limit_seconds=14400),simulated_hands=24,kong_training=dict(hands=10),elapsed_seconds=20,early_stop=False,nodes=[ci],kong=kong,pressure={'A':dict(net=ci)},elo=dict(hands=8,gain=0,gain_bootstrap_lower=-12),gates=dict(net=False),screen=[dict(label=0,value=1,hands=300,net=0)],promoted=False,test_command='pytest')
    r.report(tmp_path,result)
    text=(tmp_path/'docs/ai_weights_v4_round3_report.md').read_text(encoding='utf-8')
    for heading in ('方法修订 R2','功效表','序贯节点','放铳','杠专项','压力 A~D','Elo','门槛逐项','下一轮候选','结论与下一轮建议'):
        assert heading in text
    assert '未晋升' in text
