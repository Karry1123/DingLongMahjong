"""HTTP 路由：切牌推荐、算胡明细、牌局步进等 API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.game_step import process_game_step
from app.core.ev_engine import calculate_best_discards
from app.core.pool_tracker import get_remaining_tiles
from app.core.scoring import calculate_hu_points
from app.schemas import (
    AutoDealRequest,
    AutoDealResponse,
    CalculateHuRequest,
    CalculateHuResponse,
    DrawCardRequest,
    DrawCardResponse,
    GameRecordRequest,
    GameRecordResponse,
    GameStepRequest,
    GameStepResponse,
    HandRequest,
    PlayerState,
    RecommendResponse,
    SettlementRequest,
    SettlementResponse,
)

router = APIRouter(prefix="/api", tags=["mahjong"])


@router.post("/recommend", response_model=RecommendResponse)
def recommend_discard(request: HandRequest) -> RecommendResponse:
    """根据暗手、副露、对手公开信息与「得」，返回进攻/防守净 EV 切牌推荐。"""
    slots = len(request.hand_tiles) + 3 * len(request.melds)
    if slots != 14:
        raise HTTPException(
            status_code=400,
            detail=(
                "切牌推荐要求待切状态："
                "len(hand_tiles)+3*len(melds)==14"
                f"（暗手目标 {14 - 3 * len(request.melds)} 张），"
                f"当前 hand={len(request.hand_tiles)}, melds={len(request.melds)}, slots={slots}"
            ),
        )
    try:
        rem = get_remaining_tiles(request)
        result = calculate_best_discards(
            hand_tiles=request.hand_tiles,
            dealer_tile=request.dealer_tile,
            is_dealer=request.is_dealer,
            seat_wind=request.seat_wind,
            discarded_tiles=request.collect_all_discards(),
            melds=request.melds,
            opponents=request.opponents,
            rem_tiles=rem,
            round_wind=request.round_wind,
        )
        from app.core.evaluator import check_self_drawn_win

        win_info = check_self_drawn_win(
            hand_tiles=request.hand_tiles,
            melds=request.melds,
            dealer_tile=request.dealer_tile,
            seat_wind=request.seat_wind,
            round_wind=request.round_wind,
            is_dealer=request.is_dealer,
            win_tile=request.latest_drawn_tile,
            players=[
                {
                    "seat_wind": request.seat_wind,
                    "is_dealer": request.is_dealer,
                    "melds": request.melds,
                },
                *[
                    {
                        "seat_wind": o.seat_wind,
                        "is_dealer": o.is_dealer,
                        "melds": o.melds,
                    }
                    for o in request.opponents
                ],
            ]
            if len(request.opponents) == 3
            else None,
        )
        result["can_self_win"] = win_info is not None
        result["self_win_info"] = win_info
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RecommendResponse(**result)


@router.post("/calculate-hu", response_model=CalculateHuResponse)
def calculate_hu(request: CalculateHuRequest) -> CalculateHuResponse:
    """独立算胡明细：返回完整 tile_hu / fan / final_hu / details。

    默认枚举得还原取最高胡（与结算一致）；若显式传入 restored_jokers>0
    或客户端需要固定声明，仍可用 ``calculate_hu_points`` 路径。
    """
    from app.core.scoring import calculate_best_hu_points, calculate_hu_points

    try:
        # restored_jokers==0 且未强制：自动枚举最优声明
        if request.restored_jokers == 0:
            result = calculate_best_hu_points(
                melds=request.melds,
                hand_tiles=request.hand_tiles,
                win_tile=request.win_tile,
                is_zimo=request.is_zimo,
                seat_wind=request.seat_wind,
                dealer_tile=request.dealer_tile,
                base_hu=request.base_hu,
                round_wind=request.round_wind,
            )
        else:
            result = calculate_hu_points(
                melds=request.melds,
                hand_tiles=request.hand_tiles,
                win_tile=request.win_tile,
                is_zimo=request.is_zimo,
                seat_wind=request.seat_wind,
                dealer_tile=request.dealer_tile,
                base_hu=request.base_hu,
                restored_jokers=request.restored_jokers,
                round_wind=request.round_wind,
            )
    except ValueError as exc:
        # 无法和牌、得还原超限、张数不合法等
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    factor = 3.0 if request.is_dealer else 2.0
    return CalculateHuResponse(
        tile_hu=result["tile_hu"],
        base_hu=result["base_hu"],
        fan=result["fan"],
        final_hu=result["final_hu"],
        is_hard_hu=result["is_hard_hu"],
        details=result["details"],
        others_hu=result.get("others_hu"),
        settlement_factor=factor,
        settlement_income=float(result["final_hu"]) * factor,
    )


@router.post("/game/step", response_model=GameStepResponse)
def game_step(request: GameStepRequest) -> GameStepResponse:
    """牌局时序步进：应用 DRAW/DISCARD/MELD/PASS，返回下一阶段与推荐。

    - 他家打牌且自家有吃/碰/杠/胡 → ``action_phase=CALL`` + ``call_decision``
    - 自家摸牌或副露后待切 → ``action_phase=DISCARD`` + ``recommend_discard``
    - 其余 → ``action_phase=WAIT``
    """
    try:
        return process_game_step(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/settle", response_model=SettlementResponse)
def settle_round(request: SettlementRequest) -> SettlementResponse:
    """终局筹码结算：§6 庄闲支付 + 固有胡头互结；断言无包牌。"""
    from app.core.settlement import calculate_final_settlement

    try:
        if request.wrap_penalty:
            raise ValueError("台州规则禁止包牌：wrap_penalty 必须为 False")
        result = calculate_final_settlement(
            winner_seat=request.winner_seat,
            win_type=request.win_type,
            dealer_tile=request.dealer_tile,
            players=[p.model_dump() for p in request.players],
            points=request.points,
            hand_tiles=request.hand_tiles,
            melds=request.melds,
            win_tile=request.win_tile,
            discarder_seat=request.discarder_seat,
            wrap_penalty=False,
            restored_jokers=request.restored_jokers,
            round_wind=request.round_wind,
        )
    except (ValueError, AssertionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SettlementResponse(**result)


@router.post("/game/auto-deal", response_model=AutoDealResponse)
def auto_deal(request: AutoDealRequest) -> AutoDealResponse:
    """洗牌发牌：返回四家手牌、公示得、牌墙剩余。"""
    from app.core.deck_engine import setup_new_game

    try:
        result = setup_new_game(request.dealer_seat)
    except (ValueError, AssertionError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AutoDealResponse(**result)


@router.post("/game/draw-card", response_model=DrawCardResponse)
def draw_card(request: DrawCardRequest) -> DrawCardResponse:
    """从牌墙头部摸 1 张；空墙则标记荒牌流局。"""
    from app.core.deck_engine import draw_tile_from_wall

    result = draw_tile_from_wall(request.wall_tiles)
    return DrawCardResponse(**result)


@router.post("/game/record", response_model=GameRecordResponse)
def save_game_record_api(request: GameRecordRequest) -> GameRecordResponse:
    """正式结算后归档完整牌谱；重复提交同一局返回原编号。"""
    from app.core.record_manager import archive_completed_game

    try:
        meta = archive_completed_game(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"轨迹落盘失败：{exc}",
        ) from exc
    return GameRecordResponse(ok=True, round_id=meta["round_id"],
                              game_id=meta["game_id"], timestamp=meta["timestamp"],
                              path=meta["path"], absolute_path=meta["path"],
                              bytes_written=meta["bytes_written"], steps_count=meta["steps_count"])


@router.get("/game/records")
def fetch_game_record_summaries() -> dict:
    """List the latest completed games with seat-relative settlement summaries."""
    from app.core.record_manager import list_game_record_summaries

    return {"records": list_game_record_summaries()}


@router.get("/game/records/{game_id}")
def fetch_game_record(game_id: str) -> dict:
    """按 GM 编号取回可重放的起手、牌墙、动作与终局结果。"""
    from app.core.record_manager import get_game_record

    record = get_game_record(game_id)
    if record is None:
        raise HTTPException(status_code=404, detail="未找到该牌谱编号")
    return record


class ThreatRequest(BaseModel):
    dealer_tile: str
    wall_count: int = Field(ge=0)
    opponents: list[PlayerState] = Field(default_factory=list, max_length=3)


@router.post("/game/threats")
def opponent_threats(request: ThreatRequest) -> dict:
    from app.core.threat_assessment import assess_opponent_threats

    try:
        return {"threats": assess_opponent_threats(
            request.opponents, request.dealer_tile, request.wall_count)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
