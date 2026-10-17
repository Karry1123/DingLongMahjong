import copy
import pytest
from scripts.validate_ai_weights_focused import combine,gate
from tools.arena import summarize

def report(seed):
    rows=[{'seed':seed,'dealer':d,'net':[0,0,0,0],'winner':None,'dealin':None,'draw':True,'policies':['v0']*4} for d in range(4)]
    result=summarize(rows,1,'ev');result['candidate_seat']=1
    return result

def test_pooling_rejects_repeated_walls_and_different_implementations():
    a=report(1);b=report(2)
    assert combine(a,b)['hands']==8
    with pytest.raises(ValueError):combine(a,a)
    other=copy.deepcopy(b);other['policy_sha256']='changed'
    with pytest.raises(ValueError):combine(a,other)
    other=copy.deepcopy(b);other['mode']='fast'
    with pytest.raises(ValueError):combine(a,other)

def test_single_comparison_gate_requires_complete_4000_and_positive_bound():
    s={'mean_gain_per_hand':1,'standard_error':.1,'clusters':1000}
    assert gate(s,4000)[0]
    assert not gate(s,2000)[0]
    assert not gate(dict(s,clusters=500),4000)[0]
    assert not gate(dict(s,standard_error=1),4000)[0]
