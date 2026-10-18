"""Cheap, deterministic contracts for the isolated V3 round-one experiment."""
import copy
import hashlib
import json
import random
import sys
from collections import Counter
from types import SimpleNamespace

import pytest

from app.core import call_decision, ev_engine, tenpai_model
from app.core.action_generator import ActionType, get_available_actions
from app.core.ai_weights import ai_weights_session
from tests.test_claim_invariance import gm86
from tools import v3_experiment as v3
from tools.weights import POOL, fingerprint, load_weights, runtime, validate_weights


def advancing_chow():
    return dict(hand_tiles=['1m','2m','4m','5m','6m','7p','8p','9p','3s','4s','E','E','C'],
                melds=[], opponents=[], dealer_tile='9s', seat_wind='E', round_wind='E',
                is_dealer=True, discarded_tile='3m', discarded_tiles=['3m'])


def decision(module, state):
    actions = get_available_actions(state['hand_tiles'], state['melds'],
                                    state['discarded_tile'], 'N', 'E', state['dealer_tile'])
    return module.evaluate_call_decision(actions, **state)


def production_values():
    modules = dict(ev_engine=ev_engine, tenpai_model=tenpai_model)
    return ({key: getattr(modules[key.split('.')[0]], key.split('.')[1])
             for key in v3.BOUNDS}, call_decision.SHANTEN_PENALTY)


@pytest.mark.parametrize('accelerated', [False, True])
def test_private_runtime_loads_both_named_parameters_and_imported_copy(accelerated):
    cfg = copy.deepcopy(v3.baseline())
    cfg['weights'][v3.KEYS[0]] = 144
    cfg['weights'][v3.KEYS[1]] *= .9
    before = production_values()
    modules = runtime(cfg, accelerated)
    assert modules['ev_engine'] is not ev_engine
    assert modules['call_decision'] is not call_decision
    assert modules['ev_engine'].SHANTEN_PENALTY == 144
    assert modules['call_decision'].SHANTEN_PENALTY == 144
    assert modules['ev_engine']._UKEIRE_QUALITY_WEIGHT == cfg['weights'][v3.KEYS[1]]
    assert production_values() == before
    assert not any(name.startswith('app.core._v3_') for name in sys.modules)


@pytest.mark.parametrize('key', v3.KEYS)
def test_each_round_one_parameter_changes_real_discard_scores(key):
    from app.core.deck_engine import setup_new_game
    # This fixed initial wall has deep-shanten choices with nonzero quality ukeire.
    deal = setup_new_game('E', rng=random.Random(19))
    kwargs = dict(hand_tiles=deal['hands']['E'], dealer_tile=deal['dealer_tile'],
                  is_dealer=True, seat_wind='E', include_self_gang=False)
    parent = v3.baseline()
    results = []
    values = []
    before = production_values()
    for scale in (.9, 1, 1.1):
        cfg = copy.deepcopy(parent)
        value = parent['weights'][key] * scale
        cfg['weights'][key] = round(value) if key == v3.KEYS[0] else value
        validate_weights(cfg)
        values.append(cfg['weights'][key])
        rows = runtime(cfg)['ev_engine'].calculate_best_discards(**kwargs)['candidates']
        results.append({row['tile']: row for row in rows})
    low, middle, high = results
    assert low.keys() == middle.keys() == high.keys()
    triggered = 0
    for tile, row in middle.items():
        a, b = low[tile], high[tile]
        assert a['shanten'] == row['shanten'] == b['shanten']
        assert a['effective_count'] == row['effective_count'] == b['effective_count']
        if key == v3.KEYS[0]:
            assert b['attack_ev'] == a['attack_ev']
            expected = -row['shanten'] * (values[2] - values[0])
            assert b['ev_score'] - a['ev_score'] == pytest.approx(expected, abs=.0002)
            triggered += row['shanten'] > 0
        elif row['shanten'] >= 2:
            attack_delta = b['attack_ev'] - a['attack_ev']
            if attack_delta > 0:
                triggered += 1
                assert b['ev_score'] - a['ev_score'] == pytest.approx(attack_delta, abs=.0002)
                # Quality is a linear numeric score component at the same state.
                assert row['attack_ev'] == pytest.approx((a['attack_ev'] + b['attack_ev']) / 2, abs=.0002)
    assert triggered > 0
    assert production_values() == before


@pytest.mark.parametrize('state_factory,expected', [(gm86, ActionType.PASS), (advancing_chow, ActionType.CHI)])
@pytest.mark.parametrize('accelerated', [False, True])
def test_parent_guard_agrees_with_production_session(state_factory, expected, accelerated):
    before = production_values()
    state = state_factory()
    private = decision(runtime(v3.baseline(), accelerated)['call_decision'], state)
    assert production_values() == before
    with ai_weights_session():
        production = decision(call_decision, state)
        assert private.to_dict() == production.to_dict()
        assert private.recommended_action.action_type == expected
    assert production_values() == before


def test_round_one_candidates_freeze_every_other_weight():
    parent = v3.baseline()
    configs = v3.candidates()
    assert len(configs) == 6
    assert len({fingerprint(cfg) for cfg in configs}) == 6
    for cfg in configs:
        assert validate_weights(cfg) is cfg
        assert {k: v for k, v in cfg['weights'].items() if k not in v3.KEYS} == {
            k: v for k, v in parent['weights'].items() if k not in v3.KEYS}
        for key, (lo, hi) in zip(v3.KEYS, v3.LIMITS):
            assert lo <= cfg['weights'][key] <= hi
            assert abs(cfg['weights'][key] / parent['weights'][key] - 1) <= .15


@pytest.mark.parametrize('key', [k for k in v3.baseline()['weights'] if k not in v3.KEYS])
def test_each_other_weight_is_frozen(key):
    cfg = copy.deepcopy(v3.baseline())
    cfg['weights'][key] += .001
    with pytest.raises(ValueError, match='freeze'):
        v3.validate_v3(cfg)


@pytest.mark.parametrize('index,value', [(0,111), (0,151), (1,.75), (1,1.03)])
def test_round_one_bounds_reject_outside_values(index, value):
    cfg = copy.deepcopy(v3.baseline())
    cfg['weights'][v3.KEYS[index]] = value
    with pytest.raises(ValueError, match='bounds'):
        v3.validate_v3(cfg)


def test_version_source_hash_and_historical_identity_are_isolated():
    historical = load_weights(POOL / 'baseline_v1.json')
    expected = hashlib.sha256(json.dumps(historical['weights'], sort_keys=True).encode()).hexdigest()
    assert fingerprint(historical) == expected == '560c1b97f2a3da4402e1051df4c3e0384fc4ba601b43a36204bfbee538e6d05f'
    cfg = v3.baseline()
    assert cfg['weights'] == historical['weights']
    assert fingerprint(cfg) != fingerprint(historical)
    renamed = copy.deepcopy(cfg)
    renamed['name'] = 'irrelevant display name'
    assert fingerprint(renamed) == fingerprint(cfg)
    bad = copy.deepcopy(cfg)
    bad['runtime_hashes']['ev_engine'] = '0' * 64
    assert fingerprint(bad) != fingerprint(cfg)
    with pytest.raises(ValueError, match='provenance'):
        validate_weights(bad)
    with pytest.raises(ValueError, match='snapshot modified'):
        v3.guard_runtime(bad, False)
    assert not any(name.startswith('app.core._v3_') for name in sys.modules)
    bad = copy.deepcopy(cfg)
    bad['policy_version'] = 'V3-unknown'
    with pytest.raises(ValueError, match='Unknown policy'):
        validate_weights(bad)
    assert decision(runtime(historical)['call_decision'], gm86()).recommended_action.action_type == ActionType.CHI


@pytest.mark.parametrize('blocks,expected', [(250, [150,300,300]), (75, [45,90,90]), (74, [44,89,89])])
@pytest.mark.parametrize('seed', [21610000, 21810000, 61017])
def test_quota_schedule_is_deterministic_mixed_and_preserves_fallback_quota(blocks, expected, seed):
    schedule = v3.quota_schedule(blocks, seed)
    assert schedule == v3.quota_schedule(blocks, seed)
    assert len(schedule) == blocks
    assert all(len(trio) == 3 and len(set(trio)) >= 2 and 1 in trio for trio in schedule)
    counts = Counter(p for trio in schedule for p in trio)
    assert [counts[i] for i in range(3)] == expected


def test_small_quota_schedule_repairs_historical_only_tail_without_changing_quota():
    # Small schedules frequently place two remaining historical slots at the tail.
    # Repair must preserve the earlier mixed trios as well as the global quota.
    for seed in range(100):
        schedule = v3.quota_schedule(5, seed)
        assert all(len(set(trio)) >= 2 for trio in schedule)
        assert Counter(p for trio in schedule for p in trio) == {0:3, 1:6, 2:6}


def test_wall_bootstrap_is_deterministic_and_counts_walls():
    values = [-4, 2, 3, 11]
    result = v3.interval(values, repeats=1000)
    assert result == v3.interval(iter(values), repeats=1000)
    assert result['clusters'] == 4
    assert result['mean'] == 3
    assert result['normal_lower'] < 3 < result['normal_upper']
    assert result['bootstrap_lower'] <= 3 <= result['bootstrap_upper']
    assert v3.interval([2,2], repeats=100) == dict(mean=2, se=0, normal_lower=2,
        normal_upper=2, bootstrap_lower=2, bootstrap_upper=2, clusters=2)
    with pytest.raises(ValueError, match='two walls'):
        v3.interval([1])


def passing_comparison():
    def bounds(mean, lo, hi):
        return dict(mean=mean, normal_lower=lo, bootstrap_lower=lo,
                    normal_upper=hi, bootstrap_upper=hi, clusters=250)
    counts = dict(tenpai_opp=300, tenpai_break=0)
    for t in v3.CLAIMS:
        counts.update({t+'_opp':300, t+'_take':100, t+'_benefit_opp':250, t+'_benefit_take':80})
    return dict(candidate=copy.deepcopy(counts), baseline=copy.deepcopy(counts),
                net=bounds(1,.1,2), dealin=bounds(0,-.001,.001),
                progress=bounds(0,-.01,.01), zimo=bounds(0,-.001,.001),
                low_tenpai=bounds(0,-.001,.001),
                claims={t:dict(candidate=1/3,baseline=1/3) for t in v3.CLAIMS})


def test_gates_pass_only_with_full_evidence():
    comparison = passing_comparison()
    assert all(v3.gates(comparison, {'A':comparison}, True, 0).values())
    assert not v3.gates(comparison, {}, True)['elo']
    assert not v3.gates(comparison, {}, False, 0)['invariants']


@pytest.mark.parametrize('metric,field,value,gate', [
    ('net','normal_lower',0,'net'), ('net','bootstrap_lower',-.1,'net'),
    ('net','clusters',249,'main_sample'), ('dealin','mean',.0001,'dealin'),
    ('dealin','normal_upper',.0051,'dealin'), ('dealin','bootstrap_upper',.0051,'dealin'),
])
def test_gates_reject_bad_net_and_dealin_growth(metric, field, value, gate):
    comparison = passing_comparison()
    comparison[metric][field] = value
    assert not v3.gates(comparison, {}, True, 0)[gate]


@pytest.mark.parametrize('claim', v3.CLAIMS)
def test_gates_require_claim_opportunities_and_observed_rates(claim):
    comparison = passing_comparison()
    comparison['candidate'][claim+'_opp'] = 199
    comparison['claims'][claim]['candidate'] = None
    result = v3.gates(comparison, {}, True, 0)
    assert not result['opportunities_'+claim]
    assert not result['rate_'+claim]


def test_gates_reject_missing_progress_tenpai_and_bad_pressure_elo():
    comparison = passing_comparison()
    comparison['progress'] = comparison['low_tenpai'] = None
    pressure = passing_comparison()
    pressure['net']['bootstrap_lower'] = -1.01
    result = v3.gates(comparison, {'D':pressure}, True, -10.01)
    assert not result['progress']
    assert not result['low_risk_tenpai']
    assert not result['pressure_D']
    assert not result['elo']


def test_collector_counts_decisions_once_and_audits_parent_on_the_same_state(monkeypatch):
    from tools import arena
    seen = []
    class ParentPolicy:
        def __init__(self, cfg, mode):
            assert cfg == v3.baseline() and mode == 'ev'

        def choose(self, match, seat):
            seen.append((match, seat))
            return dict(action_type='chi', tiles=['1m','2m','3m'])

    monkeypatch.setattr(arena, 'Policy', ParentPolicy)
    options = [dict(action_type='chi', tiles=['1m','2m','3m']),
               dict(action_type='chi', tiles=['2m','3m','4m']),
               dict(action_type='pong', tiles=['3m']*3), dict(action_type='pass')]
    match = SimpleNamespace(options={'E':options}, phase='audit')
    collector = v3.Collector(2)
    collector.before(match, 'E', 1, dict(action_type='pass'), None)
    assert not collector.metrics and not seen
    collector.before(match, 'E', 2, dict(action_type='pass'), None)
    assert seen == [(match, 'E')]
    counts = collector.metrics
    assert counts['chi_opp'] == counts['pong_opp'] == 1
    assert counts['chi_take'] == counts['pong_take'] == 0
    assert counts['audit_chi_opp'] == counts['audit_pong_opp'] == 1
    assert counts['audit_chi_take'] == counts['audit_pong_take'] == 0
    assert counts['audit_parent_chi_take'] == 1
    assert counts['audit_parent_pong_take'] == 0
    assert counts['audit_actions'] == counts['audit_flips'] == 1
    assert counts['ming_gang_opp'] == 0


def test_collector_progress_uses_only_paired_normal_discard_windows(monkeypatch):
    monkeypatch.setattr(v3, 'shanten', lambda hand, god, meld_count: int(hand[0]))
    action = dict(action_type='discard', tiles=['X'])
    match = SimpleNamespace(options={'E':[action]}, phase='discard', god='9p',
                            hands={'E':[]}, melds={'E':[]})
    collector = v3.Collector(0, audit=False)
    def discard(shanten):
        match.hands['E'] = [str(shanten), 'X']
        collector.before(match, 'E', 0, action, None)
        collector.after(match, 'E', 0, action)

    discard(3)
    assert collector.metrics['progress_windows'] == 0  # No preceding draw window.
    discard(2)
    assert collector.metrics['progress_windows'] == collector.metrics['progress_sum'] == 1
    match.options['E'] = [dict(action_type='chi', tiles=['1m','2m','3m'])]
    collector.before(match, 'E', 0, match.options['E'][0], None)
    match.options['E'] = [action]
    discard(1)  # Mandatory discard after a claim is not a normal draw window.
    assert collector.metrics['progress_windows'] == 1
    discard(3)  # No comparable prior normal discard remains after that claim.
    assert collector.metrics['progress_windows'] == 1
    discard(2)
    assert collector.metrics['progress_windows'] == collector.metrics['progress_sum'] == 2
    assert collector.metrics['progress_3_windows'] == 2
    # End of hand contributes no fabricated following state to the denominator.
    assert collector.previous == 2
    assert sum(value for key, value in collector.metrics.items()
               if key != 'progress_windows' and key.startswith('progress_')
               and key.endswith('_windows')) == 2


class FakeExecutor:
    def __init__(self, fail_after=None):
        self.jobs = []
        self.fail_after = fail_after

    def map(self, function, jobs, chunksize):
        assert chunksize == 1
        for index, job in enumerate(jobs):
            if index == self.fail_after:
                raise RuntimeError('interrupted fake worker')
            self.jobs.append(job)
            seed, _, configs, physical, _ = job
            order = [(physical-1+j)%4 for j in range(4)]
            yield [dict(seed=seed, dealer=dealer, physical_candidate_seat=physical,
                        policies=[fingerprint(configs[s]) for s in order],
                        net=[0,0,0,0], winner=None, dealin=None, draw=True,
                        win_type=None, behavior={}) for dealer in range(4)]


def test_evaluator_schedule_seat_rotation_and_checkpoint_identity(tmp_path, monkeypatch):
    from scripts import tune_ai_weights_v3 as tuner
    monkeypatch.setattr(tuner, 'implementation_hash', lambda: 'implementation-1')
    clock = iter(range(0,1000,20))
    monkeypatch.setattr(tuner.time, 'monotonic', lambda: next(clock))
    executor = FakeExecutor()
    evaluator = tuner.Evaluator(tmp_path, executor)
    cfg = v3.baseline()
    report = evaluator.evaluate(cfg, 16, 61017, 'cheap')
    assert [job[3] for job in executor.jobs] == [0,1,2,3]
    assert [job[0] for job in executor.jobs] == [61017,61018,61019,61020]
    assert all(fingerprint(job[2][job[3]]) == fingerprint(cfg) for job in executor.jobs)
    assert all(row['policies'][1] == fingerprint(cfg) for row in report['rows'])
    schedule = json.loads((tmp_path/'cheap_schedule.json').read_text())
    assert schedule['schedule'] == v3.quota_schedule(4, 61017)
    assert evaluator.evaluate(cfg, 16, 61017, 'cheap') == report
    assert len(executor.jobs) == 4
    assert not (tmp_path/'cheap.partial.json').exists()
    with pytest.raises(ValueError, match='Checkpoint'):
        evaluator.evaluate(cfg, 16, 61018, 'cheap')
    evaluator.version = 'implementation-2'
    with pytest.raises(ValueError, match='Checkpoint'):
        evaluator.evaluate(cfg, 16, 61017, 'cheap')


def test_partial_checkpoint_resumes_only_complete_matching_blocks(tmp_path, monkeypatch):
    from scripts import tune_ai_weights_v3 as tuner
    monkeypatch.setattr(tuner, 'implementation_hash', lambda: 'implementation-1')
    clock = iter(range(0,1000,20))
    monkeypatch.setattr(tuner.time, 'monotonic', lambda: next(clock))
    interrupted = tuner.Evaluator(tmp_path, FakeExecutor(fail_after=1))
    cfg = v3.baseline()
    with pytest.raises(RuntimeError, match='interrupted'):
        interrupted.evaluate(cfg, 16, 61017, 'resume')
    partial = tmp_path/'resume.partial.json'
    saved = json.loads(partial.read_text())
    assert len(saved['rows']) == 4
    executor = FakeExecutor()
    resumed = tuner.Evaluator(tmp_path, executor)
    report = resumed.evaluate(cfg, 16, 61017, 'resume')
    assert len(report['rows']) == 16
    assert [job[1] for job in executor.jobs] == [1,2,3]
    assert not partial.exists()
    (tmp_path/'resume.json').unlink()
    saved['rows'][0]['physical_candidate_seat'] = 3
    partial.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='Partial schedule'):
        resumed.evaluate(cfg, 16, 61017, 'resume')
    saved['rows'] = saved['rows'][:3]
    partial.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='Partial block'):
        resumed.evaluate(cfg, 16, 61017, 'resume')
