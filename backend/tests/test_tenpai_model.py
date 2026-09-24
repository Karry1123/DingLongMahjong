"""对手听牌概率：巡目先验 + 弃牌河中张贝叶斯修正。"""

from __future__ import annotations

import unittest

from app.core.tenpai_model import (
    _base_tenpai_prob,
    _closed_prior,
    estimate_opponents_tenpai,
    estimate_tenpai_probability,
)
from app.schemas import Meld, MeldType, PlayerState


def _pong(tile: str) -> Meld:
    return Meld(meld_type=MeldType.PONG, tiles=[tile, tile, tile])


class TestClosedPriorCurve(unittest.TestCase):
    def test_early_turns_in_3_to_8_percent_band(self):
        # 门清 1~6 巡基础先验约 3%~8%
        for t in range(1, 7):
            p = _closed_prior(t)
            self.assertGreaterEqual(p, 0.03 - 1e-9, msg=f"turn={t}")
            self.assertLessEqual(p, 0.09 + 1e-9, msg=f"turn={t}")

    def test_mid_turns_rise(self):
        p6 = _closed_prior(6)
        p9 = _closed_prior(9)
        p11 = _closed_prior(11)
        self.assertGreater(p9, p6)
        self.assertGreater(p11, p9)
        # 中巡门清自然抬升到约 15%~30% 量级
        self.assertGreaterEqual(p9, 0.12)
        self.assertLessEqual(p11, 0.35)

    def test_monotonic_in_turn(self):
        prev = _closed_prior(0)
        for t in range(1, 19):
            cur = _closed_prior(t)
            self.assertGreaterEqual(cur, prev)
            prev = cur


class TestAcceptanceA_EarlyHonorTerminals(unittest.TestCase):
    """测试 A：开局第 3 巡，门清全打字牌+幺九 → 听牌率 < 6%。"""

    def test_early_safe_discards_stay_low(self):
        opp = PlayerState(
            seat_wind="S",
            is_dealer=False,
            discards=["E", "1m", "9s"],
            melds=[],
        )
        p = estimate_tenpai_probability(opp, turn_count=3)
        self.assertLess(p, 0.06)
        self.assertGreaterEqual(p, 0.02)


class TestAcceptanceB_CentralTileCuts(unittest.TestCase):
    """测试 B：第 5 巡切 5m、第 6 巡切 4s → 听牌率抬至 18%~28%+。"""

    def test_central_cuts_raise_tenpai(self):
        # 前序字牌/幺九，再连续主动中张
        discards = ["W", "N", "1p", "9m", "5m", "4s"]
        opp = PlayerState(
            seat_wind="W",
            is_dealer=False,
            discards=discards,
            melds=[],
        )
        # rem 充足 → 非跟打绝张
        rem = {t: 3 for t in ("5m", "4s", "W", "N", "1p", "9m")}
        p = estimate_tenpai_probability(
            opp, turn_count=6, rem_pool=rem
        )
        self.assertGreaterEqual(p, 0.18)
        self.assertLessEqual(p, 0.95)


class TestMeldAndDealer(unittest.TestCase):
    def test_melds_raise_above_closed(self):
        closed = PlayerState(
            seat_wind="S", discards=["1m"] * 6, melds=[]
        )
        one = PlayerState(
            seat_wind="W",
            discards=["1m"] * 6,
            melds=[_pong("9s")],
        )
        pc = estimate_tenpai_probability(closed)
        po = estimate_tenpai_probability(one)
        self.assertGreater(po, pc)

    def test_dealer_boost(self):
        common = dict(seat_wind="E", discards=["1m"] * 6, melds=[])
        plain = PlayerState(**common, is_dealer=False)
        dealer = PlayerState(**common, is_dealer=True)
        self.assertGreater(
            estimate_tenpai_probability(dealer),
            estimate_tenpai_probability(plain),
        )

    def test_probability_clamped(self):
        opp = PlayerState(
            seat_wind="N",
            is_dealer=True,
            discards=["E"] * 4 + ["5m", "4p", "6s", "5s"],
            melds=[_pong("9s"), _pong("1s"), _pong("9m")],
        )
        rem = {t: 3 for t in ("5m", "4p", "6s", "5s")}
        p = estimate_tenpai_probability(opp, rem_pool=rem)
        self.assertGreaterEqual(p, 0.02)
        self.assertLessEqual(p, 0.95)


class TestGenbutsuCentralIgnored(unittest.TestCase):
    def test_dead_central_not_boosted_like_active(self):
        discards = ["W", "N", "1p", "9m", "5m", "4s"]
        opp = PlayerState(seat_wind="S", discards=discards, melds=[])
        rem_dead = {"5m": 0, "4s": 0, "W": 2, "N": 2, "1p": 2, "9m": 2}
        rem_live = {"5m": 3, "4s": 3, "W": 2, "N": 2, "1p": 2, "9m": 2}
        p_dead = estimate_tenpai_probability(opp, rem_pool=rem_dead)
        p_live = estimate_tenpai_probability(opp, rem_pool=rem_live)
        self.assertGreater(p_live, p_dead)


class TestMultiOpponents(unittest.TestCase):
    def test_returns_all_seat_keys_and_linkage_shape(self):
        ops = [
            PlayerState(seat_wind="S", discards=["E", "1m", "9s"]),
            PlayerState(
                seat_wind="W",
                discards=["W", "N", "1p", "9m", "5m", "4s"],
                melds=[],
            ),
            PlayerState(
                seat_wind="N",
                discards=["1m"] * 8,
                melds=[_pong("2s"), _pong("3s")],
            ),
        ]
        rem = {"5m": 3, "4s": 3}
        result = estimate_opponents_tenpai(
            ops, dealer_tile="7p", rem_map=rem
        )
        self.assertEqual(set(result.keys()), {"S", "W", "N"})
        self.assertLess(result["S"], result["W"])
        for v in result.values():
            self.assertGreaterEqual(v, 0.02)
            self.assertLessEqual(v, 0.95)

    def test_base_helper_still_exported(self):
        # 兼容旧测试导入路径：_base_tenpai_prob(turn, melds=0)
        p = _base_tenpai_prob(6, 0)
        self.assertAlmostEqual(p, _closed_prior(6), places=6)


if __name__ == "__main__":
    unittest.main()
