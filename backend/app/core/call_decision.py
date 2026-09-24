"""副露（吃/碰/杠）与过牌（PASS）的期望值权衡。

流程：
1. 有 HU → 用结算胡数估算即时收益，并与 PASS 的后续期望比较。
2. 对其余 CHI/PONG/MING_GANG：模拟副露后进入待切，取
   ``calculate_best_discards`` 最优净 EV，再叠加：
   - 向听阶梯化的门清/硬胡机会成本；
   - 碰牌激励（幺九/字刻底胡 + 废牌即切加速）。
3. PASS：按当前等待进张估进攻 EV − 向听×120；极早巡低风险的强单色手另计
   混一色/清一色成型期望，不假设过牌会触发振听。
4. 比较净 EV，选出 recommended_action。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.schemas import Meld, MeldType, PlayerState

from .action_generator import (
    Action,
    ActionType,
    is_redundant_complete_sequence_chi,
)
from .constants import DRAGONS, WINDS
from .evaluator import check_win_or_shanten
from .ev_engine import (
    SHANTEN_PENALTY,
    _build_rem_map,
    _collect_ukeire,
    _is_pure_isolated_tile,
    _logical_tile,
    calculate_best_discards,
    evaluate_rinshan_then_discard,
)
from .mapper import preprocess_hand
from .scoring import (
    DEFAULT_BASE_HU,
    MAX_PAYMENT_PER_PLAYER,
    MING_GANG_SIMPLE_HU,
    MING_GANG_TERMINAL_HONOR_HU,
    PONG_SIMPLE_HU,
    PONG_TERMINAL_HONOR_HU,
    _is_terminal_or_honor,
    calculate_best_hu_points,
    calculate_unwon_base_hu,
)
from .tenpai_model import estimate_opponents_tenpai

# 门清/硬胡「机会成本」基准（乘向听折现后从副露 EV 扣除）
_MENQING_HARD_HU_COST = 48.0
# 碰后切出废牌（客风孤张等）的做牌加速奖励
_JUNK_CUT_SPEED_BONUS_MIN = 15.0
_JUNK_CUT_SPEED_BONUS_MAX = 25.0
# 底胡激励换算到 EV 的系数（庄家略放大）
_PONG_HU_EV_SCALE = 2.5
# 未进入听牌估值时，役牌一番按成牌机会折现；听牌估值已包含番数。
_YAKUHAI_FAN_MAKE_CHANCE = {0: 0.25, 1: 0.65}
# 冗余完整顺子吃牌：暗顺搬明顺，浪费摸牌巡
_REDUNDANT_SEQUENCE_CHI_PENALTY = 55.0
# 吃/碰后向听未降：副露无加速
_NO_SHANTEN_DROP_CALL_PENALTY = 18.0
# 过牌获得下一巡自摸进张权的基准价值
_PASS_DRAW_TURN_BASE = 22.0
_PASS_DRAW_UKEIRE_SCALE = 0.35  # 每张有效进张额外加成（封顶见下）
_PASS_DRAW_UKEIRE_CAP = 20
_EARLY_FLUSH_MIN_SUIT_TILES = 8
_EARLY_FLUSH_MIN_HAND_TILES = 10


@dataclass
class CallActionScore:
    """单个响应动作的 EV 评估。"""

    action: Action
    net_ev: float
    note: str = ""
    hu_ev: float | None = None
    pass_ev: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "net_ev": round(self.net_ev, 4),
            "note": self.note,
            "hu_ev": round(self.hu_ev, 4) if self.hu_ev is not None else None,
            "pass_ev": round(self.pass_ev, 4) if self.pass_ev is not None else None,
        }


@dataclass
class CallDecisionResponse:
    """副露/过牌决策结果。"""

    recommended_action: Action
    reason: str
    candidates: list[CallActionScore] = field(default_factory=list)
    hu_ev: float | None = None
    pass_ev: float | None = None
    est_final_points: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_action": self.recommended_action.to_dict(),
            "reason": self.reason,
            "candidates": [c.to_dict() for c in self.candidates],
            "available_actions": [c.action.to_dict() for c in self.candidates],
            "hu_ev": round(self.hu_ev, 4) if self.hu_ev is not None else None,
            "pass_ev": round(self.pass_ev, 4) if self.pass_ev is not None else None,
            "est_final_points": self.est_final_points,
        }


def evaluate_call_decision(
    available_actions: list[Action],
    hand_tiles: list[str],
    melds: list[Meld] | Sequence[Meld],
    opponents: list[PlayerState] | Sequence[PlayerState],
    dealer_tile: str,
    seat_wind: str,
    round_wind: str,
    is_dealer: bool,
    *,
    discarded_tile: str | None = None,
    discarded_tiles: list[str] | None = None,
    turn_count: int | None = None,
) -> CallDecisionResponse:
    """比较吃/碰/杠与过牌的净 EV，给出推荐响应。

    Args:
        available_actions: ``get_available_actions`` 的结果。
        hand_tiles: 响应方当前门清（通常 13 张）。
        melds: 响应方已有副露。
        opponents: 其余三家公开状态。
        dealer_tile / seat_wind / round_wind / is_dealer: 局况。
        discarded_tile: 本拍打出张（可从 HU/副露动作推断；建议显式传入）。
        discarded_tiles: 已见废牌（含本张更佳），供 Rem。

    Note:
        ``round_wind`` 传给后续切牌评估，圈风不能当作无役客风。
    """
    if seat_wind not in WINDS:
        raise ValueError(f"seat_wind 非法：{seat_wind!r}")

    meld_list = list(melds or [])
    opp_list = list(opponents or [])
    actions = list(available_actions or [])
    if not actions:
        raise ValueError("available_actions 为空")

    disc = discarded_tile or _infer_discarded_tile(actions)
    if not disc:
        raise ValueError("无法确定 discarded_tile，请显式传入")

    river = list(discarded_tiles or [])
    if disc not in river:
        river = river + [disc]

    hu_actions = [a for a in actions if a.action_type == ActionType.HU]
    shanten_now = _hand_shanten(hand_tiles, meld_list, dealer_tile)
    hard_disc = _hard_hu_discount(shanten_now)

    scores: list[CallActionScore] = []
    hu_ev: float | None = None
    pass_ev: float | None = None
    est_final_points: int | None = None
    pass_flush_note = ""

    if hu_actions:
        winning_tile = hu_actions[0].tiles[0] if hu_actions[0].tiles else disc
        try:
            hu_detail = calculate_best_hu_points(
                melds=meld_list,
                hand_tiles=hand_tiles,
                win_tile=winning_tile,
                is_zimo=False,
                seat_wind=seat_wind,
                dealer_tile=dealer_tile,
                round_wind=round_wind,
            )
            est_final_points = int(hu_detail["final_hu"])
            # 闲家捉铳总收款为 2×胡数（庄家全额 + 两闲各半）；庄家为 3×。
            hu_ev = float(min(est_final_points, MAX_PAYMENT_PER_PLAYER) * (3 if is_dealer else 2))
        except (ValueError, KeyError, TypeError):
            # 合法动作生成器已确认和型；遇到旧状态数据不完整时仍提供有限估值。
            est_final_points = 10
            hu_ev = float(min(est_final_points, MAX_PAYMENT_PER_PLAYER) * (3 if is_dealer else 2))

    for action in actions:
        if action.action_type == ActionType.PASS:
            ev = _evaluate_pass_ev(
                hand_tiles=hand_tiles,
                melds=meld_list,
                dealer_tile=dealer_tile,
                seat_wind=seat_wind,
                is_dealer=is_dealer,
                discarded_tiles=river,
                opponents=opp_list,
            )
            flush_bonus, flush_note = _early_flush_ambition_bonus(
                hand_tiles=hand_tiles,
                melds=meld_list,
                opponents=opp_list,
                discarded_tiles=river,
                turn_count=turn_count,
            )
            pass_flush_note = flush_note
            if hu_ev is not None:
                # 过牌面对现成和张只保留后续 EV 的折现值；不把等待收益当成即时兑现。
                ev *= 0.55
            ev += flush_bonus
            # 深向听：过牌不享受「硬胡全额溢价」；听牌/一向听才保留门清溢价
            ev += _MENQING_HARD_HU_COST * hard_disc * 0.35
            note = _pass_note(shanten_now, hard_disc)
            if flush_note:
                note = f"{note}；{flush_note}"
            pass_ev = float(ev)
            scores.append(
                CallActionScore(
                    action=action, net_ev=ev, note=note,
                    hu_ev=hu_ev, pass_ev=pass_ev,
                )
            )
            continue

        if action.action_type == ActionType.HU:
            scores.append(CallActionScore(
                action=action, net_ev=float(hu_ev or 0.0),
                note=f"即时捉铳，预估胡数 {est_final_points}；即时净收益 {hu_ev:.2f}",
                hu_ev=hu_ev, pass_ev=None,
            ))
            continue

        if action.action_type in (
            ActionType.CHI,
            ActionType.PONG,
            ActionType.MING_GANG,
        ):
            if _breaks_flush_plan(hand_tiles, action, dealer_tile):
                scores.append(CallActionScore(
                    action=action,
                    net_ev=float("-inf"),
                    note="手牌处于早巡强单色胚子，副露杂色序数牌会破坏混一色/清一色路线",
                ))
                continue
            try:
                ev, note = _evaluate_call_ev(
                    action=action,
                    hand_tiles=hand_tiles,
                    melds=meld_list,
                    discarded_tile=disc,
                    dealer_tile=dealer_tile,
                    seat_wind=seat_wind,
                    is_dealer=is_dealer,
                    discarded_tiles=river,
                    opponents=opp_list,
                    shanten_before=shanten_now,
                    hard_hu_discount=hard_disc,
                    round_wind=round_wind,
                )
            except ValueError as exc:
                scores.append(
                    CallActionScore(
                        action=action,
                        net_ev=float("-inf"),
                        note=f"模拟失败：{exc}",
                    )
                )
                continue
            scores.append(
                CallActionScore(action=action, net_ev=ev, note=note)
            )
            continue

        scores.append(
            CallActionScore(
                action=action,
                net_ev=float("-inf"),
                note="未支持的动作类型",
            )
        )

    if not scores:
        raise ValueError("无任何可评估动作")

    # 三张暗刻面对外部第四张时，碰后仍须切掉余下那张；明杠则锁定更高
    # 底胡并获得岭上补张。嵌套抽样 EV 对这一次额外摸牌可能低估，按
    # 明杠与明刻的固定胡差给出可解释的结构下界。
    if Counter(hand_tiles)[disc] == 3:
        pong = next((s for s in scores if s.action.action_type == ActionType.PONG), None)
        kong = next((s for s in scores if s.action.action_type == ActionType.MING_GANG), None)
        if pong and kong and pong.net_ev > float("-inf") and kong.net_ev > float("-inf"):
            terminal = _is_terminal_or_honor(_logical_tile(disc, dealer_tile))
            pong_hu = PONG_TERMINAL_HONOR_HU if terminal else PONG_SIMPLE_HU
            kong_hu = MING_GANG_TERMINAL_HONOR_HU if terminal else MING_GANG_SIMPLE_HU
            hu_weight = 1.0 if shanten_now <= 1 else 0.85
            floor_gap = ((kong_hu - pong_hu) * _PONG_HU_EV_SCALE
                         * (1.15 if is_dealer else 1.0) * hu_weight
                         + _PASS_DRAW_TURN_BASE * 0.35)
            if kong.net_ev < pong.net_ev + floor_gap:
                kong.net_ev = pong.net_ev + floor_gap
                kong.note += f"；绝张暗刻相对碰牌锁定+{kong_hu - pong_hu}胡并获得岭上补张"

    best = max(scores, key=lambda s: s.net_ev)
    reason = _build_reason(best, scores, shanten_now)
    if (
        best.action.action_type == ActionType.PASS
        and hu_ev is not None
        and pass_ev is not None
        and pass_flush_note
    ):
        reason = (
            "早巡极佳清一色/混一色胚子，放铳率极低，过牌造大牌收益显著高于即时鸡胡"
            f"（PASS EV={pass_ev:.2f} > HU EV={hu_ev:.2f}）"
        )
    return CallDecisionResponse(
        recommended_action=best.action,
        reason=reason,
        candidates=sorted(scores, key=lambda s: s.net_ev, reverse=True),
        hu_ev=hu_ev,
        pass_ev=pass_ev,
        est_final_points=est_final_points,
    )


# ---------------------------------------------------------------------------
# 向听阶梯 / 碰牌激励
# ---------------------------------------------------------------------------

def _hard_hu_discount(shanten: int) -> float:
    """硬胡翻倍（×2）期待收益的向听折现系数。

    - shanten >= 2：0.15（牌散，不为飘渺硬胡放弃副露加速）
    - shanten == 1：0.5
    - shanten <= 0：1.0（已听，尽量硬碰硬）
    """
    if shanten <= 0:
        return 1.0
    if shanten == 1:
        return 0.5
    return 0.15


def _hand_shanten(
    hand_tiles: list[str], melds: list[Meld], dealer_tile: str
) -> int:
    needed = 4 - len(melds)
    logical = preprocess_hand(hand_tiles, dealer_tile)
    return int(check_win_or_shanten(logical, 0, needed_melds=needed))


def _pass_note(shanten: int, hard_disc: float) -> str:
    if shanten >= 2:
        return (
            f"过牌摸牌推进（向听 {shanten}，硬胡折现×{hard_disc:.2f}；"
            "保留暗顺/搭子并从牌墙进张）"
        )
    if shanten == 1:
        return "过牌保留一向听门清/硬胡潜力，并获得自摸进张巡（折现×0.5）"
    return "过牌保留听牌门清/硬胡潜力"


def _early_flush_ambition_bonus(
    *,
    hand_tiles: list[str],
    melds: list[Meld],
    opponents: list[PlayerState],
    discarded_tiles: list[str],
    turn_count: int | None,
) -> tuple[float, str]:
    """为极早巡、低风险的深单色胚子估算保留大牌路线的期望价值。"""
    turn = int(turn_count if turn_count is not None else max(
        (len(o.discards or []) for o in opponents), default=0
    ))
    if turn > 3:
        return 0.0, ""
    suited = Counter(t[1] for t in hand_tiles if _is_suited_tile(t))
    if not suited:
        return 0.0, ""
    suit, suit_count = suited.most_common(1)[0]
    honors = sum(1 for t in hand_tiles if t in WINDS or t in DRAGONS)
    same_and_honors = suit_count + honors
    if suit_count < _EARLY_FLUSH_MIN_SUIT_TILES or same_and_honors < _EARLY_FLUSH_MIN_HAND_TILES:
        return 0.0, ""
    tenpai = estimate_opponents_tenpai(opponents, rem_map=None)
    if tenpai and max(tenpai.values()) >= 0.15:
        return 0.0, ""

    off_suit = sum(
        1 for t in hand_tiles
        if _is_suited_tile(t) and t[1] != suit
    )
    # 以清一色/混一色高胡值乘保守成型概率折现；杂张越少、主色越深越可信。
    projected_points = 200.0 if honors else 260.0
    make_probability = min(0.48, 0.18 + 0.025 * (suit_count - 8) + 0.035 * max(0, 3 - off_suit))
    make_probability *= 0.92 ** len(melds)
    safety_credit = max(0.0, 12.0 * (1.0 - (max(tenpai.values()) if tenpai else 0.03) / 0.15))
    bonus = projected_points * make_probability + safety_credit
    kind = "清一色" if honors == 0 else "混一色"
    note = (
        f"早巡强{kind}胚子（主色 {suit_count} 张、待处理杂色 {off_suit} 张），"
        f"成型期望 +{bonus:.1f}；对手听牌风险低"
    )
    return bonus, note


def _breaks_flush_plan(hand_tiles: list[str], action: Action, dealer_tile: str) -> bool:
    suited = Counter(t[1] for t in hand_tiles if _is_suited_tile(t))
    if not suited:
        return False
    suit, count = suited.most_common(1)[0]
    if count < _EARLY_FLUSH_MIN_SUIT_TILES:
        return False
    # 混一色保留字牌；跨门序数副露会永久破坏单色路线。
    return any(
        _is_suited_tile(t) and t[1] != suit
        for t in (action.tiles or [])
        if t != dealer_tile
    )


def _is_suited_tile(tile: str) -> bool:
    return len(tile) == 2 and tile[0].isdigit() and tile[1] in "mps"


def _pong_yakuhai_fan(tile: str, dealer_tile: str, seat_wind: str, round_wind: str) -> int:
    """碰出的固定字牌番数；自风与圈风相同可叠加。"""
    face = _logical_tile(tile, dealer_tile)
    return int(tile in DRAGONS) + int(face == seat_wind) + int(face == round_wind)


def _pong_incentive(
    *,
    action: Action,
    discarded_tile: str,
    hand_before: list[str],
    hand_after: list[str],
    dealer_tile: str,
    seat_wind: str,
    is_dealer: bool,
    best_discard: str,
    shanten_before: int,
    shanten_after: int,
    melds_before: list[Meld],
    melds_after: list[Meld],
    round_wind: str,
) -> tuple[float, str]:
    """碰牌收益量化：幺九/字底胡 + 废牌即切加速。"""
    if action.action_type != ActionType.PONG:
        return 0.0, ""

    face = _logical_tile(discarded_tile, dealer_tile)
    terminal = _is_terminal_or_honor(face)
    hu = PONG_TERMINAL_HONOR_HU if terminal else PONG_SIMPLE_HU
    scale = _PONG_HU_EV_SCALE * (1.15 if is_dealer else 1.0)
    hu_weight = 1.0 if shanten_before <= 1 else 0.85
    bonus = float(hu) * scale * hu_weight

    fan_count = _pong_yakuhai_fan(discarded_tile, dealer_tile, seat_wind, round_wind)

    if fan_count:
        before = calculate_unwon_base_hu(
            hand_before, melds_before, seat_wind, dealer_tile,
            round_wind=round_wind,
        )["calculated_points"]
        after_hand = list(hand_after)
        if best_discard in after_hand:
            after_hand.remove(best_discard)
        after = calculate_unwon_base_hu(
            after_hand, melds_after, seat_wind, dealer_tile,
            round_wind=round_wind,
        )["calculated_points"]
        # 未胡两家间各按固有胡差额的一半互结。
        settlement_premium = max(float(hu), float(after - before))
        # 听牌切牌 EV 已按实际番数估值，仅补足未被覆盖的翻番期望。
        make_chance = _YAKUHAI_FAN_MAKE_CHANCE.get(shanten_after, 0.45)
        fan_premium = (
            (DEFAULT_BASE_HU + hu) * (2 ** fan_count - 1)
            * (3 if is_dealer else 2) * make_chance
        )
        bonus += settlement_premium + fan_premium

    parts: list[str] = []
    if terminal:
        parts.append(f"碰出一组幺九刻（+{hu}胡）")
    else:
        parts.append(f"碰出一组中张刻（+{hu}胡）")
    if fan_count:
        parts.append(
            f"碰牌锁定{_tile_cn(discarded_tile)}明刻(+{hu}底胡，"
            f"+{fan_count}番翻倍)，奠定高胡数底子"
        )

    junk_bonus = 0.0
    if best_discard:
        disc_id = _logical_tile(best_discard, dealer_tile)
        is_guest = disc_id in WINDS and disc_id != seat_wind
        # hand_after = 碰后、切前的暗手
        is_iso = _is_pure_isolated_tile(
            best_discard, hand_after, dealer_tile
        )
        if is_guest and is_iso:
            junk_bonus = _JUNK_CUT_SPEED_BONUS_MAX
            parts.append(
                f"并可切出废牌客风{_tile_cn(best_discard)}，显著加快做牌速度"
            )
        elif is_iso:
            junk_bonus = (
                _JUNK_CUT_SPEED_BONUS_MIN + _JUNK_CUT_SPEED_BONUS_MAX
            ) / 2.0
            parts.append(f"并可切出废牌 {best_discard}，加快做牌速度")
        elif is_guest:
            junk_bonus = _JUNK_CUT_SPEED_BONUS_MIN
            parts.append(f"并可切出客风 {_tile_cn(best_discard)}")

    if shanten_before >= 2:
        bonus += 12.0
        parts.append("散牌期副露成型加速")

    _ = hand_before  # 保留参数对称，便于后续扩展「碰前雀头」分析
    return bonus + junk_bonus, "；".join(parts)


def _tile_cn(code: str) -> str:
    wind = {"E": "东", "S": "南", "W": "西", "N": "北"}
    if code in wind:
        return wind[code]
    if code in DRAGONS:
        return {"C": "红中", "F": "发财", "P": "白板"}[code]
    if len(code) == 2 and code[1] in "mps":
        suit = {"m": "万", "p": "筒", "s": "条"}[code[1]]
        return f"{code[0]}{suit}"
    return code


# ---------------------------------------------------------------------------
# 模拟副露 / 过牌
# ---------------------------------------------------------------------------

def _evaluate_call_ev(
    *,
    action: Action,
    hand_tiles: list[str],
    melds: list[Meld],
    discarded_tile: str,
    dealer_tile: str,
    seat_wind: str,
    is_dealer: bool,
    discarded_tiles: list[str],
    opponents: list[PlayerState],
    shanten_before: int,
    hard_hu_discount: float,
    round_wind: str = "E",
) -> tuple[float, str]:
    new_hand, new_melds = _apply_meld_action(
        hand_tiles, melds, action, discarded_tile
    )
    hard_note = _hard_hu_impact_note(
        hand_tiles, new_hand, dealer_tile, hard_hu_discount
    )
    shanten_after = _hand_shanten(new_hand, new_melds, dealer_tile)

    if action.action_type == ActionType.MING_GANG:
        ev = evaluate_rinshan_then_discard(
            round_wind=round_wind,
            hand_tiles=new_hand,
            melds=new_melds,
            dealer_tile=dealer_tile,
            seat_wind=seat_wind,
            is_dealer=is_dealer,
            discarded_tiles=discarded_tiles,
            opponents=opponents,
        )
        # 开杠损失门清：按向听折现扣机会成本
        ev -= _MENQING_HARD_HU_COST * hard_hu_discount
        face = _logical_tile(discarded_tile, dealer_tile)
        hu = (MING_GANG_TERMINAL_HONOR_HU if _is_terminal_or_honor(face)
              else MING_GANG_SIMPLE_HU)
        # 与碰的固定底胡使用同一尺度。杠分已经锁定，岭上补张 EV 则由上面的
        # 枚举独立计算；否则会把明杠误判为一次没有底胡的普通副露。
        hu_weight = 1.0 if shanten_before <= 1 else 0.85
        ev += hu * _PONG_HU_EV_SCALE * (1.15 if is_dealer else 1.0) * hu_weight
        return ev, f"明杠锁定+{hu}底胡，岭上补张再切；{hard_note}"

    # 吃/碰后立即待切
    result = calculate_best_discards(
        round_wind=round_wind,
        hand_tiles=new_hand,
        dealer_tile=dealer_tile,
        is_dealer=is_dealer,
        seat_wind=seat_wind,
        discarded_tiles=discarded_tiles,
        melds=new_melds,
        opponents=opponents,
    )
    best = result["candidates"][0]
    ev = float(best["ev_score"])

    # 役牌碰出确定的番数足以抵消常规门清机会成本。
    is_yakuhai_pong = (
        action.action_type == ActionType.PONG
        and _pong_yakuhai_fan(discarded_tile, dealer_tile, seat_wind, round_wind) > 0
    )
    if not is_yakuhai_pong:
        ev -= _MENQING_HARD_HU_COST * hard_hu_discount

    incent = 0.0
    incent_note = ""
    if action.action_type == ActionType.PONG:
        incent, incent_note = _pong_incentive(
            action=action,
            discarded_tile=discarded_tile,
            hand_before=hand_tiles,
            hand_after=new_hand,
            dealer_tile=dealer_tile,
            seat_wind=seat_wind,
            is_dealer=is_dealer,
            best_discard=str(best.get("tile") or ""),
            shanten_before=shanten_before,
            shanten_after=shanten_after,
            melds_before=melds,
            melds_after=new_melds,
            round_wind=round_wind,
        )
        ev += incent

    redundant_note = ""
    if action.action_type == ActionType.CHI:
        red = _redundant_sequence_chi_penalty(
            hand_tiles=hand_tiles,
            discarded_tile=discarded_tile,
            chi_tiles=list(action.tiles or []),
            dealer_tile=dealer_tile,
        )
        if red > 0:
            ev -= red
            seq_label = _chi_sequence_label(
                list(action.tiles or []), discarded_tile, dealer_tile
            )
            redundant_note = (
                f"手牌已持有完整 {seq_label} 顺子，"
                "副露无法提升向听且浪费摸牌机会"
            )

    # 吃牌后向听未降：副露无加速（碰另有底胡/废牌激励，不套此罚）
    if (
        action.action_type == ActionType.CHI
        and shanten_after >= shanten_before
    ):
        ev -= _NO_SHANTEN_DROP_CALL_PENALTY

    note_parts = [
        f"副露后最优切 {best['tile']}",
        f"攻 {best.get('attack_ev', 0)} / 防 {best.get('defense_loss', 0)}",
    ]
    if incent_note:
        note_parts.append(incent_note)
    if redundant_note:
        note_parts.append(redundant_note)
    note_parts.append(hard_note)
    return ev, "；".join(note_parts)


def _evaluate_pass_ev(
    *,
    hand_tiles: list[str],
    melds: list[Meld],
    dealer_tile: str,
    seat_wind: str,
    is_dealer: bool,
    discarded_tiles: list[str],
    opponents: list[PlayerState],
) -> float:
    """过牌：等待进张估进攻 EV − 向听×120 + 自摸巡摸牌权价值。"""
    needed = 4 - len(melds)
    logical = preprocess_hand(hand_tiles, dealer_tile)
    shanten = check_win_or_shanten(logical, 0, needed_melds=needed)

    meld_phys = [t for m in melds for t in m.tiles]
    opp_meld_phys = [
        t for o in opponents for m in (o.melds or []) for t in (m.tiles or [])
    ]
    rem_map = _build_rem_map(
        hand_tiles, discarded_tiles, meld_phys + opp_meld_phys, dealer_tile
    )
    ukeire = _collect_ukeire(
        remain_raw=hand_tiles,
        rem_map=rem_map,
        dealer_tile=dealer_tile,
        seat_wind=seat_wind,
        is_dealer=is_dealer,
        needed_melds=needed,
        melds=melds,
    )
    total_rem = sum(u["rem"] for u in ukeire)
    if ukeire and total_rem > 0:
        attack = sum(
            (u["rem"] / total_rem) * u["est_win_points"] for u in ukeire
        )
        # 硬胡进张按向听折现（深向听不把 ×2 硬胡当满分）
        hard_disc = _hard_hu_discount(int(shanten))
        if hard_disc < 1.0 - 1e-9:
            soft = sum(
                (u["rem"] / total_rem) * u["est_win_points"]
                for u in ukeire
                if not u.get("is_hard_hu")
            )
            hard = sum(
                (u["rem"] / total_rem) * u["est_win_points"]
                for u in ukeire
                if u.get("is_hard_hu")
            )
            # 硬胡部分：保留折现后的溢价（近似硬胡分 ≈ 软胡×2 → 溢价=硬-软份）
            attack = soft + hard * hard_disc
    else:
        attack = 0.0

    ev = float(attack) - max(shanten, 0) * SHANTEN_PENALTY

    # 过牌保留下一巡自摸抽牌权：非听牌时显著加分（对抗无意义副露）
    if shanten >= 1:
        ukeire_term = min(int(total_rem), _PASS_DRAW_UKEIRE_CAP)
        draw_bonus = _PASS_DRAW_TURN_BASE + ukeire_term * _PASS_DRAW_UKEIRE_SCALE
        # 深向听更依赖摸牌推进
        if shanten >= 2:
            draw_bonus *= 1.15
        ev += draw_bonus

    return float(ev)


def _apply_meld_action(
    hand_tiles: list[str],
    melds: list[Meld],
    action: Action,
    discarded_tile: str,
) -> tuple[list[str], list[Meld]]:
    """把手牌中的副露用张移除，并追加新副露。"""
    if action.action_type == ActionType.CHI:
        mtype = MeldType.CHI
    elif action.action_type == ActionType.PONG:
        mtype = MeldType.PONG
    elif action.action_type == ActionType.MING_GANG:
        mtype = MeldType.MING_GANG
    else:
        raise ValueError(f"非副露动作：{action.action_type}")

    need = Counter(action.tiles)
    if need[discarded_tile] < 1:
        need[discarded_tile] += 1
    need[discarded_tile] -= 1  # 由牌河提供

    hand = list(hand_tiles)
    for tile, cnt in need.items():
        for _ in range(cnt):
            if tile not in hand:
                raise ValueError(f"手牌缺少副露用张 {tile!r}")
            hand.remove(tile)

    new_meld = Meld(meld_type=mtype, tiles=list(action.tiles))
    if mtype == MeldType.PONG and len(new_meld.tiles) != 3:
        new_meld = Meld(
            meld_type=mtype,
            tiles=[discarded_tile] * 3,
        )
    if mtype == MeldType.MING_GANG and len(new_meld.tiles) != 4:
        from_hand = [discarded_tile] * 3
        new_meld = Meld(
            meld_type=mtype,
            tiles=from_hand + [discarded_tile],
        )

    return hand, list(melds) + [new_meld]


def _hard_hu_impact_note(
    hand_before: list[str],
    hand_after: list[str],
    dealer_tile: str,
    hard_hu_discount: float,
) -> str:
    """副露对硬胡路径的影响说明（含向听折现提示）。"""
    before_j = sum(
        1
        for t in preprocess_hand(hand_before, dealer_tile)
        if t == "JOKER"
    )
    after_j = sum(
        1
        for t in preprocess_hand(hand_after, dealer_tile)
        if t == "JOKER"
    )
    disc_txt = f"硬胡折现×{hard_hu_discount:.2f}"
    if before_j == 0 and after_j == 0:
        return f"仍无得在手（{disc_txt}；明刻胡头低于暗刻）"
    if after_j > 0:
        return f"手中仍有得，软胡路径（{disc_txt}）"
    return f"副露后得不在门清（{disc_txt}）"


def _infer_discarded_tile(actions: list[Action]) -> str | None:
    for a in actions:
        if a.action_type == ActionType.HU and a.tiles:
            return a.tiles[0]
        if a.action_type == ActionType.PONG and a.tiles:
            return a.tiles[0]
        if a.action_type == ActionType.MING_GANG and a.tiles:
            return a.tiles[0]
        if a.action_type == ActionType.CHI and a.tiles:
            continue
    return None


def _redundant_sequence_chi_penalty(
    *,
    hand_tiles: list[str],
    discarded_tile: str,
    chi_tiles: list[str],
    dealer_tile: str,
) -> float:
    if is_redundant_complete_sequence_chi(
        hand_tiles, discarded_tile, chi_tiles, dealer_tile
    ):
        return float(_REDUNDANT_SEQUENCE_CHI_PENALTY)
    return 0.0


def _chi_sequence_label(
    chi_tiles: list[str], discarded_tile: str, dealer_tile: str
) -> str:
    faces = [
        _logical_tile(t, dealer_tile) for t in list(chi_tiles or [])
    ]
    if discarded_tile:
        dface = _logical_tile(discarded_tile, dealer_tile)
        if dface not in faces:
            faces.append(dface)
    suited = sorted(
        {
            f
            for f in faces
            if len(f) == 2 and f[1] in ("m", "p", "s") and f[0].isdigit()
        },
        key=lambda x: (x[1], int(x[0])),
    )
    if len(suited) >= 3:
        return "".join(suited[:3])
    return "该"


def _build_reason(
    best: CallActionScore,
    all_scores: list[CallActionScore],
    shanten: int,
) -> str:
    if best.action.action_type == ActionType.PASS:
        others = [
            s
            for s in all_scores
            if s.action.action_type != ActionType.PASS
            and s.net_ev > float("-inf")
        ]
        redundant_chi = next(
            (
                s
                for s in others
                if s.action.action_type == ActionType.CHI
                and "已持有完整" in (s.note or "")
            ),
            None,
        )
        if redundant_chi is not None:
            return (
                f"{redundant_chi.note}，应坚决过牌摸牌"
                f"（PASS EV={best.net_ev:.2f} > "
                f"CHI EV={redundant_chi.net_ev:.2f}）"
            )
        if others:
            top_call = max(others, key=lambda s: s.net_ev)
            if shanten >= 2:
                return (
                    f"过牌略优（向听 {shanten}，摸牌进张权已计入；"
                    f"PASS EV={best.net_ev:.2f} > "
                    f"{top_call.action.action_type.value} EV={top_call.net_ev:.2f}）"
                )
            return (
                "过牌保留门清/硬胡潜力的收益高于副露"
                f"（PASS EV={best.net_ev:.2f} > "
                f"{top_call.action.action_type.value} EV={top_call.net_ev:.2f}）"
            )
        return "过牌等待进张"

    # 役牌碰优先说明已锁定的固有胡与番数。
    if best.action.action_type == ActionType.PONG and "碰牌锁定" in (best.note or ""):
        premium = next(
            p for p in best.note.split("；") if p.startswith("碰牌锁定")
        )
        return f"推荐碰：{premium}（净 EV={best.net_ev:.2f}）"

    # 碰牌优先用激励文案（底胡 + 废牌加速）
    if best.action.action_type == ActionType.PONG and "碰出" in (best.note or ""):
        incent_parts = [
            p
            for p in best.note.split("；")
            if p.startswith("碰出")
            or p.startswith("并可切出")
            or p.startswith("散牌期")
        ]
        if incent_parts:
            return f"推荐碰：{'，'.join(incent_parts)}（净 EV={best.net_ev:.2f}）"
        return f"推荐碰：{best.note}（净 EV={best.net_ev:.2f}）"

    return (
        f"推荐 {best.action.action_type.value}："
        f"净 EV={best.net_ev:.2f}（{best.note}）"
    )
