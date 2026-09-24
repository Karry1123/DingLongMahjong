"""全场壁牌 Rem / dealer_tile 公示占用单测（rule.md §2）。"""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.core.pool_tracker import get_effective_remaining, get_remaining_tiles
from app.schemas import HandRequest, Meld, MeldType, PlayerState


def _full_hand_14() -> list[str]:
    """构造合法 14 张待切手（无重复超限）。"""
    return [
        "1m", "2m", "3m", "4m", "5m", "6m", "7m",
        "1p", "2p", "3p", "4p", "5p", "6p", "7p",
    ]


class TestDealerTileOccupancy(unittest.TestCase):
    """得牌公示占用：Rem(dealer) 相对同名可见牌多扣 1。"""

    def test_dealer_shown_subtracts_one(self):
        req = HandRequest(
            hand_tiles=_full_hand_14(),
            melds=[],
            discards=[],
            dealer_tile="5s",
            seat_wind="E",
            round_wind="E",
            is_dealer=True,
            opponents=[],
        )
        rem = get_remaining_tiles(req)
        # 手牌无 5s、无副露/废牌 → Rem(5s)=4-1(公示)=3
        self.assertEqual(rem["5s"], 3)
        # 非得牌且未出现 → Rem=4
        self.assertEqual(rem["9s"], 4)
        # 手牌中的 1m：Rem=4-1=3（非得，无公示）
        self.assertEqual(rem["1m"], 3)

    def test_dealer_in_hand_and_shown(self):
        """手中持有 1 张得同名牌 + 公示 1 张 → Rem=4-1-1=2。"""
        hand = _full_hand_14()
        hand[0] = "5s"
        req = HandRequest(
            hand_tiles=hand,
            melds=[],
            dealer_tile="5s",
            seat_wind="E",
            is_dealer=False,
            opponents=[],
        )
        rem = get_remaining_tiles(req)
        self.assertEqual(rem["5s"], 2)

    def test_whiteboard_physical_isolation_from_dealer(self):
        """情况 A：得=5m 时，P 与 5m 物理隔离扣减，互不影响。"""
        hand = _full_hand_14()
        # 原手含 5m 一张：改成 P，再保留/确认仅一张 5m
        hand[4] = "P"  # 原位置是 5m → 改为白板
        # hand 中仍有… 等等 5m 被换掉了，放回一张 5m
        hand[5] = "5m"  # 原 6m → 5m，使手中恰 1 张 5m、1 张 P
        req = HandRequest(
            hand_tiles=hand,
            melds=[],
            discards=["P"],
            dealer_tile="5m",
            seat_wind="E",
            is_dealer=False,
            opponents=[],
        )
        rem = get_remaining_tiles(req)
        # 5m：手 1 + 公示 1 → Rem=2；不因 P 减少
        self.assertEqual(rem["5m"], 2)
        # P：手 1 + 河 1 → Rem=2；不因得公示再扣
        self.assertEqual(rem["P"], 2)


class TestOpponentsAndLegacy(unittest.TestCase):
    def test_opponents_reduce_rem(self):
        req = HandRequest(
            hand_tiles=_full_hand_14(),
            melds=[],
            discards=["8s"],
            dealer_tile="3s",
            seat_wind="E",
            is_dealer=False,
            opponents=[
                PlayerState(
                    seat_wind="S",
                    discards=["8s"],
                    melds=[
                        Meld(
                            meld_type=MeldType.PONG,
                            tiles=["9p", "9p", "9p"],
                        )
                    ],
                ),
                PlayerState(seat_wind="W", discards=["3s"]),
                PlayerState(seat_wind="N"),
            ],
        )
        rem = get_remaining_tiles(req)
        # 8s：两家牌河各 1 → Rem=2
        self.assertEqual(rem["8s"], 2)
        # 9p：对手碰 3 → Rem=1
        self.assertEqual(rem["9p"], 1)
        # 3s：对手河 1 + 公示 1 → Rem=2
        self.assertEqual(rem["3s"], 2)

    def test_effective_excludes_zero(self):
        hand = ["1m"] * 4 + ["2m"] * 4 + ["3m"] * 4 + ["4m", "5m"]
        req = HandRequest(
            hand_tiles=hand,
            dealer_tile="9s",
            seat_wind="E",
            is_dealer=True,
        )
        rem = get_remaining_tiles(req)
        self.assertEqual(rem["1m"], 0)
        eff = get_effective_remaining(req)
        self.assertNotIn("1m", eff)
        self.assertEqual(eff["9s"], 3)  # 仅公示

    def test_global_count_over_four_rejected(self):
        with self.assertRaises(ValidationError):
            HandRequest(
                hand_tiles=_full_hand_14(),
                discards=["1m", "1m"],
                dealer_tile="5s",
                seat_wind="E",
                is_dealer=False,
                opponents=[
                    PlayerState(
                        seat_wind="S",
                        melds=[
                            Meld(
                                meld_type=MeldType.PONG,
                                tiles=["1m", "1m", "1m"],
                            )
                        ],
                    )
                ],
            )

    def test_legacy_discarded_tiles_without_opponents(self):
        """无 opponents 时 discarded_tiles 仍计入 Rem（兼容旧前端）。"""
        req = HandRequest(
            hand_tiles=_full_hand_14(),
            dealer_tile="E",
            seat_wind="E",
            is_dealer=True,
            discarded_tiles=["2s", "2s"],
        )
        rem = get_remaining_tiles(req)
        self.assertEqual(rem["2s"], 2)
        self.assertEqual(rem["E"], 3)  # 仅公示

    def test_opponent_hand_tiles_forbidden_on_player_state(self):
        """上帝视角暗手不得进入 PlayerState / Rem 扣减。"""
        with self.assertRaises(ValidationError):
            PlayerState(
                seat_wind="S",
                discards=["5p"],
                hand_tiles=["1m", "2m", "3m"],  # type: ignore[call-arg]
            )

    def test_rem_ignores_hypothetical_closed_hands(self):
        """即便对手暗手「应有」某张牌，Rem 也只能按公开信息扣。"""
        # 自家 14 张不含 9s；公开信息也不含 9s → Rem(9s)=4
        req = HandRequest(
            hand_tiles=_full_hand_14(),
            dealer_tile="E",
            seat_wind="E",
            is_dealer=True,
            opponents=[
                PlayerState(seat_wind="S", discards=[], melds=[]),
                PlayerState(seat_wind="W", discards=[], melds=[]),
                PlayerState(seat_wind="N", discards=[], melds=[]),
            ],
        )
        rem = get_remaining_tiles(req)
        self.assertEqual(rem["9s"], 4)
        # 公开副露才会扣
        req2 = HandRequest(
            hand_tiles=_full_hand_14(),
            dealer_tile="E",
            seat_wind="E",
            is_dealer=True,
            opponents=[
                PlayerState(
                    seat_wind="S",
                    melds=[
                        Meld(
                            meld_type=MeldType.PONG,
                            tiles=["9s", "9s", "9s"],
                        )
                    ],
                ),
                PlayerState(seat_wind="W"),
                PlayerState(seat_wind="N"),
            ],
        )
        self.assertEqual(get_remaining_tiles(req2)["9s"], 1)


if __name__ == "__main__":
    unittest.main()
