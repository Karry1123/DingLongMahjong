import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestSingleTileHand(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.state = {
            'hand_tiles': ['2p'], 'dealer_tile': 'F', 'seat_wind': 'E',
            'is_dealer': True, 'discards': [],
            'melds': [
                {'meld_type': kind, 'tiles': [tile] * count}
                for kind, tile, count in [('pong', '1m', 3), ('ming_gang', '9m', 4),
                                         ('an_gang', '1s', 4), ('pong', '9s', 3)]
            ],
            'opponents': [{'seat_wind': seat, 'is_dealer': False, 'melds': [], 'discards': []}
                          for seat in ['S', 'W', 'N']],
        }

    def test_single_wait_draw_and_discard(self):
        response = self.client.post('/api/recommend', json=self.state)
        self.assertEqual(response.status_code, 200, response.text)
        info = response.json()
        self.assertIsNone(info['best_tile'])
        self.assertEqual(info['candidates'], [])
        self.assertEqual(info['shanten'], 0)
        self.assertEqual({x['tile']: x['rem'] for x in info['effective_tiles']}, {'2p': 3, 'F': 3})
        drawn = self.client.post('/api/game/step', json={**self.state,
            'event': {'actor_seat': 'E', 'event_type': 'DRAW', 'tile': '3p'}})
        self.assertEqual(drawn.status_code, 200, drawn.text)
        after = drawn.json()['updated_state']
        self.assertEqual(after['hand_tiles'], ['2p', '3p'])
        recommended = self.client.post('/api/recommend', json=after)
        self.assertEqual(recommended.status_code, 200, recommended.text)
        cut = self.client.post('/api/game/step', json={**after,
            'event': {'actor_seat': 'E', 'event_type': 'DISCARD', 'tile': '3p'}})
        self.assertEqual(cut.status_code, 200, cut.text)
        self.assertEqual(cut.json()['updated_state']['hand_tiles'], ['2p'])
        win = self.client.post('/api/game/step', json={**self.state,
            'event': {'actor_seat': 'E', 'event_type': 'DRAW', 'tile': '2p'}})
        self.assertEqual(win.status_code, 200, win.text)
        self.assertTrue(win.json()['can_self_win'])
        self.assertEqual(win.json()['self_win_info']['win_tile'], '2p')

    def test_single_tile_requires_four_melds(self):
        response = self.client.post('/api/recommend', json={**self.state, 'melds': self.state['melds'][:3]})
        self.assertEqual(response.status_code, 422)
