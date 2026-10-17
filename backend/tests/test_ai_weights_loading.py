import copy
import json
import random
import shutil
import pytest
from fastapi.testclient import TestClient
from app.core import ev_engine,call_decision,tenpai_model
from app.core.ai_weights import CONFIG_DIR,BOUNDS,ai_weights_session,read_policy
from app.core.deck_engine import setup_new_game
from app.main import app
from tools.weights import load_weights,runtime

def config_copy(tmp_path):
    for name in ('ai_weights_v0.json','ai_weights_optimized.json'):
        shutil.copyfile(CONFIG_DIR/name,tmp_path/name)
    return tmp_path

def test_optimized_preferred_and_missing_file_falls_back_to_frozen_v0(tmp_path):
    directory=config_copy(tmp_path)
    original=ev_engine.SHANTEN_PENALTY
    with ai_weights_session(directory) as status:
        assert status['version']=='V1'
        assert ev_engine.SHANTEN_PENALTY==131
        assert call_decision.SHANTEN_PENALTY==131
        assert tenpai_model._SIGMOID_CENTER==read_policy(directory)[0]['weights']['tenpai_model._SIGMOID_CENTER']
    assert ev_engine.SHANTEN_PENALTY==original
    (directory/'ai_weights_optimized.json').unlink()
    with ai_weights_session(directory) as status:
        assert status['version']=='V0'
        assert ev_engine.SHANTEN_PENALTY==call_decision.SHANTEN_PENALTY==120

@pytest.mark.parametrize('key,value',[
    ('ev_engine.SHANTEN_PENALTY',-1),('ev_engine._SHAPE_JOKER',float('nan')),
    ('ev_engine._SHAPE_JOKER',True),('ev_engine._SHAPE_PAIR',9)])
def test_invalid_config_rejected_without_partial_application(tmp_path,key,value):
    directory=config_copy(tmp_path)
    path=directory/'ai_weights_optimized.json'
    cfg=json.loads(path.read_text(encoding='utf-8'));cfg['weights'][key]=value
    path.write_text(json.dumps(cfg),encoding='utf-8')
    before=(ev_engine.SHANTEN_PENALTY,call_decision.SHANTEN_PENALTY)
    with pytest.raises(ValueError):
        with ai_weights_session(directory):pass
    assert (ev_engine.SHANTEN_PENALTY,call_decision.SHANTEN_PENALTY)==before

def test_fastapi_startup_loads_weights_and_recommendation_matches_validated_policy():
    cfg=load_weights(CONFIG_DIR/'ai_weights_optimized.json')
    original=ev_engine.SHANTEN_PENALTY
    with TestClient(app) as client:
        assert app.state.ai_policy['version']=='V1'
        assert client.get('/health').json()=={'status':'ok'}
        for seed in (19,42):
            deal=setup_new_game('E',rng=random.Random(seed))
            kwargs=dict(hand_tiles=deal['hands']['E'],dealer_tile=deal['dealer_tile'],is_dealer=True,seat_wind='E',include_self_gang=True)
            assert ev_engine.calculate_best_discards(**kwargs)==runtime(cfg)['ev_engine'].calculate_best_discards(**kwargs)
        response=client.post('/api/recommend',json={k:v for k,v in kwargs.items() if k!='include_self_gang'})
        assert response.status_code==200,response.text
        from app.core.action_generator import get_available_actions
        hand=['1m','2m','3m','4m','5m','6m','1p','2p','3p','4s','5s','C','C']
        actions=get_available_actions(hand,[],'C','S','E','9p')
        call_args=dict(available_actions=actions,hand_tiles=hand,melds=[],opponents=[],dealer_tile='9p',seat_wind='E',round_wind='E',is_dealer=True,discarded_tile='C')
        assert call_decision.evaluate_call_decision(**call_args).to_dict()==runtime(cfg)['call_decision'].evaluate_call_decision(**call_args).to_dict()
    assert ev_engine.SHANTEN_PENALTY==original

def test_production_whiteboard_overlap_matches_validated_fix():
    hand=['5m','5m','P','C','C','1p','2p','3p','7s','8s','9s','N','W','2s']
    result=ev_engine._overlap_pair_ryanmen_shape(hand,'6m')
    assert 'P' in result['choices'] and '6m' not in result['choices']
