"""Production V1 guard: redundant CHI stays legal but is not recommended."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core import call_decision as c
from app.core.action_generator import ActionType, get_available_actions
from app.core.ai_weights import ai_weights_session, CONFIG_DIR
from tests.test_claim_invariance import gm86


def decision(k):
    actions=get_available_actions(k['hand_tiles'],k['melds'],k['discarded_tile'],'N','E',k['dealer_tile'])
    return actions,c.evaluate_call_decision(actions,**k)


@pytest.mark.parametrize('reverse_actions', [False, True])
def test_gm86_production_v1_guards_recommendation_but_preserves_player_options(reverse_actions):
    path=CONFIG_DIR/'ai_weights_optimized.json';old=path.read_bytes()
    with ai_weights_session() as status:
        assert status['version']=='V1'
        actions,r=decision(gm86())
        if reverse_actions:
            r=c.evaluate_call_decision(list(reversed(actions)),**gm86())
        assert any(a.action_type==ActionType.CHI for a in actions)
        assert r.recommended_action.action_type==ActionType.PASS
        assert r.pass_ev==99
        chow_scores=[s for s in r.candidates if s.action.action_type==ActionType.CHI]
        assert chow_scores
        assert all(s.net_ev<r.pass_ev and '仍可手动吃牌' in s.note for s in chow_scores)
        assert {'chi','pass'} <= {a['action_type'] for a in r.to_dict()['available_actions']}
        assert '原样打回' in r.reason
    assert path.read_bytes()==old


def test_normal_advancing_chow_remains_recommended():
    k=dict(hand_tiles=['1m','2m','4m','5m','6m','7p','8p','9p','3s','4s','E','E','C'],
           melds=[],opponents=[],dealer_tile='9s',seat_wind='E',round_wind='E',is_dealer=True,
           discarded_tile='3m',discarded_tiles=['3m'])
    with ai_weights_session():
        _,r=decision(k)
        assert r.recommended_action.action_type==ActionType.CHI
        assert '1→0' in r.reason


def test_game_step_api_recommends_pass_but_keeps_serializable_player_chow_option():
    k=gm86()
    state={key:k[key] for key in ('hand_tiles','melds','opponents','dealer_tile','seat_wind','round_wind','is_dealer')}
    state['melds']=[m.model_dump(mode='json') for m in state['melds']]
    state['opponents']=[o.model_dump(mode='json') for o in state['opponents']]
    # API applies the just-discarded 1m itself.
    state['opponents'][-1]['discards'].pop()
    state['discards']=['S','W','9s','8s']
    state['event']={'event_type':'DISCARD','actor_seat':'N','tile':'1m'}
    with TestClient(app) as client:
        r=client.post('/api/game/step',json=state)
        assert r.status_code==200,r.text
        decision=r.json()['call_decision']
        assert decision['recommended_action']['action_type']=='pass'
        assert {'chi','pass'} <= {a['action_type'] for a in decision['available_actions']}
        chow=next(s for s in decision['candidates'] if s['action']['action_type']=='chi')
        assert chow['net_ev']<decision['pass_ev']
        assert 'Infinity' not in r.text


def test_wait_signature_does_not_filter_higher_hu_value(monkeypatch):
    # Even equal wait width is insufficient if any tile's score/fan improves.
    def collect(hand,*args):
        return [dict(tile='6m',rem=4,est_base_points=10,est_final_points=20 if hand==['1m'] else 24,
                     est_win_points=60 if hand==['1m'] else 72,is_hard_hu=False)]
    monkeypatch.setattr(c,'_collect_ukeire',collect)
    assert not c._same_live_win_profile(['1m'],[],['2m'],[],'9p','E',True,[],[])
