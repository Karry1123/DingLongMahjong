"""GM-4720EF: supplied complete shape and the actual archived public board."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import PlayerState
from app.core.action_generator import ActionType, get_available_actions
from app.core.call_decision import evaluate_call_decision, _apply_meld_action, _hand_shanten
from app.core.scoring import calculate_best_hu_points, PONG_TERMINAL_HONOR_HU

SUPPLIED_HAND = '1m 1m 3p 3p 3p 7p 8p 8p 9p 2s 3s 4s C'.split()
ARCHIVE = json.loads((Path(__file__).parent/'fixtures/gm4720ef.json').read_text())


def decision(hand, dealer=True):
    opponents=[PlayerState.model_validate(p) for p in ARCHIVE['opponents']]
    actions=get_available_actions(hand_tiles=hand,melds=[],discarded_tile='1m',provider_seat='N',player_seat='E',dealer_tile='1s')
    result=evaluate_call_decision(actions,hand,[],opponents,'1s','E','E',dealer,
        discarded_tile='1m',discarded_tiles=ARCHIVE['discards']+sum([p.discards for p in opponents],[]),turn_count=5)
    return result


@pytest.mark.parametrize('hand',[SUPPLIED_HAND,ARCHIVE['hand_tiles']])
def test_pong_recommended_over_pass_with_archived_opponent_melds(hand):
    result=decision(hand)
    assert result.recommended_action.action_type == ActionType.PONG
    scores={c.action.action_type:c for c in result.candidates}
    assert scores[ActionType.PONG].net_ev > scores[ActionType.PASS].net_ev
    assert '+4胡' in scores[ActionType.PONG].note


def test_second_pair_is_a_valid_head_and_open_terminal_triplet_keeps_hard_hu():
    result=decision(SUPPLIED_HAND)
    hand,melds=_apply_meld_action(SUPPLIED_HAND,[],result.recommended_action,'1m')
    hand.remove('C')
    assert _hand_shanten(hand,melds,'1s') == 0
    score=calculate_best_hu_points(melds=melds,hand_tiles=hand,win_tile='8p',is_zimo=False,
        seat_wind='E',dealer_tile='1s',round_wind='E')
    assert score['is_hard_hu']
    assert PONG_TERMINAL_HONOR_HU == 4
    assert '直接听牌' in result.candidates[0].note
    assert '庄家连庄机会' in result.candidates[0].note


def test_archived_shape_is_not_falsely_labeled_immediate_tenpai():
    result=decision(ARCHIVE['hand_tiles'])
    pong=next(c for c in result.candidates if c.action.action_type == ActionType.PONG)
    assert '直接听牌' not in pong.note
    assert '向听 1→1' in pong.note


def test_dead_waits_and_dangerous_discards_do_not_force_a_call():
    # Tempo incentives cannot turn dead waits into a forced push or erase defense loss.
    for waits in [0,4]:
        with patch('app.core.call_decision.calculate_best_discards',return_value={
            'candidates':[{'tile':'C','ev_score':-1000.,'effective_count':waits,'defense_loss':1000.}]}):
            result=decision(SUPPLIED_HAND)
        assert result.recommended_action.action_type == ActionType.PASS
        pong=next(c for c in result.candidates if c.action.action_type == ActionType.PONG)
        assert ('直接听牌' in pong.note) == (waits>0)


def test_game_step_api_delivers_pong_recommendation_for_both_shapes():
    with TestClient(app) as client:
        for hand in [SUPPLIED_HAND,ARCHIVE['hand_tiles']]:
            payload={**ARCHIVE,'hand_tiles':hand,'event':{'event_type':'DISCARD','actor_seat':'N','tile':'1m'}}
            # The step appends this new discard; do not count its archived river copy twice.
            payload['opponents']=[{**p,'discards':p['discards'][:-1] if p['seat_wind']=='N' else p['discards']} for p in ARCHIVE['opponents']]
            response=client.post('/api/game/step',json=payload)
            assert response.status_code==200,response.text
            data=response.json()['call_decision']
            assert data['recommended_action']['action_type']=='pong'
            assert data['recommended_action']['provider_seat']=='N'
