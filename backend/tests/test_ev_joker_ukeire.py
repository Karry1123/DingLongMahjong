"""Physical joker/substitute regression cases for discard and draw enumeration."""

import pytest

from app.core.constants import ALL_TILES
from app.core.ev_engine import _collect_ukeire, calculate_best_discards
from app.core.evaluator import check_win_or_shanten
from app.core.mapper import preprocess_hand


def collect(hand, dealer, needed=4):
    rem = {tile: 4 - hand.count(tile) - (tile == dealer) for tile in ALL_TILES}
    return _collect_ukeire(
        remain_raw=hand, rem_map=rem, dealer_tile=dealer,
        seat_wind="E", is_dealer=True, needed_melds=needed, melds=[], light=True,
    )


@pytest.mark.parametrize("dealer", ["6p", "P"])
def test_joker_single_waits_on_every_available_physical_tile(dealer):
    rows = collect([dealer], dealer, needed=0)
    assert {row["tile"] for row in rows} == set(ALL_TILES)
    assert sum(row["rem"] for row in rows) == 134


def test_substitute_neighbors_match_exhaustive_shanten_search():
    hand = "1m 1m 1m 2m 2m 2m 3m 3m 3m E E P 9s".split()
    base = check_win_or_shanten(preprocess_hand(hand, "6p"))
    expected = {
        tile for tile in ALL_TILES
        if check_win_or_shanten(preprocess_hand(hand + [tile], "6p")) < base
    }
    actual = {row["tile"] for row in collect(hand, "6p")}
    assert {"4p", "5p", "7p", "8p"} <= actual
    assert actual == expected


@pytest.mark.parametrize("extra", ALL_TILES)
def test_reported_thirteen_tile_skeleton_never_recommends_whiteboard(extra):
    # The report lists 13 tiles; cover every possible missing 14th tile.
    hand = "1m 1m 6m 7m 2p 2p 5p P 2s 5s E E E".split() + [extra]
    result = calculate_best_discards(
        hand, "6p", True, "E", include_self_gang=False,
    )
    assert result["best_tile"] not in {"P", "6p"}
    assert "6p" not in {row["tile"] for row in result["candidates"]}
    if extra == "6p":
        assert result["best_tile"] == "2s"
        assert {row["tile"] for row in result["candidates"]} == {"2s", "5s"}
        for row in result["candidates"]:
            remain = hand.copy()
            remain.remove(row["tile"])
            assert preprocess_hand(remain, "6p").count("JOKER") == 1
            base = check_win_or_shanten(preprocess_hand(remain, "6p"))
            expected = {
                t for t in ALL_TILES
                if check_win_or_shanten(preprocess_hand(remain + [t], "6p")) < base
            }
            assert {t["tile"] for t in row["effective_tiles"]} == expected
