"""出牌响应动作 get_available_actions 单测。"""

from __future__ import annotations

import unittest

from app.core.action_generator import (
    ActionType,
    assert_chi_provider_is_kamicha,
    get_available_actions,
)
from app.schemas import Meld, MeldType


def _types(actions) -> set[str]:
    return {a.action_type.value for a in actions}


class TestChiKamichaOnly(unittest.TestCase):
    """跨家吃牌拦截：仅上家可吃。"""

    def test_cross_seat_no_chi(self):
        # 自家东，下家南打牌 → 不可吃
        hand = ["2s", "3s", "9m", "9m", "1p", "1p", "2p", "2p", "3p", "3p", "4p", "5p", "6p"]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=[],
            discarded_tile="4s",
            provider_seat="S",  # 下家
            player_seat="E",
            dealer_tile="9s",
        )
        self.assertNotIn(ActionType.CHI.value, _types(actions))
        self.assertIn(ActionType.PASS.value, _types(actions))

    def test_kamicha_can_chi(self):
        # 自家东，上家北打牌 → 可吃 2-3-4s
        hand = ["2s", "3s", "9m", "9m", "1p", "1p", "2p", "2p", "3p", "3p", "4p", "5p", "6p"]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=[],
            discarded_tile="4s",
            provider_seat="N",  # 上家
            player_seat="E",
            dealer_tile="9s",
        )
        chi = [a for a in actions if a.action_type == ActionType.CHI]
        self.assertTrue(chi)
        self.assertTrue(any(set(a.tiles) == {"2s", "3s", "4s"} for a in chi))

    def test_assert_chi_provider(self):
        with self.assertRaises(AssertionError):
            assert_chi_provider_is_kamicha("S", "E")
        assert_chi_provider_is_kamicha("N", "E")  # 不上抛


class TestJokerNotInGang(unittest.TestCase):
    """百搭不入杠：不得用「得」充第 4 张明杠。"""

    def test_two_real_plus_joker_no_ming_gang(self):
        # 得=7p；手中 2 张 5m + 1 张得，打出 5m → 可碰不可杠
        hand = [
            "5m",
            "5m",
            "7p",  # 得
            "1s",
            "2s",
            "3s",
            "4s",
            "5s",
            "6s",
            "7s",
            "8s",
            "9s",
            "1p",
        ]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=[],
            discarded_tile="5m",
            provider_seat="S",
            player_seat="E",
            dealer_tile="7p",
        )
        types = _types(actions)
        self.assertIn(ActionType.PONG.value, types)
        self.assertNotIn(ActionType.MING_GANG.value, types)

    def test_three_real_allows_ming_gang(self):
        hand = [
            "5m",
            "5m",
            "5m",
            "1s",
            "2s",
            "3s",
            "4s",
            "5s",
            "6s",
            "7s",
            "8s",
            "9s",
            "1p",
        ]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=[],
            discarded_tile="5m",
            provider_seat="S",
            player_seat="E",
            dealer_tile="7p",
        )
        self.assertIn(ActionType.MING_GANG.value, _types(actions))
        self.assertIn(ActionType.PONG.value, _types(actions))


class TestChiNoJokerWildcard(unittest.TestCase):
    def test_cannot_chi_with_joker_fill(self):
        # 得=5s；手中 3s + 得，打出 4s — 不得用得当 5s 吃
        hand = [
            "3s",
            "5s",  # 得
            "1m",
            "2m",
            "3m",
            "4m",
            "5m",
            "6m",
            "7m",
            "8m",
            "9m",
            "1p",
            "2p",
        ]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=[],
            discarded_tile="4s",
            provider_seat="N",
            player_seat="E",
            dealer_tile="5s",
        )
        self.assertNotIn(ActionType.CHI.value, _types(actions))

    def test_whiteboard_can_chi_as_substitute(self):
        # 得=5s；手中 3s + 白板(P→5s)，打出 4s → 可吃
        hand = [
            "3s",
            "P",
            "1m",
            "2m",
            "3m",
            "4m",
            "5m",
            "6m",
            "7m",
            "8m",
            "9m",
            "1p",
            "2p",
        ]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=[],
            discarded_tile="4s",
            provider_seat="N",
            player_seat="E",
            dealer_tile="5s",
        )
        chi = [a for a in actions if a.action_type == ActionType.CHI]
        self.assertTrue(chi)


class TestRonAndPass(unittest.TestCase):
    def test_pass_always_present(self):
        actions = get_available_actions(
            hand_tiles=["1m"] * 13,
            melds=[],
            discarded_tile="9s",
            provider_seat="S",
            player_seat="E",
            dealer_tile="5m",
        )
        self.assertIn(ActionType.PASS.value, _types(actions))

    def test_ron_when_complete(self):
        # 三组副露 + 雀头听：手 1p1p，打出凑暗刻… 手 8p8p 听 8p
        melds = [
            Meld(meld_type=MeldType.CHI, tiles=["1m", "2m", "3m"]),
            Meld(meld_type=MeldType.CHI, tiles=["4m", "5m", "6m"]),
            Meld(meld_type=MeldType.CHI, tiles=["7m", "8m", "9m"]),
        ]
        hand = ["8p", "8p", "2s", "2s"]  # 听 2s 或暗刻？ 2s2s + 8p8p 需要第三面子
        # 正确听牌：门清只需 1 面子+雀头 → 4 张。8p8p 2s2s 胡 2s → 刻+雀
        hand = ["8p", "8p", "2s", "2s"]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=melds,
            discarded_tile="2s",
            provider_seat="S",
            player_seat="E",
            dealer_tile="5m",
        )
        self.assertIn(ActionType.HU.value, _types(actions))


if __name__ == "__main__":
    unittest.main()
