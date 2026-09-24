"""副露 vs 过牌 EV 权衡单测。"""

from __future__ import annotations

import unittest

from app.core.action_generator import (
    Action,
    ActionType,
    get_available_actions,
)
from app.core.call_decision import _pong_yakuhai_fan, evaluate_call_decision
from app.schemas import Meld, MeldType, PlayerState


class TestHuPriority(unittest.TestCase):
    def test_hu_recommended_immediately(self):
        melds = [
            Meld(meld_type=MeldType.CHI, tiles=["1m", "2m", "3m"]),
            Meld(meld_type=MeldType.CHI, tiles=["4m", "5m", "6m"]),
            Meld(meld_type=MeldType.CHI, tiles=["7m", "8m", "9m"]),
        ]
        hand = ["8p", "8p", "2s", "2s"]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=melds,
            discarded_tile="2s",
            provider_seat="S",
            player_seat="E",
            dealer_tile="5m",
        )
        decision = evaluate_call_decision(
            available_actions=actions,
            hand_tiles=hand,
            melds=melds,
            opponents=[],
            dealer_tile="5m",
            seat_wind="E",
            round_wind="E",
            is_dealer=False,
            discarded_tile="2s",
        )
        self.assertEqual(
            decision.recommended_action.action_type, ActionType.HU
        )
        self.assertIn("捉铳", decision.reason)

    def test_early_heavy_suit_can_pass_instead_of_forced_ron(self):
        """早巡 9 张主色、两张杂色时显式比较 HU/PASS，允许保留染手路线。"""
        hand = ["1m"] * 3 + ["2m"] * 3 + ["3m"] * 3 + ["1p", "3p", "W", "W"]
        opponents = [
            PlayerState(seat_wind="E", is_dealer=True, discards=["2p"]),
            PlayerState(seat_wind="S", discards=["9s"]),
            PlayerState(seat_wind="W", discards=["1s"]),
        ]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=[],
            discarded_tile="2p",
            provider_seat="E",
            player_seat="N",
            dealer_tile="5s",
        )
        self.assertEqual(
            {a.action_type for a in actions}, {ActionType.HU, ActionType.PASS}
        )

        decision = evaluate_call_decision(
            available_actions=actions,
            hand_tiles=hand,
            melds=[],
            opponents=opponents,
            dealer_tile="5s",
            seat_wind="N",
            round_wind="E",
            is_dealer=False,
            discarded_tile="2p",
            discarded_tiles=["2p", "9s", "1s"],
            turn_count=1,
        )
        self.assertIsNotNone(decision.hu_ev)
        self.assertIsNotNone(decision.pass_ev)
        self.assertGreater(decision.pass_ev, decision.hu_ev)
        self.assertEqual(decision.recommended_action.action_type, ActionType.PASS)
        data = decision.to_dict()
        self.assertGreater(data["pass_ev"], data["hu_ev"])
        self.assertIn("早巡", data["reason"])

    def test_off_suit_chi_is_rejected_for_deep_single_suit_hand(self):
        hand = ["1m"] * 3 + ["2m"] * 3 + ["3m"] * 3 + ["1p", "3p", "W", "W"]
        chi = Action(
            action_type=ActionType.CHI,
            tiles=["1p", "2p", "3p"],
            provider_seat="E",
        )
        passed = Action(action_type=ActionType.PASS, tiles=[], provider_seat="E")
        decision = evaluate_call_decision(
            available_actions=[chi, passed],
            hand_tiles=hand,
            melds=[],
            opponents=[PlayerState(seat_wind=w, discards=["2p"]) for w in ("E", "S", "W")],
            dealer_tile="5s",
            seat_wind="N",
            round_wind="E",
            is_dealer=False,
            discarded_tile="2p",
            turn_count=1,
        )
        by_type = {c.action.action_type: c for c in decision.candidates}
        self.assertEqual(decision.recommended_action.action_type, ActionType.PASS)
        self.assertEqual(by_type[ActionType.CHI].net_ev, float("-inf"))
        self.assertIn("破坏混一色/清一色", by_type[ActionType.CHI].note)


class TestPassVsCallEv(unittest.TestCase):
    def test_pong_fan_respects_dragons_seat_and_round_wind(self):
        self.assertEqual(_pong_yakuhai_fan("C", "N", "W", "E"), 1)
        self.assertEqual(_pong_yakuhai_fan("F", "N", "W", "E"), 1)
        self.assertEqual(_pong_yakuhai_fan("P", "N", "W", "E"), 1)
        self.assertEqual(_pong_yakuhai_fan("W", "N", "W", "E"), 1)
        self.assertEqual(_pong_yakuhai_fan("E", "N", "W", "E"), 1)
        self.assertEqual(_pong_yakuhai_fan("E", "N", "W", "S"), 0)
        self.assertEqual(_pong_yakuhai_fan("W", "N", "W", "W"), 2)

    def test_red_dragon_pong_beats_pass_with_north_as_dealer_tile(self):
        """西风持中对子、得为北风时，碰中锁定明刻与三元番。"""
        hand = [
            "1p", "4p", "5p", "5p", "2s", "3s", "5s",
            "7s", "8s", "9s", "E", "C", "C",
        ]
        actions = get_available_actions(
            hand_tiles=hand, melds=[], discarded_tile="C",
            provider_seat="E", player_seat="W", dealer_tile="N",
        )
        decision = evaluate_call_decision(
            available_actions=actions, hand_tiles=hand, melds=[],
            opponents=[PlayerState(seat_wind="E", is_dealer=True, discards=["C"])],
            dealer_tile="N", seat_wind="W", round_wind="E",
            is_dealer=False, discarded_tile="C", discarded_tiles=["C"],
        )
        scores = {c.action.action_type: c.net_ev for c in decision.candidates}
        self.assertGreater(scores[ActionType.PONG], scores[ActionType.PASS] + 10)
        self.assertEqual(decision.recommended_action.action_type, ActionType.PONG)
        self.assertIn("碰牌锁定红中明刻(+4底胡，+1番翻倍)", decision.reason)

    def test_pass_preferred_when_chi_cannot_apply(self):
        """非法/无法落地的吃对比过牌 → PASS 胜出并给出门清理由。"""
        hand = ["1m"] * 13
        actions = [
            Action(
                action_type=ActionType.CHI,
                tiles=["2s", "3s", "4s"],
                provider_seat="N",
            ),
            Action(
                action_type=ActionType.PASS,
                tiles=[],
                provider_seat="N",
            ),
        ]
        decision = evaluate_call_decision(
            available_actions=actions,
            hand_tiles=hand,
            melds=[],
            opponents=[],
            dealer_tile="9p",
            seat_wind="E",
            round_wind="E",
            is_dealer=False,
            discarded_tile="4s",
        )
        self.assertEqual(
            decision.recommended_action.action_type, ActionType.PASS
        )
        self.assertIn("过牌", decision.reason)
        by_type = {c.action.action_type: c.net_ev for c in decision.candidates}
        self.assertGreater(by_type[ActionType.PASS], by_type[ActionType.CHI])

    def test_pong_terminal_beats_pass_on_scattered_hand(self):
        """散牌三向听：下家切 1s，碰幺九刻并切客风北，应优于过牌。"""
        hand = [
            "4m",
            "5m",
            "7m",
            "8m",
            "1p",
            "2p",
            "4p",
            "1s",
            "1s",
            "3s",
            "5s",
            "7s",
            "N",
        ]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=[],
            discarded_tile="1s",
            provider_seat="S",
            player_seat="E",
            dealer_tile="5p",
        )
        decision = evaluate_call_decision(
            available_actions=actions,
            hand_tiles=hand,
            melds=[],
            opponents=[],
            dealer_tile="5p",
            seat_wind="E",
            round_wind="E",
            is_dealer=True,
            discarded_tile="1s",
            discarded_tiles=["1s"],
        )
        self.assertEqual(
            decision.recommended_action.action_type, ActionType.PONG
        )
        by_type = {c.action.action_type: c.net_ev for c in decision.candidates}
        self.assertGreater(by_type[ActionType.PONG], by_type[ActionType.PASS])
        self.assertIn("幺九刻", decision.reason)
        self.assertIn("北", decision.reason)
        pong_c = next(
            c
            for c in decision.candidates
            if c.action.action_type == ActionType.PONG
        )
        self.assertIn("加快做牌", pong_c.note)

    def test_pong_vs_pass_picks_higher_ev(self):
        """碰与过牌均评分，推荐净 EV 更大者。"""
        melds = [
            Meld(meld_type=MeldType.CHI, tiles=["1p", "2p", "3p"]),
            Meld(meld_type=MeldType.CHI, tiles=["4p", "5p", "6p"]),
        ]
        hand = ["5m", "5m", "7m", "8m", "9m", "2s", "3s"]
        actions = get_available_actions(
            hand_tiles=hand,
            melds=melds,
            discarded_tile="5m",
            provider_seat="S",
            player_seat="E",
            dealer_tile="1s",
        )
        self.assertIn(ActionType.PONG, {a.action_type for a in actions})
        self.assertNotIn(ActionType.HU, {a.action_type for a in actions})

        decision = evaluate_call_decision(
            available_actions=actions,
            hand_tiles=hand,
            melds=melds,
            opponents=[],
            dealer_tile="1s",
            seat_wind="E",
            round_wind="E",
            is_dealer=False,
            discarded_tile="5m",
        )
        finite = {
            c.action.action_type: c.net_ev
            for c in decision.candidates
            if c.net_ev > float("-inf")
        }
        self.assertIn(ActionType.PONG, finite)
        self.assertIn(ActionType.PASS, finite)
        best_type = max(finite, key=lambda k: finite[k])
        self.assertEqual(
            decision.recommended_action.action_type, best_type
        )
        # 碰后明刻 vs 过牌：至少完成了双边评估
        pong_c = next(
            c for c in decision.candidates if c.action.action_type == ActionType.PONG
        )
        self.assertIn("副露后最优切", pong_c.note)


class TestRedundantSequenceChi(unittest.TestCase):
    """手持完整 567s 时上家切 5s：必须过牌，严禁推荐吃。"""

    def test_pass_beats_redundant_567s_chi(self):
        hand = [
            "9m",
            "9m",
            "2p",
            "6p",
            "7p",
            "5s",
            "6s",
            "7s",
            "9s",
            "F",
        ]
        melds = [Meld(meld_type=MeldType.PONG, tiles=["E", "E", "E"])]
        dealer = "5m"
        actions = get_available_actions(
            hand_tiles=hand,
            melds=melds,
            discarded_tile="5s",
            provider_seat="N",
            player_seat="E",
            dealer_tile=dealer,
        )
        self.assertIn(ActionType.CHI, {a.action_type for a in actions})
        self.assertIn(ActionType.PASS, {a.action_type for a in actions})

        decision = evaluate_call_decision(
            available_actions=actions,
            hand_tiles=hand,
            melds=melds,
            opponents=[
                PlayerState(seat_wind="S"),
                PlayerState(seat_wind="W"),
                PlayerState(seat_wind="N", discards=["5s"]),
            ],
            dealer_tile=dealer,
            seat_wind="E",
            round_wind="E",
            is_dealer=False,
            discarded_tile="5s",
        )
        self.assertEqual(
            decision.recommended_action.action_type, ActionType.PASS
        )
        self.assertIn("过牌", decision.reason)
        self.assertIn("完整", decision.reason)
        by = {c.action.action_type: c for c in decision.candidates}
        self.assertGreater(by[ActionType.PASS].net_ev, by[ActionType.CHI].net_ev)
        self.assertIn("已持有完整", by[ActionType.CHI].note)


if __name__ == "__main__":
    unittest.main()
