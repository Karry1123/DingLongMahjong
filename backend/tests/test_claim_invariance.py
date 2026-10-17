"""Behavioral guardrails for V2; historical V1 intentionally remains reproducible."""
import copy
import pytest
from app.core.action_generator import ActionType, get_available_actions
from app.core.claim_v2 import DEFAULTS, BOUNDS
from app.schemas import Meld, PlayerState
from tools.weights import POOL, load_weights, runtime, validate_weights, fingerprint


def candidate(weights=None):
    cfg=copy.deepcopy(load_weights(POOL/'baseline_v1.json'))
    cfg.update(policy_version='V2-claims',claim_weights=dict(weights or DEFAULTS))
    return cfg


def gm86():
    return dict(hand_tiles=['2p','1m','2m','3m','5m','7m','8m','7p','8p','9p'],
        melds=[Meld(meld_type='pong',tiles=['E']*3)],dealer_tile='2p',seat_wind='E',round_wind='E',is_dealer=True,
        opponents=[PlayerState(seat_wind='S',discards=['N','W','2m']),
                   PlayerState(seat_wind='W',discards=['N','1m'],melds=[Meld(meld_type='chi',tiles=['7p','8p','9p'])]),
                   PlayerState(seat_wind='N',discards=['W','1p','1m'],melds=[Meld(meld_type='chi',tiles=['4s','5s','6s'])])],
        discarded_tile='1m',discarded_tiles=['S','W','9s','8s','N','W','2m','N','1m','W','1p','1m'])


def decide(cfg,k):
    actions=get_available_actions(k['hand_tiles'],k['melds'],k['discarded_tile'],'N',k['seat_wind'],k['dealer_tile'])
    return runtime(cfg)['call_decision'].evaluate_call_decision(actions,**k)


def assert_pass_over_chi(result):
    passed=next(s.net_ev for s in result.candidates if s.action.action_type==ActionType.PASS)
    claims=[s for s in result.candidates if s.action.action_type==ActionType.CHI]
    assert claims
    assert all(passed>s.net_ev for s in claims)
    assert result.recommended_action.action_type==ActionType.PASS


@pytest.mark.parametrize('edge',['default','min','max'])
@pytest.mark.parametrize('dead',[0,1,2])
def test_gm86_same_tile_return_strictly_loses_at_all_penalty_bounds(edge,dead):
    weights=DEFAULTS if edge=='default' else {k:v[0 if edge=='min' else 1] for k,v in BOUNDS.items()}
    k=gm86();k['discarded_tiles']+=['6m','9m']*dead
    assert_pass_over_chi(decide(candidate(weights),k))


def test_v1_counterexample_preserved_and_v2_scale_matches_identical_waits():
    old=load_weights(POOL/'baseline_v1.json');k=gm86()
    result=decide(old,k)
    assert result.recommended_action.action_type==ActionType.CHI
    assert [s.net_ev for s in result.candidates]==[135.2,99.0]
    ev=runtime(candidate())['call_evaluator_v2']
    rem=ev.remaining(k['hand_tiles'],k['melds'],k['discarded_tiles'],k['opponents'],'2p')
    before=ev.waiting(k['hand_tiles'],k['melds'],'2p','E',True,rem)
    action=get_available_actions(k['hand_tiles'],k['melds'],'1m','N','E','2p')[0]
    hand,melds=ev.legacy._apply_meld_action(k['hand_tiles'],k['melds'],action,'1m');hand.remove('1m')
    after=ev.waiting(hand,melds,'2p','E',True,rem)
    assert before==after
    assert before['value']==198 and before['count']==16
    assert_pass_over_chi(decide(candidate(),k))


@pytest.mark.parametrize('dealer',[False,True])
def test_closed_sequence_opening_no_gain_is_rejected_without_inventing_menzen_yaku(dealer):
    k=dict(hand_tiles=['1m','2m','3m','4m','5m','6m','7p','8p','9p','7s','7s','4p','5p'],
           melds=[],opponents=[],dealer_tile='9s',seat_wind='E',round_wind='E',is_dealer=dealer,
           discarded_tile='1m',discarded_tiles=['1m'])
    assert_pass_over_chi(decide(candidate(),k))


def test_useful_chow_to_tenpai_is_not_suppressed():
    k=dict(hand_tiles=['1m','2m','4m','5m','6m','7p','8p','9p','3s','4s','E','E','C'],
           melds=[],opponents=[],dealer_tile='9s',seat_wind='E',round_wind='E',is_dealer=True,
           discarded_tile='3m',discarded_tiles=['3m'])
    r=decide(candidate(),k)
    assert r.recommended_action.action_type==ActionType.CHI
    assert '1→0' in r.reason


def test_chow_that_regresses_shanten_is_strictly_below_pass():
    # Reproducible wall 212: using 3p/4p to claim 2p strands the concealed shape.
    k=dict(hand_tiles=['6m','2p','C','3s','4p','6m','6p','5p','5s','7m','7m','3p','1p'],
           melds=[],opponents=[],dealer_tile='8s',seat_wind='E',round_wind='E',is_dealer=True,
           discarded_tile='2p',discarded_tiles=['2p'])
    r=decide(candidate(),k)
    passed=next(s.net_ev for s in r.candidates if s.action.action_type==ActionType.PASS)
    bad=next(s for s in r.candidates if s.action.tiles==['2p','3p','4p'])
    assert '1→2' in bad.note
    assert bad.net_ev<passed


def test_kong_enumeration_counts_winning_replacement_without_discard(monkeypatch):
    ev=runtime(candidate())['call_evaluator_v2']
    melds=[Meld(meld_type='ming_gang',tiles=['1m']*4),Meld(meld_type='chi',tiles=['1p','2p','3p']),Meld(meld_type='chi',tiles=['4p','5p','6p'])]
    hand=['7s','8s','9s','E']
    def no_discard(*a,**kw):raise AssertionError('Winning replacement must not be discarded')
    monkeypatch.setattr(ev,'after_discard',no_discard)
    hu=ev.ev._best_hu_points(melds=melds,hand_tiles=hand,win_tile='E',seat_wind='E',dealer_tile='5m')
    assert ev.kong(hand,melds,'5m','E',True,[],[],'E',{'E':2})==hu['final_hu']*3


@pytest.mark.parametrize('hand,tile,expected',[
    (['1m','2m','3m','4m','5m','6m','7p','8p','9p','E','E','N','C'],'E',ActionType.PONG),
    (['1m']*3+['2m','3m','4m','4p','5p','6p','7s','8s','9s','N'],'1m',ActionType.MING_GANG),
])
def test_useful_pung_and_kong_are_not_suppressed(hand,tile,expected):
    actions=get_available_actions(hand,[],tile,'S','E','5p')
    r=runtime(candidate())['call_decision'].evaluate_call_decision(actions,hand,[],[],'5p','E','E',True,discarded_tile=tile,discarded_tiles=[tile])
    assert r.recommended_action.action_type==expected


def test_every_physical_seat_and_dealer_are_balanced_and_pool_is_mixed():
    from tools.claim_experiment import schedule
    old=load_weights(POOL/'baseline_v0.json');v1=load_weights(POOL/'baseline_v1.json');v2=candidate()
    for i in range(4):
        _,configs,_,seat=schedule(v2,[old,v1],100+i,i,'ev')
        assert seat==i
        assert fingerprint(configs[seat])==fingerprint(v2)
        assert {fingerprint(c) for j,c in enumerate(configs) if j!=seat}=={fingerprint(old),fingerprint(v1)}


def test_v1_weights_frozen_and_distinct_policy_identity():
    cfg=candidate();old=load_weights(POOL/'baseline_v1.json')
    assert cfg['weights']==old['weights']
    assert fingerprint(cfg)!=fingerprint(old)
    cfg['weights']['ev_engine.SHANTEN_PENALTY']+=1
    with pytest.raises(ValueError,match='freeze'):validate_weights(cfg)


@pytest.mark.parametrize('bad',[-1,float('nan'),True,101])
def test_claim_parameter_hard_bounds(bad):
    cfg=candidate();cfg['claim_weights']['redundant_chow_penalty']=bad
    with pytest.raises(ValueError):validate_weights(cfg)


def test_unaccelerated_v2_matches_accelerated_decision():
    cfg=candidate();k=gm86();actions=get_available_actions(k['hand_tiles'],k['melds'],'1m','N','E','2p')
    assert runtime(cfg,False)['call_decision'].evaluate_call_decision(actions,**k).to_dict()==runtime(cfg)['call_decision'].evaluate_call_decision(actions,**k).to_dict()


@pytest.mark.parametrize('edge',['default','min','max'])
def test_same_tile_unchanged_waits_removed_from_ai_available_pool(edge):
    values=DEFAULTS if edge=='default' else {k:v[0 if edge=='min' else 1] for k,v in BOUNDS.items()}
    r=decide(candidate(values),gm86())
    assert all(a['action_type']!='chi' for a in r.to_dict()['available_actions'])
    assert next(s for s in r.candidates if s.action.action_type==ActionType.CHI).net_ev==float('-inf')
    assert r.recommended_action.action_type==ActionType.PASS


def test_tenpai_guard_does_not_filter_a_genuinely_improved_wait():
    evaluator=runtime(candidate())['call_evaluator_v2']
    before={'shanten':0,'ukeire':[dict(tile='1m',rem=2,est_base_points=10,est_final_points=20,est_win_points=60,is_hard_hu=False)]}
    after=copy.deepcopy(before);after['ukeire'][0]['est_final_points']=24
    assert not evaluator.unchanged_waits(before,after)


def test_gain_and_defense_gate():
    from scripts.tune_claim_weights import promotion_passes
    stats={'clusters':500,'mean_gain_per_hand':.1,'lower_95_percent':-.2}
    assert promotion_passes(stats,{'deal_in_rate':.18},{'deal_in_rate':.18})
    assert not promotion_passes(stats,{'deal_in_rate':.18},{'deal_in_rate':.1805})
    assert not promotion_passes(dict(stats,mean_gain_per_hand=0),{'deal_in_rate':.18},{'deal_in_rate':.17})
    assert not promotion_passes(stats,{'deal_in_rate':.18},{'deal_in_rate':.17},smoke=True)
