"""Legacy round_wind fields must never affect current DingLong scoring or EV."""
import pytest
from app.core.scoring import calculate_best_hu_points, calculate_unwon_base_hu
from app.core.call_decision import _pong_yakuhai_fan
from app.core.ev_engine import calculate_best_discards
from app.schemas import Meld, MeldType

@pytest.mark.parametrize('kind', [MeldType.PONG,MeldType.MING_GANG,MeldType.AN_GANG])
def test_east_open_pung_and_kongs_only_add_own_seat_fan(kind):
    melds=[Meld(meld_type=kind,tiles=['E']*(3 if kind==MeldType.PONG else 4)),
           Meld(meld_type=MeldType.CHI,tiles=['2m','3m','4m']),
           Meld(meld_type=MeldType.CHI,tiles=['5m','6m','7m'])]
    def hu(seat,circle):
        return calculate_best_hu_points(melds,['2p','2p','5s','5s'],'5s',False,seat,'9p',round_wind=circle)
    a,b=hu('N','E'),hu('N','W')
    assert a['final_hu']==b['final_hu']
    assert 'round_wind_pung_kong' not in a['details']['fans']
    assert 'seat_wind_pung_kong' not in a['details']['fans']
    own=hu('E','E')
    assert own['details']['fans']['seat_wind_pung_kong']==1
    assert own['final_hu']==a['final_hu']*2
    assert not any('圈风' in text for text in own['details']['fan_items'])
    inherent=calculate_unwon_base_hu([],melds,'N','9p',round_wind='E')
    alternate=calculate_unwon_base_hu([],melds,'N','9p',round_wind='W')
    assert inherent['calculated_points']==alternate['calculated_points']
    assert all(item['kind']!='round_wind' for item in inherent['fan_details'])

def test_concealed_east_pung_no_circle_fan():
    hand='E E E 1m 2m 3m 4p 5p 6p 7s 8s 9s 2p'.split()
    scores=[calculate_best_hu_points([],hand,'2p',True,'N','9p',round_wind=w) for w in ['E','S','W','N']]
    assert len({score['final_hu'] for score in scores})==1
    assert all('round_wind_pung_kong' not in score['details']['fans'] for score in scores)

def test_pong_and_discard_ev_ignore_legacy_circle_identity():
    assert _pong_yakuhai_fan('E','9p','S','E')==0
    assert _pong_yakuhai_fan('E','9p','E','E')==1
    hand='1p 4p 5p 5p 2s 3s 5s 7s 8s 9s E W N N'.split()
    results=[calculate_best_discards(hand,'5m',True,'E',round_wind=w,include_self_gang=False) for w in ['E','W']]
    assert [(c['tile'],c['ev_score']) for c in results[0]['candidates']]==[(c['tile'],c['ev_score']) for c in results[1]['candidates']]
