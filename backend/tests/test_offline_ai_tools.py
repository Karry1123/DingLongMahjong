import copy
import math
import random
from pathlib import Path
import pytest
from app.core import ev_engine,danger_model
from app.core.deck_engine import setup_new_game
from tools.weights import POOL,PARAMETERS,load_weights,runtime,validate_weights,fingerprint
from tools.arena import simulate,evaluate_pool,paired_comparison
from scripts.tune_ai_weights import mutate,promotion_gate

def baseline():return load_weights(POOL/'baseline_v0.json')

@pytest.mark.parametrize('value',[-1,float('nan'),float('inf'),1000000,True])
def test_rejects_invalid_weights(value):
    cfg=baseline();cfg['weights']['ev_engine.SHANTEN_PENALTY']=value
    with pytest.raises(ValueError):validate_weights(cfg)

def test_complete_schema_and_source_binding():
    cfg=baseline();cfg['weights'].pop(next(iter(PARAMETERS)))
    with pytest.raises(ValueError):validate_weights(cfg)
    cfg=baseline();cfg['source_hashes']['ev_engine']='wrong'
    with pytest.raises(ValueError):validate_weights(cfg)

def test_baseline_ev_matches_existing_and_candidate_is_isolated():
    cfg=baseline();original=ev_engine.SHANTEN_PENALTY
    deal=setup_new_game('E',rng=random.Random(19))
    kw=dict(hand_tiles=deal['hands']['E'],dealer_tile=deal['dealer_tile'],is_dealer=True,seat_wind='E',include_self_gang=True)
    assert runtime(cfg)['ev_engine'].calculate_best_discards(**kw)==ev_engine.calculate_best_discards(**kw)
    changed=copy.deepcopy(cfg);changed['weights']['ev_engine.SHANTEN_PENALTY']=200
    assert runtime(changed)['ev_engine'].SHANTEN_PENALTY==200
    assert ev_engine.SHANTEN_PENALTY==original
    assert runtime(cfg)['ev_engine'].SHANTEN_PENALTY==original

def test_seed_and_process_determinism_and_zero_sum():
    cfg=baseline()
    a=simulate([cfg]*4,4,37,1,'fast');b=simulate([cfg]*4,4,37,2,'fast')
    assert a['rows']==b['rows']
    assert all(sum(r['net'])==0 for r in a['rows'])
    assert [r['dealer'] for r in a['rows']]==[0,1,2,3]
    assert sum(x['wins'] for x in a['seats'])==sum(r['winner'] is not None for r in a['rows'])

def test_pool_never_four_same_and_pairing_rejects_mismatched_walls():
    cfg=baseline();report=evaluate_pool(cfg,8,7,1,'fast')
    assert all(len(set(r['policies']))>=2 for r in report['rows'])
    assert paired_comparison(report,report)['mean_gain_per_hand']==0
    changed=copy.deepcopy(report);changed['rows'][0]['seed']+=1
    with pytest.raises(ValueError):paired_comparison(report,changed)
    with pytest.raises(ValueError):evaluate_pool(cfg,4,7,1,'fast',[cfg])

def test_mutation_is_bounded_and_fast_or_small_samples_cannot_promote():
    cfg=baseline();rng=random.Random(9)
    keys=['ev_engine.SHANTEN_PENALTY','ev_engine._DEFENSE_RISK_REFERENCE']
    for _ in range(100):validate_weights(mutate(cfg,rng,keys,.5))
    stats={'clusters':500,'mean_gain_per_hand':100,'standard_error':1}
    assert not promotion_gate(stats,2000,'fast',1,2.576)
    assert not promotion_gate(stats,1000,'ev',1,2.576)
    assert promotion_gate(stats,2000,'ev',1,2.576)
    stats['mean_gain_per_hand']=1
    assert not promotion_gate(stats,2000,'ev',1,2.576)

def test_win_only_legal_actions_match_production_and_no_globals_mutated():
    from tools.arena import fast_available_actions
    from app.core.action_generator import get_available_actions
    from app.core import action_generator
    original=action_generator._can_ron
    for seed in range(12):
        deal=setup_new_game('E',rng=random.Random(seed))
        for seat in 'SWN':
            args=(deal['hands'][seat],[],deal['hands']['E'][-1],'E',seat,deal['dealer_tile'])
            assert fast_available_actions(*args)==get_available_actions(*args)
    assert action_generator._can_ron is original

def test_indexed_shanten_matches_reference_with_jokers_and_open_hands():
    from app.core.constants import ALL_TILES
    from app.core.evaluator import check_win_or_shanten
    from tools.shanten_kernel import shanten
    rng=random.Random(43)
    for needed in range(5):
        for jokers in range(min(3*needed+1,4)+1):
            for _ in range(12):
                hand=rng.sample(list(ALL_TILES)*4,3*needed+1-jokers)+['JOKER']*jokers
                assert shanten(hand,0,needed)==check_win_or_shanten(hand,0,needed)

def test_accelerated_ev_and_draw_pruning_equal_frozen_reference():
    from app.schemas import PlayerState
    cfg=baseline();fast=runtime(cfg)['ev_engine'];raw=runtime(cfg,False)['ev_engine']
    for seed in (2,7,19):
        deal=setup_new_game('E',rng=random.Random(seed))
        kw=dict(hand_tiles=deal['hands']['E'],dealer_tile=deal['dealer_tile'],is_dealer=True,seat_wind='E',
                opponents=[PlayerState(seat_wind=s,discards=['1m','C']) for s in 'SWN'],include_self_gang=True)
        assert fast.calculate_best_discards(**kw)==raw.calculate_best_discards(**kw)
    # Returned candidate arrays are fresh: consumers cannot poison cached results.
    kw=dict(hand_tiles=deal['hands']['E'],dealer_tile=deal['dealer_tile'],rem_map={t:3 for t in deal['hands']['E']},seat_wind='E')
    expected=raw.generate_candidate_discards(**kw)
    fast.generate_candidate_discards(**kw).clear()
    assert fast.generate_candidate_discards(**kw)==expected

def test_all_core_parameters_feed_fast_proxy_and_edges_stay_frozen():
    from types import SimpleNamespace
    from tools.core_search import CORE_KEYS,exploration_scores
    cfg=baseline();rng=random.Random(99)
    for _ in range(30):
        child=mutate(cfg,rng,CORE_KEYS,.08)
        assert all(child['weights'][k]==v for k,v in cfg['weights'].items() if k not in CORE_KEYS)
    changed=set()
    for hand in (['3m','4m','4m','5m','6m','C','C','F','1p','9s','2s','7p','8p','N'],
                 ['3m','4m','4m','5m','6m','C','F','1p','9s','2s','7p','8p','N','W']):
        match=SimpleNamespace(hands={'E':hand},god='3m',rivers={s:['1s']*8 for s in 'ESWN'},melds={s:[] for s in 'ESWN'})
        rows=[{'action_type':'discard','tiles':[t]} for t in dict.fromkeys(hand)]
        original=exploration_scores(match,'E',rows,cfg['weights'])
        for key in CORE_KEYS:
            weights=dict(cfg['weights']);weights[key]*=1.1
            if exploration_scores(match,'E',rows,weights)!=original:changed.add(key)
    assert changed==set(CORE_KEYS)

def test_elite_filter_never_validates_losers_and_keeps_at_most_three():
    from tools.two_stage import select_elites
    cfg=baseline()
    def report(net,win):return {'seats':[{}, {'net_points':net,'win_rate':win}]}
    trials=[]
    for i,net in enumerate((-10,0,1,20,5,30)):
        child=copy.deepcopy(cfg);child['weights']['ev_engine._SHAPE_JOKER']+=i*.1
        trials.append({'config':child,'report':report(net,.1+i*.01)})
    elites=select_elites(trials,report(0,.25))
    assert [e['report']['seats'][1]['net_points'] for e in elites]==[30,20,5]

def test_persistent_workers_preserve_paired_results():
    from concurrent.futures import ProcessPoolExecutor
    cfg=baseline()
    expected=evaluate_pool(cfg,4,51,1,'explore')
    with ProcessPoolExecutor(max_workers=2) as executor:
        first=evaluate_pool(cfg,4,51,2,'explore',executor=executor)
        second=evaluate_pool(cfg,4,51,2,'explore',executor=executor)
    assert first['rows']==second['rows']==expected['rows']

def test_two_stage_smoke_cannot_promote_even_if_significant(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from tools import two_stage
    from scripts.tune_ai_weights import atomic_json,compact
    cfg=baseline()
    args=SimpleNamespace(seed=9,generations=1,population=1,hands=4,validation_hands=52,
        elites=3,workers=1,sigma=.08,minimum_gain=1,smoke_test=True,output=tmp_path,history_dir=tmp_path/'history')
    calls=[]
    def evaluate(candidate,hands,seed,workers,mode,pool):
        calls.append((mode,hands,seed))
        winner=fingerprint(candidate)!=fingerprint(cfg)
        return {'seats':[{}, {'net_points':100 if winner else 0,'win_rate':.3 if winner else .2,'deal_in_rate':.1}], 'rows':[]}
    monkeypatch.setattr(two_stage,'paired_comparison',lambda a,b:{'mean_gain_per_hand':100,'standard_error':0,'clusters':500})
    two_stage._run(args,cfg,[cfg],atomic_json,mutate,lambda *a:True,compact,evaluate)
    assert (tmp_path/'best_candidate.json').exists()
    assert not (tmp_path/'ai_weights_optimized.json').exists()
    assert not args.history_dir.exists()
    assert json_load(tmp_path/'validation_0000_0.json')['status']=='smoke_unvalidated'
    assert calls[:2]==[('explore',4,9)]*2
    assert all(seed!=9 for mode,hands,seed in calls if mode=='ev')

def json_load(path):
    import json
    return json.loads(path.read_text())

def test_checkpoint_resumes_complete_blocks_and_reuses_finished_evaluation(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    from tools import experiment_io
    from scripts.tune_ai_weights import atomic_json
    args=SimpleNamespace(checkpoint_dir=tmp_path/'checkpoints',output=tmp_path/'run')
    evaluator=experiment_io.CheckpointEvaluator(args,None,atomic_json)
    cfg=baseline();pool=[cfg,load_weights(POOL/'conservative.json')]
    expected=evaluator(cfg,8,101,1,'explore',pool)
    path=next(evaluator.root.glob('evaluation_*.json'))
    key=path.stem.removeprefix('evaluation_')
    path.unlink()
    atomic_json(evaluator.root/('partial_'+key+'.json'),{'rows':expected['rows'][:4],'elapsed':.01})
    recovered=evaluator(cfg,8,101,1,'explore',pool)
    assert recovered['rows']==expected['rows']
    monkeypatch.setattr(experiment_io,'evaluate_pool',lambda *a,**kw:pytest.fail('Must reuse checkpoint'))
    assert evaluator(cfg,8,101,1,'explore',pool)['rows']==expected['rows']

def test_whiteboard_overlap_choices_are_physical_tiles():
    ev=runtime(baseline())['ev_engine']
    hand=['5m','5m','P','C','C','1p','2p','3p','7s','8s','9s','N','W','2s']
    shape=ev._overlap_pair_ryanmen_shape(hand,'6m')
    assert shape is not None and 'P' in shape['choices'] and '6m' not in shape['choices']
    assert all(t in hand for t in shape['choices'])
