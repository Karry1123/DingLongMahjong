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
) -> list[dict]:
    """Use public signals only; an estimated probability never triggers a warning alone."""
    public = [PlayerState.model_validate(source) for source in opponents]
    results = []
    visible_discards = Counter(tile for player in public for tile in player.discards)
    for player in public:
        meld_count = len(player.melds)
        probability = estimate_tenpai_probability(player, dealer_tile=dealer_tile)
        recent = player.discards[-2:]
        consecutive_fresh_middle = (
            len(recent) == 2
            and all(_is_middle(tile) and visible_discards[tile] == 1 for tile in recent)
        )
        if wall_count > 55:
            level, reason = "safe", "early_round"
        elif wall_count <= 25:
            level, reason = "high", "late_round"
        elif meld_count >= 3:
            level, reason = "warn", "many_melds"
        elif wall_count <= 50 and meld_count >= 2:
            level = "warn"
            reason = "discard_pattern" if wall_count < 50 and consecutive_fresh_middle else "many_melds"
        else:
            level, reason = "safe", "steady"
        results.append({"seat_wind": player.seat_wind, "probability": round(probability, 3),
                        "meld_count": meld_count, "level": level, "reason": reason})
    return results
