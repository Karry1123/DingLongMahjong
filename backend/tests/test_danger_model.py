"""放铳率 estimate_tile_danger 单测。"""

from __future__ import annotations

import unittest

from app.core.danger_model import estimate_tile_danger
from app.core.pool_tracker import get_remaining_tiles
from app.schemas import HandRequest, Meld, MeldType, PlayerState


def _pong(tile: str) -> Meld:
    return Meld(meld_type=MeldType.PONG, tiles=[tile] * 3)


def _chi(*tiles: str) -> Meld:
    return Meld(meld_type=MeldType.CHI, tiles=list(tiles))


def _rem_full(dealer: str = "5s") -> dict[str, int]:
    """近似满壁：仅得公示占用。"""
    from app.core.constants import ALL_TILES

    rem = {t: 4 for t in ALL_TILES}
    rem[dealer] = 3
    return rem


class TestGenbutsuAndWall(unittest.TestCase):
    def test_genbutsu_zero(self):
        opp = PlayerState(seat_wind="S", discards=["5m", "E", "2p"])
        d = estimate_tile_danger("5m", opp, _rem_full(), "9s")
        self.assertEqual(d, 0.0)

    def test_exhausted_rem_zero(self):
        opp = PlayerState(seat_wind="S", discards=[])
        rem = _rem_full()
        rem["5m"] = 0
        d = estimate_tile_danger("5m", opp, rem, "9s")
        self.assertEqual(d, 0.0)


class TestFreshness(unittest.TestCase):
    def test_honor_live_vs_dead(self):
        opp = PlayerState(seat_wind="S")
        rem = _rem_full("5s")
        live = estimate_tile_danger("C", opp, rem, "5s")
        self.assertAlmostEqual(live, 0.16, places=5)

        rem_dead = dict(rem)
        rem_dead["C"] = 2  # 已见 2 张
        dead = estimate_tile_danger("C", opp, rem_dead, "5s")
        self.assertAlmostEqual(dead, 0.02, places=5)
        self.assertLess(dead, live)

    def test_mid_vs_terminal_base(self):
        opp = PlayerState(seat_wind="S")
        rem = _rem_full()
        mid = estimate_tile_danger("5p", opp, rem, "9s")
        terminal = estimate_tile_danger("1p", opp, rem, "9s")
        self.assertAlmostEqual(mid, 0.18, places=5)
        self.assertAlmostEqual(terminal, 0.08, places=5)
        self.assertGreater(mid, terminal)


class TestSequenceWallDiscount(unittest.TestCase):
    def test_both_neighbors_dead_reduces_mid(self):
        opp = PlayerState(seat_wind="S")
        rem = _rem_full()
        base = estimate_tile_danger("5p", opp, rem, "9s")
        rem_broken = dict(rem)
        rem_broken["4p"] = 0
        rem_broken["6p"] = 0
        broken = estimate_tile_danger("5p", opp, rem_broken, "9s")
        self.assertLess(broken, base)
        self.assertAlmostEqual(broken, base * 0.45, places=5)


class TestDyeHand(unittest.TestCase):
    def test_same_suit_two_melds_boost_mid(self):
        opp = PlayerState(
            seat_wind="W",
            melds=[_chi("2m", "3m", "4m"), _pong("8m")],
        )
        rem = _rem_full()
        # 染万：5m 为 3~7 → ×2.2
        dyed = estimate_tile_danger("5m", opp, rem, "9s")
        plain_opp = PlayerState(seat_wind="W")
        plain = estimate_tile_danger("5m", plain_opp, rem, "9s")
        self.assertAlmostEqual(dyed, plain * 2.2, places=5)

        # 它色筒 → ×0.25
        other = estimate_tile_danger("5p", opp, rem, "9s")
        self.assertAlmostEqual(other, plain * 0.25, places=5)

    def test_mixed_suits_no_dye(self):
        opp = PlayerState(
            seat_wind="W",
            melds=[_chi("2m", "3m", "4m"), _pong("8p")],
        )
        rem = _rem_full()
        plain_opp = PlayerState(seat_wind="W")
        self.assertAlmostEqual(
            estimate_tile_danger("5m", opp, rem, "9s"),
            estimate_tile_danger("5m", plain_opp, rem, "9s"),
            places=5,
        )


class TestWhiteboardSubstitute(unittest.TestCase):
    def test_pong_whiteboard_counts_as_dealer_suit(self):
        """得=5m 时碰白板三次 → 逻辑为万子染手的一脸。"""
        opp = PlayerState(
            seat_wind="N",
            melds=[
                _pong("P"),  # → 5m
                _chi("2m", "3m", "4m"),
            ],
        )
        rem = _rem_full("5m")
        # 物理 P 的 Rem 与危险度按物理键；染手看逻辑花色
        # 打 6m（3~7 万）应被染手加倍
        plain = estimate_tile_danger(
            "6m", PlayerState(seat_wind="N"), rem, "5m"
        )
        dyed = estimate_tile_danger("6m", opp, rem, "5m")
        self.assertAlmostEqual(dyed, plain * 2.2, places=5)

        # 打物理 P：非现物时按字牌/替身？P 物理是字牌身份在 _is_honor
        # 危险用物理 P → honor base；染手对非序数不乘
        # 若打 5m 物理键：逻辑万 5 → 染手 ×2.2
        d5 = estimate_tile_danger("5m", opp, rem, "5m")
        # rem 中 5m 因公示为 3，appeared=1，base 仍约 0.18
        self.assertAlmostEqual(d5, 0.18 * 2.2, places=5)

    def test_genbutsu_physical_p_not_dealer(self):
        """打出过物理白板，仅 P 现物；得同名 5m 不因此现物。"""
        opp = PlayerState(seat_wind="S", discards=["P"])
        rem = _rem_full("5m")
        self.assertEqual(estimate_tile_danger("P", opp, rem, "5m"), 0.0)
        self.assertGreater(estimate_tile_danger("5m", opp, rem, "5m"), 0.0)


class TestWithPoolTracker(unittest.TestCase):
    def test_integration_rem_from_request(self):
        hand = [
            "1m", "2m", "3m", "4m", "5m", "6m", "7m",
            "1p", "2p", "3p", "4p", "5p", "6p", "7p",
        ]
        opp = PlayerState(seat_wind="S", discards=["8s", "8s"])
        req = HandRequest(
            hand_tiles=hand,
            dealer_tile="3s",
            seat_wind="E",
            is_dealer=True,
            opponents=[
                opp,
                PlayerState(seat_wind="W"),
                PlayerState(seat_wind="N"),
            ],
        )
        rem = get_remaining_tiles(req)
        # 8s 已见 2 张在对手河，仍可能有壁牌
        self.assertGreater(rem["8s"], 0)
        # 现物
        self.assertEqual(
            estimate_tile_danger("8s", opp, rem, "3s"), 0.0
        )


if __name__ == "__main__":
    unittest.main()
