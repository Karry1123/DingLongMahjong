"""切牌 EV 推荐引擎（进攻 + 无包牌防守净损失）。

对齐 rule.md §5 / §6 与 scoring.calculate_hu_points：
    进攻 EV_attack(D)
        · 听牌 / 一向听：Σ_T (Rem(T)/TotalRem) · (H_final(T) × 庄闲系数)
          庄家系数 ×3，闲家 ×2；进张按自摸估；**无自摸加番、无辣子封顶**。
        · 多向听（≥2 或进张折现为 0）：
          EV_attack ≈ 有效进张×质量权重 + 搭子成型分 + 役牌潜力(×Rem衰减)
                      − 客风占位惩罚 − 向听×25
          另加骨架项：拆唯一雀头重罚、切纯孤张奖励、好形推进奖励；
          绝张/残缺字牌（Rem≤1）潜力归零并优先切除；
          好形时防守损失 ×0.45，避免生张微差逆转拆雀头。
        · 序数孤张靠张中心度：4/5/6 ≫ 3/7 ≫ 2/8 ≫ 1/9（听牌亦生效）；
          百搭≥1 且另有偏张/字牌孤张时，切中张扣罚；
          |ΔNetEV|≤3 近邻簇优先更多进张、其次保留更高中张靠张分。

    防守 NetLoss(k | D)
        = P(Tenpai_k) · P(DealIn_k|D) · RiskWeight(D)
          · max(Loss_ron(k)/2, Loss_ron(k) − Rebate_zimo_others(k))
        RiskWeight = 1 + min(P(DealIn|Tenpai)/0.12, 2)，为策略风险权重。
        Loss：庄对庄/闲对庄/庄对闲全额；闲对闲半额（§6，无包牌）。
        Rebate：放铳结束牌局，避免其余听牌者自摸带来的期望损失。

    净期望
        Net_EV(D) = EV_attack(D) − Σ_k NetLoss(k|D) − Shanten×120

未即时和牌的进张：对下层听牌期望再按「进听+1 手兑现」折现（至少 /2）。
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from app.schemas import Meld, MeldType, PlayerState

from .constants import ALL_TILES, DRAGONS, JOKER, WINDS
from .danger_model import estimate_tile_danger
from .evaluator import check_win_or_shanten, is_complete_win
from .mapper import preprocess_hand
from .pool_tracker import rem_tile as pool_rem_tile
from .scoring import (
    ANKO_SIMPLE_HU,
    ANKO_TERMINAL_HONOR_HU,
    AN_GANG_TERMINAL_HONOR_HU,
    DEFAULT_BASE_HU,
    FAN_DRAGON_PUNG_OR_KONG,
    FAN_SEAT_WIND_PUNG_OR_KONG,
    ZIMO_HU,
    calculate_hu_points,
    calculate_meld_points,
)
from .tenpai_model import estimate_opponents_tenpai

SHANTEN_PENALTY = 120
# 其余听牌者在「本窗口」自摸威胁的先验权重（防守折让）
_ZIMO_THREAT_PRIOR = 0.28
# 杠后岭上补张枚举上限（按 Rem 降序采样，控制嵌套 EV 成本）
_RINSHAN_SAMPLE_CAP = 12
# 未即时和牌的进张：进听后再摸才可能胡，至少再折 1 手
_IISHANTEN_TURN_DISCOUNT = 2

# —— 多向听进攻近似（rule.md §5.3 役牌潜力）——
_UKEIRE_QUALITY_WEIGHT = 1.25  # 有效进张枚数质量权重
_TENPAI_RYANMEN_BASELINE = 8  # 标准两面等待的可摸张数；听牌胡分须计入命中机会
_DEEP_SHANTEN_UNIT = 25  # 多向听内向听档位代价（与 SHANTEN_PENALTY 分工）
_YAKUHAI_SINGLE_POTENTIAL = 10.0  # 役牌孤张保留分（中发白 / 自风）
_YAKUHAI_PAIR_POTENTIAL = 16.0  # 役牌对子（接近刻）
_YAKUHAI_PUNG_POTENTIAL = 22.0  # 已成役牌刻
_SHAPE_PAIR = 8.0
_SHAPE_PUNG = 20.0
_SHAPE_RYANMEN = 10.0
_SHAPE_KANCHAN = 5.0
_SHAPE_PENCHAN = 3.0
_COMPOSITE_KANCHAN_UPGRADE_BONUS = 7.0  # 留 2-4 并摸 5 可形成 4-5 两面
_ANTI_PONG_TERMINAL_BONUS = 3.0  # 场见至少两张幺九，外部最多余一张，无法成碰
_SHAPE_ISOLATED_MID = 1.5
_SHAPE_ISOLATED_TERM = 0.5
_SHAPE_JOKER = 12.0  # 手内「得」百搭
_GUEST_WIND_SINGLE_PENALTY = 12.0  # 无役客风孤张占位价值低，优先切出
_GUEST_WIND_PAIR_PENALTY = 1.5  # 客风对子略扣（不如役牌对）
_GUEST_SUBSTITUTE_HOLD_SCALE = 0.2  # 白板替身客风：有雀头潜力，占位惩罚压到 20%
_SUBSTITUTE_HONOR_KEEP_BONUS = 8.0  # 保留健康白板替身字牌的雀头潜力加分
_ORPHAN_TERMINAL_UKEIRE_SCALE = 0.22  # 纯 1/9 两步靠搭进张泡沫折现
_ORPHAN_TERMINAL_KEEP_PENALTY = 9.0  # 切后仍持无邻张 1/9 的加重占位惩罚

# —— 雀头保护 / 孤张切除 / 好形一向听推进 ——
_JANTOU_BREAK_PENALTY = 20.0  # 拆唯一法定雀头
_ISOLATED_CUT_BONUS = 6.0  # 切出纯孤张（与核心搭子无关）
_TERMINAL_ISO_CUT_BONUS = 7.5  # 切幺九孤张（优先于中张，次于死字牌）
_ORPHAN_TERMINAL_CUT_BONUS = 16.0  # 无任何同花色邻/嵌的 1/9：最优先切除
_DEAD_HONOR_CUT_BONUS = 14.0  # 切绝张/残缺字牌（Rem≤1）
_ISOLATED_KEEP_PENALTY = 4.0  # 切后仍持有序数/字牌孤张
_DEAD_HONOR_KEEP_PENALTY = 8.0  # 切后仍持绝张字牌（加重）
_GOOD_SHAPE_PUSH_BONUS = 10.0  # 好形（刻+两面×2+雀头）推进奖励
_GOOD_SHAPE_DEFENSE_SCALE = 0.45  # 好形时压缩防守过度反应
_MAX_DISCARD_CANDIDATES = 8  # 弱搭填充上限；漂浮孤张全部保留不受挤出
_SEEN_GUEST_WIND_CUT_BONUS = 5.5  # Rem≤2 场见客风：优先切除
_SUBSTITUTE_YAKUHAI_CUT_PENALTY = 9.0  # 切健康白板替身役牌（得≠白）惩罚
_SUBSTITUTE_HONOR_CUT_PENALTY = 12.0  # 切健康白板替身字牌（含客风）惩罚
_HEALTHY_YAKUHAI_CUT_FACTOR = 0.25  # 供给充足的役牌孤张：切除奖励压到 25%
_NEIGHBOR_OF_GOD_KEEP_BONUS = 15.0  # 财神同门 ±1/±2 的孤张顺子连接保留价值

# —— 序数孤张靠张中心度 / 百搭中张保护 / EV 近邻平局 ——
# 保留价值：4/5/6 中张最高；2/8 偏张显著更低（切出奖励 = REF − keep）
_CENTRALITY_KEEP_BY_DIGIT: dict[int, float] = {
    1: 0.0,
    2: 1.5,
    3: 5.0,
    4: 10.0,
    5: 12.0,
    6: 10.0,
    7: 5.0,
    8: 1.5,
    9: 0.0,
}
_CENTRALITY_CUT_REF = 12.0  # 与 5 序数保留分对齐
_CENTRALITY_CUT_SCALE_TENPAI = 0.40  # 听牌：微差纠偏（切 8 ≈ +4.2）
_CENTRALITY_CUT_SCALE_DEEP = 0.55  # 一向听+：加强偏张优先
_JOKER_MID_CUT_PENALTY = 4.5  # 持百搭时切 4/5/6 且另有偏张/字牌孤张
_MID_DIGITS = frozenset({4, 5, 6})
_EV_NEAR_TIE_EPS = 3.0  # |ΔNetEV|≤3 时按进张数 / 保留中张裁决
_GUEST_WITH_HEAD_CUT_BONUS = 24.0  # 已有雀头：无役客风先于幺九清理
_GUEST_WITH_HEAD_HOLD_PENALTY = 18.0
_TERMINAL_EXTENSION_KEEP_BONUS = 6.0
_CENTRAL_SYNERGY_KEEP_BONUS = 12.0
_DEFENSE_RISK_REFERENCE = 0.12  # 高危切牌的风险厌恶尺度，非概率修正

_WIND_CN = {"E": "东风", "S": "南风", "W": "西风", "N": "北风"}
_DRAGON_CN = {"C": "中", "F": "发", "P": "白"}


def calculate_best_discards(
    hand_tiles: list[str],
    dealer_tile: str,
    is_dealer: bool,
    seat_wind: str,
    discarded_tiles: list[str] | None = None,
    melds: Sequence[Meld] | None = None,
    opponents: Sequence[PlayerState] | None = None,
    rem_tiles: Mapping[str, int] | None = None,
    *,
    include_self_gang: bool = True,
    round_wind: str = "E",
) -> dict:
    """枚举暗手切牌，按 Net_EV = 进攻 − 防守净损失 − 向听惩罚 排序。

    Args:
        include_self_gang: 为 True 时附带评估暗杠/补杠候选（岭上补张期望）。
            内部递归评估补张切牌时必须为 False，避免无限递归。

    Returns:
        ``{"best_tile", "candidates", "self_gang_candidates"}``
    """
    meld_list = list(melds or [])
    discarded = list(discarded_tiles or [])
    opp_list = list(opponents or [])
    # discarded_tiles 可能已包含对手牌河；按各牌最大计数合并，避免重复扣 Rem。
    river_counts = Counter(t for o in opp_list for t in o.discards)
    discarded = list((Counter(discarded) | river_counts).elements())

    if seat_wind not in WINDS:
        raise ValueError(f"seat_wind 非法：{seat_wind!r}，须为 E/S/W/N")
    if round_wind not in WINDS:
        raise ValueError(f"round_wind 非法：{round_wind!r}，须为 E/S/W/N")
    if not 0 <= len(meld_list) <= 4:
        raise ValueError(f"melds 长度须在 0..4，当前 {len(meld_list)}")

    needed_melds = 4 - len(meld_list)
    expected_hand = needed_melds * 3 + 2
    if len(hand_tiles) != expected_hand:
        raise ValueError(
            "牌型位不守恒：要求 len(hand_tiles) + 3*len(melds) == 14，"
            f"当前 hand={len(hand_tiles)}, melds={len(meld_list)}"
        )

    meld_phys = [t for m in meld_list for t in m.tiles]
    # 对手公开副露必须计入 Rem（绝张 / 进张权重）；优先用 pool_tracker 全场结果
    opp_meld_phys = [
        t for o in opp_list for m in (o.melds or []) for t in (m.tiles or [])
    ]
    all_meld_phys = meld_phys + opp_meld_phys
    table_rem = (
        dict(rem_tiles)
        if rem_tiles is not None
        else _build_rem_map(hand_tiles, discarded, all_meld_phys, dealer_tile)
    )

    tenpai_probs = estimate_opponents_tenpai(
        opp_list,
        dealer_tile=dealer_tile,
        rem_map=table_rem,
    )
    # 预先估算各对手铳/自摸点数与对我家的 Loss
    opp_threats = [
        _build_opponent_threat(o, dealer_tile, is_dealer) for o in opp_list
    ]

    candidates: list[dict] = []

    discard_pool = _select_discard_candidates(
        hand_tiles=hand_tiles,
        dealer_tile=dealer_tile,
        rem_map=table_rem,
        seat_wind=seat_wind,
        round_wind=round_wind,
    )

    for discard in discard_pool:
        remain_raw = _remove_one(hand_tiles, discard)
        remain_logical = preprocess_hand(remain_raw, dealer_tile)
        shanten = check_win_or_shanten(
            remain_logical, 0, needed_melds=needed_melds
        )

        # 切出 D 后：手牌少一张 D，Rem(D) 相应 +1（供进张权重）
        rem_after = dict(table_rem)
        rem_after[discard] = rem_after.get(discard, 0) + 1

        # 听牌才做胡分/进张穷举；一向听及以上只用进张枚数 + 深向听近似
        light_ukeire = shanten >= 1
        ukeire = _collect_ukeire(
            remain_raw=remain_raw,
            rem_map=rem_after,
            dealer_tile=dealer_tile,
            seat_wind=seat_wind,
            is_dealer=is_dealer,
            needed_melds=needed_melds,
            melds=meld_list,
            light=light_ukeire,
        )
        effective_count = sum(u["rem"] for u in ukeire)
        total_rem = effective_count
        effective_tiles = sorted(
            ({"tile": u["tile"], "rem": int(u["rem"])} for u in ukeire),
            key=lambda x: x["tile"],
        )

        if ukeire and total_rem > 0:
            est_base = round(
                sum(u["rem"] * u["est_base_points"] for u in ukeire) / total_rem
            )
            est_final = round(
                sum(u["rem"] * u["est_final_points"] for u in ukeire) / total_rem
            )
            hard_weight = sum(u["rem"] for u in ukeire if u["is_hard_hu"])
            is_hard_hu = hard_weight * 2 >= total_rem
            ukeire_attack = sum(
                (u["rem"] / total_rem) * u["est_win_points"] for u in ukeire
            )
        else:
            est_base = 0
            est_final = 0
            is_hard_hu = False
            ukeire_attack = 0.0

        # 多向听：进张折现常为 0，改用进张枚数 + 搭子/役牌潜力近似，避免候选进攻分抹平
        use_deep_approx = shanten >= 2 or (
            shanten > 0 and ukeire_attack <= 1e-9
        )
        shape_score = _shape_quality_score(remain_raw, dealer_tile)
        yakuhai_score = _yakuhai_potential_score(
            remain_raw, dealer_tile, seat_wind, table_rem, round_wind
        )
        guest_penalty = _guest_wind_hold_penalty(
            remain_raw, dealer_tile, seat_wind, table_rem, round_wind
        )
        shape_upgrade_bonus = _composite_kanchan_upgrade_bonus(
            hand_tiles, discard, dealer_tile, table_rem
        )
        anti_pong_bonus = _anti_pong_terminal_bonus(
            hand_tiles, discard, dealer_tile, table_rem
        )
        if use_deep_approx:
            quality_ukeire = _deep_quality_ukeire_count(
                remain_raw, ukeire, dealer_tile
            )
            sub_keep = _substitute_honor_keep_bonus(
                remain_raw, dealer_tile, table_rem
            )
            attack_ev = (
                float(quality_ukeire) * _UKEIRE_QUALITY_WEIGHT
                + shape_score
                + yakuhai_score
                + sub_keep
                - guest_penalty
                - max(shanten, 0) * _DEEP_SHANTEN_UNIT
            )
        else:
            # ukeire_attack 是「已经摸中胡张」的条件均值。切牌排序还须计入
            # 摸中机会，否则高胡数的窄听会压过进张更多的两面听。
            overlap = _overlap_pair_ryanmen_shape(hand_tiles, dealer_tile)
            attack_ev = float(ukeire_attack) * (
                effective_count / _TENPAI_RYANMEN_BASELINE
                if shanten == 0 and overlap and discard in overlap["choices"]
                else 1.0
            )
        attack_ev += shape_upgrade_bonus + anti_pong_bonus

        # 骨架调整：雀头锁定、孤张优先、靠张中心度、百搭中张保护
        # delta 以闲家尺度标定，乘以庄闲系数/2 以保持庄≈1.5×闲
        structure = _structure_attack_adjustment(
            hand_before=hand_tiles,
            discard=discard,
            remain_raw=remain_raw,
            dealer_tile=dealer_tile,
            seat_wind=seat_wind,
            open_meld_count=len(meld_list),
            shanten=shanten,
            rem_map=table_rem,
            round_wind=round_wind,
        )
        settle = _settlement_factor(is_dealer)
        attack_ev += float(structure["delta"]) * (settle / 2.0)
        good_shape = bool(structure["good_shape"])
        kept_centrality = _kept_centrality_score(remain_raw, dealer_tile)

        # —— 防守：无包牌净损失 ——
        deal_in_risks: dict[str, float] = {}
        defense_details: dict[str, dict] = {}
        defense_loss = 0.0
        for threat in opp_threats:
            opp = threat["opponent"]
            p_tenpai = float(tenpai_probs.get(opp.seat_wind, 0.0))
            p_dealin = estimate_tile_danger(
                discard, opp, table_rem, dealer_tile, hand_tiles=hand_tiles
            )
            deal_in_risks[opp.seat_wind] = round(p_dealin, 6)

            rebate = _defense_rebate(threat, opp_threats, tenpai_probs)
            # 自摸折让不能把放铳变成收益；至少保留半数即时损失。
            net_unit = max(threat["loss_ron"] * 0.5, threat["loss_ron"] - rebate)
            risk_weight = 1.0 + min(p_dealin / _DEFENSE_RISK_REFERENCE, 2.0)
            defense_loss += p_tenpai * p_dealin * net_unit * risk_weight

            pay_label = (
                "全额"
                if (opp.is_dealer or is_dealer)
                else "半额（闲对闲）"
            )
            defense_details[opp.seat_wind] = {
                "tenpai_prob": round(p_tenpai, 4),
                "deal_in_rate": round(p_dealin, 6),
                "est_ron_points": round(float(threat["ron_points"]), 2),
                "loss_if_deal_in": round(float(threat["loss_ron"]), 2),
                "payment_label": pay_label,
                "is_dealer": bool(opp.is_dealer),
                "risk_weight": round(risk_weight, 4),
            }

        # 好形推进：压缩「生张中张」防守过度反应，避免 0.x 分逆转拆雀头
        if good_shape and shanten > 0 and max(deal_in_risks.values(), default=0) < _DEFENSE_RISK_REFERENCE:
            defense_loss *= _GOOD_SHAPE_DEFENSE_SCALE

        is_safe_all = _is_safe_all(discard, opp_list)

        net_ev = (
            attack_ev
            - defense_loss
            - max(shanten, 0) * SHANTEN_PENALTY
        )

        note = _discard_candidate_note(
            discard=discard,
            remain_raw=remain_raw,
            dealer_tile=dealer_tile,
            seat_wind=seat_wind,
            shanten=shanten,
            effective_count=effective_count,
            use_deep_approx=use_deep_approx,
            shape_score=shape_score,
            yakuhai_score=yakuhai_score,
            structure_note=structure.get("note") or "",
            rem_map=table_rem,
            max_deal_in_rate=max(deal_in_risks.values()) if deal_in_risks else 0.0,
            round_wind=round_wind,
        )
        if _is_completed_sequence_surplus(discard, hand_tiles, dealer_tile):
            dragon = next((t for t in ("C", "F") if t in remain_raw), None)
            head_hint = (
                f"；财神可配{_honor_label(dragon)}作雀头，保留三元番潜力"
                if dragon and dealer_tile in remain_raw else ""
            )
            note = f"切出重叠张 {discard}，锁定完整顺子{head_hint}"
        if shape_upgrade_bonus:
            note += f"；复合搭子改良潜力 +{shape_upgrade_bonus:.1f}（保留嵌搭，进张可升级两面）"
        if anti_pong_bonus:
            note += f"；幺九场见至少两张，无法再被碰，控场安全 +{anti_pong_bonus:.1f}"

        candidates.append(
            {
                "tile": discard,
                "ev_score": round(float(net_ev), 4),
                "attack_ev": round(float(attack_ev), 4),
                "shape_upgrade_bonus": round(shape_upgrade_bonus, 4),
                "anti_pong_safety_bonus": round(anti_pong_bonus, 4),
                "dealer_neighbor_keep_bonus": round(
                    float(structure.get("dealer_neighbor_keep_bonus", 0.0)), 4
                ),
                "defense_loss": round(float(defense_loss), 4),
                "deal_in_risks": deal_in_risks,
                "defense_details": defense_details,
                "is_safe_all": bool(is_safe_all),
                "effective_count": int(effective_count),
                "effective_tiles": effective_tiles,
                "is_hard_hu": bool(is_hard_hu),
                "est_base_points": int(est_base),
                "est_final_points": int(est_final),
                "note": note,
                "shanten": int(shanten),
                "_shanten": shanten,
                "_kept_centrality": float(kept_centrality),
                "_isolate_priority": _isolate_discard_priority(
                    discard, hand_tiles, dealer_tile, seat_wind,
                    round_wind, table_rem,
                ) if shanten > 0 else None,
            }
        )

    if not candidates:
        raise ValueError("无可用切牌候选")

    _apply_seen_guest_dominance(
        candidates, hand_tiles, dealer_tile, seat_wind, round_wind, table_rem,
    )

    # 净 EV 优先；同净 EV 时更低向听、更多进张、更高保留中张分优先
    candidates.sort(
        key=lambda c: (
            c["ev_score"],
            -c["_shanten"],
            c["effective_count"],
            c["_kept_centrality"],
            c["est_base_points"],
        ),
        reverse=True,
    )
    _apply_near_ev_tiebreak(candidates)
    _apply_equal_ukeire_isolate_tiebreak(candidates)
    for c in candidates:
        del c["_shanten"]
        del c["_kept_centrality"]
        del c["_isolate_priority"]

    self_gang_candidates: list[dict] = []
    if include_self_gang:
        self_gang_candidates = _evaluate_self_gang_candidates(
            hand_tiles=hand_tiles,
            melds=meld_list,
            dealer_tile=dealer_tile,
            seat_wind=seat_wind,
            is_dealer=is_dealer,
            discarded_tiles=discarded,
            opponents=opp_list,
            rem_tiles=table_rem,
            round_wind=round_wind,
        )

    best_discard = candidates[0]
    best_action = {
        "action_type": "discard",
        "tile": best_discard["tile"],
        "ev_score": best_discard["ev_score"],
    }
    if self_gang_candidates:
        # 已碰的第四张锁定明杠底胡与岭上补张；无抢杠胡模型时默认优先补杠。
        # 原始 ev_score 保留供 UI 对照，动作选择权重单独计算，避免伪造净 EV。
        best_gang = max(
            self_gang_candidates,
            key=lambda g: max(
                float(g["ev_score"]) + (12.0 if g["action_type"] == "bu_gang" else 0.0),
                float(best_discard["ev_score"]) + 1.0 if g["action_type"] == "bu_gang" else float(g["ev_score"]),
            ),
        )
        selection_ev = max(
            float(best_gang["ev_score"]) + (12.0 if best_gang["action_type"] == "bu_gang" else 0.0),
            float(best_discard["ev_score"]) + 1.0 if best_gang["action_type"] == "bu_gang" else float(best_gang["ev_score"]),
        )
        if selection_ev > float(best_discard["ev_score"]):
            best_action = {
                "action_type": best_gang["action_type"],
                "tile": best_gang["tile"],
                "ev_score": best_gang["ev_score"],
            }

    return {
        "best_tile": best_discard["tile"],
        "best_action": best_action,
        "candidates": candidates,
        "self_gang_candidates": self_gang_candidates,
    }


def evaluate_rinshan_then_discard(
    *,
    hand_tiles: list[str],
    melds: Sequence[Meld],
    dealer_tile: str,
    seat_wind: str,
    is_dealer: bool,
    discarded_tiles: list[str] | None = None,
    opponents: Sequence[PlayerState] | None = None,
    rem_tiles: Mapping[str, int] | None = None,
    round_wind: str = "E",
) -> float:
    """杠后：枚举岭上补张，再对 待切手 做切牌 EV，按 Rem 加权。"""
    meld_list = list(melds or [])
    discarded = list(discarded_tiles or [])
    opp_list = list(opponents or [])
    meld_phys = [t for m in meld_list for t in m.tiles]
    opp_meld_phys = [
        t for o in opp_list for m in (o.melds or []) for t in (m.tiles or [])
    ]
    all_meld_phys = meld_phys + opp_meld_phys
    rem_map = (
        dict(rem_tiles)
        if rem_tiles is not None
        else _build_rem_map(hand_tiles, discarded, all_meld_phys, dealer_tile)
    )
    total = 0
    acc = 0.0
    sampled = 0
    # 按剩余枚数降序，优先高权重补张（控制嵌套 EV 成本）
    ordered = sorted(
        ((t, int(rem_map.get(t, 0))) for t in ALL_TILES),
        key=lambda x: -x[1],
    )
    for tile, rem in ordered:
        if rem <= 0:
            continue
        trial = hand_tiles + [tile]
        rem_after = dict(rem_map)
        rem_after[tile] = rem - 1
        try:
            result = calculate_best_discards(
                hand_tiles=trial,
                dealer_tile=dealer_tile,
                is_dealer=is_dealer,
                seat_wind=seat_wind,
                discarded_tiles=discarded,
                melds=meld_list,
                opponents=opp_list,
                rem_tiles=rem_after,
                include_self_gang=False,
                round_wind=round_wind,
            )
        except ValueError:
            continue
        ev = float(result["candidates"][0]["ev_score"])
        acc += rem * ev
        total += rem
        sampled += 1
        if sampled >= _RINSHAN_SAMPLE_CAP:
            break
    if total <= 0:
        needed = 4 - len(meld_list)
        shanten = check_win_or_shanten(
            preprocess_hand(hand_tiles, dealer_tile),
            0,
            needed_melds=needed,
        )
        return float(-max(shanten, 0) * SHANTEN_PENALTY)
    return acc / total


def _evaluate_self_gang_candidates(
    *,
    hand_tiles: list[str],
    melds: list[Meld],
    dealer_tile: str,
    seat_wind: str,
    is_dealer: bool,
    discarded_tiles: list[str],
    opponents: list[PlayerState],
    rem_tiles: Mapping[str, int],
    round_wind: str = "E",
) -> list[dict]:
    """评估暗杠/补杠：锁入高额杠分 + 岭上补张后再切的期望。"""
    from .action_generator import ActionType, get_legal_turn_actions

    out: list[dict] = []
    for action in get_legal_turn_actions(hand_tiles, melds, dealer_tile):
        if action.action_type not in (ActionType.AN_GANG, ActionType.BU_GANG):
            continue
        face = action.tiles[0] if action.tiles else ""
        if not face:
            continue
        try:
            new_hand, new_melds, hu_bonus, label = _apply_self_gang_for_eval(
                hand_tiles, melds, action, dealer_tile
            )
        except ValueError:
            continue

        rinshan_ev = evaluate_rinshan_then_discard(
            hand_tiles=new_hand,
            melds=new_melds,
            dealer_tile=dealer_tile,
            seat_wind=seat_wind,
            is_dealer=is_dealer,
            discarded_tiles=discarded_tiles,
            opponents=opponents,
            rem_tiles=rem_tiles,
            round_wind=round_wind,
        )
        # 杠分相对「不杠」的增量，按庄闲系数折入进攻侧（粗估即时锁定）
        settle = 3.0 if is_dealer else 2.0
        bonus_ev = float(hu_bonus) * settle * 0.35
        net = float(rinshan_ev) + bonus_ev
        out.append(
            {
                "action_type": action.action_type.value,
                "tile": face,
                "tiles": list(action.tiles),
                "ev_score": round(net, 4),
                "attack_ev": round(float(rinshan_ev) + bonus_ev, 4),
                "defense_loss": 0.0,
                "est_hu_bonus": int(hu_bonus),
                "note": (
                    f"{label}锁定 +{hu_bonus} 胡；"
                    f"岭上补张后再切期望 {rinshan_ev:.2f}"
                ),
            }
        )

    out.sort(key=lambda c: c["ev_score"], reverse=True)
    return out


def _apply_self_gang_for_eval(
    hand_tiles: list[str],
    melds: list[Meld],
    action,
    dealer_tile: str,
) -> tuple[list[str], list[Meld], int, str]:
    """模拟暗杠/补杠后的手牌与副露，并返回相对不杠的胡数增量。"""
    from .action_generator import ActionType

    face = action.tiles[0]
    hand = list(hand_tiles)
    meld_list = list(melds)

    if action.action_type == ActionType.AN_GANG:
        if face == dealer_tile:
            raise ValueError("得不可暗杠")
        for _ in range(4):
            if face not in hand:
                raise ValueError(f"暗杠缺少 {face}")
            hand.remove(face)
        new_meld = Meld(meld_type=MeldType.AN_GANG, tiles=[face] * 4)
        gang_hu = int(calculate_meld_points(new_meld, dealer_tile))
        # 不杠时四张按暗刻计（§5.2.7）
        anko_hu = (
            ANKO_TERMINAL_HONOR_HU
            if gang_hu >= AN_GANG_TERMINAL_HONOR_HU
            else ANKO_SIMPLE_HU
        )
        return hand, meld_list + [new_meld], gang_hu - anko_hu, "暗杠"

    if action.action_type == ActionType.BU_GANG:
        if face == dealer_tile:
            raise ValueError("得不可补杠")
        if face not in hand:
            raise ValueError(f"补杠缺少 {face}")
        hand.remove(face)
        upgraded = False
        new_melds: list[Meld] = []
        for m in meld_list:
            mtype = (
                m.meld_type.value
                if hasattr(m.meld_type, "value")
                else str(m.meld_type)
            )
            if (
                not upgraded
                and mtype in ("pong", "peng")
                and m.tiles
                and m.tiles[0] == face
            ):
                new_melds.append(
                    Meld(meld_type=MeldType.MING_GANG, tiles=[face] * 4)
                )
                upgraded = True
            else:
                new_melds.append(m)
        if not upgraded:
            raise ValueError(f"无对应碰可补杠 {face}")
        pong_hu = int(
            calculate_meld_points(
                Meld(meld_type=MeldType.PONG, tiles=[face] * 3), dealer_tile
            )
        )
        gang_hu = int(
            calculate_meld_points(
                Meld(meld_type=MeldType.MING_GANG, tiles=[face] * 4),
                dealer_tile,
            )
        )
        return hand, new_melds, gang_hu - pong_hu, "补杠"

    raise ValueError(f"非自家杠动作：{action.action_type}")


# ---------------------------------------------------------------------------
# 防守：对手点数 / 支付 / 折让
# ---------------------------------------------------------------------------

def _build_opponent_threat(
    opponent: PlayerState,
    dealer_tile: str,
    self_is_dealer: bool,
) -> dict[str, Any]:
    """可见副露估算对手铳/自摸点数，及对我家的 Loss。"""
    ron_pts, zimo_pts = _estimate_opponent_hu_points(opponent, dealer_tile)
    loss_ron = _payment_loss(ron_pts, opponent.is_dealer, self_is_dealer)
    loss_zimo = _payment_loss(zimo_pts, opponent.is_dealer, self_is_dealer)
    return {
        "opponent": opponent,
        "ron_points": ron_pts,
        "zimo_points": zimo_pts,
        "loss_ron": loss_ron,
        "loss_zimo": loss_zimo,
    }


def _estimate_opponent_hu_points(
    opponent: PlayerState, dealer_tile: str
) -> tuple[float, float]:
    """EstPoints：H_base(10) + 副露胡头，再 ×2^(役牌/门风翻)。

    点炮无自摸 +2；自摸威胁另加 ZIMO_HU（仍不加番）。
    """
    meld_fu = sum(
        calculate_meld_points(m, dealer_tile) for m in opponent.melds
    )
    fan = _visible_yakuhai_fan(opponent, dealer_tile)
    mult = 2 ** fan
    tile_part = DEFAULT_BASE_HU + meld_fu
    ron = float(tile_part * mult)
    zimo = float((tile_part + ZIMO_HU) * mult)
    return ron, zimo


def _visible_yakuhai_fan(opponent: PlayerState, dealer_tile: str) -> int:
    """中发白刻/杠各 +1；门风刻/杠 +1。"""
    fan = 0
    for meld in opponent.melds:
        if meld.meld_type == MeldType.CHI:
            continue
        if not meld.tiles:
            continue
        identity = _logical_tile(meld.tiles[0], dealer_tile)
        if identity in ("C", "F", "P"):
            fan += FAN_DRAGON_PUNG_OR_KONG
        if identity == opponent.seat_wind:
            fan += FAN_SEAT_WIND_PUNG_OR_KONG
    return fan


def _payment_loss(
    points: float, opp_is_dealer: bool, self_is_dealer: bool
) -> float:
    """§6 非对称支付（无包牌）：庄相关全额，闲对闲半额。"""
    if opp_is_dealer or self_is_dealer:
        return float(points)
    return float(points) / 2.0


def _defense_rebate(
    target: dict[str, Any],
    all_threats: list[dict[str, Any]],
    tenpai_probs: Mapping[str, float],
) -> float:
    """放铳给 target 后，阻断其余听牌者自摸的期望损失（防守折让补偿）。"""
    rebate = 0.0
    target_wind = target["opponent"].seat_wind
    for other in all_threats:
        ow = other["opponent"].seat_wind
        if ow == target_wind:
            continue
        p_t = float(tenpai_probs.get(ow, 0.0))
        rebate += p_t * _ZIMO_THREAT_PRIOR * float(other["loss_zimo"])
    return rebate


def _is_safe_all(tile: str, opponents: Sequence[PlayerState]) -> bool:
    """是否对当前所有对手均为现物（无对手时视为 True）。"""
    if not opponents:
        return True
    return all(tile in o.discards for o in opponents)


def _logical_tile(tile: str, dealer_tile: str) -> str:
    """物理牌 → 逻辑身份（情况 A：P → dealer_tile）。"""
    if dealer_tile == "P":
        return tile
    if tile == "P":
        return dealer_tile
    return tile


def _identity_supply_rem(
    identity: str,
    dealer_tile: str,
    rem_map: Mapping[str, int],
) -> int:
    """逻辑身份后续可摸入的物理供给 Rem。

    情况 A（得 ≠ 白）：``identity == dealer_tile`` 时，墙中同名得牌为百搭，
    **仅白板 P** 能再提供该身份 → 必须读 ``Rem(P)``，严禁用 ``Rem(得)``。
    """
    if dealer_tile != "P" and identity == dealer_tile:
        return int(rem_map.get("P", 0))
    return int(rem_map.get(identity, 0))


def _is_whiteboard_substitute(tile: str, dealer_tile: str) -> bool:
    """物理白板是否正承担得牌替身（情况 A）。"""
    return dealer_tile != "P" and tile == "P"


def _existing_pair_count(hand_tiles: list[str], dealer_tile: str) -> int:
    """现成实牌对子数；不把百搭或已成刻子的三张当备用雀头。"""
    return sum(n == 2 for t, n in _hand_identity_counts(hand_tiles, dealer_tile).items()
               if t != JOKER)


def _has_established_structure(hand_tiles: list[str], dealer_tile: str) -> bool:
    """已有实牌对子或暗刻，不需非本门风单张博雀头。"""
    return any(n >= 2 for t, n in _hand_identity_counts(hand_tiles, dealer_tile).items()
               if t != JOKER)


def _is_guest_wind_single(
    tile: str, hand_tiles: list[str], dealer_tile: str,
    seat_wind: str, round_wind: str,
) -> bool:
    """非本门风、非圈风的客风单张。"""
    return (
        tile in WINDS
        and tile in hand_tiles
        and tile not in (dealer_tile, seat_wind, round_wind)
        and _hand_identity_counts(hand_tiles, dealer_tile).get(tile, 0) == 1
    )


def _terminal_has_extension(
    tile: str, hand_tiles: list[str], dealer_tile: str,
    rem_map: Mapping[str, int],
) -> bool:
    """仅距三格的同色单张提供弱延伸；远端对子及距四格不算联系。"""
    if not _is_orphan_terminal_tile(tile, hand_tiles, dealer_tile):
        return False
    identity = _logical_tile(tile, dealer_tile)
    digit, suit = int(identity[0]), identity[1]
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    related = any(
        counts.get(f"{d}{suit}", 0) == 1
        for d in range(1, 10) if abs(d - digit) == 3
    )
    bridges = (2, 3) if digit == 1 else (7, 8)
    return related and any(
        _identity_supply_rem(f"{d}{suit}", dealer_tile, rem_map) > 0
        for d in bridges
    )


def _isolate_discard_priority(
    tile: str, hand_tiles: list[str], dealer_tile: str,
    seat_wind: str, round_wind: str, rem_map: Mapping[str, int],
) -> int | None:
    """孤张顺位：已有对子时的熟/生客风 > 无直接联系幺九 > 中张。"""
    if _is_guest_wind_single(tile, hand_tiles, dealer_tile, seat_wind, round_wind):
        if not _has_established_structure(hand_tiles, dealer_tile):
            return None
        return 3 if int(rem_map.get(tile, 0)) <= 2 else 2
    identity = _logical_tile(tile, dealer_tile)
    if (tile != dealer_tile and len(identity) == 2
            and identity[1] in ("m", "p", "s")
            and (_is_floating_isolated_tile(tile, hand_tiles, dealer_tile)
                 or (int(identity[0]) in _MID_DIGITS
                     and _is_pure_isolated_tile(tile, hand_tiles, dealer_tile)))):
        return int(_is_orphan_terminal_tile(tile, hand_tiles, dealer_tile))
    return None


# ---------------------------------------------------------------------------
# 切牌候选前置剪枝
# ---------------------------------------------------------------------------

def _select_discard_candidates(
    *,
    hand_tiles: list[str],
    dealer_tile: str,
    rem_map: Mapping[str, int],
    seat_wind: str,
    round_wind: str = "E",
) -> list[str]:
    """生成切牌候选（别名：generate_candidate_discards）。

    规则：
    - 绝对剔除「得」dealer_tile
    - **必须入选**：漂浮孤张（无 ±1/±2 靠搭，含字牌/幺九/废中张）
    - **必须入选**：完整顺子中的多余同名张（如 2344 且另有雀头候选）
    - 次选：嵌张/边张弱搭子端点
    - 漂浮孤张全部保留，禁止被 max 截断挤掉（如 F、9p）
    """
    return generate_candidate_discards(
        hand_tiles=hand_tiles,
        dealer_tile=dealer_tile,
        rem_map=rem_map,
        seat_wind=seat_wind,
        round_wind=round_wind,
    )


def generate_candidate_discards(
    *,
    hand_tiles: list[str],
    dealer_tile: str,
    rem_map: Mapping[str, int],
    seat_wind: str,
    round_wind: str = "E",
) -> list[str]:
    """切牌候选生成器：漂浮孤张必留、得剔除、弱搭子次选。"""
    unique = [t for t in dict.fromkeys(hand_tiles) if t != dealer_tile]
    if not unique:
        return list(dict.fromkeys(hand_tiles))[:_MAX_DISCARD_CANDIDATES]
    # 两组以上副露时暗手最多 8 张，穷举所有物理切牌很便宜。
    # 局部孤张剪枝会把 445 中的重叠对子误当作不可切的成型雀头。
    if len(hand_tiles) <= 8:
        return unique

    must: list[str] = []
    weak: list[str] = []
    rest: list[str] = []

    for t in unique:
        if (_is_floating_isolated_tile(t, hand_tiles, dealer_tile)
                or _is_completed_sequence_surplus(t, hand_tiles, dealer_tile)):
            must.append(t)
        elif (_is_weak_taatsu_edge(t, hand_tiles, dealer_tile)
              or _is_composite_kanchan_split_candidate(t, hand_tiles, dealer_tile)):
            weak.append(t)
        else:
            rest.append(t)

    must = list(dict.fromkeys(must))
    weak = list(dict.fromkeys(weak))
    rest = list(dict.fromkeys(rest))

    def urgency(tile: str) -> tuple:
        return _discard_cut_urgency(
            tile, hand_tiles, dealer_tile, rem_map, seat_wind, round_wind
        )

    must.sort(key=urgency)
    weak.sort(key=urgency)
    rest.sort(key=urgency)

    # 有漂浮孤张 / 弱搭时：禁止再拆对子或成型面子
    out = list(must)
    for t in weak:
        if t in out:
            continue
        # 孤张全部保留；弱搭填到上限
        if len(out) >= max(_MAX_DISCARD_CANDIDATES, len(must)):
            break
        out.append(t)

    if out:
        return out

    # 无明显废牌：按紧迫度取上限（可含多余对子）
    return sorted(unique, key=urgency)[:_MAX_DISCARD_CANDIDATES]


def _is_completed_sequence_surplus(
    tile: str, hand_tiles: list[str], dealer_tile: str,
) -> bool:
    """完整顺子已用去一张同名牌时，另一张可切；须有其他雀头来源。

    例如 2344 条 + 财神 + 发：切一张 4 条仍留 234 顺子，
    财神可配发作雀头。候选先入池，最终仍由真实胡分与放铳 EV 裁决。
    """
    if tile == dealer_tile or len(tile) != 2 or tile[1] not in "mps":
        return False
    if hand_tiles.count(tile) < 2:
        return False
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    alternate_head = any(
        identity not in (tile, JOKER) and count >= 2
        for identity, count in counts.items()
    ) or (
        counts[JOKER] >= 1
        and any(identity not in (tile, JOKER) and count >= 1
                for identity, count in counts.items())
    )
    if not alternate_head:
        return False
    digit, suit = int(tile[0]), tile[1]
    return any(
        all(counts[f"{n}{suit}"] > 0 for n in range(start, start + 3)
            if n != digit)
        for start in range(max(1, digit - 2), min(7, digit) + 1)
    )


def _is_floating_isolated_tile(
    tile: str, hand_tiles: list[str], dealer_tile: str
) -> bool:
    """真正漂浮孤张：单张，且无同花色 ±1 / ±2 靠搭（字牌单张恒为孤张）。

    与「仅无 ±1」的纯孤张不同：嵌张端点（6m-8m）不算漂浮孤张，
    避免把弱搭子误当成必须优先切的废牌并挤掉 F/9p。
    """
    identity = (
        JOKER
        if tile == dealer_tile
        else _logical_tile(tile, dealer_tile)
    )
    if identity == JOKER:
        return False
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    if int(counts.get(identity, 0)) != 1:
        return False
    if identity in WINDS or identity in DRAGONS:
        return True
    if len(identity) != 2 or identity[1] not in ("m", "p", "s"):
        return False
    digit = int(identity[0])
    suit = identity[1]
    for d in (digit - 2, digit - 1, digit + 1, digit + 2):
        if 1 <= d <= 9 and int(counts.get(f"{d}{suit}", 0)) > 0:
            return False
    return True


def _is_orphan_terminal_tile(
    tile: str, hand_tiles: list[str], dealer_tile: str
) -> bool:
    """无任何同花色邻张/嵌张的 1/9 幺九孤张（最劣质两步靠搭）。"""
    identity = (
        JOKER
        if tile == dealer_tile
        else _logical_tile(tile, dealer_tile)
    )
    if len(identity) != 2 or identity[1] not in ("m", "p", "s"):
        return False
    if identity[0] not in ("1", "9"):
        return False
    return _is_floating_isolated_tile(tile, hand_tiles, dealer_tile)


def _is_orphan_terminal_foam_wait(
    wait: str, remain_raw: list[str], dealer_tile: str
) -> bool:
    """进张是否仅为无邻张 1/9 服务的两步靠搭泡沫（如单 9m 的 7m/8m）。"""
    if len(wait) != 2 or wait[1] not in ("m", "p", "s"):
        return False
    wd = int(wait[0])
    ws = wait[1]
    hit_orphan = False
    hit_other = False
    for t in remain_raw:
        if t == dealer_tile:
            continue
        identity = _logical_tile(t, dealer_tile)
        if len(identity) != 2 or identity[1] != ws:
            continue
        digit = int(identity[0])
        if abs(digit - wd) not in (1, 2):
            continue
        if _is_orphan_terminal_tile(t, remain_raw, dealer_tile):
            hit_orphan = True
        else:
            hit_other = True
    return hit_orphan and not hit_other


def _deep_quality_ukeire_count(
    remain_raw: list[str],
    ukeire: Sequence[Mapping[str, Any]],
    dealer_tile: str,
) -> float:
    """多向听进张质量：压低纯 1/9 两步靠搭泡沫。"""
    total = 0.0
    for u in ukeire:
        rem = float(u["rem"])
        tile = str(u["tile"])
        if _is_orphan_terminal_foam_wait(tile, remain_raw, dealer_tile):
            rem *= _ORPHAN_TERMINAL_UKEIRE_SCALE
        total += rem
    return total


def _substitute_honor_keep_bonus(
    hand_tiles: list[str],
    dealer_tile: str,
    rem_map: Mapping[str, int] | None = None,
) -> float:
    """保留健康白板替身字牌的雀头/成对潜力加分。"""
    if dealer_tile == "P" or "P" not in hand_tiles:
        return 0.0
    rem = rem_map or {}
    rem_n = _identity_supply_rem(dealer_tile, dealer_tile, rem)
    if rem_n < 2:
        return 0.0
    return _SUBSTITUTE_HONOR_KEEP_BONUS


def _is_extra_pair_tile(
    tile: str, hand_tiles: list[str], dealer_tile: str
) -> bool:
    """对子中的一张：允许多余对子进入候选（深向听可考虑拆）。"""
    identity = (
        JOKER
        if tile == dealer_tile
        else _logical_tile(tile, dealer_tile)
    )
    if identity == JOKER:
        return False
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    return int(counts.get(identity, 0)) == 2


def _overlap_pair_ryanmen_shape(
    hand_tiles: list[str], dealer_tile: str,
) -> dict[str, Any] | None:
    """识别独立雀头 + XX(X±1)；X 可拆出两面，邻张可拆成对子听。"""
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    if counts[JOKER]:
        return None
    pairs = [t for t, n in counts.items() if n == 2]
    if len(pairs) != 2:
        return None
    for overlap in pairs:
        if len(overlap) != 2 or overlap[1] not in "mps":
            continue
        digit, suit = int(overlap[0]), overlap[1]
        neighbors = []
        for n in (digit - 1, digit + 1):
            if not 1 <= n <= 9 or counts[f"{n}{suit}"] != 1:
                continue
            if min(digit, n) == 1 or max(digit, n) == 9:
                continue  # 12 / 89 是边搭，不能按标准两面等待估值
            # 已被完整顺子占用的邻张不能视作 XXY 中的浮动搭子。
            in_sequence = any(
                all(counts[f"{k}{suit}"] > 0 for k in range(start, start + 3))
                for start in range(max(1, n - 2), min(7, n) + 1)
            )
            if not in_sequence:
                neighbors.append(f"{n}{suit}")
        if neighbors:
            return {"head": next(t for t in pairs if t != overlap),
                    "choices": {overlap, *neighbors}}
    return None


def _is_weak_taatsu_edge(
    tile: str, hand_tiles: list[str], dealer_tile: str
) -> bool:
    """嵌张边张（有 ±2 无 ±1）或边张搭子端点，视为弱搭子可切候选。"""
    identity = (
        JOKER
        if tile == dealer_tile
        else _logical_tile(tile, dealer_tile)
    )
    if identity == JOKER or len(identity) != 2 or identity[1] not in (
        "m",
        "p",
        "s",
    ):
        return False
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    if int(counts.get(identity, 0)) != 1:
        return False
    digit = int(identity[0])
    suit = identity[1]
    has_adj = any(
        1 <= d <= 9 and int(counts.get(f"{d}{suit}", 0)) > 0
        for d in (digit - 1, digit + 1)
    )
    if has_adj:
        return False
    has_kan = any(
        1 <= d <= 9 and int(counts.get(f"{d}{suit}", 0)) > 0
        for d in (digit - 2, digit + 2)
    )
    return bool(has_kan)


def _is_composite_kanchan_split_candidate(
    tile: str, hand_tiles: list[str], dealer_tile: str,
) -> bool:
    """让 1-2-4 / 6-8-9 两端进入切牌候选，保留可改良的嵌张。"""
    if len(tile) != 2 or tile[1] not in 'mps' or tile == dealer_tile:
        return False
    digit, suit = int(tile[0]), tile[1]
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    if digit == 1:
        return bool(counts.get(f"1{suit}") and counts.get(f"2{suit}") and counts.get(f"4{suit}"))
    if digit == 9:
        return bool(counts.get(f"6{suit}") and counts.get(f"8{suit}") and counts.get(f"9{suit}"))
    return False


def _discard_cut_urgency(
    tile: str,
    hand_tiles: list[str],
    dealer_tile: str,
    rem_map: Mapping[str, int],
    seat_wind: str,
    round_wind: str = "E",
) -> tuple:
    """越小越应优先进入候选 / 优先切出。"""
    identity = (
        JOKER
        if tile == dealer_tile
        else _logical_tile(tile, dealer_tile)
    )
    rem_n = (
        4
        if identity == JOKER
        else _identity_supply_rem(identity, dealer_tile, rem_map)
    )
    yakuhai = _yakuhai_identities(dealer_tile, seat_wind, round_wind)
    floating = _is_floating_isolated_tile(tile, hand_tiles, dealer_tile)

    if identity == JOKER:
        return (100, tile)
    priority = _isolate_discard_priority(
        tile, hand_tiles, dealer_tile, seat_wind, round_wind, rem_map
    )
    if priority is not None and priority >= 2:
        return (-priority, tile)
    # 无邻张幺九次于上述客风，仍先于健康白板替身
    if floating and (
        len(identity) == 2
        and identity[1] in ("m", "p", "s")
        and identity[0] in ("1", "9")
    ):
        return (0, tile)
    # 场见/残缺客风：次优先（不含健康白板替身）
    if (
        identity in WINDS
        and identity not in yakuhai
        and rem_n <= 2
        and not (
            _is_whiteboard_substitute(tile, dealer_tile) and rem_n >= 2
        )
    ):
        return (0, tile)
    if _is_honor_identity(identity) and rem_n <= 1:
        return (0, tile)
    # 健康白板替身（役牌或客风）：压后评估
    if _is_whiteboard_substitute(tile, dealer_tile) and rem_n >= 2:
        return (12, tile)
    # 漂浮字牌 / 役牌孤张：必须高优先级评估（禁止被截断漏选）
    if floating and identity in WINDS and identity not in yakuhai:
        return (1, tile)
    if floating and identity in yakuhai:
        return (1, tile)
    if floating:
        return (3, tile)
    if _is_pure_isolated_tile(tile, hand_tiles, dealer_tile):
        # 仅无 ±1、但仍有嵌张联系的「半孤张」
        return (5, tile)
    if _is_weak_taatsu_edge(tile, hand_tiles, dealer_tile):
        return (6, tile)
    if identity in WINDS and identity not in yakuhai:
        return (8, tile)
    if _is_extra_pair_tile(tile, hand_tiles, dealer_tile):
        return (15, tile)
    return (50, tile)


# ---------------------------------------------------------------------------
# 多向听：搭子质量 / 役牌潜力 / 客风占位
# ---------------------------------------------------------------------------

def _yakuhai_identities(
    dealer_tile: str, seat_wind: str, round_wind: str = "E",
) -> set[str]:
    """可计翻的役牌逻辑身份：中/发/白 + 门风 + 圈风（§5.3）。"""
    dragons = {"C", "F"}
    # 得=白时，物理 P 即白板役牌；否则 P 已被映射为得牌，不计入白
    if dealer_tile == "P":
        dragons.add("P")
    return dragons | {seat_wind, round_wind}


def _hand_identity_counts(
    hand_tiles: list[str], dealer_tile: str
) -> Counter[str]:
    """物理手牌 → 逻辑身份计数（P 按得映射；得本身仍保留原码便于识别百搭张）。"""
    counts: Counter[str] = Counter()
    for t in hand_tiles:
        if t == dealer_tile:
            # 手内「得」：计为百搭占位，不并入序数搭子/役牌计数
            counts[JOKER] += 1
        else:
            counts[_logical_tile(t, dealer_tile)] += 1
    return counts


def _is_honor_identity(tile: str) -> bool:
    return tile in WINDS or tile in DRAGONS


def _honor_label(tile: str) -> str:
    return _WIND_CN.get(tile) or _DRAGON_CN.get(tile) or tile


def _honor_rem_factor(rem: int) -> float:
    """字牌孤张保留潜力对 Rem 的折现权重。

    Rem≤1：成对/刻希望断绝（摸刻需 2 张），潜力归零；
    Rem=2：残缺，大幅折价；Rem≥3：完整役牌加分。
    """
    if rem <= 1:
        return 0.0
    if rem == 2:
        return 0.4
    return 1.0


def _yakuhai_potential_score(
    hand_tiles: list[str],
    dealer_tile: str,
    seat_wind: str,
    rem_map: Mapping[str, int] | None = None,
    round_wind: str = "E",
) -> float:
    """切后剩余手牌的役牌翻数潜力：孤张/对子/刻子分档加分。

    孤张必须按**身份供给 Rem**衰减（白板替身读 Rem(P)，非 Rem(得)）。
    """
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    yakuhai = _yakuhai_identities(dealer_tile, seat_wind, round_wind)
    rem = rem_map or {}
    score = 0.0
    for tile in yakuhai:
        n = int(counts.get(tile, 0))
        if n >= 3:
            score += _YAKUHAI_PUNG_POTENTIAL
        elif n == 2:
            score += _YAKUHAI_PAIR_POTENTIAL
        elif n == 1:
            if tile == round_wind or _is_guest_wind_single(
                tile, hand_tiles, dealer_tile, seat_wind, round_wind
            ):
                continue  # 圈风/客风单张不赋予隐形保留分；对子/成刻仍按规则估值。
            rem_n = _identity_supply_rem(tile, dealer_tile, rem)
            score += _YAKUHAI_SINGLE_POTENTIAL * _honor_rem_factor(rem_n)
    return score


def _guest_wind_hold_penalty(
    hand_tiles: list[str],
    dealer_tile: str,
    seat_wind: str,
    rem_map: Mapping[str, int] | None = None,
    round_wind: str = "E",
) -> float:
    """持有无役客风的占位惩罚（保留价值≈0，应优先切出）。

    Rem 越低惩罚越重：绝张客风视作死废牌占位。
    白板替身客风（得为客风且手中持 P）：有成对雀头潜力，惩罚大幅下调。
    """
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    rem = rem_map or {}
    has_sub_tile = "P" in hand_tiles and dealer_tile != "P"
    penalty = 0.0
    for wind in WINDS:
        if wind == seat_wind:
            continue
        n = int(counts.get(wind, 0))
        if wind == round_wind:
            continue
        if n == 1:
            rem_n = _identity_supply_rem(wind, dealer_tile, rem)
            # Rem≤1 → 1.5×；Rem=2 → 1.2×；否则原值
            scale = 1.5 if rem_n <= 1 else (1.2 if rem_n == 2 else 1.0)
            # 白板替身且供给尚可：不当废客风清掉
            if (
                has_sub_tile
                and dealer_tile == wind
                and rem_n >= 2
            ):
                scale *= _GUEST_SUBSTITUTE_HOLD_SCALE
            base = _GUEST_WIND_SINGLE_PENALTY
            if (_has_established_structure(hand_tiles, dealer_tile)
                    and _is_guest_wind_single(
                        wind, hand_tiles, dealer_tile, seat_wind, round_wind)):
                base = _GUEST_WITH_HEAD_HOLD_PENALTY
            penalty += min(base * scale, 15.0)
        elif n >= 2:
            penalty += _GUEST_WIND_PAIR_PENALTY * n
    return penalty


def _shape_quality_score(hand_tiles: list[str], dealer_tile: str) -> float:
    """面子/搭子成型分：刻 > 对 > 两面 > 嵌张 > 边张 > 孤张。"""
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    score = float(counts.get(JOKER, 0)) * _SHAPE_JOKER

    work: Counter[str] = Counter(
        {t: n for t, n in counts.items() if t != JOKER}
    )

    # 刻 / 对（对子残留 1 张可继续组搭）
    for tile, n in list(work.items()):
        if n >= 3:
            kongs = n // 3
            score += kongs * _SHAPE_PUNG
            work[tile] = n % 3
        if work[tile] == 2:
            score += _SHAPE_PAIR
            work[tile] = 1

    # 序数搭子
    for suit in ("m", "p", "s"):
        avail = [int(work.get(f"{d}{suit}", 0)) for d in range(1, 10)]
        # 两面 / 边张：相邻
        for i in range(8):
            while avail[i] > 0 and avail[i + 1] > 0:
                d1, d2 = i + 1, i + 2
                if (d1, d2) in ((1, 2), (8, 9)):
                    score += _SHAPE_PENCHAN
                else:
                    score += _SHAPE_RYANMEN
                avail[i] -= 1
                avail[i + 1] -= 1
        # 嵌张：隔一张
        for i in range(7):
            while avail[i] > 0 and avail[i + 2] > 0:
                score += _SHAPE_KANCHAN
                avail[i] -= 1
                avail[i + 2] -= 1
        for i, n in enumerate(avail):
            if n <= 0:
                continue
            digit = i + 1
            if digit in (1, 9):
                score += n * _SHAPE_ISOLATED_TERM
            else:
                score += n * _SHAPE_ISOLATED_MID

    # 字牌残张：役牌已在潜力分；客风在惩罚项；此处不重复加分
    return score


def _composite_kanchan_upgrade_bonus(
    hand_tiles: list[str], discard: str, dealer_tile: str,
    rem_map: Mapping[str, int],
) -> float:
    """偏好拆除 1-2 保留 2-4：摸入 5 可把嵌搭升级为 4-5 两面。"""
    if len(discard) != 2 or discard[1] not in 'mps':
        return 0.0
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    suit, digit = discard[1], int(discard[0])
    # 1-2-4：拆 1 留 2-4；6-8-9：拆 9 留 6-8 保留进张延展。
    patterns = ((1, 2, 4, 5, 1), (6, 8, 9, 7, 9))
    for low, middle, high, improve, target_discard in patterns:
        if digit != target_discard:
            continue
        if (counts.get(f"{low}{suit}", 0) and counts.get(f"{middle}{suit}", 0)
                and counts.get(f"{high}{suit}", 0)
                and rem_map.get(f"{improve}{suit}", 0) > 0):
            return _COMPOSITE_KANCHAN_UPGRADE_BONUS
    return 0.0


def _anti_pong_terminal_bonus(
    hand_tiles: list[str], discard: str, dealer_tile: str,
    rem_map: Mapping[str, int],
) -> float:
    """至少两张幺九已公开可见时，奖励先打出无法再被碰成刻的牌。"""
    if len(discard) != 2 or discard[1] not in 'mps' or int(discard[0]) not in (1, 9):
        return 0.0
    public_seen = max(
        0, 4 - int(rem_map.get(discard, 0)) - hand_tiles.count(discard)
    )
    return _ANTI_PONG_TERMINAL_BONUS if public_seen >= 2 else 0.0


def _closed_skeleton(
    hand_tiles: list[str], dealer_tile: str
) -> dict[str, Any]:
    """解析暗手骨架：刻/对/两面数、唯一雀头、纯孤张集合。"""
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    work: Counter[str] = Counter(
        {t: n for t, n in counts.items() if t != JOKER}
    )

    mentsu = 0
    pairs: list[str] = []
    for tile, n in list(work.items()):
        if n >= 3:
            k = n // 3
            mentsu += k
            work[tile] = n % 3
        if work[tile] == 2:
            pairs.append(tile)
            work[tile] = 0  # 对子整组锁定为雀头候选，不参与搭子

    ryanmen = 0
    kanchan = 0
    penchan = 0
    isolated: list[str] = []

    for suit in ("m", "p", "s"):
        avail = [int(work.get(f"{d}{suit}", 0)) for d in range(1, 10)]
        for i in range(8):
            while avail[i] > 0 and avail[i + 1] > 0:
                d1, d2 = i + 1, i + 2
                if (d1, d2) in ((1, 2), (8, 9)):
                    penchan += 1
                else:
                    ryanmen += 1
                avail[i] -= 1
                avail[i + 1] -= 1
        for i in range(7):
            while avail[i] > 0 and avail[i + 2] > 0:
                kanchan += 1
                avail[i] -= 1
                avail[i + 2] -= 1
        for i, n in enumerate(avail):
            if n > 0:
                isolated.extend([f"{i + 1}{suit}"] * n)

    # 字牌残余（非对/刻）视为孤张
    for tile, n in work.items():
        if len(tile) == 2 and tile[1] in ("m", "p", "s"):
            continue
        if n > 0:
            isolated.extend([tile] * n)

    taatsu = ryanmen + kanchan + penchan
    return {
        "mentsu": mentsu,
        "pairs": pairs,
        "ryanmen": ryanmen,
        "kanchan": kanchan,
        "penchan": penchan,
        "taatsu": taatsu,
        "isolated": isolated,
        "jokers": int(counts.get(JOKER, 0)),
    }


def _is_pair_locked_skeleton(
    sk: Mapping[str, Any], *, open_meld_count: int
) -> bool:
    """面子/搭子已饱和且仅 1 对 → 该对为法定雀头，不可拆。"""
    pairs = list(sk.get("pairs") or [])
    if len(pairs) != 1:
        return False
    blocks = int(sk["mentsu"]) + int(sk["taatsu"]) + int(open_meld_count)
    # 标准 4 面子：公开+暗刻+搭子 已能凑满「面子位」时，唯一对子即雀头
    return blocks >= 4


def _is_good_push_shape(
    sk: Mapping[str, Any], *, open_meld_count: int
) -> bool:
    """好形：至少 1 暗刻、≥2 两面、恰好 1 雀头（或等价高两面密度）。"""
    if len(sk.get("pairs") or []) != 1:
        return False
    if int(sk["mentsu"]) < 1:
        return False
    if int(sk["ryanmen"]) >= 2:
        return True
    # 1 公开顺 + 暗刻 + 两面×2 也视为好形推进
    return int(open_meld_count) >= 1 and int(sk["taatsu"]) >= 2


def _is_pure_isolated_tile(
    tile: str, hand_tiles: list[str], dealer_tile: str
) -> bool:
    """纯孤张：非对/刻成员，且无同花色 ±1 邻接（字牌单张亦算）。

    不计 ±2 嵌张联系：法定雀头对子上的远邻（如 7s 对 vs 5s）不构成搭子关联。
    """
    identity = (
        JOKER
        if tile == dealer_tile
        else _logical_tile(tile, dealer_tile)
    )
    if identity == JOKER:
        return False
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    if int(counts.get(identity, 0)) != 1:
        return False
    if identity in WINDS or identity in DRAGONS:
        return True
    if len(identity) != 2 or identity[1] not in ("m", "p", "s"):
        return False
    digit = int(identity[0])
    suit = identity[1]
    # 仅两面邻接；对子/刻子占用的远张不阻止「纯孤张」判定
    for d in (digit - 1, digit + 1):
        if 1 <= d <= 9 and int(counts.get(f"{d}{suit}", 0)) > 0:
            return False
    return True


def _joker_physical_count(hand_tiles: list[str], dealer_tile: str) -> int:
    """手内物理「得」张数（百搭充裕度）。"""
    return sum(1 for t in hand_tiles if t == dealer_tile)


def _suit_digit(identity: str) -> int | None:
    """序数牌逻辑编码 → 点数；非序数返回 None。"""
    if len(identity) == 2 and identity[1] in ("m", "p", "s"):
        return int(identity[0])
    return None


def _centrality_keep_score(tile: str, dealer_tile: str) -> float:
    """序数孤张保留价值（Tile Centrality）。字牌/百搭为 0。"""
    identity = (
        JOKER
        if tile == dealer_tile
        else _logical_tile(tile, dealer_tile)
    )
    if identity == JOKER or _is_honor_identity(identity):
        return 0.0
    digit = _suit_digit(identity)
    if digit is None:
        return 0.0
    return float(_CENTRALITY_KEEP_BY_DIGIT.get(digit, 0.0))


def _kept_centrality_score(
    remain_raw: list[str], dealer_tile: str
) -> float:
    """切后剩余无邻接序数单张的靠张保留分之和（含嵌搭中张）。"""
    total = 0.0
    seen: set[str] = set()
    for t in remain_raw:
        if t in seen or t == dealer_tile:
            continue
        seen.add(t)
        if not _is_pure_isolated_tile(t, remain_raw, dealer_tile):
            continue
        total += _centrality_keep_score(t, dealer_tile)
    return total


def _central_synergy_keep_score(
    hand_tiles: list[str], dealer_tile: str, rem_map: Mapping[str, int],
) -> float:
    """中张单张配合同色既有搭子的改良价值，按两面靠张物理供给衰减。"""
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    total = 0.0
    for tile in dict.fromkeys(hand_tiles):
        identity = _logical_tile(tile, dealer_tile)
        digit = _suit_digit(identity)
        if digit not in _MID_DIGITS or not _is_pure_isolated_tile(tile, hand_tiles, dealer_tile):
            continue
        suit = identity[1]
        if not any(counts.get(f"{d}{suit}", 0) and counts.get(f"{d + 1}{suit}", 0)
                   for d in range(1, 9)):
            continue
        supply = sum(_identity_supply_rem(f"{d}{suit}", dealer_tile, rem_map)
                     for d in (digit - 1, digit + 1))
        total += _CENTRAL_SYNERGY_KEEP_BONUS * min(supply / 8.0, 1.0)
    return total


def _neighbor_of_god_keep_score(
    hand_tiles: list[str], dealer_tile: str,
) -> float:
    """孤张序数牌紧邻同门财神时，奖励保留其后续顺子连接潜力。"""
    if len(dealer_tile) != 2 or dealer_tile[1] not in ('m', 'p', 's'):
        return 0.0
    god_digit = int(dealer_tile[0])
    suit = dealer_tile[1]
    counts = _hand_identity_counts(hand_tiles, dealer_tile)
    bonus = 0.0
    for tile in dict.fromkeys(hand_tiles):
        if tile == dealer_tile:
            continue
        identity = _logical_tile(tile, dealer_tile)
        digit = _suit_digit(identity)
        if (digit is None or identity[1] != suit or digit == god_digit
                or abs(digit - god_digit) > 2):
            continue
        if int(counts.get(identity, 0)) != 1:
            continue
        # 只奖励仍可向顺子延伸的漂浮单张，避免重复给既成搭子加分。
        if _is_floating_isolated_tile(tile, hand_tiles, dealer_tile):
            bonus += _NEIGHBOR_OF_GOD_KEEP_BONUS
    return bonus


def _has_cheaper_isolate_alternative(
    hand_tiles: list[str],
    dealer_tile: str,
    *,
    excluding: str,
) -> bool:
    """是否另有更应切的偏张/幺九/字牌漂浮孤张（相对中张）。"""
    for t in dict.fromkeys(hand_tiles):
        if t == excluding or t == dealer_tile:
            continue
        if not _is_floating_isolated_tile(t, hand_tiles, dealer_tile):
            continue
        identity = _logical_tile(t, dealer_tile)
        if _is_honor_identity(identity):
            return True
        digit = _suit_digit(identity)
        if digit is not None and digit not in _MID_DIGITS:
            return True
    return False


def _structure_attack_adjustment(
    *,
    hand_before: list[str],
    discard: str,
    remain_raw: list[str],
    dealer_tile: str,
    seat_wind: str,
    open_meld_count: int,
    shanten: int,
    rem_map: Mapping[str, int] | None = None,
    round_wind: str = "E",
) -> dict[str, Any]:
    """雀头保护 / 孤张切除 / 靠张中心度 / 百搭中张保护 / 好形推进。

    多向听孤张切除顺位（奖励从高到低）：
    已有对子时，无役客风优先于无联系幺九；
    同色延伸联系保留额外价值，健康役牌/白板替身不按客风清理。

    听牌（shanten==0）仍应用序数靠张中心度与百搭中张保护，
    避免「进张胡分微差」逆推切掉核心 5 序数中张。
    """
    if shanten < 0:
        return {"delta": 0.0, "good_shape": False, "note": ""}

    rem = rem_map or {}
    disc_id = (
        JOKER
        if discard == dealer_tile
        else _logical_tile(discard, dealer_tile)
    )
    yakuhai = _yakuhai_identities(dealer_tile, seat_wind, round_wind)
    jokers = _joker_physical_count(hand_before, dealer_tile)
    keep_c = _centrality_keep_score(discard, dealer_tile)
    disc_digit = _suit_digit(disc_id)
    floating = _is_floating_isolated_tile(
        discard, hand_before, dealer_tile
    )
    pure_iso = _is_pure_isolated_tile(discard, hand_before, dealer_tile)

    # —— 听牌：仅靠张中心度 + 百搭中张保护 ——
    if shanten == 0:
        neighbor_bonus = _neighbor_of_god_keep_score(remain_raw, dealer_tile)
        delta = neighbor_bonus
        notes: list[str] = []
        if neighbor_bonus:
            notes.append(f"保留财神邻张顺子连接潜力 +{neighbor_bonus:.1f}")
        if pure_iso or floating:
            if disc_digit is not None:
                delta += (
                    _CENTRALITY_CUT_REF - keep_c
                ) * _CENTRALITY_CUT_SCALE_TENPAI
                if disc_digit in (2, 8):
                    notes.append("切出偏张孤张")
                elif disc_digit in (1, 9):
                    notes.append("切出幺九孤张")
                elif disc_digit in _MID_DIGITS:
                    notes.append("切出中张孤张")
            if (
                jokers >= 1
                and disc_digit in _MID_DIGITS
                and _has_cheaper_isolate_alternative(
                    hand_before, dealer_tile, excluding=discard
                )
            ):
                delta -= _JOKER_MID_CUT_PENALTY
                notes.append("百搭充裕时切出中张")
            elif jokers >= 1 and disc_digit in (2, 8):
                mid_kept = any(
                    _centrality_keep_score(t, dealer_tile) >= 8.0
                    for t in remain_raw
                    if t != dealer_tile
                    and _is_floating_isolated_tile(
                        t, remain_raw, dealer_tile
                    )
                )
                if mid_kept:
                    notes.append("保留中张配合百搭")
        return {
            "delta": float(delta),
            "good_shape": False,
            "note": "；".join(notes),
            "dealer_neighbor_keep_bonus": neighbor_bonus,
        }

    before = _closed_skeleton(hand_before, dealer_tile)
    after = _closed_skeleton(remain_raw, dealer_tile)
    delta = 0.0
    notes = []

    # (1) 拆唯一法定雀头 → 重罚（仅一向听及以内；深向听禁止套用）
    if shanten <= 1 and _is_pair_locked_skeleton(
        before, open_meld_count=open_meld_count
    ):
        head = before["pairs"][0]
        if disc_id == head:
            delta -= _JANTOU_BREAK_PENALTY
            notes.append("拆唯一雀头重罚")
    elif shanten == 1:
        overlap = _overlap_pair_ryanmen_shape(hand_before, dealer_tile)
        if overlap and disc_id == overlap["head"] and any(
            check_win_or_shanten(
                preprocess_hand(_remove_one(hand_before, choice), dealer_tile),
                needed_melds=4 - open_meld_count,
            ) == 0 for choice in overlap["choices"]
        ):
            delta -= _JANTOU_BREAK_PENALTY
            notes.append("拆唯一独立雀头重罚")

    # (2) 切纯孤张：按 Rem / 字牌类别 / 序数中心度分档奖励
    if pure_iso:
        rem_n = _identity_supply_rem(disc_id, dealer_tile, rem)
        is_sub = _is_whiteboard_substitute(discard, dealer_tile)

        if (_has_established_structure(hand_before, dealer_tile)
                and _is_guest_wind_single(
                    discard, hand_before, dealer_tile, seat_wind, round_wind)):
            delta += _GUEST_WITH_HEAD_CUT_BONUS
            if rem_n <= 2:
                delta += _SEEN_GUEST_WIND_CUT_BONUS
            notes.append("已有对子，优先切除无役客风孤张")
        elif _is_honor_identity(disc_id) and rem_n <= 1:
            delta += _DEAD_HONOR_CUT_BONUS
            notes.append("切除绝张字牌")
        elif is_sub and rem_n >= 2:
            # 白板替身（役牌或客风）：严禁当废白/废客风切除
            pen = (
                _SUBSTITUTE_YAKUHAI_CUT_PENALTY
                if disc_id in yakuhai
                else _SUBSTITUTE_HONOR_CUT_PENALTY
            )
            delta -= pen
            notes.append(
                "保留白板替身役牌"
                if disc_id in yakuhai
                else "保留白板替身字牌"
            )
        elif disc_id in WINDS and disc_id not in yakuhai:
            delta += _ISOLATED_CUT_BONUS
            if rem_n <= 2:
                delta += _SEEN_GUEST_WIND_CUT_BONUS
                notes.append("切除场见客风")
            else:
                notes.append("切除纯孤张")
        elif (
            floating
            and disc_id in yakuhai
            and shanten >= 2
            and rem_n <= 2
        ):
            # 仅残缺役牌才按废牌全额切除
            delta += _ISOLATED_CUT_BONUS
            notes.append("切除残缺役牌孤张")
        elif _is_honor_identity(disc_id) and disc_id in yakuhai:
            if rem_n >= 3:
                delta += _ISOLATED_CUT_BONUS * _HEALTHY_YAKUHAI_CUT_FACTOR
                notes.append("切除役牌孤张")
            else:
                factor = 0.7 if rem_n == 2 else 0.35
                delta += _ISOLATED_CUT_BONUS * factor
                notes.append(
                    "切除残缺役牌孤张" if rem_n == 2 else "切除役牌孤张"
                )
        elif disc_digit in (1, 9):
            if _terminal_has_extension(discard, hand_before, dealer_tile, rem):
                delta += _TERMINAL_ISO_CUT_BONUS
                notes.append("切出有同花色延伸靠搭潜力的幺九")
            elif floating and _is_orphan_terminal_tile(
                discard, hand_before, dealer_tile
            ):
                delta += _ORPHAN_TERMINAL_CUT_BONUS
                notes.append("切除无邻张幺九孤张")
            else:
                delta += _TERMINAL_ISO_CUT_BONUS
                notes.append("切除幺九孤张")
        else:
            # 序数孤张：基础切除分 + 偏张相对中张的靠张差
            delta += _ISOLATED_CUT_BONUS
            delta += (
                _CENTRALITY_CUT_REF - keep_c
            ) * _CENTRALITY_CUT_SCALE_DEEP
            if disc_digit in (2, 8):
                notes.append("切除偏张孤张")
            elif disc_digit in _MID_DIGITS:
                notes.append("切除中张孤张")
            else:
                notes.append("切除纯孤张")

        # 百搭充裕：禁止在有偏张/字牌孤张可选时优先切 4/5/6
        if (
            jokers >= 1
            and disc_digit in _MID_DIGITS
            and _has_cheaper_isolate_alternative(
                hand_before, dealer_tile, excluding=discard
            )
        ):
            delta -= _JOKER_MID_CUT_PENALTY
            notes.append("百搭充裕时切出中张")

    # 切后仍持孤张：健康役牌/健康白板替身可豁免；无邻张 1/9 加重；绝张字牌加重
    keep_penalty = 0.0
    dead_keep = 0
    orphan_keep = 0
    other_keep = 0
    for t in after["isolated"]:
        rem_t = _identity_supply_rem(t, dealer_tile, rem)
        if _is_honor_identity(t) and rem_t <= 1:
            dead_keep += 1
        elif t in yakuhai and not _is_guest_wind_single(
            t, remain_raw, dealer_tile, seat_wind, round_wind,
        ):
            continue  # 健康役牌孤张允许保留
        elif (
            dealer_tile != "P"
            and t == dealer_tile
            and rem_t >= 2
            and "P" in remain_raw
        ):
            continue  # 健康白板替身字牌允许保留
        elif (
            len(t) == 2
            and t[0] in ("1", "9")
            and t[1] in ("m", "p", "s")
            and any(
                (
                    x == t
                    or (
                        x == "P"
                        and dealer_tile != "P"
                        and _logical_tile(x, dealer_tile) == t
                    )
                )
                and _is_orphan_terminal_tile(x, remain_raw, dealer_tile)
                and not _terminal_has_extension(x, remain_raw, dealer_tile, rem)
                for x in remain_raw
            )
        ):
            orphan_keep += 1
        else:
            other_keep += 1
    if dead_keep:
        keep_penalty += _DEAD_HONOR_KEEP_PENALTY * min(dead_keep, 3)
    if orphan_keep:
        keep_penalty += _ORPHAN_TERMINAL_KEEP_PENALTY * min(orphan_keep, 2)
    if other_keep:
        keep_penalty += _ISOLATED_KEEP_PENALTY * min(other_keep, 3)
    delta -= keep_penalty
    # 延伸与两面改良不改变向听/进张，只修正远期牌形保留价值。
    for tile in dict.fromkeys(remain_raw):
        if _terminal_has_extension(tile, remain_raw, dealer_tile, rem):
            delta += _TERMINAL_EXTENSION_KEEP_BONUS
    central_synergy = _central_synergy_keep_score(remain_raw, dealer_tile, rem)
    delta += central_synergy
    if central_synergy:
        notes.append(f"保留中张两面改良潜力 +{central_synergy:.1f}")
    neighbor_bonus = _neighbor_of_god_keep_score(remain_raw, dealer_tile)
    delta += neighbor_bonus
    if neighbor_bonus:
        notes.append(f"保留财神邻张顺子连接潜力 +{neighbor_bonus:.1f}")

    # (3) 好形推进奖励
    good = _is_good_push_shape(after, open_meld_count=open_meld_count)
    if good:
        delta += _GOOD_SHAPE_PUSH_BONUS
        notes.append("好形推进")

    return {
        "delta": float(delta),
        "good_shape": bool(good),
        "note": "；".join(notes),
        "dealer_neighbor_keep_bonus": neighbor_bonus,
    }


def _apply_seen_guest_dominance(
    candidates: list[dict], hand_tiles: list[str], dealer_tile: str,
    seat_wind: str, round_wind: str, rem_map: Mapping[str, int],
) -> None:
    """熟客客风在进张、安全性双重支配数牌孤张时修正净 EV。

    不要求手牌已有对子：未听牌时，只要场见客风有更多进张、风险不更高，
    且与数牌孤张处于同一向听档，就应优先跟打熟张。绝不跨向听档覆盖真实进张。
    """
    for guest in candidates:
        tile = guest["tile"]
        if (guest["shanten"] < 1
                or not _is_guest_wind_single(tile, hand_tiles, dealer_tile, seat_wind, round_wind)
                or int(rem_map.get(tile, 0)) > 2):
            continue  # 手牌已有一张，Rem<=2 才能证明另有公开张，Rem=3 仍是生张。
        dominated = [c for c in candidates
                     if len(c["tile"]) == 2 and c["tile"] != dealer_tile
                     and _is_pure_isolated_tile(c["tile"], hand_tiles, dealer_tile)
                     and c["shanten"] == guest["shanten"]
                     and c["effective_count"] <= guest["effective_count"]
                     and c["defense_loss"] >= guest["defense_loss"]
                     and all(guest["deal_in_risks"].get(s, 0) <= risk
                             for s, risk in c["deal_in_risks"].items())]
        if not dominated:
            continue
        # 超出近邻平局窗口，避免后续中心度重排再次将数牌置于客风之前。
        target = max(c["ev_score"] for c in dominated) + _EV_NEAR_TIE_EPS + 1.0
        bonus = round(max(0.0, target - guest["ev_score"]), 4)
        guest["guest_pruning_bonus"] = bonus
        guest["attack_ev"] = round(guest["attack_ev"] + bonus, 4)
        guest["ev_score"] = round(guest["ev_score"] + bonus, 4)
        guest["note"] += f"；场见非本门风优先清理（策略修正 +{bonus:.1f}）"


def _apply_near_ev_tiebreak(
    candidates: list[dict],
    *,
    eps: float = _EV_NEAR_TIE_EPS,
) -> None:
    """净 EV 极近时：优先更多有效进张，其次保留更高中张靠张分。

    在已按 ev_score 降序排好的列表上，把与榜首 |ΔEV|≤eps 的簇
    按 (effective_count, kept_centrality, ev_score) 重排。
    """
    if len(candidates) < 2:
        return
    best_ev = float(candidates[0]["ev_score"])
    cluster: list[dict] = []
    rest: list[dict] = []
    for c in candidates:
        if best_ev - float(c["ev_score"]) <= eps + 1e-9:
            cluster.append(c)
        else:
            rest.append(c)
    if len(cluster) < 2:
        return
    cluster.sort(
        key=lambda c: (
            int(c["effective_count"]),
            float(c.get("_kept_centrality", 0.0)),
            float(c["ev_score"]),
        ),
        reverse=True,
    )
    candidates[:] = cluster + rest


def _apply_equal_ukeire_isolate_tiebreak(candidates: list[dict]) -> None:
    """同向听、同进张时，按客风/数牌孤张顺位决胜。

    仅重排可比孤张原有位置；不同向听、进张及役牌、替身均不参与。
    """
    groups: dict[tuple[int, int], list[int]] = {}
    for i, c in enumerate(candidates):
        if c.get("_isolate_priority") is not None:
            groups.setdefault((c["shanten"], c["effective_count"]), []).append(i)
    for indices in groups.values():
        ranked = sorted(
            (candidates[i] for i in indices),
            key=lambda c: (c["_isolate_priority"], c["ev_score"]),
            reverse=True,
        )
        for i, candidate in zip(indices, ranked):
            candidates[i] = candidate


def _discard_candidate_note(
    *,
    discard: str,
    remain_raw: list[str],
    dealer_tile: str,
    seat_wind: str,
    shanten: int,
    effective_count: int,
    use_deep_approx: bool,
    shape_score: float,
    yakuhai_score: float,
    structure_note: str = "",
    rem_map: Mapping[str, int] | None = None,
    max_deal_in_rate: float = 0.0,
    round_wind: str = "E",
) -> str:
    """生成切牌候选说明（多向听突出客风/役牌/搭子取舍）。"""
    identity = (
        JOKER
        if discard == dealer_tile
        else _logical_tile(discard, dealer_tile)
    )
    rem = rem_map or {}
    rem_n = (
        4
        if identity == JOKER
        else _identity_supply_rem(identity, dealer_tile, rem)
    )
    jokers = _joker_physical_count(
        list(remain_raw) + [discard], dealer_tile
    )
    if "优先切除无役客风" in structure_note:
        suffix = ""
        if "P" in remain_raw and dealer_tile != "P":
            suffix = f"，保留白板（替身{_honor_label(dealer_tile)}）"
        return (
            f"已有 {_existing_pair_count(remain_raw, dealer_tile)} 组对子，"
            f"优先切除无役客风孤张{_honor_label(identity)}，"
            f"保留数牌靠搭与役牌潜力{suffix}"
        )
    if "同花色延伸靠搭" in structure_note:
        return f"{discard} 有同花色延伸靠搭潜力，已有对子时应先清理无役客风"

    # 偏张 + 百搭 + 保留中张：优先专用文案
    if (
        "保留中张配合百搭" in structure_note
        or (
            "切出偏张" in structure_note
            and jokers >= 1
            and any(
                _centrality_keep_score(t, dealer_tile) >= 8.0
                for t in remain_raw
                if t != dealer_tile
                and _is_floating_isolated_tile(t, remain_raw, dealer_tile)
            )
        )
    ):
        mid_keep = next(
            (
                t
                for t in remain_raw
                if t != dealer_tile
                and _centrality_keep_score(t, dealer_tile) >= 8.0
                and _is_floating_isolated_tile(t, remain_raw, dealer_tile)
            ),
            None,
        )
        joker_label = "双「得」" if jokers >= 2 else "「得」"
        mid_label = mid_keep or "中张"
        return (
            f"切出偏张 {discard}，保留核心中张 {mid_label} 配合{joker_label}"
            f"最大化两面靠搭与成型速度"
        )
    if "百搭充裕时切出中张" in structure_note:
        return (
            f"切出中张 {discard} 会浪费百搭弹性（有偏张/字牌孤张可选，不推荐）"
        )

    # 场见客风 + 保留白板替身
    if "切除场见客风" in structure_note or (
        identity in WINDS
        and identity not in (seat_wind, round_wind)
        and rem_n <= 2
        and _is_pure_isolated_tile(
            discard, list(remain_raw) + [discard], dealer_tile
        )
    ):
        # Rem=2 且手持 1 → 场见公开 1 张
        public_seen = max(0, 4 - rem_n - 1)
        wind_cn = _honor_label(identity)
        risk_pct = f"{max_deal_in_rate * 100:.1f}%"
        if "P" in remain_raw and dealer_tile != "P":
            sub_cn = _honor_label(dealer_tile)
            return (
                f"{wind_cn}场见 {public_seen} 张且极度安全（铳率 {risk_pct}），"
                f"白板承接{sub_cn}替身属性具有做刻潜力，优先切出{wind_cn}"
            )
        return (
            f"{wind_cn}场见 {public_seen} 张（铳率 {risk_pct}），"
            f"成对/刻希望低，优先切出熟张客风"
        )
    if "保留白板替身役牌" in structure_note:
        sub_cn = _honor_label(dealer_tile)
        return (
            f"白板承接{sub_cn}替身属性（役牌/做刻潜力），"
            f"有场见客风时应优先切客风而非白板"
        )
    if "保留白板替身字牌" in structure_note:
        sub_cn = _honor_label(dealer_tile)
        return (
            f"白板承接{sub_cn}替身属性（雀头/字牌潜力），"
            f"应优先切无邻张幺九孤张而非白板"
        )
    if (
        "切除无邻张幺九孤张" in structure_note
        or (
            "切除幺九孤张" in structure_note
            and "P" in remain_raw
            and dealer_tile != "P"
        )
    ):
        sub_cn = _honor_label(dealer_tile) if dealer_tile != "P" else ""
        keep_hint = (
            f"，保留白板（承接{sub_cn}替身）的雀头与字牌潜力"
            if sub_cn and "P" in remain_raw
            else "，保留中张靠张与字牌潜力"
        )
        return (
            f"切出无邻张联系的 1/9 幺九孤张 {discard}{keep_hint}"
        )

    # 绝张 / 残缺字牌：优先专用理由
    if _is_honor_identity(identity) and rem_n <= 1:
        seen = 4 - rem_n  # 手+河+副露+公示已占用
        label = _honor_label(identity)
        # 保留的序数孤张靠张提示：优先「纯孤张」幺九（如 9s），勿提已有邻张的 1m
        hand_proxy = list(remain_raw) + [discard]
        keep_terms = [
            t
            for t in remain_raw
            if len(t) == 2
            and t[1] in ("m", "p", "s")
            and t[0] in ("1", "9")
            and _is_pure_isolated_tile(t, hand_proxy, dealer_tile)
        ]
        if not keep_terms:
            keep_terms = [
                t
                for t in remain_raw
                if len(t) == 2
                and t[1] in ("m", "p", "s")
                and t[0] in ("1", "9")
            ]
        keep_hint = ""
        if keep_terms:
            uniq = list(dict.fromkeys(keep_terms))
            keep_hint = f"，保留 {uniq[0]} 靠张空间"
        return (
            f"全场已见 {seen} 张{label}（绝张），无法靠搭且成对概率极低，"
            f"优先切出死废牌{keep_hint}"
        )

    # 客风孤张优先用专用文案（与「纯序数孤张」区分）
    if identity in WINDS and identity not in (seat_wind, round_wind):
        has_complex = shape_score >= (_SHAPE_PAIR + _SHAPE_RYANMEN * 0.5)
        has_yakuhai = yakuhai_score >= _YAKUHAI_SINGLE_POTENTIAL * 0.4
        if has_complex and has_yakuhai:
            return "切出无役客风孤张，保留 2m/3m 复合搭子与中/发役牌潜力"
        parts = ["切出无役客风孤张"]
        if has_complex:
            parts.append("保留序数对子/搭子")
        if has_yakuhai:
            parts.append("保留中/发/自风役牌潜力")
        return "，".join(parts)
    if structure_note and "切除漂浮役牌孤张" in structure_note:
        return "切出漂浮役牌孤张，多向听优先清理废牌"
    if structure_note and "切除残缺役牌孤张" in structure_note:
        return "切出残缺役牌孤张，成刻供给不足优先清理"
    if structure_note and "切除绝张字牌" in structure_note:
        return structure_note
    if structure_note and "切除偏张孤张" in structure_note:
        return "切出偏张孤张，保留中张靠张与雀头/搭子好形"
    if structure_note and "切除纯孤张" in structure_note:
        return "切出纯孤张，保留雀头与两面搭子好形"
    if structure_note and "切除幺九孤张" in structure_note:
        return "切出幺九孤张，保留中张靠张与役牌潜力"
    if structure_note and "拆唯一雀头" in structure_note:
        return "拆唯一雀头破坏一向听骨架（不推荐）"
    if (
        identity in _yakuhai_identities(dealer_tile, seat_wind, round_wind)
        and shanten >= 2
        and _is_floating_isolated_tile(discard, remain_raw + [discard], dealer_tile)
    ):
        return "切出漂浮役牌孤张，多向听优先清理废牌"
    if identity in _yakuhai_identities(dealer_tile, seat_wind, round_wind):
        return f"切出役牌 {identity}（损失翻数潜力）"
    if use_deep_approx:
        extra = f"；{structure_note}" if structure_note else ""
        return (
            f"多向听近似：进张 {effective_count}、搭子 {shape_score:.1f}、"
            f"役牌潜力 {yakuhai_score:.1f}、向听 {shanten}{extra}"
        )
    return structure_note or ""


# ---------------------------------------------------------------------------
# 进攻：有效进张 + calculate_hu_points
# ---------------------------------------------------------------------------

def _collect_ukeire(
    remain_raw: list[str],
    rem_map: Mapping[str, int],
    dealer_tile: str,
    seat_wind: str,
    is_dealer: bool,
    needed_melds: int,
    melds: list[Meld],
    *,
    light: bool = False,
) -> list[dict]:
    """切牌后剩余暗牌的有效进张；胡数来自 ``calculate_hu_points``。

    ``light=True``（一向听及以上）：只统计使向听下降的进张枚数。
    进张判定禁止对「14 张未和」跑全切向听；听牌只做 ``is_complete_win``。
    """
    base_logical = preprocess_hand(remain_raw, dealer_tile)
    base_shanten = check_win_or_shanten(
        base_logical, 0, needed_melds=needed_melds
    )
    settle = _settlement_factor(is_dealer)
    result: list[dict] = []

    scan_tiles = _ukeire_scan_tiles(
        remain_raw, dealer_tile, rem_map, base_shanten=base_shanten
    )

    for tile in scan_tiles:
        rem = int(rem_map.get(tile, 0))
        if rem <= 0:
            continue

        if base_shanten <= 0:
            # 听牌：只认能胡的进张
            trial_logical = preprocess_hand(remain_raw + [tile], dealer_tile)
            if not is_complete_win(trial_logical, 0, needed_melds=needed_melds):
                continue
            new_shanten = -1
        else:
            # 一向听+：摸打后若存在切牌使 13 张向听下降，则计为有效进张
            if not _draw_improves_shanten(
                remain_raw=remain_raw,
                draw_tile=tile,
                dealer_tile=dealer_tile,
                rem_map=rem_map,
                seat_wind=seat_wind,
                needed_melds=needed_melds,
                base_shanten=base_shanten,
            ):
                continue
            new_shanten = base_shanten - 1

        if light or new_shanten > 0:
            result.append(
                {
                    "tile": tile,
                    "rem": rem,
                    "est_win_points": 0.0,
                    "est_base_points": 0,
                    "est_final_points": 0,
                    "is_hard_hu": False,
                }
            )
            continue

        scored = _score_ukeire_tile(
            remain_raw=remain_raw,
            win_tile=tile,
            new_shanten=new_shanten,
            melds=melds,
            seat_wind=seat_wind,
            dealer_tile=dealer_tile,
            rem_map=rem_map,
            needed_melds=needed_melds,
            settle=settle,
        )
        if scored is None:
            continue

        result.append(
            {
                "tile": tile,
                "rem": rem,
                "est_win_points": scored["income"],
                "est_base_points": scored["est_base"],
                "est_final_points": scored["est_final"],
                "is_hard_hu": scored["is_hard_hu"],
            }
        )

    return result


def _draw_improves_shanten(
    *,
    remain_raw: list[str],
    draw_tile: str,
    dealer_tile: str,
    rem_map: Mapping[str, int],
    seat_wind: str,
    needed_melds: int,
    base_shanten: int,
) -> bool:
    """13 张摸入后，是否存在一切使向听严格下降（只试少量切牌，不跑 14 张全枚举）。"""
    trial = list(remain_raw) + [draw_tile]
    # 直接胡
    if is_complete_win(
        preprocess_hand(trial, dealer_tile), 0, needed_melds=needed_melds
    ):
        return True

    pool = _select_discard_candidates(
        hand_tiles=trial,
        dealer_tile=dealer_tile,
        rem_map=rem_map,
        seat_wind=seat_wind,
    )
    # 摸入张本身也允许立刻打出（进张无用时）
    opts = list(dict.fromkeys([draw_tile, *pool]))
    for discard in opts:
        if discard not in trial and discard != draw_tile:
            continue
        try:
            remain13 = _remove_one(trial, discard)
        except ValueError:
            continue
        s = check_win_or_shanten(
            preprocess_hand(remain13, dealer_tile),
            0,
            needed_melds=needed_melds,
        )
        if s < base_shanten:
            return True
    return False


def _ukeire_scan_tiles(
    remain_raw: list[str],
    dealer_tile: str,
    rem_map: Mapping[str, int],
    *,
    base_shanten: int,
) -> list[str]:
    """生成值得检测的进张候选：邻接序数 + 手中相关牌 + 字牌，禁止无脑扫 34。"""
    cands: set[str] = set()
    for t in remain_raw:
        if t == dealer_tile:
            continue
        if int(rem_map.get(t, 0)) > 0:
            cands.add(t)  # 对/刻进张
        if len(t) == 2 and t[1] in ("m", "p", "s"):
            digit = int(t[0])
            suit = t[1]
            for d in (digit - 2, digit - 1, digit + 1, digit + 2):
                if 1 <= d <= 9:
                    code = f"{d}{suit}"
                    if int(rem_map.get(code, 0)) > 0:
                        cands.add(code)

    # 字牌 / 得：听牌或手中相关均放入（含空听自风等常见听口）
    for h in list(WINDS) + list(DRAGONS):
        if int(rem_map.get(h, 0)) > 0:
            cands.add(h)
    if int(rem_map.get(dealer_tile, 0)) > 0:
        cands.add(dealer_tile)

    if not cands:
        return [t for t in ALL_TILES if int(rem_map.get(t, 0)) > 0]
    return list(cands)


def _score_ukeire_tile(
    *,
    remain_raw: list[str],
    win_tile: str,
    new_shanten: int,
    melds: list[Meld],
    seat_wind: str,
    dealer_tile: str,
    rem_map: Mapping[str, int],
    needed_melds: int,
    settle: float,
) -> dict[str, Any] | None:
    if new_shanten < 0:
        hu = _best_hu_points(
            melds=melds,
            hand_tiles=remain_raw,
            win_tile=win_tile,
            seat_wind=seat_wind,
            dealer_tile=dealer_tile,
        )
        if hu is None:
            return None
        final_hu = int(hu["final_hu"])
        return {
            "income": float(final_hu) * settle,
            "est_base": int(hu["tile_hu"]) + int(hu["base_hu"]),
            "est_final": final_hu,
            "is_hard_hu": bool(hu["is_hard_hu"]),
        }

    # new_shanten == 0：进听。直接对 13 张听牌手求胡分期望，禁止再枚举切牌嵌套
    if new_shanten == 0:
        tenpai_hand = remain_raw + [win_tile]
        # 14 张且向听 0 → 需先切一张才是标准听牌；用轻量期望
        expect_full = needed_melds * 3 + 2
        if len(tenpai_hand) == expect_full:
            nested = _tenpai_expected_hu_light(
                hand_tiles=tenpai_hand,
                melds=melds,
                seat_wind=seat_wind,
                dealer_tile=dealer_tile,
                rem_map=rem_map,
                needed_melds=needed_melds,
                settle=settle,
            )
        else:
            nested = _average_win_scores(
                remain_raw=tenpai_hand,
                melds=melds,
                seat_wind=seat_wind,
                dealer_tile=dealer_tile,
                rem_map=rem_map,
                settle=settle,
            )
        if nested is None:
            return {
                "income": 0.0,
                "est_base": 0,
                "est_final": 0,
                "is_hard_hu": False,
            }
        discount = max(new_shanten, 0) + _IISHANTEN_TURN_DISCOUNT
        return {
            "income": nested["income"] / discount,
            "est_base": nested["est_base"],
            "est_final": nested["est_final"],
            "is_hard_hu": nested["is_hard_hu"],
        }

    return {
        "income": 0.0,
        "est_base": 0,
        "est_final": 0,
        "is_hard_hu": False,
    }


def _tenpai_expected_hu_light(
    hand_tiles: list[str],
    melds: list[Meld],
    seat_wind: str,
    dealer_tile: str,
    rem_map: Mapping[str, int],
    needed_melds: int,
    settle: float,
) -> dict[str, Any] | None:
    """14 张进听工作型：只试少数切牌候选，避免全手嵌套。"""
    discard_pool = _select_discard_candidates(
        hand_tiles=hand_tiles,
        dealer_tile=dealer_tile,
        rem_map=rem_map,
        seat_wind=seat_wind,
    )
    best: dict[str, Any] | None = None
    for discard in discard_pool:
        if discard not in hand_tiles:
            continue
        remain = _remove_one(hand_tiles, discard)
        rem_logical = preprocess_hand(remain, dealer_tile)
        if check_win_or_shanten(rem_logical, 0, needed_melds=needed_melds) != 0:
            continue
        nested_rem = dict(rem_map)
        nested_rem[discard] = nested_rem.get(discard, 0) + 1
        avg = _average_win_scores(
            remain_raw=remain,
            melds=melds,
            seat_wind=seat_wind,
            dealer_tile=dealer_tile,
            rem_map=nested_rem,
            settle=settle,
        )
        if avg is None:
            continue
        if best is None or avg["income"] > best["income"]:
            best = avg
    return best


def _tenpai_expected_hu(
    hand_tiles: list[str],
    melds: list[Meld],
    seat_wind: str,
    dealer_tile: str,
    rem_map: Mapping[str, int],
    needed_melds: int,
    settle: float,
) -> dict[str, Any] | None:
    logical = preprocess_hand(hand_tiles, dealer_tile)
    shanten = check_win_or_shanten(logical, 0, needed_melds=needed_melds)

    expect_tenpai = needed_melds * 3 + 1
    if len(hand_tiles) == expect_tenpai and shanten == 0:
        return _average_win_scores(
            remain_raw=hand_tiles,
            melds=melds,
            seat_wind=seat_wind,
            dealer_tile=dealer_tile,
            rem_map=rem_map,
            settle=settle,
        )

    expect_full = needed_melds * 3 + 2
    if len(hand_tiles) != expect_full:
        return None

    return _tenpai_expected_hu_light(
        hand_tiles=hand_tiles,
        melds=melds,
        seat_wind=seat_wind,
        dealer_tile=dealer_tile,
        rem_map=rem_map,
        needed_melds=needed_melds,
        settle=settle,
    )


def _average_win_scores(
    remain_raw: list[str],
    melds: list[Meld],
    seat_wind: str,
    dealer_tile: str,
    rem_map: Mapping[str, int],
    settle: float,
) -> dict[str, Any] | None:
    total_rem = 0
    acc_income = 0.0
    acc_base = 0.0
    acc_final = 0.0
    hard_rem = 0
    needed = 4 - len(melds)

    scan = _ukeire_scan_tiles(
        remain_raw, dealer_tile, rem_map, base_shanten=0
    )

    for tile in scan:
        rem = int(rem_map.get(tile, 0))
        if rem <= 0:
            continue
        trial_logical = preprocess_hand(remain_raw + [tile], dealer_tile)
        if not is_complete_win(trial_logical, 0, needed_melds=needed):
            continue

        hu = _best_hu_points(
            melds=melds,
            hand_tiles=remain_raw,
            win_tile=tile,
            seat_wind=seat_wind,
            dealer_tile=dealer_tile,
        )
        if hu is None:
            continue

        final_hu = int(hu["final_hu"])
        est_base = int(hu["tile_hu"]) + int(hu["base_hu"])
        total_rem += rem
        acc_income += rem * final_hu * settle
        acc_base += rem * est_base
        acc_final += rem * final_hu
        if hu["is_hard_hu"]:
            hard_rem += rem

    if total_rem <= 0:
        return None

    return {
        "income": acc_income / total_rem,
        "est_base": round(acc_base / total_rem),
        "est_final": round(acc_final / total_rem),
        "is_hard_hu": hard_rem * 2 >= total_rem,
    }


def _best_hu_points(
    melds: list[Meld],
    hand_tiles: list[str],
    win_tile: str,
    seat_wind: str,
    dealer_tile: str,
) -> dict[str, Any] | None:
    full = list(hand_tiles) + [win_tile]
    logical = preprocess_hand(full, dealer_tile)
    max_restore = sum(1 for t in logical if t == JOKER)

    best: dict[str, Any] | None = None
    for restored in range(0, max_restore + 1):
        try:
            hu = calculate_hu_points(
                melds=melds,
                hand_tiles=hand_tiles,
                win_tile=win_tile,
                is_zimo=True,
                seat_wind=seat_wind,
                dealer_tile=dealer_tile,
                base_hu=DEFAULT_BASE_HU,
                restored_jokers=restored,
            )
        except ValueError:
            continue
        if best is None or hu["final_hu"] > best["final_hu"]:
            best = hu
    return best


def _settlement_factor(is_dealer: bool) -> float:
    """自摸和牌收入系数：庄 ×3，闲 ×2（§6）。"""
    return 3.0 if is_dealer else 2.0


def _build_rem_map(
    hand_tiles: list[str],
    discarded_tiles: list[str],
    meld_tiles: list[str],
    dealer_tile: str,
) -> dict[str, int]:
    from collections import Counter

    hand_c = Counter(hand_tiles)
    disc_c = Counter(discarded_tiles)
    meld_c = Counter(meld_tiles)
    return {
        t: pool_rem_tile(
            t,
            hand_count=hand_c.get(t, 0),
            discard_count=disc_c.get(t, 0),
            meld_count=meld_c.get(t, 0),
            dealer_tile=dealer_tile,
        )
        for t in ALL_TILES
    }


def rem_tile(
    tile: str,
    hand_tiles: list[str],
    discarded_tiles: list[str],
    dealer_tile: str,
    meld_tiles: list[str] | None = None,
) -> int:
    """兼容旧调用：单张 Rem（结果 ≥0）。"""
    return pool_rem_tile(
        tile,
        hand_count=sum(1 for t in hand_tiles if t == tile),
        discard_count=sum(1 for t in discarded_tiles if t == tile),
        meld_count=sum(1 for t in (meld_tiles or []) if t == tile),
        dealer_tile=dealer_tile,
    )


def _remove_one(tiles: list[str], tile: str) -> list[str]:
    removed = False
    result: list[str] = []
    for t in tiles:
        if not removed and t == tile:
            removed = True
            continue
        result.append(t)
    if not removed:
        raise ValueError(f"手牌中不存在 {tile!r}")
    return result
