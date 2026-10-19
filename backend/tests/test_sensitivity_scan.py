"""R1 contracts: correct runtime injection, freeze/order and report rendering."""
import copy
import pytest
from tools import sensitivity_scan as s
from tools.weights import runtime,validate_weights
from scripts.tune_ai_weights_v4_round2 import kong_gates

@pytest.mark.parametrize('key',s.KEYS)
def test_runtime_injects_every_scanned_key(key):
    cfg=s.perturb(key,1.4);validate_weights(cfg)
    module,attr,*suffix=key.split('.')
    actual=getattr(runtime(cfg)[module],attr)
    if suffix:actual=actual[int(suffix[0])]
    assert actual==cfg['weights'][key]

def test_candidate_selection_and_freeze():
    ranking=[dict(key=k,rate=r,directions=[dict(scale=.6,flips=30),dict(scale=1.4,flips=20)]) for k,r in zip(s.KEYS,(.04,.03,.02,.009,0))]
    selected,cfgs=s.select_candidates(ranking)
    assert len(selected)==3 and len(cfgs)==7
    for cfg in cfgs:validate_weights(cfg)
    bad=copy.deepcopy(cfgs[1]);bad['weights'][s.KEYS[1]]*=1.1
    with pytest.raises(ValueError,match='single'):validate_weights(bad)
    bad=s.baseline();bad['weights']['call_decision._PASS_DRAW_TURN_BASE']+=1
    with pytest.raises(ValueError,match='frozen'):validate_weights(bad)

def test_kong_special_gates_require_benefit_and_sufficiency():
    counts={t:dict(states=200,parent_take=100,candidate_take=100,benefit=75,benefit_parent_take=75,benefit_candidate_take=75) for t in s.KONGS}
    assert all(kong_gates(counts).values())
    counts['ming_gang']['benefit_candidate_take']=74
    counts['an_gang']['states']=199
    g=kong_gates(counts)
    assert not g['noncollapse_ming_gang'] and not g['opportunities_an_gang']

def test_immediate_win_is_not_beneficial_kong_refusal(monkeypatch):
    from types import SimpleNamespace
    import tools.arena
    class Winner:
        def __init__(self,*args):pass
        def choose(self,*args):return {'action_type':'self_draw_win'}
    monkeypatch.setattr(tools.arena,'Policy',Winner)
    monkeypatch.setattr(s,'action_scores',lambda *a:pytest.fail('Immediate win must bypass kong benefit scoring'))
    state=SimpleNamespace(seat='E',options={'E':[{'action_type':'self_draw_win'},{'action_type':'an_gang'}]})
    result=s.kong_compare((s.baseline(),[state]))
    assert result['an_gang']['states']==1
    assert result['an_gang']['benefit']==0
    assert result['an_gang']['candidate_take']==0

def test_fixed_state_legal_actions_have_local_scores():
    from tools.arena import Policy
    states,kongs=s.collect_wall((9876500,'fast'))
    assert len(states)<=32
    p=Policy(s.baseline(),'ev')
    for state in states[:3]+kongs[:3]:
        action=s.descriptor(p.choose(state,state.seat))
        scores=s.action_scores(p,state)
        assert action in scores

def test_report_renders_without_source_anchors(tmp_path,monkeypatch):
    from tools import v4_reporting as report
    (tmp_path/'docs').mkdir();monkeypatch.setattr(report,'ROOT',tmp_path/'backend')
    ci=dict(mean=0,normal_lower=0,bootstrap_lower=0,normal_upper=0,bootstrap_upper=0)
    comparison=dict(net=ci,dealin=ci,candidate={},baseline={},claims={t:dict(candidate=0,baseline=0) for t in s.v3.CLAIMS})
    row=dict(key=s.KEYS[0],replays=40,flips=0,rate=0,mean_flip_ev=None,missing_ev=[0]*4,bounds=[80,180])
    result=dict(promoted=False,metadata={},simulated_hands=20,elapsed_seconds=1,sensitivity=dict(seed=1,walls=40,states=1000,seconds=1,ranking=[row]),selected=[],main=comparison,pressure={},elo={},gates={'net':False},kong={},kong_training={})
    report.write_report(tmp_path,result,[comparison])
    text=(tmp_path/'docs/ai_weights_v4_round2_report.md').read_text(encoding='utf-8')
    assert '当前幅度内不敏感，继续冻结' in text
    for heading in ('方法修订摘要','敏感度排序全表','快筛','主验证','杠专项','压力单元','E 锚点赛','门槛逐项','下一轮建议'):assert heading in text
