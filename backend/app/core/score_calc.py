"""副露胡头（兼容入口）。

完整胡数请使用 ``app.core.scoring.calculate_hu_points``。
本模块保留 ``calculate_meld_points``，内部转发至新计分模块。
"""

from __future__ import annotations

from app.schemas import Meld

from .scoring import calculate_meld_points as calculate_meld_points

__all__ = ["calculate_meld_points"]
