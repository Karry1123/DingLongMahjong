"""Opponent warnings inferred only from visible melds, rivers, and wall count."""

from __future__ import annotations

from collections import Counter
from typing import Sequence

from app.core.tenpai_model import estimate_tenpai_probability
from app.schemas import PlayerState


def _is_middle(tile: str) -> bool:
    return len(tile) == 2 and tile[0] in "456" and tile[1] in "mps"


def assess_opponent_threats(
    opponents: Sequence[PlayerState | dict], dealer_tile: str, wall_count: int,
    turn_count: int | None = None, self_discards: Sequence[str] = (),
) -> list[dict]:
    """Classify one current warning per opponent from public table information."""
    public = [PlayerState.model_validate(source) for source in opponents]
    results = []
    visible_discards = Counter(self_discards)
    visible_discards.update(tile for player in public for tile in player.discards)
    visible_discards.update(tile for player in public for meld in player.melds for tile in meld.tiles)
    round_turn = turn_count if turn_count is not None else max((len(p.discards) for p in public), default=0) + 1
    for player in public:
        meld_count = len(player.melds)
        probability = estimate_tenpai_probability(player, turn_count=round_turn, dealer_tile=dealer_tile)
        recent = player.discards[-2:]
        consecutive_fresh_middle = (
            len(recent) == 2
            and all(_is_middle(tile) and visible_discards[tile] == 1 for tile in recent)
        )
        if wall_count > 55 or round_turn <= 4:
            level, reason = "safe", "early_round"
        elif probability >= 0.8 or meld_count >= 3 or (meld_count >= 2 and wall_count <= 50):
            level, reason = "high", "high_tenpai"
        elif consecutive_fresh_middle:
            level, reason = "warn", "fresh_middle"
        elif meld_count >= 1:
            level, reason = "warn", "new_meld"
        else:
            level, reason = "safe", "steady"
        results.append({"seat_wind": player.seat_wind, "probability": round(probability, 3),
                        "meld_count": meld_count, "level": level, "reason": reason})
    return results
