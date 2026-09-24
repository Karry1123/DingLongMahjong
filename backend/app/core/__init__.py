"""台州麻将规则核心模块。"""

from .constants import (
    ALL_TILES,
    DRAGONS,
    FULL_DECK_SIZE,
    HONORS,
    JOKER,
    JOKER_WALL_CAPACITY,
    MANS,
    PINS,
    SOUS,
    WINDS,
    build_full_deck,
)
from .evaluator import check_ron_win, check_self_drawn_win, check_win_or_shanten
from .ev_engine import calculate_best_discards
from .action_generator import Action, ActionType, get_available_actions
from .call_decision import CallDecisionResponse, evaluate_call_decision
from .danger_model import estimate_tile_danger
from .deck_engine import draw_tile_from_wall, setup_new_game
from .pool_tracker import get_effective_remaining, get_remaining_tiles
from .score_calc import calculate_meld_points
from .scoring import calculate_hu_points
from .settlement import calculate_final_settlement
from .tenpai_model import estimate_opponents_tenpai, estimate_tenpai_probability
from .mapper import preprocess_hand

__all__ = [
    "ALL_TILES",
    "Action",
    "ActionType",
    "CallDecisionResponse",
    "DRAGONS",
    "FULL_DECK_SIZE",
    "HONORS",
    "JOKER",
    "JOKER_WALL_CAPACITY",
    "MANS",
    "PINS",
    "SOUS",
    "WINDS",
    "build_full_deck",
    "calculate_best_discards",
    "calculate_final_settlement",
    "calculate_hu_points",
    "calculate_meld_points",
    "check_ron_win",
    "check_self_drawn_win",
    "check_win_or_shanten",
    "draw_tile_from_wall",
    "estimate_opponents_tenpai",
    "estimate_tenpai_probability",
    "estimate_tile_danger",
    "evaluate_call_decision",
    "get_available_actions",
    "get_effective_remaining",
    "get_remaining_tiles",
    "preprocess_hand",
    "setup_new_game",
]
