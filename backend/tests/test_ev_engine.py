"""EV 引擎：真实计分进攻 + 无包牌防守。"""

from __future__ import annotations

import unittest

from app.core.ev_engine import (
    _is_completed_sequence_surplus,
    _estimate_opponent_hu_points,
    _payment_loss,
    calculate_best_discards,
)
from app.core.scoring import calculate_hu_points
from app.schemas import Meld, MeldType, PlayerState


def _m(meld_type: MeldType, tiles: list[str]) -> Meld:
    return Meld(meld_type=meld_type, tiles=tiles)


class TestJokerDragonSequenceOverlap(unittest.TestCase):
    def test_cut_surplus_four_sou_instead_of_live_green_dragon(self):
        melds = [
            _m(MeldType.CHI, ["1p", "2p", "3p"]),
            _m(MeldType.CHI, ["5m", "6m", "7m"]),
        ]
        hand = ["P", "1m", "3m", "2s", "3s", "4s", "4s", "F"]
        opponents = [
            PlayerState(seat_wind="E", is_dealer=True),
            PlayerState(seat_wind="S"),
            PlayerState(seat_wind="W"),
        ]
        result = calculate_best_discards(
            hand_tiles=hand, dealer_tile="P", is_dealer=False,
            seat_wind="N", round_wind="E", melds=melds,
            opponents=opponents, include_self_gang=False,
        )
        by_tile = {c["tile"]: c for c in result["candidates"]}
        self.assertEqual(result["best_tile"], "4s")
        self.assertIn("4s", by_tile)
        self.assertIn("F", by_tile)
        self.assertEqual(by_tile["4s"]["shanten"], 0)
        self.assertGreater(by_tile["4s"]["ev_score"], by_tile["F"]["ev_score"])
        self.assertGreater(by_tile["4s"]["est_final_points"], by_tile["F"]["est_final_points"])
        self.assertIn("锁定完整顺子", by_tile["4s"]["note"])
        self.assertIn("三元番潜力", by_tile["4s"]["note"])
        self.assertFalse(by_tile["F"]["is_safe_all"])

    def test_surplus_needs_complete_sequence_and_alternate_head(self):
        self.assertTrue(_is_completed_sequence_surplus(
            "5s", ["3s", "4s", "5s", "5s", "P", "F"], "P"))
        self.assertFalse(_is_completed_sequence_surplus(
            "5s", ["3s", "5s", "5s", "P", "F"], "P"))
        self.assertFalse(_is_completed_sequence_surplus(
            "5s", ["3s", "4s", "5s", "5s"], "P"))

    def test_overlapping_445_taatsu_keeps_the_complete_sequence_and_head(self):
        melds = [
            _m(MeldType.CHI, ["2s", "P", "4s"]),  # P substitutes 3s
            _m(MeldType.PONG, ["9s"] * 3),
        ]
        hand = ["1m", "1m", "2m", "3m", "4m", "4p", "5p", "4p"]
        result = calculate_best_discards(
            hand, dealer_tile="3s", is_dealer=False, seat_wind="E",
            melds=melds, include_self_gang=False,
        )
        by_tile = {c["tile"]: c for c in result["candidates"]}
        self.assertEqual(result["best_tile"], "4p")
        self.assertGreater(by_tile["4p"]["ev_score"], by_tile["5p"]["ev_score"])
        self.assertGreater(by_tile["5p"]["ev_score"], by_tile["1m"]["ev_score"])
        self.assertEqual(by_tile["4p"]["shanten"], 0)
        self.assertEqual(by_tile["1m"]["shanten"], 1)
        self.assertGreater(by_tile["4p"]["effective_count"], by_tile["5p"]["effective_count"])


class TestEvUsesRealScoring(unittest.TestCase):
    """打九筒案例：进张胡数须与 calculate_hu_points 一致。"""

    def setUp(self):
        self.melds = [
            _m(MeldType.PONG, ["1m"] * 3),
            _m(MeldType.CHI, ["1m", "2m", "3m"]),
            _m(MeldType.CHI, ["2m", "3m", "4m"]),
        ]
        self.hand = ["1p", "1p", "4p", "4p", "9p"]

    def test_discard_9p_matches_scoring_module(self):
        result = calculate_best_discards(
            hand_tiles=self.hand,
            dealer_tile="5m",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=[],
            melds=self.melds,
            opponents=[],
        )
        c9 = next(c for c in result["candidates"] if c["tile"] == "9p")

        remain = ["1p", "1p", "4p", "4p"]
        h1 = calculate_hu_points(
            self.melds, remain, "1p", True, "E", "5m"
        )
        h4 = calculate_hu_points(
            self.melds, remain, "4p", True, "E", "5m"
        )
        h5 = calculate_hu_points(
            self.melds, remain, "5m", True, "E", "5m"
        )

        expected_final = round(
            (2 * h1["final_hu"] + 2 * h4["final_hu"] + 3 * h5["final_hu"]) / 7
        )
        expected_base = round(
            (
                2 * (h1["tile_hu"] + h1["base_hu"])
                + 2 * (h4["tile_hu"] + h4["base_hu"])
                + 3 * (h5["tile_hu"] + h5["base_hu"])
            )
            / 7
        )

        self.assertEqual(c9["est_final_points"], expected_final)
        self.assertEqual(c9["est_base_points"], expected_base)
        self.assertEqual(h1["final_hu"], 48)
        self.assertEqual(h4["final_hu"], 40)
        self.assertTrue(c9["is_hard_hu"])
        self.assertEqual(c9["defense_loss"], 0.0)
        self.assertAlmostEqual(c9["ev_score"], c9["attack_ev"], places=4)
        self.assertTrue(c9["is_safe_all"])

    def test_tenpai_beats_iishanten_on_44558_hand(self):
        """444 + 白(替5) + 888 + 9：切 9 听牌，切 8 一向听；应推荐 9m。"""
        hand = ["4m", "4m", "4m", "P", "8m", "8m", "8m", "9m"]
        melds = [
            _m(MeldType.MING_GANG, ["1m"] * 4),
            _m(MeldType.AN_GANG, ["S"] * 4),
        ]
        for is_dealer in (False, True):
            result = calculate_best_discards(
                hand_tiles=hand,
                dealer_tile="5m",
                is_dealer=is_dealer,
                seat_wind="E",
                discarded_tiles=[],
                melds=melds,
                opponents=[],
                include_self_gang=False,
            )
            self.assertEqual(
                result["best_tile"],
                "9m",
                f"庄={is_dealer} 时应切九万听牌，实际 {result['best_tile']}",
            )
            by_tile = {c["tile"]: c for c in result["candidates"]}
            self.assertGreater(
                by_tile["9m"]["ev_score"],
                by_tile["8m"]["ev_score"],
            )
        melds = [
            _m(MeldType.CHI, ["1m", "2m", "3m"]),
            _m(MeldType.CHI, ["4m", "5m", "6m"]),
            _m(MeldType.CHI, ["7m", "8m", "9m"]),
        ]
        hand = ["2p", "2p", "3p", "3p", "5s"]
        result = calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="9p",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=[],
            melds=melds,
        )
        self.assertEqual(result["best_tile"], "5s")
        best = result["candidates"][0]
        self.assertTrue(best["is_hard_hu"])
        self.assertGreater(best["est_final_points"], 0)
        self.assertIn("attack_ev", best)
        self.assertIn("deal_in_risks", best)

    def test_dealer_settlement_triples_income_component(self):
        common = dict(
            hand_tiles=self.hand,
            dealer_tile="5m",
            seat_wind="E",
            discarded_tiles=[],
            melds=self.melds,
            opponents=[],
        )
        xian = calculate_best_discards(is_dealer=False, **common)
        zhuang = calculate_best_discards(is_dealer=True, **common)
        c_x = next(c for c in xian["candidates"] if c["tile"] == "9p")
        c_z = next(c for c in zhuang["candidates"] if c["tile"] == "9p")
        self.assertAlmostEqual(
            c_z["attack_ev"] / c_x["attack_ev"], 1.5, places=4
        )
        self.assertEqual(c_x["est_final_points"], c_z["est_final_points"])


class TestDeepShantenHonorPriority(unittest.TestCase):
    """开局多向听：优先切无役客风，勿拆 2m 对子/搭子。"""

    def test_prefer_guest_north_over_breaking_2m(self):
        # 得=6m，门风东；手含 2m2m3m 复合搭 + 北/中/发
        hand = [
            "6m",
            "2m",
            "2m",
            "3p",
            "4p",
            "8p",
            "1s",
            "3s",
            "7s",
            "9s",
            "N",
            "C",
            "F",
            "3m",
        ]
        result = calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="6m",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=[],
            melds=[],
            opponents=[],
            include_self_gang=False,
        )
        self.assertEqual(result["best_tile"], "N")
        by_tile = {c["tile"]: c for c in result["candidates"]}
        # 客风应优于拆 2m；2m 若因无其它废牌进入候选，EV 也须更低
        self.assertIn("N", by_tile)
        if "2m" in by_tile:
            self.assertGreater(by_tile["N"]["ev_score"], by_tile["2m"]["ev_score"])
        note = by_tile["N"].get("note") or ""
        self.assertIn("无役客风", note)
        self.assertIn("役牌", note)

    def test_dead_seat_wind_beats_terminal_9s(self):
        """北风位：河上已见 2 张北 → Rem(N)=1 绝张，必须优于切九条。"""
        hand = [
            "1m",
            "2m",
            "4m",
            "4m",
            "5m",
            "3p",
            "6p",
            "7p",
            "6s",
            "N",
            "C",
            "F",
            "F",
            "9s",
        ]
        opponents = [
            PlayerState(seat_wind="E", discards=[]),
            PlayerState(seat_wind="S", discards=["N"]),  # 对家
            PlayerState(seat_wind="W", discards=["N"]),  # 下家
        ]
        discarded = ["N", "N"]
        result = calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="5p",
            is_dealer=False,
            seat_wind="N",
            discarded_tiles=discarded,
            melds=[],
            opponents=opponents,
            include_self_gang=False,
        )
        self.assertEqual(
            result["best_tile"],
            "N",
            f"绝张北风应优先于九条，实际推荐 {result['best_tile']}",
        )
        by = {c["tile"]: c for c in result["candidates"]}
        self.assertGreater(by["N"]["ev_score"], by["9s"]["ev_score"])
        note = by["N"].get("note") or ""
        self.assertIn("绝张", note)
        self.assertIn("北风", note)
        self.assertIn("9s", note)
        self.assertIn("死废牌", note)


class TestEvPerformanceJokerHand(unittest.TestCase):
    """规整带「得」手牌：候选剪枝后须在 300ms 内出推荐。"""

    def test_structured_joker_hand_under_300ms(self):
        hand = [
            "S",
            "3m",
            "4m",
            "5m",
            "8m",
            "7p",
            "9p",
            "3s",
            "4s",
            "5s",
            "N",
            "N",
            "F",
            "F",
        ]
        import time

        from app.core.evaluator import clear_shanten_cache

        clear_shanten_cache()
        t0 = time.perf_counter()
        result = calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="S",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=[],
            melds=[],
            opponents=[],
            include_self_gang=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertLess(
            elapsed_ms,
            300.0,
            f"EV 耗时 {elapsed_ms:.1f}ms，超过 300ms 上限",
        )
        self.assertIn(result["best_tile"], {"8m", "7p", "9p"})
        self.assertLessEqual(len(result["candidates"]), 5)
        self.assertNotIn("S", [c["tile"] for c in result["candidates"]])


    def test_floating_isolates_must_include_f_and_9p(self):
        """摸 3p 后：F/9p 必进候选；不得因剪枝漏选而强推切 6p。"""
        import time

        from app.core.evaluator import clear_shanten_cache

        hand = [
            "2m",
            "3m",
            "3m",
            "6m",
            "8m",
            "1p",
            "6p",
            "9p",
            "4s",
            "4s",
            "9s",
            "9s",
            "F",
            "3p",
        ]
        clear_shanten_cache()
        # 预热向听缓存后计量（冷启动含大量首次拆解）
        calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="5m",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=[],
            melds=[],
            opponents=[],
            include_self_gang=False,
        )
        t0 = time.perf_counter()
        result = calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="5m",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=[],
            melds=[],
            opponents=[],
            include_self_gang=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        tiles = [c["tile"] for c in result["candidates"]]
        self.assertIn("F", tiles, f"候选漏选发财：{tiles}")
        self.assertIn("9p", tiles, f"候选漏选九筒：{tiles}")
        by = {c["tile"]: c for c in result["candidates"]}
        # 切 6p / F / 9p 向听应同档（均为正确拆解下的同一向听）
        self.assertEqual(by["6p"]["shanten"], by["F"]["shanten"])
        self.assertEqual(by["6p"]["shanten"], by["9p"]["shanten"])
        # 推荐应为漂浮孤张，而非拆嵌张端点去「刷假进张」
        self.assertIn(result["best_tile"], {"F", "9p", "6p"})
        self.assertLess(elapsed_ms, 500.0, f"耗时 {elapsed_ms:.1f}ms")


class TestJantouProtectionVsIsolated(unittest.TestCase):
    """好形暗刻+两面×2+雀头：必须切纯孤张 5s，严禁拆 7s 雀头。"""

    def test_cut_5s_not_break_7s_pair(self):
        hand = [
            "4m",
            "5m",
            "8m",
            "8m",
            "8m",
            "4p",
            "5p",
            "7s",
            "7s",
            "C",
            "5s",
        ]
        melds = [_m(MeldType.CHI, ["7s", "8s", "9s"])]
        # 7s 现物安全、5s 生张中张 → 曾被防守差值逆转
        opponents = [
            PlayerState(seat_wind="S", discards=["7s", "2m", "9p"]),
            PlayerState(seat_wind="W", discards=["3p", "9m"]),
            PlayerState(seat_wind="N", discards=["1p", "2p"]),
        ]
        discarded = ["7s", "2m", "9p", "3p", "9m", "1p", "2p"]
        result = calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="1m",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=discarded,
            melds=melds,
            opponents=opponents,
            include_self_gang=False,
        )
        self.assertEqual(result["best_tile"], "5s")
        by = {c["tile"]: c for c in result["candidates"]}
        # 即使雀头进入候选，净 EV 也必须显著低于孤张 5s
        if "7s" in by:
            self.assertGreater(by["5s"]["ev_score"] - by["7s"]["ev_score"], 10.0)
        self.assertIn("孤张", by["5s"].get("note") or "")


class TestDefenseNoBao(unittest.TestCase):
    def test_genbutsu_safe_all_and_zero_risk(self):
        """三家均打过的现物：is_safe_all，放铳率全 0。"""
        melds = [
            _m(MeldType.CHI, ["1m", "2m", "3m"]),
            _m(MeldType.CHI, ["4m", "5m", "6m"]),
            _m(MeldType.CHI, ["7m", "8m", "9m"]),
        ]
        hand = ["2p", "2p", "3p", "3p", "5s"]
        opponents = [
            PlayerState(seat_wind="S", discards=["5s", "1p"]),
            PlayerState(seat_wind="W", discards=["5s", "9p"]),
            PlayerState(seat_wind="N", discards=["5s"]),
        ]
        result = calculate_best_discards(
            hand_tiles=hand,
            dealer_tile="9s",
            is_dealer=False,
            seat_wind="E",
            discarded_tiles=["5s", "5s", "5s", "1p", "9p"],
            melds=melds,
            opponents=opponents,
        )
        c5 = next(c for c in result["candidates"] if c["tile"] == "5s")
        self.assertTrue(c5["is_safe_all"])
        self.assertEqual(c5["deal_in_risks"]["S"], 0.0)
        self.assertEqual(c5["deal_in_risks"]["W"], 0.0)
        self.assertEqual(c5["deal_in_risks"]["N"], 0.0)
        self.assertEqual(c5["defense_loss"], 0.0)

    def test_payment_loss_half_for_xian_vs_xian(self):
        self.assertEqual(_payment_loss(40, False, False), 20.0)
        self.assertEqual(_payment_loss(40, True, False), 40.0)
        self.assertEqual(_payment_loss(40, False, True), 40.0)

    def test_opponent_est_points_yakuhai_fan(self):
        opp = PlayerState(
            seat_wind="E",
            is_dealer=False,
            melds=[_m(MeldType.PONG, ["C", "C", "C"])],
        )
        ron, zimo = _estimate_opponent_hu_points(opp, "5m")
        # 明刻字 4 + 底 10，翻 1 → 14*2=28；自摸 +2 → 16*2=32
        self.assertEqual(ron, 28.0)
        self.assertEqual(zimo, 32.0)


class TestUkeireEightPinVsFiveSou(unittest.TestCase):
    """双得听牌：须切偏张 8p、保留核心中张 5s（非微差切 5s）。"""

    def setUp(self):
        self.hand = ["2m", "2m", "5m", "7m", "8p", "5s", "W", "W"]
        self.melds = [
            _m(MeldType.PONG, ["N", "N", "N"]),
            _m(MeldType.PONG, ["1m", "1m", "1m"]),
        ]
        self.dealer = "2m"

    def test_prefer_cut_8p_keep_central_5s(self):
        result = calculate_best_discards(
            hand_tiles=self.hand,
            dealer_tile=self.dealer,
            is_dealer=False,
            seat_wind="S",
            discarded_tiles=[],
            melds=self.melds,
            opponents=[
                PlayerState(seat_wind="E", is_dealer=True),
                PlayerState(seat_wind="W"),
                PlayerState(seat_wind="N"),
            ],
        )
        self.assertEqual(result["best_tile"], "8p")
        by = {c["tile"]: c for c in result["candidates"]}
        c8 = by["8p"]
        c5 = by["5s"]
        self.assertEqual(c8["effective_count"], 26)
        self.assertEqual(c5["effective_count"], 22)
        self.assertGreater(c8["ev_score"], c5["ev_score"])
        self.assertIn("偏张", c8["note"])
        self.assertIn("5s", c8["note"])
        self.assertIn("得", c8["note"])

    def test_effective_tiles_diff_is_four(self):
        result = calculate_best_discards(
            hand_tiles=self.hand,
            dealer_tile=self.dealer,
            is_dealer=False,
            seat_wind="S",
            discarded_tiles=[],
            melds=self.melds,
            opponents=[
                PlayerState(seat_wind="E", is_dealer=True),
                PlayerState(seat_wind="W"),
                PlayerState(seat_wind="N"),
            ],
        )
        by = {c["tile"]: c for c in result["candidates"]}
        c8 = by["8p"]
        c5 = by["5s"]
        map8 = {x["tile"]: x["rem"] for x in c8["effective_tiles"]}
        map5 = {x["tile"]: x["rem"] for x in c5["effective_tiles"]}
        self.assertEqual(sum(map8.values()), 26)
        self.assertEqual(sum(map5.values()), 22)
        only8 = {k: map8[k] for k in map8 if k not in map5}
        only5 = {k: map5[k] for k in map5 if k not in map8}
        self.assertEqual(sum(only8.values()) - sum(only5.values()), 4)


class TestWhiteboardSubstituteVsSeenGuestWind(unittest.TestCase):
    """得=南：白板替身≡南，场见西应优先切西而非切白。"""

    def setUp(self):
        self.hand = [
            "4m",
            "1p",
            "4p",
            "7p",
            "8p",
            "5s",
            "7s",
            "7s",
            "9s",
            "P",
            "W",
            "C",
            "C",
            "3m",
        ]
        self.dealer = "S"
        self.opponents = [
            PlayerState(seat_wind="S", is_dealer=True, discards=["W"]),
            PlayerState(seat_wind="W"),
            PlayerState(seat_wind="N"),
        ]

    def test_prefer_cut_west_keep_whiteboard_substitute(self):
        for seat in ("E", "S"):
            with self.subTest(seat=seat):
                result = calculate_best_discards(
                    hand_tiles=self.hand,
                    dealer_tile=self.dealer,
                    is_dealer=False,
                    seat_wind=seat,
                    discarded_tiles=["W"],
                    melds=[],
                    opponents=self.opponents,
                )
                by = {c["tile"]: c for c in result["candidates"]}
                self.assertIn("W", by)
                self.assertIn("P", by)
                # 核心：场见客风西应明显优于切健康白板替身
                self.assertGreater(by["W"]["ev_score"], by["P"]["ev_score"])
                self.assertNotEqual(
                    result["best_tile"],
                    "P",
                    f"seat={seat} 不应切白板替身，实际 {result['best_tile']}",
                )
                # 若首推仍是西，理由须点出替身保护
                if result["best_tile"] == "W":
                    note = by["W"]["note"]
                    self.assertIn("西", note)
                    self.assertIn("白板", note)
                    self.assertIn("替身", note)

    def test_identity_supply_rem_uses_whiteboard(self):
        from app.core.ev_engine import _identity_supply_rem, _build_rem_map

        rem = _build_rem_map(self.hand, ["W"], [], self.dealer)
        # 身份南的供给只能来自白板，而非墙中得牌（百搭）
        self.assertEqual(_identity_supply_rem("S", self.dealer, rem), rem["P"])
        self.assertEqual(_identity_supply_rem("W", self.dealer, rem), rem["W"])


class TestOrphanTerminalOverWhiteboardSubstitute(unittest.TestCase):
    """得=西：白板≡西；无邻张九万应优先于切出健康白板替身。"""

    def setUp(self):
        self.hand = [
            "9m",
            "1p",
            "3p",
            "5p",
            "3s",
            "6s",
            "7s",
            "8s",
            "8s",
            "N",
            "P",
        ]
        self.dealer = "W"
        self.melds = [
            Meld(meld_type=MeldType.PONG, tiles=["9s", "9s", "9s"]),
        ]
        self.opponents = [
            PlayerState(seat_wind="E", is_dealer=True),
            PlayerState(seat_wind="S"),
            PlayerState(seat_wind="W"),
        ]

    def test_prefer_cut_9m_keep_whiteboard_as_west(self):
        result = calculate_best_discards(
            hand_tiles=self.hand,
            dealer_tile=self.dealer,
            is_dealer=False,
            seat_wind="N",
            discarded_tiles=[],
            melds=self.melds,
            opponents=self.opponents,
        )
        self.assertEqual(
            result["best_tile"],
            "9m",
            f"应切九万，实际 {result['best_tile']}",
        )
        by = {c["tile"]: c for c in result["candidates"]}
        self.assertIn("9m", by)
        self.assertIn("P", by)
        self.assertGreater(by["9m"]["ev_score"], by["P"]["ev_score"])
        note = by["9m"]["note"]
        self.assertIn("幺九", note)
        self.assertIn("白板", note)
        self.assertIn("西", note)


if __name__ == "__main__":
    unittest.main()
