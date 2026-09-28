import json
import sqlite3
import zlib

import pytest

from app.core.pvp_records import archive_pvp_game, scoring_groups
from app.core.scoring import calculate_unwon_player_points
from tests.test_pvp_match import custom, act


def test_archive_fifo_is_500_exact_and_duplicate_does_not_change_order(tmp_path):
    path = tmp_path / 'pvp.sqlite3'
    for i in range(503):
        archive_pvp_game({'phase': 'finished', 'result': {'kind': 'draw'}, 'game_id': f'GM-{i:06}', 'steps': [{'seat': 'E'}]}, db_path=path)
    archive_pvp_game({'phase': 'finished', 'result': {'kind': 'draw'}, 'game_id': 'GM-000003'}, db_path=path)
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT game_id,payload FROM pvp_game_records ORDER BY id').fetchall()
    assert len(rows) == 500
    assert rows[0][0] == 'GM-000003' and rows[-1][0] == 'GM-000502'
    assert json.loads(zlib.decompress(rows[0][1]))['steps'] == [{'seat': 'E'}]
    with pytest.raises(ValueError):
        archive_pvp_game({'phase': 'discard', 'game_id': 'GM-INCOMPLETE'}, db_path=path)


def test_scoring_groups_exclude_sequences_dead_tiles_and_unvalued_pairs():
    hand = 'C C S S N N 3p 4p 5p 1m 1m 1m F'.split()
    melds = [{'meld_type': 'chi', 'tiles': ['2s', '3s', '4s']},
             {'meld_type': 'pong', 'tiles': ['9m'] * 3},
             {'meld_type': 'an_gang', 'tiles': ['8p'] * 4}]
    detail = calculate_unwon_player_points(hand_tiles=hand, melds=melds, seat_wind='S', dealer_tile='6p')
    groups = scoring_groups(detail, hand, '6p')
    assert {g['kind'] for g in groups} == {'pong', 'an_gang', 'anko', 'pair'}
    assert [g['tile'] for g in groups if g['kind'] == 'pair'] == ['C', 'S']
    assert all(g['hu'] > 0 for g in groups)
    assert not any(tile in {'N', '3p', '4p', '5p', 'F', '2s', '3s', '4s'} for g in groups for tile in g['tiles'])


def test_white_substitute_uses_physical_tiles_for_scored_seat_pair():
    hand = ['P', 'S', '2p', '3p', '4p']
    detail = calculate_unwon_player_points(hand_tiles=hand, melds=[], seat_wind='S', dealer_tile='S')
    assert scoring_groups(detail, hand, 'S')[0]['tiles'] == ['P', 'S']


def test_completed_result_reveals_winner_but_not_other_full_hands(tmp_path):
    match = custom({'E': '1m 1m 1m 2m 3m 4m 3p 4p 5p 6s 7s 8s C C'.split()}, god='9s')
    act(match, 'E', 'self_draw_win')
    result = match.view('S')['result']
    assert result['game_id'] == match.game_id
    assert len(result['seat_details']['E']['hand_tiles_with_win']) == 14
    assert result['hu_detail']['winning_hand_groups']
    assert all(result['seat_details'][seat]['hand_tiles'] == [] for seat in 'SWN')
    assert sum(result['net_by_seat'].values()) == 0
    record = match.archive_record()
    assert record['steps'][-1]['action'] == 'self_draw_win'
    assert record['initial_deal']['wall_tiles']
    assert record['final_hands']['S'] == match.hands['S']
    archive_pvp_game(record, db_path=tmp_path / 'pvp.sqlite3')
