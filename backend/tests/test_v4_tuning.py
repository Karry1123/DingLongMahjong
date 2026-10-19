"""V4 isolation, direction selection and outcome-label contracts."""
import copy
import pytest
from tools import v4_experiment as v4
from tools.weights import runtime, validate_weights, fingerprint


@pytest.mark.parametrize('group', ['A','B'])
def test_whitelist_runtime_and_bounds(group):
    parent=v4.baseline(group)
    for key in v4.GROUPS[group]:
        cfg=v4.perturb(group,key,1.1)
        validate_weights(cfg)
        assert getattr(runtime(cfg)['danger_model'],key.split('.')[1])==cfg['weights'][key]
        assert runtime(cfg)['ev_engine'].estimate_tile_danger is runtime(cfg)['danger_model'].estimate_tile_danger
        assert fingerprint(cfg)!=fingerprint(parent)
        bad=copy.deepcopy(cfg);bad['weights'][key]*=2
        with pytest.raises(ValueError):validate_weights(bad)
    bad=copy.deepcopy(parent);bad['weights']['ev_engine.SHANTEN_PENALTY']+=1
    with pytest.raises(ValueError,match='frozen'):validate_weights(bad)
    assert fingerprint(parent)!=fingerprint(__import__('tools.v3_experiment',fromlist=['baseline']).baseline())


def test_probe_selection_and_zero_direction_filter():
    p={'probe_states':100}
    assert v4.select_group(p)[0]=='B'
    label,cfg=next((l,c) for l,c in v4.probes() if l.startswith('A_'))
    p['probe_'+label+'_flips']=50
    assert v4.select_group(p)[0]=='A'
    candidates=v4.candidates('A',p)
    assert len(candidates)==2
    assert candidates[1]['weights']==cfg['weights']


def test_calibration_terminal_ron_updates_only_last_discard():
    c=v4.Collector(0)
    c.metrics.update(cal_n=2,cal_brier_sum=.01+.04,cal_2_n=1,cal_2_p=.2)
    c.last_prediction=(.2,2)
    c.finish(dict(dealin=0,win_type='ron'),0)
    assert c.metrics['cal_brier_sum']==pytest.approx(.65)
    assert c.metrics['cal_y']==1
    assert c.metrics['cal_2_y']==1
    c.finish(dict(dealin=0,win_type='rob_kong'),0)
    assert c.metrics['cal_y']==1


def test_v4_report_uses_functional_helpers():
    from tools.report_common import table, intervals
    assert table(('a','b'),[(1,2)])[-1]=='| 1 | 2 |'
    assert '证据不足' in '\n'.join(intervals({'net':None},('net',)))
