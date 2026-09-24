"""台州麻将决策系统输入/输出数据模型。

牌面编码严格遵循 rule.md §1：
- 序数牌：1m~9m、1p~9p、1s~9s
- 字牌：E（东）、S（南）、W（西）、N（北）、C（中）、F（发）、P（白板）

副露结构遵循 rule.md §3（吃 / 碰 / 明杠 / 暗杠）：
每组副露在 14 张牌型中占 3 个「面子位」（杠虽为 4 张物理牌，仍只占 1 面子）。
"""

from __future__ import annotations

import re
from collections import Counter
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# rule.md §1 合法牌面编码
_TILE_PATTERN = r"^([1-9][mps]|[ESWNCFP])$"
_TILE_DESCRIPTION = (
    "台州麻将牌面编码：序数牌 1m~9m / 1p~9p / 1s~9s，"
    "字牌 E/S/W/N/C/F/P（白板）"
)
_TILE_RE = re.compile(_TILE_PATTERN)

SeatWind = Literal["E", "S", "W", "N"]


def _validate_tile_list(tiles: List[str], field_name: str) -> List[str]:
    for i, tile in enumerate(tiles):
        if not _TILE_RE.match(tile):
            raise ValueError(
                f"{field_name}[{i}]={tile!r} 非法；{_TILE_DESCRIPTION}"
            )
    return tiles


class MeldType(str, Enum):
    """副露类型（rule.md §3）。"""

    CHI = "chi"
    PONG = "pong"
    MING_GANG = "ming_gang"
    AN_GANG = "an_gang"


class Meld(BaseModel):
    """单组副露：吃 / 碰为 3 张，明杠 / 暗杠为 4 张。"""

    meld_type: MeldType = Field(..., description="副露类型")
    claimed_tile: str | None = Field(None, description="从牌河取得的物理牌，用于横置展示")
    provider_seat: str | None = Field(None, description="供牌方座次")
    tiles: List[str] = Field(
        ...,
        description="副露牌面编码列表（吃/碰 3 张，杠 4 张）",
    )

    @field_validator("tiles")
    @classmethod
    def validate_tiles_codes(cls, tiles: List[str]) -> List[str]:
        return _validate_tile_list(tiles, "tiles")

    @model_validator(mode="after")
    def validate_tiles_length(self) -> Meld:
        n = len(self.tiles)
        if self.claimed_tile is not None and self.claimed_tile not in self.tiles:
            raise ValueError("claimed_tile 必须属于副露牌组")
        if self.provider_seat is not None and self.provider_seat not in ("E", "S", "W", "N"):
            raise ValueError("provider_seat 必须为 E/S/W/N")
        if self.meld_type in (MeldType.CHI, MeldType.PONG):
            if n != 3:
                raise ValueError(
                    f"{self.meld_type.value} 的 tiles 长度必须为 3，当前为 {n}"
                )
        elif self.meld_type in (MeldType.MING_GANG, MeldType.AN_GANG):
            if n != 4:
                raise ValueError(
                    f"{self.meld_type.value} 的 tiles 长度必须为 4，当前为 {n}"
                )
        return self


class PlayerState(BaseModel):
    """单家公开状态（对手三家；不含暗手）。

    ``extra='forbid'``：拒绝 ``hand_tiles`` / ``handTiles`` 等暗手字段，
    防止上帝视角泄露进入 Rem / EV 计算。
    """

    model_config = ConfigDict(extra="forbid")

    seat_wind: SeatWind = Field(..., description="该家门风 E/S/W/N")
    is_dealer: bool = Field(False, description="是否为庄家")
    melds: List[Meld] = Field(
        default_factory=list,
        description="该家已公开副露",
    )
    discards: List[str] = Field(
        default_factory=list,
        description="该家牌河（按摸打顺序）",
    )

    @field_validator("discards")
    @classmethod
    def validate_discards(cls, tiles: List[str]) -> List[str]:
        return _validate_tile_list(tiles, "discards")

    @model_validator(mode="after")
    def validate_meld_count(self) -> PlayerState:
        if len(self.melds) > 4:
            raise ValueError(
                f"PlayerState.melds 长度须 ≤4，当前 {len(self.melds)}"
            )
        return self


class HandRequest(BaseModel):
    """决策请求：自家暗手 + 四方公开信息 + 得 / 圈风。

    牌型守恒：
        - 待切（摸牌后 / 副露后）：len(hand_tiles) + 3 * len(melds) == 14
        - 待摸或响应副露：len(hand_tiles) + 3 * len(melds) == 13
    副露组数 ∈ [0, 4]。杠按 1 组面子计（公式中系数为 3，而非物理 4 张）。

    全场物理校验：自家手牌/副露/牌河 + 三家副露/牌河，任意单种 ≤4。
    """

    hand_tiles: List[str] = Field(
        ...,
        min_length=2,
        max_length=14,
        description="自家门清手牌（未副露部分）",
    )
    melds: List[Meld] = Field(
        default_factory=list,
        description="自家已公开副露",
    )
    discards: List[str] = Field(
        default_factory=list,
        description="自家牌河（按摸打顺序）",
    )
    dealer_tile: str = Field(
        ...,
        pattern=_TILE_PATTERN,
        description="本局「得」（财神/百搭）牌面编码",
    )
    seat_wind: SeatWind = Field(
        ...,
        description="自家门风/自风：E/S/W/N",
    )
    round_wind: SeatWind = Field(
        "E",
        description="圈风（场风）E/S/W/N，默认东风圈",
    )
    is_dealer: bool = Field(
        ...,
        description="自家是否为庄家（影响结算支付矩阵）",
    )
    opponents: List[PlayerState] = Field(
        default_factory=list,
        description="其余三家公开状态（0~3 家；满桌应为 3）",
    )
    # 兼容旧前端：无 opponents 时视为「全场已见废牌」汇总
    discarded_tiles: List[str] = Field(
        default_factory=list,
        description="[兼容旧版] 全场废牌汇总；opponents 为空时并入 Rem 扣减",
    )

    @field_validator("hand_tiles")
    @classmethod
    def validate_hand_tiles(cls, tiles: List[str]) -> List[str]:
        return _validate_tile_list(tiles, "hand_tiles")

    @field_validator("discards")
    @classmethod
    def validate_self_discards(cls, tiles: List[str]) -> List[str]:
        return _validate_tile_list(tiles, "discards")

    @field_validator("discarded_tiles")
    @classmethod
    def validate_discarded_tiles(cls, tiles: List[str]) -> List[str]:
        return _validate_tile_list(tiles, "discarded_tiles")

    @model_validator(mode="after")
    def validate_hand_table_and_pool(self) -> HandRequest:
        n_melds = len(self.melds)
        if n_melds > 4:
            raise ValueError(f"melds 长度必须在 0~4 之间，当前为 {n_melds}")

        if len(self.opponents) > 3:
            raise ValueError(
                f"opponents 最多 3 家，当前 {len(self.opponents)}"
            )

        # 每组副露占 3 个牌型位；门清 + 3×副露 ∈ {13 待摸/响应, 14 待切}
        total_slots = len(self.hand_tiles) + 3 * n_melds
        if total_slots not in (13, 14):
            raise ValueError(
                "牌型位不守恒：要求 len(hand_tiles) + 3 * len(melds) ∈ {13, 14}，"
                f"当前 hand_tiles={len(self.hand_tiles)}, melds={n_melds}, "
                f"合计={total_slots}"
            )

        # 门风唯一
        winds = [self.seat_wind] + [o.seat_wind for o in self.opponents]
        if len(winds) != len(set(winds)):
            raise ValueError(f"门风重复：{winds}")

        # 庄家至多一家（含自家）
        dealer_flags = [self.is_dealer] + [o.is_dealer for o in self.opponents]
        if sum(1 for d in dealer_flags if d) > 1:
            raise ValueError("庄家标记冲突：至多一家 is_dealer=True")

        # 全场可见物理牌：自家手/副露/河 + 三家副露/河（+ 旧版 discarded_tiles）
        counts: Counter[str] = Counter(self.hand_tiles)
        for tile in self.discards:
            counts[tile] += 1
        for mi, meld in enumerate(self.melds):
            for tile in meld.tiles:
                counts[tile] += 1

        for oi, opp in enumerate(self.opponents):
            for tile in opp.discards:
                counts[tile] += 1
            for mi, meld in enumerate(opp.melds):
                for tile in meld.tiles:
                    counts[tile] += 1

        # 无四方拆分时，兼容字段计入全场废牌
        if not self.opponents:
            for tile in self.discarded_tiles:
                counts[tile] += 1

        for tile, n in counts.items():
            if n > 4:
                raise ValueError(
                    f"物理牌 {tile!r} 全场可见出现 {n} 次（>4）；"
                    "含自家手牌/副露/牌河与对手副露/牌河"
                )

        return self

    def collect_all_discards(self) -> List[str]:
        """汇总全场已舍出物理牌（供 Rem / EV 使用）。"""
        out: List[str] = list(self.discards)
        for opp in self.opponents:
            out.extend(opp.discards)
        # 旧客户端只传 discarded_tiles、无 opponents
        if not self.opponents and self.discarded_tiles:
            out.extend(self.discarded_tiles)
        return out

    def collect_all_meld_tiles(self) -> List[str]:
        """汇总全场已副露物理牌。"""
        out: List[str] = []
        for meld in self.melds:
            out.extend(meld.tiles)
        for opp in self.opponents:
            for meld in opp.melds:
                out.extend(meld.tiles)
        return out


class RecommendItem(BaseModel):
    """单一切牌候选的评估结果。"""

    tile: str = Field(
        ...,
        pattern=_TILE_PATTERN,
        description="建议切出的牌",
    )
    ev_score: float = Field(
        ...,
        description="净期望 Net_EV = attack_ev − defense_loss − 向听×120",
    )
    attack_ev: float = Field(
        0.0,
        description="进攻期望：进张加权 H_final × 庄闲系数",
    )
    defense_loss: float = Field(
        0.0,
        description="综合放铳净损失期望 Σ NetLoss(k)",
    )
    deal_in_risks: dict[str, float] = Field(
        default_factory=dict,
        description="对三家各自的放铳率 P(DealIn|Tenpai)，键为 seat_wind",
    )
    defense_details: dict[str, dict] = Field(
        default_factory=dict,
        description=(
            "各对手防守明细：tenpai_prob / deal_in_rate / "
            "est_ron_points / loss_if_deal_in / payment_label / is_dealer"
        ),
    )
    is_safe_all: bool = Field(
        False,
        description="是否为当前所有对手共同现物",
    )
    effective_count: int = Field(
        ...,
        ge=0,
        description="有效进张总枚数 TotalRem",
    )
    effective_tiles: List[dict] = Field(
        default_factory=list,
        description=(
            "有效进张明细：[{tile, rem}, ...]，"
            "sum(rem)==effective_count；供审计听口差集"
        ),
    )
    is_hard_hu: bool = Field(
        ...,
        description="是否含硬胡潜力（rule.md §4.3：未利用「得」万能替代）",
    )
    est_base_points: int = Field(
        ...,
        ge=0,
        description="预估翻前胡数（tile_hu + base_hu，来自 calculate_hu_points）",
    )
    est_final_points: int = Field(
        ...,
        ge=0,
        description="预估最终胡数 final_hu=(tile_hu+base_hu)×2^fan（进张加权）",
    )
    note: str = Field(
        "",
        description="切牌理由（多向听：客风/役牌/搭子取舍说明）",
    )


class SelfGangItem(BaseModel):
    """自家暗杠 / 补杠候选（与切牌候选并列，按净 EV 排序）。"""

    action_type: Literal["an_gang", "bu_gang"] = Field(
        ...,
        description="an_gang 暗杠 / bu_gang 碰后补杠",
    )
    tile: str = Field(
        ...,
        pattern=_TILE_PATTERN,
        description="开杠目标牌面",
    )
    tiles: List[str] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="四张同名面子",
    )
    ev_score: float = Field(
        ...,
        description="净期望：岭上补张后再切 EV + 杠分增量折现",
    )
    attack_ev: float = Field(0.0, description="进攻侧期望")
    defense_loss: float = Field(
        0.0,
        description="开杠本身不切牌，防守损通常为 0",
    )
    est_hu_bonus: int = Field(
        ...,
        ge=0,
        description="相对不杠的牌型胡增量（暗杠相对暗刻 / 补杠相对明刻）",
    )
    note: str = Field("", description="评估说明")


class TurnActionChoice(BaseModel):
    action_type: Literal["discard", "an_gang", "bu_gang"]
    tile: str = Field(..., pattern=_TILE_PATTERN)
    ev_score: float


class RecommendResponse(BaseModel):
    """切牌推荐响应。"""

    best_tile: str = Field(
        ...,
        pattern=_TILE_PATTERN,
        description="推荐最优切牌",
    )
    best_action: Optional[TurnActionChoice] = Field(
        None,
        description="本巡首选行动：discard/an_gang/bu_gang；best_tile 仍供切牌列表展示",
    )
    candidates: List[RecommendItem] = Field(
        ...,
        description="切牌候选列表（含 EV、有效进张、硬胡潜力）",
    )
    self_gang_candidates: List[SelfGangItem] = Field(
        default_factory=list,
        description="暗杠/补杠候选（有则与切牌 EV 对照）",
    )
    can_self_win: bool = Field(
        False,
        description="当前待切手是否已可自摸和牌",
    )
    self_win_info: Optional[dict] = Field(
        None,
        description="自摸和牌明细（can_self_win 时有值）",
    )


class CalculateHuRequest(BaseModel):
    """算胡明细请求：听牌手 + 胡张 + 副露 + 局况。

    牌型守恒（胡牌瞬间）：
        len(hand_tiles) + 1 + 3 * len(melds) == 14
    即 hand_tiles 为不含胡张的门清剩余牌。
    """

    hand_tiles: List[str] = Field(
        ...,
        min_length=1,
        max_length=14,
        description="门清剩余手牌（已去除副露，不含胡牌张）",
    )
    melds: List[Meld] = Field(
        default_factory=list,
        description="副露列表（chi / pong / ming_gang / an_gang）",
    )
    win_tile: str = Field(
        ...,
        pattern=_TILE_PATTERN,
        description="胡的那张牌",
    )
    is_zimo: bool = Field(..., description="是否自摸")
    seat_wind: SeatWind = Field(..., description="自风 E/S/W/N")
    round_wind: SeatWind = Field(
        "E",
        description="圈风 E/S/W/N（与门风叠番时各计 1 翻）",
    )
    dealer_tile: str = Field(
        ...,
        pattern=_TILE_PATTERN,
        description="本局财神（得）",
    )
    restored_jokers: int = Field(
        0,
        ge=0,
        le=4,
        description="得还原张数（默认 0）",
    )
    base_hu: int = Field(
        10,
        ge=0,
        description="底胡（默认 10）",
    )
    is_dealer: bool = Field(
        False,
        description="是否庄家（可选；用于附带结算期望收入）",
    )

    @field_validator("hand_tiles")
    @classmethod
    def validate_hand_tiles(cls, tiles: List[str]) -> List[str]:
        return _validate_tile_list(tiles, "hand_tiles")

    @model_validator(mode="after")
    def validate_win_shape_slots(self) -> CalculateHuRequest:
        n_melds = len(self.melds)
        if n_melds > 4:
            raise ValueError(f"melds 长度必须在 0~4 之间，当前为 {n_melds}")

        # 听牌门清张数 = needed_melds×3 + 1；加上 win_tile 后满 14 位
        total_slots = len(self.hand_tiles) + 1 + 3 * n_melds
        if total_slots != 14:
            raise ValueError(
                "牌型位不守恒：要求 len(hand_tiles) + 1 + 3*len(melds) == 14，"
                f"当前 hand={len(self.hand_tiles)}, win=1, melds={n_melds}, "
                f"合计={total_slots}"
            )

        counts: Counter[str] = Counter(self.hand_tiles)
        counts[self.win_tile] += 1
        for mi, meld in enumerate(self.melds):
            for tile in meld.tiles:
                counts[tile] += 1
                if counts[tile] > 4:
                    raise ValueError(
                        f"物理牌 {tile!r} 出现 {counts[tile]} 次（>4），"
                        f"来源含 hand_tiles / win_tile / melds[{mi}]"
                    )
        return self


class CalculateHuResponse(BaseModel):
    """算胡明细响应（对齐 scoring.calculate_hu_points）。"""

    tile_hu: int = Field(..., ge=0, description="牌型胡数（不含底胡）")
    base_hu: int = Field(..., ge=0, description="底胡")
    fan: int = Field(..., ge=0, description="总翻数")
    final_hu: int = Field(..., ge=0, description="胡牌者最终胡数")
    is_hard_hu: bool = Field(..., description="是否硬碰硬")
    details: dict = Field(..., description="得分明细（雀头/面子/自摸/嵌档/翻）")
    others_hu: int | None = Field(
        None,
        description="未胡者参考胡数 tile_hu×2^fan（计分模块附带）",
    )
    settlement_factor: float | None = Field(
        None,
        description="庄闲系数（若请求提供 is_dealer：庄 3 / 闲 2）",
    )
    settlement_income: float | None = Field(
        None,
        description="期望筹码收入 final_hu × settlement_factor",
    )


# ---------------------------------------------------------------------------
# 牌局时序步进 /api/game/step
# ---------------------------------------------------------------------------

StepEventType = Literal["DRAW", "DISCARD", "MELD", "PASS"]
ActionPhase = Literal["DISCARD", "CALL", "WAIT", "DRAW"]


class StepEvent(BaseModel):
    """单步牌局事件（应用到 HandRequest 局面上）。"""

    actor_seat: SeatWind = Field(..., description="事件发起方门风 E/S/W/N")
    event_type: StepEventType = Field(
        ...,
        description="DRAW 摸牌 / DISCARD 切牌 / MELD 副露 / PASS 过牌",
    )
    tile: Optional[str] = Field(
        None,
        pattern=_TILE_PATTERN,
        description="摸入或打出的牌；PASS 时可填被过的那张",
    )
    provider_seat: SeatWind | None = Field(
        None, description="MELD/PASS 所响应的最近出牌方；同名历史弃牌不得替代",
    )
    meld: Optional[Meld] = Field(
        None,
        description="MELD 时的副露结构；其它事件应为 null",
    )

    @model_validator(mode="after")
    def validate_event_payload(self) -> StepEvent:
        et = self.event_type
        if et == "DRAW":
            if not self.tile:
                raise ValueError("DRAW 事件必须提供 tile（摸入张）")
            if self.meld is not None:
                raise ValueError("DRAW 事件不得附带 meld")
        elif et == "DISCARD":
            if not self.tile:
                raise ValueError("DISCARD 事件必须提供 tile（打出张）")
            if self.meld is not None:
                raise ValueError("DISCARD 事件不得附带 meld")
        elif et == "MELD":
            if self.meld is None:
                raise ValueError("MELD 事件必须提供 meld")
            if (self.provider_seat and self.meld.provider_seat
                    and self.provider_seat != self.meld.provider_seat):
                raise ValueError("event 与 meld 的 provider_seat 不一致")
        elif et == "PASS":
            if self.meld is not None:
                raise ValueError("PASS 事件不得附带 meld")
        return self


class CallActionModel(BaseModel):
    """副露/过牌候选动作（对齐 action_generator.Action）。"""

    action_type: str = Field(..., description="chi / pong / ming_gang / hu / pass")
    tiles: List[str] = Field(default_factory=list)
    provider_seat: str = Field("", description="出牌方门风")


class CallActionScoreModel(BaseModel):
    """单个响应动作的 EV 评估。"""

    action: CallActionModel
    net_ev: float
    note: str = ""
    hu_ev: Optional[float] = None
    pass_ev: Optional[float] = None


class CallDecisionResponse(BaseModel):
    """副露/过牌决策结果（API 层）。"""

    recommended_action: CallActionModel
    reason: str
    candidates: List[CallActionScoreModel] = Field(default_factory=list)
    available_actions: List[CallActionModel] = Field(
        default_factory=list,
        description="可选动作列表（与 candidates 中的 action 对齐）",
    )
    est_final_points: Optional[int] = Field(
        None,
        description="若可胡：预估最终胡数（可选）",
    )
    hu_ev: Optional[float] = Field(None, description="即时捉铳预期净收益")
    pass_ev: Optional[float] = Field(None, description="过牌后续造牌预期净收益")


class GameStepRequest(HandRequest):
    """牌局步进请求：完整当前局面 + 本步事件。

    ``HandRequest`` 字段表示**事件应用前**的局面；服务端依据 ``event``
    更新牌河 / 副露后再推导下一阶段与推荐。
    """

    event: StepEvent = Field(..., description="本步触发的事件")


class GameStepResponse(BaseModel):
    """牌局步进响应：下一行动权与（如需）决策推荐。"""

    next_turn_seat: SeatWind = Field(
        ...,
        description="下一个拥有出牌或响应权的座位",
    )
    need_self_action: bool = Field(
        ...,
        description="是否需要自家操作（切牌或响应副露）",
    )
    action_phase: ActionPhase = Field(
        ...,
        description="DISCARD 切牌 / CALL 响应副露 / WAIT 旁观 / DRAW 杠后岭上补牌",
    )
    recommend_discard: Optional[RecommendResponse] = Field(
        None,
        description="切牌阶段的最优推荐",
    )
    call_decision: Optional[CallDecisionResponse] = Field(
        None,
        description="副露阶段的吃碰过权衡",
    )
    updated_state: Optional[HandRequest] = Field(
        None,
        description="事件应用后的局面快照（便于客户端同步 Rem / 牌河）",
    )
    can_self_win: bool = Field(
        False,
        description="自家待切时是否已可自摸",
    )
    self_win_info: Optional[dict] = Field(
        None,
        description="自摸和牌明细",
    )


class SettlementPlayer(BaseModel):
    """结算用单家公开状态。"""

    seat_wind: SeatWind
    is_dealer: bool = False
    melds: List[Meld] = Field(default_factory=list)
    hand_tiles: List[str] = Field(
        default_factory=list,
        description="暗手（固有底胡暗刻/雀头用；上帝视角可填）",
    )

    @field_validator("hand_tiles")
    @classmethod
    def validate_settle_hand(cls, tiles: List[str]) -> List[str]:
        return _validate_tile_list(tiles, "hand_tiles") if tiles else []


class SettlementRequest(BaseModel):
    """终局结算请求（§6 无包牌矩阵）。"""

    winner_seat: SeatWind
    win_type: Literal[
        "zimo",
        "ron",
        "self_draw",
        "catch",
        "self_draw_win",
        "catch_win",
        "rob_kong",
        "hu",
    ] = Field(..., description="自摸或捉铳")
    dealer_tile: str = Field(..., pattern=_TILE_PATTERN)
    players: List[SettlementPlayer] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="四家座位/庄闲/副露",
    )
    points: Optional[int] = Field(
        None,
        description="已算好的 H_final；缺省则用 hand/melds 计或副露估算",
    )
    hand_tiles: Optional[List[str]] = Field(
        None,
        description="赢家门清（不含胡张）；代录对手时可空",
    )
    melds: Optional[List[Meld]] = Field(
        None,
        description="赢家副露；缺省用 players 中对应座位",
    )
    win_tile: Optional[str] = Field(None, pattern=_TILE_PATTERN)
    discarder_seat: Optional[SeatWind] = Field(
        None,
        description="捉铳时出枪方",
    )
    wrap_penalty: bool = Field(
        False,
        description="必须为 False（§7 禁止包牌）",
    )
    restored_jokers: int = Field(0, ge=0, le=4)
    round_wind: SeatWind = Field(
        "E",
        description="圈风（字牌刻杠叠番）",
    )


class SettlementResponse(BaseModel):
    """终局结算响应。"""

    winner_seat: SeatWind
    win_type: Literal["zimo", "ron"]
    win_type_label: str
    is_zimo: bool
    is_dealer_win: bool
    points: int
    final_hu: int
    final_points: int
    wrap_penalty: bool = False
    discarder_seat: Optional[SeatWind] = None
    net_by_seat: dict = Field(default_factory=dict)
    transfers: List[dict] = Field(default_factory=list)
    payments: dict = Field(default_factory=dict)
    dealer_seat: SeatWind
    dealer_tile: Optional[str] = None
    hu_detail: Optional[dict] = None
    seat_details: Optional[dict] = Field(
        default=None,
        description="四家门风/暗手/固有底胡/赢家拆解",
    )

class AutoDealRequest(BaseModel):
    """自动发牌请求。"""

    dealer_seat: SeatWind = Field(
        ...,
        description="庄家门风；起手 14 张并拥有第一手出牌权",
    )


class AutoDealResponse(BaseModel):
    """自动发牌响应：四家手牌 + 得 + 牌墙。"""

    dealer_seat: SeatWind
    dealer_tile: str = Field(..., pattern=_TILE_PATTERN, description="公示得牌")
    shown_occupied: bool = Field(True, description="得已公示占用，不可摸")
    hands: dict[str, List[str]] = Field(
        ...,
        description="四家门风 → 手牌列表（庄 14 / 闲 13）",
    )
    hand_counts: dict[str, int] = Field(
        ...,
        description="四家手牌张数",
    )
    wall_tiles: List[str] = Field(
        ...,
        description="剩余可摸牌墙（队列，头部先摸）",
    )
    wall_count: int = Field(..., ge=0, description="牌墙剩余张数")
    total_tiles: int = Field(136, description="全副总张数")
    first_turn_seat: SeatWind = Field(..., description="第一手出牌权（庄）")
    is_exhausted: bool = False


class DrawCardRequest(BaseModel):
    """从牌墙摸牌请求。"""

    wall_tiles: List[str] = Field(
        ...,
        description="当前可摸牌墙（调用方持有的队列快照）",
    )


class DrawCardResponse(BaseModel):
    """摸牌响应。"""

    tile: Optional[str] = Field(
        None,
        description="摸到的牌；牌墙空时为 null",
    )
    wall_tiles: List[str] = Field(
        default_factory=list,
        description="摸后剩余牌墙",
    )
    wall_count: int = Field(0, ge=0)
    is_exhausted: bool = Field(
        False,
        description="True 表示荒牌（摸前已空或摸后已空）",
    )
    note: str = ""


# ---------------------------------------------------------------------------
# 对局轨迹落盘（GameRecord）
# ---------------------------------------------------------------------------

GameLogAction = Literal["DRAW", "DISCARD", "CHI", "PONG", "GANG", "WIN"]


class GameRecordSelfRecommendation(BaseModel):
    """自家切牌时的推荐快照（参数复盘用）。"""

    best_tile: Optional[str] = Field(
        None,
        description="当时推荐的 best_tile",
    )
    net_ev: Optional[float] = Field(
        None,
        description="对应净 EV（通常取 best 候选的 ev_score）",
    )


class GameRecordStep(BaseModel):
    """对局单步轨迹。"""

    turn: int = Field(..., ge=0, description="巡目（从 1 起；未知可为 0）")
    seat: SeatWind = Field(..., description="当前行动方门风")
    action: GameLogAction = Field(..., description="动作类型")
    tile: Optional[str] = Field(
        None,
        description="涉及牌张（WIN 流局等可空）",
    )
    self_recommendation: Optional[GameRecordSelfRecommendation] = Field(
        None,
        description="仅自家 DISCARD 时填写",
    )


class GameRecordConfig(BaseModel):
    """开局配置快照。"""

    dealer_seat: SeatWind = Field(..., description="庄家门风（东）")
    dealer_tile: str = Field(
        ...,
        pattern=_TILE_PATTERN,
        description="公示得（财神）",
    )
    seat_wind: SeatWind = Field(..., description="自家门风")


class GameRecordFinalResult(BaseModel):
    """终局结果摘要。"""

    winner_seat: Optional[SeatWind] = Field(
        None,
        description="胡牌座位；流局为 null",
    )
    win_type: Optional[str] = Field(
        None,
        description="zimo / ron / draw 等",
    )
    points: Optional[int] = Field(None, description="胡头 / 点数")
    deal_in_seat: Optional[SeatWind] = Field(
        None,
        description="放铳座位（自摸/流局为 null）",
    )
    details: Optional[dict] = Field(
        None,
        description="扩展明细（hu_detail / payments / net_by_seat 等）",
    )


class GameRecordRequest(BaseModel):
    """POST /api/game/record 请求体：完整对局轨迹。"""

    round_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="局 ID（时间戳或 UUID）",
    )
    config: GameRecordConfig
    steps: List[GameRecordStep] = Field(
        default_factory=list,
        description="按时间序的步骤数组",
    )
    final_result: Optional[GameRecordFinalResult] = Field(
        None,
        description="终局结果",
    )


class GameRecordResponse(BaseModel):
    """落盘成功响应。"""

    ok: bool = True
    round_id: str
    path: str = Field(..., description="相对 backend/ 的保存路径")
    absolute_path: str
    bytes_written: int
    steps_count: int

