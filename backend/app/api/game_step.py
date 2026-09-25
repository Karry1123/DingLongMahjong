"""牌局时序步进：应用 StepEvent，推导下一阶段与推荐。

状态机（rule.md §3 / §7，自驾视角）：
- DRAW → 摸牌方进入 DISCARD；若是自家则给出切牌 EV。
- DISCARD → 若他家打出且自家有吃/碰/杠/胡，进入 CALL；否则下家待摸（WAIT）。
- MELD → 吃/碰后 slots=14 进入 DISCARD；明杠后 slots=13 进入 DRAW（岭上补牌）。
- PASS → 响应结束，打牌方之下家待摸（WAIT）。
"""

from __future__ import annotations

from collections import Counter

from app.core.action_generator import ActionType, get_available_actions
from app.core.call_decision import evaluate_call_decision
from app.core.constants import WINDS
from app.core.ev_engine import calculate_best_discards
from app.core.pool_tracker import get_remaining_tiles
from app.schemas import (
    CallDecisionResponse,
    GameStepRequest,
    GameStepResponse,
    HandRequest,
    Meld,
    MeldType,
    RecommendResponse,
    StepEvent,
)


def next_seat(seat: str) -> str:
    """逆时针下一家。"""
    return WINDS[(WINDS.index(seat) + 1) % 4]


def process_game_step(request: GameStepRequest) -> GameStepResponse:
    """应用事件 → 更新局面 → 返回阶段与推荐。"""
    event = request.event
    # 剥离 event，得到纯局面
    before = HandRequest.model_validate(
        request.model_dump(exclude={"event"})
    )
    after = apply_step_event(before, event)
    return resolve_phase(after, event)


def apply_step_event(state: HandRequest, event: StepEvent) -> HandRequest:
    """按事件更新四方牌河 / 副露 / 自家手牌；返回新 HandRequest。"""
    data = state.model_dump()
    actor = event.actor_seat
    self_seat = state.seat_wind

    if event.event_type == "DRAW":
        _apply_draw(data, actor=actor, self_seat=self_seat, tile=event.tile)
    elif event.event_type == "DISCARD":
        _apply_discard(data, actor=actor, self_seat=self_seat, tile=event.tile)
    elif event.event_type == "MELD":
        assert event.meld is not None
        _apply_meld(
            data,
            actor=actor,
            self_seat=self_seat,
            meld=event.meld,
            claimed_tile=event.tile,
            provider_seat=event.provider_seat or event.meld.provider_seat,
            claimed_discard_index=event.claimed_discard_index,
        )
    elif event.event_type == "PASS":
        # 过牌不改牌面，仅推进时序
        pass
    else:
        raise ValueError(f"未知 event_type：{event.event_type!r}")

    try:
        return HandRequest.model_validate(data)
    except Exception as exc:
        # Pydantic ValidationError → 业务 400
        raise ValueError(f"事件应用后局面非法：{exc}") from exc


def resolve_phase(state: HandRequest, event: StepEvent) -> GameStepResponse:
    """根据事件后局面决定 action_phase / 推荐。"""
    self_seat = state.seat_wind
    actor = event.actor_seat

    if event.event_type == "DRAW":
        if actor == self_seat:
            rec = _recommend_discard(state, win_tile=event.tile)
            return GameStepResponse(
                next_turn_seat=self_seat,
                need_self_action=True,
                action_phase="DISCARD",
                recommend_discard=rec,
                call_decision=None,
                updated_state=state,
                can_self_win=bool(rec.can_self_win),
                self_win_info=rec.self_win_info,
            )
        return GameStepResponse(
            next_turn_seat=actor,
            need_self_action=False,
            action_phase="WAIT",
            updated_state=state,
        )

    if event.event_type == "DISCARD":
        assert event.tile is not None
        if event.tile == state.dealer_tile:
            return GameStepResponse(
                next_turn_seat=next_seat(actor),
                need_self_action=False,
                action_phase="WAIT",
                call_decision=None,
                updated_state=state,
            )
        if actor != self_seat:
            actions = get_available_actions(
                hand_tiles=state.hand_tiles,
                melds=state.melds,
                discarded_tile=event.tile,
                provider_seat=actor,
                player_seat=self_seat,
                dealer_tile=state.dealer_tile,
            )
            meaningful = [
                a
                for a in actions
                if a.action_type != ActionType.PASS
            ]
            if meaningful:
                decision = evaluate_call_decision(
                    available_actions=actions,
                    hand_tiles=state.hand_tiles,
                    melds=state.melds,
                    opponents=state.opponents,
                    dealer_tile=state.dealer_tile,
                    seat_wind=state.seat_wind,
                    round_wind=state.round_wind,
                    is_dealer=state.is_dealer,
                    discarded_tile=event.tile,
                    discarded_tiles=state.collect_all_discards(),
                    turn_count=max(
                        [len(state.discards)]
                        + [len(o.discards) for o in state.opponents]
                    ),
                )
                return GameStepResponse(
                    next_turn_seat=self_seat,
                    need_self_action=True,
                    action_phase="CALL",
                    call_decision=CallDecisionResponse.model_validate(
                        decision.to_dict()
                    ),
                    recommend_discard=None,
                    updated_state=state,
                )
            # 无吃碰杠胡 → 下家待摸
            nxt = next_seat(actor)
            return GameStepResponse(
                next_turn_seat=nxt,
                need_self_action=False,
                action_phase="WAIT",
                updated_state=state,
            )

        # 自家切牌：等待他人响应 / 下家摸牌
        return GameStepResponse(
            next_turn_seat=next_seat(self_seat),
            need_self_action=False,
            action_phase="WAIT",
            updated_state=state,
        )

    if event.event_type == "MELD":
        if actor == self_seat:
            slots = len(state.hand_tiles) + 3 * len(state.melds)
            # 明杠/暗杠后占 1 面子但少 1 张暗手 → 13 位，须岭上补牌再切
            if slots == 13:
                return GameStepResponse(
                    next_turn_seat=self_seat,
                    need_self_action=True,
                    action_phase="DRAW",
                    recommend_discard=None,
                    call_decision=None,
                    updated_state=state,
                )
            if slots == 14:
                rec = _recommend_discard(state)
                return GameStepResponse(
                    next_turn_seat=self_seat,
                    need_self_action=True,
                    action_phase="DISCARD",
                    recommend_discard=rec,
                    call_decision=None,
                    updated_state=state,
                    can_self_win=bool(rec.can_self_win),
                    self_win_info=rec.self_win_info,
                )
            raise ValueError(
                "副露后牌型位异常："
                f"len(hand_tiles)+3*len(melds) 应为 13（杠后补牌）或 14（吃碰后切牌），"
                f"当前 hand={len(state.hand_tiles)}, melds={len(state.melds)}, slots={slots}"
            )
        return GameStepResponse(
            next_turn_seat=actor,
            need_self_action=False,
            action_phase="WAIT",
            updated_state=state,
        )

    if event.event_type == "PASS":
        provider = _infer_pass_provider(state, event, self_seat)
        nxt = next_seat(provider)
        return GameStepResponse(
            next_turn_seat=nxt,
            need_self_action=False,
            action_phase="WAIT",
            updated_state=state,
        )

    raise ValueError(f"未知 event_type：{event.event_type!r}")


# ---------------------------------------------------------------------------
# 事件应用
# ---------------------------------------------------------------------------

def _apply_draw(
    data: dict, *, actor: str, self_seat: str, tile: str | None
) -> None:
    if not tile:
        raise ValueError("DRAW 缺少 tile")
    if actor == self_seat:
        slots = len(data["hand_tiles"]) + 3 * len(data["melds"])
        if slots != 13:
            raise ValueError(
                f"自家摸牌前须为 13 位状态，当前 hand+3*melds={slots}"
            )
        data["hand_tiles"] = list(data["hand_tiles"]) + [tile]
    # 他家摸牌：暗手不可见，Rem 待其切出/副露后再扣


def _apply_discard(
    data: dict, *, actor: str, self_seat: str, tile: str | None
) -> None:
    if not tile:
        raise ValueError("DISCARD 缺少 tile")
    if actor == self_seat:
        hand = list(data["hand_tiles"])
        if tile not in hand:
            raise ValueError(f"自家手牌中无 {tile!r}，无法切出")
        hand.remove(tile)
        data["hand_tiles"] = hand
        data["discards"] = list(data["discards"]) + [tile]
    else:
        opps = [dict(o) for o in data["opponents"]]
        found = False
        for o in opps:
            if o["seat_wind"] == actor:
                o["discards"] = list(o["discards"]) + [tile]
                found = True
                break
        if not found:
            # 允许缺席对手时自动补一条公开状态
            opps.append(
                {
                    "seat_wind": actor,
                    "is_dealer": False,
                    "melds": [],
                    "discards": [tile],
                }
            )
            if len(opps) > 3:
                raise ValueError("opponents 超过 3 家")
        data["opponents"] = opps


def _apply_meld(
    data: dict,
    *,
    actor: str,
    self_seat: str,
    meld: Meld,
    claimed_tile: str | None,
    provider_seat: str | None,
    claimed_discard_index: int | None = None,
) -> None:
    meld_tiles = list(meld.tiles)
    claimed = claimed_tile or _guess_claimed_tile(meld)
    if meld.claimed_tile and claimed_tile and meld.claimed_tile != claimed_tile:
        raise ValueError("副露 claimed_tile 与响应事件 tile 不一致")
    if claimed == data.get("dealer_tile"):
        raise ValueError("台州规则：打出的财神不可吃、碰、杠或捉铳")

    # —— 暗杠：自家扣手牌；对手仅记录公开副露（代录，无暗手）——
    if meld.meld_type == MeldType.AN_GANG:
        if not meld_tiles:
            raise ValueError("暗杠缺少 tiles")
        face = meld_tiles[0]
        if face == data.get("dealer_tile"):
            raise ValueError("台州规则：百搭（得）不可用于开杠")
        if actor == self_seat:
            hand = list(data["hand_tiles"])
            for t in meld_tiles:
                if t not in hand:
                    raise ValueError(f"自家手牌缺少暗杠用张 {t!r}")
                hand.remove(t)
            data["hand_tiles"] = hand
            data["melds"] = list(data["melds"]) + [meld.model_dump()]
            return
        # 对手暗杠代录：只追加公开副露，不改牌河
        opps = [dict(o) for o in data["opponents"]]
        found = False
        for o in opps:
            if o["seat_wind"] == actor:
                o["melds"] = list(o["melds"]) + [meld.model_dump()]
                found = True
                break
        if not found:
            opps.append(
                {
                    "seat_wind": actor,
                    "is_dealer": False,
                    "melds": [meld.model_dump()],
                    "discards": [],
                }
            )
            if len(opps) > 3:
                raise ValueError("opponents 超过 3 家")
        data["opponents"] = opps
        return

    # —— 补杠：已有 PONG，手牌再扣 1 张，升级为 MING_GANG ——
    if (
        actor == self_seat
        and meld.meld_type == MeldType.MING_GANG
        and claimed
        and provider_seat is None
        and _try_upgrade_pong_to_ming_gang(data, claimed)
    ):
        return
    if (
        actor != self_seat
        and meld.meld_type == MeldType.MING_GANG
        and claimed
        and provider_seat is None
        and _try_upgrade_opponent_pong_to_ming_gang(data, actor, claimed)
    ):
        return

    if claimed is None:
        raise ValueError("MELD 无法确定吃碰杠所取的牌河张，请传 event.tile")
    if claimed not in meld_tiles:
        raise ValueError("副露面子不含供牌方打出的牌")

    # 从牌河移除被副露取走的张
    provider = _remove_from_river(
        data, claimed, provider_seat=provider_seat, actor_seat=actor,
        chi=meld.meld_type == MeldType.CHI,
        claimed_discard_index=claimed_discard_index,
    )
    meld_data = meld.model_dump()
    meld_data["provider_seat"] = provider
    meld_data["claimed_tile"] = claimed

    if actor == self_seat:
        hand = list(data["hand_tiles"])
        need = Counter(meld_tiles)
        need[claimed] -= 1  # 牌河提供
        if need[claimed] <= 0:
            del need[claimed]
        for tile, cnt in need.items():
            for _ in range(cnt):
                if tile not in hand:
                    raise ValueError(f"自家手牌缺少副露用张 {tile!r}")
                hand.remove(tile)
        data["hand_tiles"] = hand
        data["melds"] = list(data["melds"]) + [meld_data]
    else:
        opps = [dict(o) for o in data["opponents"]]
        found = False
        for o in opps:
            if o["seat_wind"] == actor:
                o["melds"] = list(o["melds"]) + [meld_data]
                found = True
                break
        if not found:
            opps.append(
                {
                    "seat_wind": actor,
                    "is_dealer": False,
                    "melds": [meld_data],
                    "discards": [],
                }
            )
            if len(opps) > 3:
                raise ValueError("opponents 超过 3 家")
        data["opponents"] = opps


def _try_upgrade_pong_to_ming_gang(data: dict, face: str) -> bool:
    """若存在对应碰且手牌有第 4 张，升级为明杠并扣手牌。成功返回 True。"""
    if face == data.get("dealer_tile"):
        raise ValueError("台州规则：百搭（得）不可用于开杠")
    hand = list(data["hand_tiles"])
    if face not in hand:
        return False
    melds = [dict(m) for m in data["melds"]]
    for i, m in enumerate(melds):
        mtype = m.get("meld_type")
        tiles = list(m.get("tiles") or [])
        if mtype in ("pong", "peng") and tiles and tiles[0] == face:
            hand.remove(face)
            melds[i] = {
                "meld_type": "ming_gang",
                "tiles": [face, face, face, face],
            }
            data["hand_tiles"] = hand
            data["melds"] = melds
            return True
    return False


def _try_upgrade_opponent_pong_to_ming_gang(data: dict, actor: str, face: str) -> bool:
    """对手补杠只升级公开碰；第四张暗手由前端牌墙状态扣除。"""
    if face == data.get("dealer_tile"):
        raise ValueError("台州规则：百搭（得）不可用于开杠")
    opps = [dict(o) for o in data["opponents"]]
    for o in opps:
        if o["seat_wind"] != actor:
            continue
        melds = [dict(m) for m in o["melds"]]
        for i, m in enumerate(melds):
            if m.get("meld_type") in ("pong", "peng") and m.get("tiles") == [face] * 3:
                melds[i] = {**m, "meld_type": "ming_gang", "tiles": [face] * 4}
                o["melds"] = melds
                data["opponents"] = opps
                return True
    return False


def _guess_claimed_tile(meld: Meld) -> str | None:
    """碰/杠取众数张；吃无法唯一确定。"""
    if meld.meld_type in (MeldType.PONG, MeldType.MING_GANG, MeldType.AN_GANG):
        counts = Counter(meld.tiles)
        return counts.most_common(1)[0][0]
    return None


def _remove_from_river(
    data: dict, tile: str, *, provider_seat: str | None,
    actor_seat: str, chi: bool, claimed_discard_index: int | None = None,
) -> str:
    """只扣事件绑定的供牌者；末张错位时须有响应窗口的原始位置。"""
    rivers = {data["seat_wind"]: list(data["discards"])}
    rivers.update({o["seat_wind"]: list(o["discards"]) for o in data["opponents"]})
    if provider_seat is None:
        raise ValueError("牌河供牌方不明确：请传 provider_seat，不能按同名历史牌搜索")
    if provider_seat == actor_seat or provider_seat not in rivers:
        raise ValueError(f"供牌方 {provider_seat!r} 非法")
    if chi and next_seat(provider_seat) != actor_seat:
        raise ValueError("吃牌只能取直接上家刚打出的牌")
    river = rivers[provider_seat]
    if claimed_discard_index is not None:
        if claimed_discard_index >= len(river) or river[claimed_discard_index] != tile:
            raise ValueError(f"供牌方 {provider_seat} 原响应位置不是 {tile!r}")
        # 仅供牌方的明确响应位置可兜底；同名历史牌不能凭牌名模糊取走。
        river.pop(claimed_discard_index)
    elif river and river[-1] == tile:
        river.pop()
    else:
        raise ValueError(f"供牌方 {provider_seat} 牌河末张不是 {tile!r}")
    if provider_seat == data["seat_wind"]:
        data["discards"] = river
    else:
        opps = [dict(o) for o in data["opponents"]]
        for o in opps:
            if o["seat_wind"] == provider_seat:
                o["discards"] = river
                break
        data["opponents"] = opps
    return provider_seat


def _infer_pass_provider(
    state: HandRequest, event: StepEvent, self_seat: str
) -> str:
    """PASS 后下一家摸牌：provider 为被过的出牌方。"""
    rivers = {self_seat: state.discards}
    rivers.update({o.seat_wind: o.discards for o in state.opponents})
    if event.provider_seat:
        river = rivers.get(event.provider_seat) or []
        if not river or (event.tile and river[-1] != event.tile):
            raise ValueError("PASS 供牌方牌河末张与响应牌不一致")
        return event.provider_seat
    raise ValueError("PASS 供牌方不明确：请传 provider_seat")


def _recommend_discard(
    state: HandRequest, *, win_tile: str | None = None
) -> RecommendResponse:
    slots = len(state.hand_tiles) + 3 * len(state.melds)
    if slots != 14:
        raise ValueError(
            "切牌推荐要求待切状态 len(hand_tiles)+3*len(melds)==14，"
            f"当前 hand={len(state.hand_tiles)}, melds={len(state.melds)}, slots={slots}"
        )
    rem = get_remaining_tiles(state)
    result = calculate_best_discards(
        hand_tiles=state.hand_tiles,
        dealer_tile=state.dealer_tile,
        is_dealer=state.is_dealer,
        seat_wind=state.seat_wind,
        discarded_tiles=state.collect_all_discards(),
        melds=state.melds,
        opponents=state.opponents,
        rem_tiles=rem,
        round_wind=state.round_wind,
    )
    from app.core.evaluator import check_self_drawn_win

    win_info = check_self_drawn_win(
        hand_tiles=state.hand_tiles,
        melds=state.melds,
        dealer_tile=state.dealer_tile,
        seat_wind=state.seat_wind,
        round_wind=state.round_wind,
        is_dealer=state.is_dealer,
        win_tile=win_tile,
    )
    result["can_self_win"] = win_info is not None
    result["self_win_info"] = win_info
    return RecommendResponse(**result)
