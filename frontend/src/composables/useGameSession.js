/**
 * 牌局时序控制器：roundState / historyStack / currentPhase，
 * 对接 POST /api/game/step，并强制全场可见物理牌 ≤4。
 */

import { computed, reactive, ref, toRaw } from 'vue'
import { MAX_PER_TILE, WIND_ORDER } from '../constants/tiles.js'
import { pveOpponentsForDealer, pveWindForPlayer, remapPveScores } from '../utils/pveSeatMapping.js'
import * as gameApi from '../services/api.js'
import {
  buildTableFromSelfWind,
  nextSeat,
  prevSeat,
  rebuildOpponentsPreservingOpen,
  DEALER_SEAT,
  windLabel,
} from '../utils/seatLayout.js'
import { sortHandTiles, isJokerPhysical, moveTileInList, ensureTileAtEnd } from '../utils/tileSorter.js'
import {
  detectTableResponses,
  buildPendingHuQueue,
  shouldEnterResponseWindow,
} from '../utils/callDetector.js'

/** @typedef {'IDLE' | 'MY_TURN_DISCARD' | 'OPPONENT_DISCARD_ACTION' | 'WAIT_RESPONSE' | 'WAITING'} SessionPhase */
/** @typedef {'SETUP' | 'PLAYING' | 'GAME_OVER'} GameLifecycle */

const PHASE_LABEL = {
  IDLE: '开局准备 / 起手录入',
  MY_TURN_DISCARD: '自家切牌',
  OPPONENT_DISCARD_ACTION: '响应他家出牌（自家）',
  WAIT_RESPONSE: '等待副露响应',
  WAITING: '旁观等待',
}

/**
 * @param {{
 *   seatWind?: string,
 *   isDealer?: boolean,
 *   dealerTile?: string,
 *   roundWind?: string,
 *   onAction?: (event: {action: string, tile: string|null, seat: string, selfSeat: string}) => void,
 * }=} initial
 */
export function useGameSession(initial = {}) {
  let sessionEpoch = 0
  let sessionRequests = new AbortController()
  const resetInProgress = ref(false)
  const postGameStep = (state, event) => gameApi.postGameStep(state, event, { signal: sessionRequests.signal })
  const postSettle = (payload) => gameApi.postSettle(payload, { signal: sessionRequests.signal })
  const postAutoDeal = (payload) => gameApi.postAutoDeal(payload, { signal: sessionRequests.signal })
  const postGameRecord = (payload) => gameApi.postGameRecord(payload, { signal: sessionRequests.signal })
  const calculateHuPoints = (payload) => gameApi.calculateHuPoints(payload, { signal: sessionRequests.signal })

  function invalidateSessionRequests() {
    sessionEpoch += 1
    sessionRequests.abort()
    sessionRequests = new AbortController()
    abortCurrentRecommend()
  }

  async function awaitCurrentSession(epoch, promise) {
    const result = await promise
    if (epoch !== sessionEpoch) throw new DOMException('旧对局请求已取消', 'AbortError')
    return result
  }

  const roundState = reactive(createInitialRoundState(initial))
  const gameMode = ref('SANDBOX')
  function emitPveAction(action, seat, tile = null) {
    if (gameMode.value !== 'PVE') return
    try { initial.onAction?.({ action, seat, tile, selfSeat: roundState.seatWind }) }
    catch (error) { console.warn('[pve sound]', error) }
  }
  // PVE identities stay relative to the user; seat winds rotate each hand.
  const dealerPlayerId = ref(0)
  const dealerSeat = ref('E')
  const roundCount = ref(1)
  const dealerRotationHistory = ref([0])
  const showGameOverModal = ref(false)
  const showRoundSummaryModal = ref(false)
  const pveRoundOverPending = ref(false)
  // Kept as an alias for existing callers; this now means visible, not eligible.
  const pveCircleSummary = showRoundSummaryModal

  /** @type {import('vue').Ref<Array<{ roundState: object, currentPhase: SessionPhase, lastStepResult: object|null }>>} */
  const historyStack = ref([])

  /** @type {import('vue').Ref<SessionPhase>} */
  const currentPhase = ref('IDLE')

  /** 最近一次 /api/game/step 响应 */
  const lastStepResult = ref(null)

  /** 刚摸入、挂在手牌最右侧的张（切出后清空） */
  const latestDrawnTile = ref(null)
  /**
   * 上帝视角：各座位「刚摸入、挂最右侧」的牌码。
   * 与 latestDrawnTile（自家）同步；对手摸牌写入对应 seat。
   * @type {import('vue').Ref<Record<string, string|null>>}
   */
  const latestDrawnBySeat = ref({ E: null, S: null, W: null, N: null })

  /** 牌墙（自动发牌后本地持有；不参与推荐请求） */
  const wallTiles = ref([])
  /** 上帝视角牌墙驱动：发牌后开启，轮转时自动摸牌 */
  const godViewWallMode = ref(false)
  /**
   * 自家摸牌完成后递增，供 App 在 nextTick 后强制拉 EV（避免与 watch 竞态）。
   */
  const recommendDrawToken = ref(0)
  /**
   * 用户手动挪动「得」后锁定该座布局，避免自动理牌立刻把百搭抓回最左。
   * 摸/切/一键理牌时清除。
   */
  const handLayoutPinned = ref({ E: false, S: false, W: false, N: false })

  /** 自动理牌开关（与 HandBar 同步） */
  const autoSortEnabled = ref(true)

  /**
   * 开局座次锁定。未锁定时仅允许改门风/财神；
   * 锁定后进入严格时序，须「重新开局」才能改座次。
   * 与 gameState 同步：SETUP → false，PLAYING → true。
   */
  const tableLocked = ref(false)

  /**
   * 生命周期：SETUP=自由录入起手；PLAYING=摸打副露严格驱动。
   * @type {import('vue').Ref<GameLifecycle>}
   */
  const gameState = ref('SETUP')

  /**
   * 当前拥有出牌权的门风（严格串行：E→S→W→N→E）
   * 开局固定从东风庄开始。
   */
  const currentTurnSeat = ref(DEALER_SEAT)

  /** 最近一次打出方（供吃碰过之后决定下家） */
  const lastDiscardSeat = ref(null)

  const loading = ref(false)
  const errorMsg = ref('')

  /**
   * 当前 /api/recommend EV 请求的 AbortController。
   * 切牌或发起新一轮推荐时 abort，避免阻塞手牌交互。
   */
  const currentRecommendAbortController = ref(null)

  /** 打断未完成的 EV 推荐请求（静默；调用方负责复位 UI Loading） */
  function abortCurrentRecommend() {
    const ac = currentRecommendAbortController.value
    if (!ac) return
    try {
      ac.abort()
    } catch {
      /* ignore */
    }
    currentRecommendAbortController.value = null
  }

  /**
   * 开始新一轮推荐：先取消上一请求，再返回本次 signal。
   * @returns {AbortSignal}
   */
  function beginRecommendFetch() {
    abortCurrentRecommend()
    const ac = new AbortController()
    currentRecommendAbortController.value = ac
    return ac.signal
  }

  /** 请求结束（成功 / 失败 / 取消）后清理 controller 引用 */
  function clearRecommendAbortController(signal) {
    const ac = currentRecommendAbortController.value
    if (ac && (!signal || ac.signal === signal)) {
      currentRecommendAbortController.value = null
    }
  }

  /** 自摸/捉铳/流局后的终局明细（GAME_OVER） */
  const selfWinSettlement = ref(null)

  /** 本局轨迹落盘：round_id + steps（GAME_OVER 时 POST /api/game/record） */
  const gameRoundId = ref('')
  const gameLogSteps = ref([])
  const initialDeal = ref(null)
  /** 自家最近一次切牌推荐快照（供 DISCARD 步骤写入 self_recommendation） */
  const pendingSelfRecommend = ref(null)
  const pendingAiRecommendations = ref({})

  /** 四家累计总分（按当前门风标签；轮庄时随门风映射平移） */
  const cumulativeScores = ref({ E: 0, S: 0, W: 0, N: 0 })

  /** 历史对局记录（保留跨局） */
  const roundHistory = ref([])

  /** 局序号 */
  const roundIndex = ref(0)

  /** 起手目标张数：庄 14 / 闲 13（rule.md §1） */
  const targetInitialCount = computed(() =>
    roundState.isDealer ? 14 : 13,
  )

  /** SETUP 且已录满起手 + 已选财神/门风 → 可「开始对局」 */
  const canStartPlaying = computed(
    () =>
      gameState.value === 'SETUP' &&
      !!roundState.dealerTile &&
      !!roundState.seatWind &&
      roundState.handTiles.length === targetInitialCount.value,
  )

  const isSetup = computed(() => gameState.value === 'SETUP')
  const isPlaying = computed(() => gameState.value === 'PLAYING')
  const isGameOver = computed(() => gameState.value === 'GAME_OVER')

  const phaseLabel = computed(() => {
    if (gameState.value === 'SETUP') {
      const n = roundState.handTiles.length
      const need = targetInitialCount.value
      return `开局准备 · 起手 ${n}/${need}（${roundState.isDealer ? '庄家' : '闲家'}）`
    }
    if (currentPhase.value === 'WAIT_RESPONSE') {
      return PHASE_LABEL.WAIT_RESPONSE
    }
    if (currentPhase.value === 'OPPONENT_DISCARD_ACTION') {
      return PHASE_LABEL.OPPONENT_DISCARD_ACTION
    }
    if (currentTurnSeat.value === roundState.seatWind) {
      const need = 14 - 3 * (roundState.melds?.length || 0)
      if (roundState.handTiles.length === need) {
        return `行动权 · 自家（${windLabel(roundState.seatWind)}）切牌`
      }
      return `行动权 · 自家摸牌`
    }
    return `行动权 · ${windLabel(currentTurnSeat.value)}风出牌`
  })

  const isSelfTurn = computed(
    () =>
      gameState.value === 'PLAYING' &&
      currentTurnSeat.value === roundState.seatWind,
  )

  const canUndo = computed(() => historyStack.value.length > 0)
  const historyDepth = computed(() => historyStack.value.length)

  // -----------------------------------------------------------------------
  // 全场可见物理牌 ≤4
  // -----------------------------------------------------------------------

  /**
   * 统计物理牌占用。
   * @param {object} state
   * @param {{ includeHiddenHands?: boolean }} [opts]
   *   includeHiddenHands=true 时计入三家暗手（上帝视角本地守恒）；
   *   推荐 / Rem 路径必须保持 false。
   */
  function countVisibleTiles(state, opts = {}) {
    /** @type {Record<string, number>} */
    const counts = Object.create(null)
    const bump = (tile) => {
      if (!tile) return
      counts[tile] = (counts[tile] || 0) + 1
    }

    for (const t of state.handTiles || []) bump(t)
    for (const t of state.discards || []) bump(t)
    for (const m of state.melds || []) {
      for (const t of m.tiles || []) bump(t)
    }
    for (const o of state.opponents || []) {
      for (const t of o.discards || []) bump(t)
      for (const m of o.melds || []) {
        for (const t of m.tiles || []) bump(t)
      }
      if (opts.includeHiddenHands) {
        for (const t of o.hand_tiles || []) bump(t)
      }
    }
    bump(state.dealerTile)

    return counts
  }

  /**
   * @param {object} state
   * @throws {Error} 任一牌种 >4
   */
  function assertVisibleTileLimit(state) {
    const counts = countVisibleTiles(state)
    const over = Object.entries(counts).filter(([, n]) => n > MAX_PER_TILE)
    if (over.length) {
      const detail = over
        .map(([tile, n]) => `${tile}×${n}`)
        .join('，')
      throw new Error(
        `全场可见物理牌超过 ${MAX_PER_TILE} 张限制：${detail}`,
      )
    }
  }

  /** 当前局面校验（供 UI 录入后即时调用） */
  function validateRoundState() {
    assertVisibleTileLimit(roundState)
  }

  // -----------------------------------------------------------------------
  // 快照（纯 POD，禁止 structuredClone 直接啃 Vue Proxy）
  // -----------------------------------------------------------------------

  /**
   * 安全深拷贝：toRaw 解包后再 JSON 序列化。
   * 失败时打印不可克隆路径，避免整局崩溃。
   * @template T
   * @param {T} value
   * @param {string} [label]
   * @returns {T|null}
   */
  function safeDeepClone(value, label = 'value') {
    if (value == null) return value
    try {
      const raw = toRaw(value)
      return JSON.parse(JSON.stringify(raw))
    } catch (e) {
      console.error(`[safeDeepClone] 无法克隆 ${label}:`, e)
      try {
        const keys =
          value && typeof value === 'object' ? Object.keys(toRaw(value)) : []
        console.error(`[safeDeepClone] top-level keys:`, keys)
      } catch {
        /* ignore */
      }
      return null
    }
  }

  /** 仅保留字符串牌码，过滤 Event / Proxy 等脏值 */
  function sanitizeTileCode(tile) {
    if (typeof tile !== 'string') return null
    const t = tile.trim()
    return t.length > 0 ? t : null
  }

  function sanitizeTileList(tiles) {
    return (tiles || [])
      .map((t) => sanitizeTileCode(t))
      .filter((t) => t != null)
  }

  function cloneRoundState(state = roundState) {
    const src = toRaw(state)
    const plain = {
      seatWind: src.seatWind,
      isDealer: !!src.isDealer,
      dealerSeat: src.dealerSeat || 'E',
      dealerTile: src.dealerTile,
      roundWind: src.roundWind || 'E',
      handTiles: sanitizeTileList(toRaw(src.handTiles) || []),
      melds: (toRaw(src.melds) || []).map((m) => {
        const mm = toRaw(m)
        return {
          ...mm,
          meld_type: mm.meld_type,
          tiles: sanitizeTileList(toRaw(mm.tiles) || []),
        }
      }),
      discards: sanitizeTileList(toRaw(src.discards) || []),
      opponents: (toRaw(src.opponents) || []).map((o) => {
        const oo = toRaw(o)
        return {
          seat_wind: oo.seat_wind,
          is_dealer: !!oo.is_dealer,
          melds: (toRaw(oo.melds) || []).map((m) => {
            const mm = toRaw(m)
            return {
              ...mm,
              meld_type: mm.meld_type,
              tiles: sanitizeTileList(toRaw(mm.tiles) || []),
            }
          }),
          discards: sanitizeTileList(toRaw(oo.discards) || []),
          hand_tiles: sanitizeTileList(toRaw(oo.hand_tiles) || []),
          role: oo.role,
        }
      }),
    }
    const cloned = safeDeepClone(plain, 'roundState')
    if (!cloned) {
      // JSON 失败时退回手写浅层拷贝（已是 plain）
      return plain
    }
    return cloned
  }

  function cloneStepResult(result) {
    if (!result) return null
    const cloned = safeDeepClone(toRaw(result), 'lastStepResult')
    if (cloned) return cloned
    // 降级：只保留可序列化的常用字段
    try {
      const r = toRaw(result)
      return {
        action_phase: r.action_phase ?? null,
        need_self_action: !!r.need_self_action,
        next_turn_seat: r.next_turn_seat ?? null,
        recommend_discard: r.recommend_discard
          ? safeDeepClone(toRaw(r.recommend_discard), 'recommend_discard')
          : null,
        call_decision: r.call_decision
          ? safeDeepClone(toRaw(r.call_decision), 'call_decision')
          : null,
        updated_state: null,
      }
    } catch (e) {
      console.error('[cloneStepResult] fallback failed', e)
      return null
    }
  }

  function pushSnapshot() {
    historyStack.value.push({
      roundState: cloneRoundState(),
      currentPhase: currentPhase.value,
      currentTurnSeat: currentTurnSeat.value,
      lastDiscardSeat: lastDiscardSeat.value,
      latestDrawnTile: sanitizeTileCode(latestDrawnTile.value),
      latestDrawnBySeat: { ...(latestDrawnBySeat.value || {}) },
      lastStepResult: cloneStepResult(lastStepResult.value),
      gameLogLength: gameLogSteps.value.length,
      pendingSelfRecommend: safeDeepClone(pendingSelfRecommend.value, 'pendingSelfRecommend'),
      pendingAiRecommendations: safeDeepClone(pendingAiRecommendations.value, 'pendingAiRecommendations') || {},
    })
  }

  /** 仅回滚「本步」刚压入的快照；禁止误弹更早步骤 */
  function rollbackLastSnapshot(didPush) {
    if (!didPush || !historyStack.value.length) return
    const snap = historyStack.value.pop()
    applyRoundState(snap.roundState)
    currentPhase.value = snap.currentPhase
    currentTurnSeat.value = snap.currentTurnSeat ?? DEALER_SEAT
    lastDiscardSeat.value = snap.lastDiscardSeat ?? null
    latestDrawnTile.value = snap.latestDrawnTile ?? null
    latestDrawnBySeat.value = {
      E: null,
      S: null,
      W: null,
      N: null,
      ...(snap.latestDrawnBySeat || {}),
    }
    lastStepResult.value = snap.lastStepResult
    restoreGameLogSnapshot(snap)
  }

  function restoreGameLogSnapshot(snap) {
    if (typeof snap.gameLogLength !== 'number') return
    gameLogSteps.value = gameLogSteps.value.slice(0, snap.gameLogLength)
    pendingSelfRecommend.value = snap.pendingSelfRecommend ?? null
    pendingAiRecommendations.value = snap.pendingAiRecommendations || {}
  }

  function applyRoundState(snapshot) {
    const s = snapshot
    roundState.seatWind = s.seatWind
    roundState.isDealer = !!s.isDealer
    roundState.dealerSeat = s.dealerSeat || 'E'
    roundState.dealerTile = s.dealerTile
    roundState.roundWind = s.roundWind || 'E'
    roundState.handTiles = [...(s.handTiles || [])]
    roundState.melds = (s.melds || []).map((m) => ({
      ...m,
      meld_type: m.meld_type,
      tiles: [...(m.tiles || [])],
    }))
    roundState.discards = [...(s.discards || [])]
    roundState.opponents = (s.opponents || []).map((o) => ({
      seat_wind: o.seat_wind,
      is_dealer: !!o.is_dealer,
      melds: (o.melds || []).map((m) => ({
        ...m,
        meld_type: m.meld_type,
        tiles: [...(m.tiles || [])],
      })),
      discards: [...(o.discards || [])],
      hand_tiles: [...(o.hand_tiles || [])],
      role: o.role,
    }))
  }

  /**
   * 应用后端 updated_state。
   * @param {object} updated
   * @param {{ keepLocalOpponents?: boolean }} [opts]
   *   keepLocalOpponents=true：不覆盖三家公开牌河/副露（防 DRAW 响应抹掉上家刚打出的牌）
   */
  function applyUpdatedStateFromApi(updated, opts = {}) {
    if (!updated) return
    if (Array.isArray(updated.hand_tiles)) {
      roundState.handTiles = [...updated.hand_tiles]
    }
    if (Array.isArray(updated.melds)) {
      roundState.melds = updated.melds.map((m) => ({
        ...m,
        meld_type: m.meld_type,
        tiles: [...(m.tiles || [])],
      }))
    }
    if (Array.isArray(updated.discards)) {
      roundState.discards = [...updated.discards]
    }
    if (updated.dealer_tile) roundState.dealerTile = updated.dealer_tile
    if (updated.seat_wind) roundState.seatWind = updated.seat_wind
    if (updated.round_wind) roundState.roundWind = updated.round_wind
    if (typeof updated.is_dealer === 'boolean') {
      roundState.isDealer = updated.is_dealer
    }

    if (opts.keepLocalOpponents) return

    if (Array.isArray(updated.opponents) && updated.opponents.length > 0) {
      const localBySeat = Object.fromEntries(
        (roundState.opponents || []).map((o) => [o.seat_wind, o]),
      )
      roundState.opponents = updated.opponents.map((o) => {
        const local = localBySeat[o.seat_wind]
        const apiDisc = [...(o.discards || [])]
        const localDisc = [...(local?.discards || [])]
        // 取更长牌河，防止 API 旧快照覆盖本地已推进的弃牌
        const discards =
          apiDisc.length >= localDisc.length ? apiDisc : localDisc
        const apiMelds = (o.melds || []).map((m) => ({
          ...m,
          meld_type: m.meld_type,
          tiles: [...(m.tiles || [])],
        }))
        const localMelds = local?.melds ? cloneMelds(local.melds) : []
        const melds =
          apiMelds.length >= localMelds.length ? apiMelds : localMelds
        return {
          seat_wind: o.seat_wind,
          is_dealer: !!o.is_dealer,
          melds,
          discards,
          hand_tiles: [...(local?.hand_tiles || [])],
          role: local?.role,
        }
      })
    }
  }

  function logTurn(tag, extra = {}) {
    const oppDisc = (roundState.opponents || [])
      .map((o) => `${o.seat_wind}:${(o.discards || []).length}`)
      .join('|')
    console.log(`[turn] ${tag}`, {
      gameState: gameState.value,
      currentTurnSeat: currentTurnSeat.value,
      phase: currentPhase.value,
      handLen: roundState.handTiles.length,
      selfDisc: roundState.discards.length,
      oppDisc,
      historyDepth: historyStack.value.length,
      ...extra,
    })
  }

  // -----------------------------------------------------------------------
  // 对局轨迹（GameRecord steps）
  // -----------------------------------------------------------------------

  function newGameRoundId() {
    const d = new Date()
    const pad = (n) => String(n).padStart(2, '0')
    const ts =
      `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` +
      `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`
    const rand = Math.random().toString(16).slice(2, 10)
    return `${ts}_${rand}`
  }

  function resetGameLog() {
    gameRoundId.value = newGameRoundId()
    gameLogSteps.value = []
    pendingSelfRecommend.value = null
    pendingAiRecommendations.value = {}
  }

  function setPendingAiRecommend(seat, rec) {
    if (!seat || !rec?.best_tile) return
    const best = rec.candidates?.find((candidate) => candidate.tile === rec.best_tile)
    pendingAiRecommendations.value = {
      ...pendingAiRecommendations.value,
      [seat]: { best_tile: rec.best_tile, net_ev: best?.ev_score ?? null,
        candidates: (rec.candidates || []).map((candidate) => ({ tile: candidate.tile,
          ev_score: candidate.ev_score, effective_count: candidate.effective_count,
          deal_in_risks: candidate.deal_in_risks, shanten: candidate.shanten })) },
    }
  }

  function setPendingSelfRecommend(rec) {
    if (!rec || !rec.best_tile) {
      pendingSelfRecommend.value = null
      return
    }
    const best = rec.candidates?.find((c) => c.tile === rec.best_tile)
    const net =
      best?.ev_score ??
      best?.net_ev ??
      rec.candidates?.[0]?.ev_score ??
      null
    pendingSelfRecommend.value = {
      best_tile: rec.best_tile,
      net_ev: net != null ? Number(net) : null,
      candidates: (rec.candidates || []).map((candidate) => ({
        tile: candidate.tile,
        ev_score: candidate.ev_score,
        effective_count: candidate.effective_count,
        deal_in_risks: candidate.deal_in_risks,
        shanten: candidate.shanten,
      })),
    }
  }

  function currentTurnNumber() {
    let n = (roundState.discards || []).length
    for (const o of roundState.opponents || []) {
      n += (o.discards || []).length
    }
    return Math.floor(n / 4) + 1
  }

  /**
   * @param {{
   *   action: 'DRAW'|'DISCARD'|'CHI'|'PONG'|'GANG'|'WIN',
   *   seat?: string,
   *   tile?: string|null,
   *   self_recommendation?: { best_tile?: string, net_ev?: number|null }|null,
   * }} step
   */
  function appendGameLogStep(step) {
    if (!gameRoundId.value) resetGameLog()
    const seat = step.seat || currentTurnSeat.value || roundState.seatWind
    const aiDecision = seat !== roundState.seatWind && ['DISCARD', 'GANG', 'WIN'].includes(step.action)
      ? pendingAiRecommendations.value[seat] : null
    if (aiDecision) {
      const next = { ...pendingAiRecommendations.value }
      delete next[seat]
      pendingAiRecommendations.value = next
    }
    gameLogSteps.value = [
      ...gameLogSteps.value,
      {
        turn: step.turn ?? currentTurnNumber(),
        seat,
        action: step.action,
        tile: step.tile ?? null,
        self_recommendation: step.self_recommendation ?? aiDecision ?? null,
        details: step.details ?? null,
        snapshot: {
          wall_count: wallTiles.value.length,
          current_turn_seat: currentTurnSeat.value,
          self: cloneRoundState(),
        },
      },
    ]
  }

  function meldActionLabel(meldType) {
    if (meldType === 'chi') return 'CHI'
    if (meldType === 'pong') return 'PONG'
    if (meldType === 'ming_gang' || meldType === 'an_gang') return 'GANG'
    return 'GANG'
  }

  async function submitGameRecord(finalResult) {
    const epoch = sessionEpoch
    try {
      if (!gameRoundId.value) return null
      const payload = {
        round_id: gameRoundId.value,
        config: {
          dealer_seat: DEALER_SEAT,
          dealer_tile: roundState.dealerTile,
          seat_wind: roundState.seatWind,
          circle_index: roundCount.value,
          round_index: roundIndex.value || 1,
          initial_hands: initialDeal.value?.hands || {},
          initial_wall_tiles: initialDeal.value?.wall_tiles || [],
        },
        steps: [...gameLogSteps.value],
        final_result: finalResult || null,
      }
      try {
        const res = await awaitCurrentSession(epoch, postGameRecord(payload))
        logTurn('submitGameRecord:ok', {
          game_id: res?.game_id,
          steps: res?.steps_count,
        })
        return res
      } catch (e) {
        if (epoch !== sessionEpoch) return
        console.warn('[submitGameRecord] failed', e)
        errorMsg.value = e?.message
          ? `${e.message}（对局已结束，轨迹未落盘）`
          : '轨迹落盘失败'
        return null
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * @param {'DISCARD'|'CALL'|'WAIT'|string} actionPhase
   * @param {boolean} needSelf
   * @returns {SessionPhase}
   */
  function mapActionPhase(actionPhase, needSelf) {
    if (actionPhase === 'DRAW' && needSelf) return 'WAITING'
    if (actionPhase === 'DISCARD' && needSelf) return 'MY_TURN_DISCARD'
    if (actionPhase === 'CALL' && needSelf) return 'OPPONENT_DISCARD_ACTION'
    if (actionPhase === 'WAIT' || actionPhase === 'DRAW') return 'WAITING'
    return needSelf ? 'MY_TURN_DISCARD' : 'WAITING'
  }

  function toHandRequestPayload() {
    /**
     * 核心隔离：推荐 / 步进请求只带三家【公开】副露与牌河。
     * 严禁打包 opponents[].hand_tiles（上帝视角暗手仅存本地）。
     */
    const opponentsPublic = roundState.opponents.map((o) => {
      const raw = o && typeof o === 'object' ? o : {}
      return {
        seat_wind: raw.seat_wind,
        is_dealer: !!raw.is_dealer,
        melds: (raw.melds || []).map((m) => ({
          ...m,
          meld_type: m.meld_type,
          tiles: [...(m.tiles || [])],
        })),
        discards: [...(raw.discards || [])],
      }
    })

    for (const o of opponentsPublic) {
      const keys = Object.keys(o)
      if (
        keys.includes('hand_tiles') ||
        keys.includes('handTiles') ||
        keys.includes('closed_hand')
      ) {
        throw new Error(
          '数据隔离失败：HandRequest.opponents 含暗手字段，已阻断推荐请求',
        )
      }
    }

    return {
      hand_tiles: [...roundState.handTiles],
      melds: roundState.melds.map((m) => ({
        ...m,
        meld_type: m.meld_type,
        tiles: [...m.tiles],
      })),
      discards: [...roundState.discards],
      dealer_tile: roundState.dealerTile,
      is_dealer: roundState.isDealer,
      seat_wind: roundState.seatWind,
      round_wind: roundState.roundWind,
      opponents: opponentsPublic,
      discarded_tiles: [],
    }
  }

  // -----------------------------------------------------------------------
  // 公开方法
  // -----------------------------------------------------------------------

  /**
   * 按开关整理暗手。
   * latestDrawnTile 只影响排序位置，清空标记时不得再从手牌删牌。
   * @param {{ keepDrawn?: boolean, force?: boolean }} [opts]
   */
  function applyHandSort(opts = {}) {
    const force = !!opts.force
    if (!force && !autoSortEnabled.value) return
    const self = roundState.seatWind
    // 手动组牌锁定时：非 force 不把「得」抓回最左
    if (handLayoutPinned.value[self] && !force) {
      const keepDrawn = opts.keepDrawn === true
      const drawn =
        keepDrawn && latestDrawnTile.value ? latestDrawnTile.value : undefined
      if (drawn) {
        roundState.handTiles = ensureTileAtEnd(roundState.handTiles, drawn)
      }
      return
    }
    if (force) clearHandLayoutPin(self)
    const n0 = roundState.handTiles.length
    const keepDrawn = opts.keepDrawn === true
    const drawn =
      keepDrawn && latestDrawnTile.value ? latestDrawnTile.value : undefined
    const sorted = sortHandTiles(
      roundState.handTiles,
      roundState.dealerTile,
      drawn,
    )
    console.assert(
      sorted.length === n0,
      `[applyHandSort] 理牌后张数变化 ${n0} → ${sorted.length}`,
    )
    roundState.handTiles = sorted
    setDrawnMarker(roundState.seatWind, keepDrawn ? latestDrawnTile.value : null)
  }

  function clearHandLayoutPin(seat) {
    if (!seat) {
      handLayoutPinned.value = { E: false, S: false, W: false, N: false }
      return
    }
    if (!handLayoutPinned.value[seat]) return
    handLayoutPinned.value = { ...handLayoutPinned.value, [seat]: false }
  }

  /**
   * 上帝视角：仅允许移动「得」百搭在暗手中的位置（插嵌组牌）。
   * @param {string} seat
   * @param {number} fromIndex
   * @param {number} toIndex 插入到该下标之前
   */
  function moveJokerInHand(seat, fromIndex, toIndex) {
    const dealer = roundState.dealerTile
    if (!dealer) throw new Error('未设置财神，无法识别百搭')

    const applyMove = (hand) => {
      if (
        typeof fromIndex !== 'number' ||
        fromIndex < 0 ||
        fromIndex >= hand.length
      ) {
        throw new Error('百搭移动：源下标无效')
      }
      const tile = hand[fromIndex]
      if (!isJokerPhysical(tile, dealer)) {
        throw new Error('仅「得」（百搭）可自由移动插嵌')
      }
      // 摸入挂右：禁止把摸入张挪进主区破坏 Gap（可整段一起挪到末尾前）
      const drawn = latestDrawnBySeat.value?.[seat]
      let dest = toIndex
      if (
        drawn &&
        hand.length > 0 &&
        hand[hand.length - 1] === drawn &&
        fromIndex !== hand.length - 1
      ) {
        // 目标不得超过摸入槽之前
        dest = Math.min(dest, hand.length - 1)
      }
      return moveTileInList(hand, fromIndex, dest)
    }

    if (seat === roundState.seatWind) {
      roundState.handTiles = applyMove(roundState.handTiles)
      handLayoutPinned.value = {
        ...handLayoutPinned.value,
        [seat]: true,
      }
      logTurn('moveJokerInHand:self', { fromIndex, toIndex })
      return roundState.handTiles
    }

    const oi = roundState.opponents.findIndex((o) => o.seat_wind === seat)
    if (oi < 0) throw new Error(`找不到座位 ${seat}`)
    const opps = roundState.opponents.map((o) => ({
      ...o,
      melds: cloneMelds(o.melds),
      discards: [...(o.discards || [])],
      hand_tiles: [...(o.hand_tiles || [])],
    }))
    opps[oi].hand_tiles = applyMove(opps[oi].hand_tiles)
    roundState.opponents = opps
    handLayoutPinned.value = {
      ...handLayoutPinned.value,
      [seat]: true,
    }
    logTurn('moveJokerInHand:opp', { seat, fromIndex, toIndex })
    return opps[oi].hand_tiles
  }

  /**
   * 设置某座「摸入挂右」标记（自家同时写 latestDrawnTile）。
   * @param {string} seat
   * @param {string|null|undefined} tile
   */
  function setDrawnMarker(seat, tile) {
    const code = tile ? sanitizeTileCode(tile) : null
    latestDrawnBySeat.value = {
      ...latestDrawnBySeat.value,
      [seat]: code || null,
    }
    if (seat === roundState.seatWind) {
      latestDrawnTile.value = code || null
    }
  }

  function clearDrawnMarker(seat) {
    setDrawnMarker(seat, null)
  }

  function clearAllDrawnMarkers() {
    latestDrawnTile.value = null
    latestDrawnBySeat.value = { E: null, S: null, W: null, N: null }
  }

  /**
   * 规整指定座位暗手（上帝视角四家共用）。
   * @param {string} seat
   * @param {{ keepDrawn?: boolean }} [opts]
   */
  function sortSeatClosedHand(seat, opts = {}) {
    const keepDrawn = opts.keepDrawn === true
    const force = !!opts.force
    const drawn = keepDrawn
      ? latestDrawnBySeat.value?.[seat] ||
        (seat === roundState.seatWind ? latestDrawnTile.value : null)
      : undefined
    const dealer = roundState.dealerTile

    // 手动插嵌锁定：只保证摸入张挂右，不强制百搭回最左
    if (handLayoutPinned.value[seat] && !force) {
      if (seat === roundState.seatWind) {
        if (drawn) {
          roundState.handTiles = ensureTileAtEnd(roundState.handTiles, drawn)
        }
        return roundState.handTiles
      }
      const oi = roundState.opponents.findIndex((o) => o.seat_wind === seat)
      if (oi < 0) return []
      const opps = roundState.opponents.map((o) => ({
        ...o,
        melds: cloneMelds(o.melds),
        discards: [...(o.discards || [])],
        hand_tiles: [...(o.hand_tiles || [])],
      }))
      if (drawn) {
        opps[oi].hand_tiles = ensureTileAtEnd(opps[oi].hand_tiles, drawn)
      }
      roundState.opponents = opps
      return opps[oi].hand_tiles
    }

    if (force) clearHandLayoutPin(seat)

    if (seat === roundState.seatWind) {
      const n0 = roundState.handTiles.length
      const sorted = sortHandTiles(roundState.handTiles, dealer, drawn || undefined)
      console.assert(
        sorted.length === n0,
        `[sortSeatClosedHand/self] ${n0} → ${sorted.length}`,
      )
      roundState.handTiles = sorted
      if (!keepDrawn) clearDrawnMarker(seat)
      else if (drawn) setDrawnMarker(seat, drawn)
      return sorted
    }

    const oi = roundState.opponents.findIndex((o) => o.seat_wind === seat)
    if (oi < 0) return []
    const opps = roundState.opponents.map((o) => ({
      ...o,
      melds: cloneMelds(o.melds),
      discards: [...(o.discards || [])],
      hand_tiles: [...(o.hand_tiles || [])],
    }))
    const n0 = opps[oi].hand_tiles.length
    opps[oi].hand_tiles = sortHandTiles(
      opps[oi].hand_tiles,
      dealer,
      drawn || undefined,
    )
    console.assert(
      opps[oi].hand_tiles.length === n0,
      `[sortSeatClosedHand/${seat}] ${n0} → ${opps[oi].hand_tiles.length}`,
    )
    roundState.opponents = opps
    if (!keepDrawn) clearDrawnMarker(seat)
    else if (drawn) setDrawnMarker(seat, drawn)
    return opps[oi].hand_tiles
  }

  /** 开局/重置：四家暗手全部理顺（无摸入右挂） */
  function sortAllClosedHands() {
    clearAllDrawnMarkers()
    clearHandLayoutPin()
    sortSeatClosedHand(roundState.seatWind, { keepDrawn: false, force: true })
    for (const o of roundState.opponents || []) {
      sortSeatClosedHand(o.seat_wind, { keepDrawn: false, force: true })
    }
  }

  /**
   * 从对手暗手扣除副露用张（上帝视角）。
   * 吃碰明杠：牌河 claimed 不在暗手；暗杠：4 张均在暗手。
   */
  function removeTilesFromOpponentHand(seat, tiles, claimed, isAnGang) {
    const oi = roundState.opponents.findIndex((o) => o.seat_wind === seat)
    if (oi < 0) return
    const opps = roundState.opponents.map((o) => ({
      ...o,
      melds: cloneMelds(o.melds),
      discards: [...(o.discards || [])],
      hand_tiles: [...(o.hand_tiles || [])],
    }))
    const hand = opps[oi].hand_tiles
    if (!hand.length) {
      roundState.opponents = opps
      return
    }
    /** @type {string[]} */
    let fromHand = []
    if (isAnGang) {
      fromHand = [...(tiles || [])]
    } else {
      fromHand = [...(tiles || [])]
      if (claimed) {
        const ci = fromHand.indexOf(claimed)
        if (ci >= 0) fromHand.splice(ci, 1)
      }
    }
    for (const t of fromHand) {
      const hi = hand.indexOf(t)
      if (hi >= 0) hand.splice(hi, 1)
    }
    roundState.opponents = opps
  }

  /**
   * 步进成功后：更新摸进张标记并理牌（不得额外扣减手牌）
   */
  function afterStepSort(event, result) {
    const self = roundState.seatWind
    if (event.event_type === 'DRAW' && event.actor_seat === self) {
      setDrawnMarker(self, event.tile || null)
      applyHandSort({ keepDrawn: true })
      return
    }
    if (event.event_type === 'DISCARD' && event.actor_seat === self) {
      // 只清「摸进」标记；牌已由 DISCARD / 本地 splice 扣除恰好 1 张
      clearDrawnMarker(self)
      applyHandSort({ keepDrawn: false })
      return
    }
    if (event.event_type === 'MELD' && event.actor_seat === self) {
      clearDrawnMarker(self)
      applyHandSort({ keepDrawn: false })
      return
    }
    if (
      result?.action_phase === 'DISCARD' &&
      result?.need_self_action &&
      !latestDrawnTile.value
    ) {
      applyHandSort({ keepDrawn: false })
    }
  }

  // -----------------------------------------------------------------------
  // 四方串行行动权（currentTurnSeat）
  // -----------------------------------------------------------------------

  /**
   * 根据 currentTurnSeat 同步 currentPhase。
   * @param {{ force?: boolean }} [opts] force=true 时强制离开 CALL / WAIT_RESPONSE 挂起态
   */
  function syncPhaseFromTurn(opts = {}) {
    if (gameState.value !== 'PLAYING') {
      currentPhase.value = 'IDLE'
      return
    }
    // 仅在「仍等用户响应副露」时挂起；副露完成 / 全员过牌必须 force 离开
    if (
      !opts.force &&
      (currentPhase.value === 'OPPONENT_DISCARD_ACTION' ||
        currentPhase.value === 'WAIT_RESPONSE')
    ) {
      return
    }

    if (currentTurnSeat.value === roundState.seatWind) {
      const need = 14 - 3 * (roundState.melds?.length || 0)
      currentPhase.value =
        roundState.handTiles.length === need
          ? 'MY_TURN_DISCARD'
          : 'WAITING'
    } else {
      currentPhase.value = 'WAITING'
    }
  }

  /**
   * 无人副露 / 过牌后：行动权逆时针给下一家；
   * 上帝视角牌墙模式下自动为下一家摸牌（含自家 → 触发切牌态 + 清旧推荐）。
   * @param {string} afterSeat 刚打完或被过的出牌方
   * @param {{ bypassLoading?: boolean }} [opts]
   */
  async function advanceTurnToNext(afterSeat, opts = {}) {
    const epoch = sessionEpoch
    try {
      // 响应窗未关闭时严禁摸牌（兜底）
      if (
        !opts.force &&
        (currentPhase.value === 'WAIT_RESPONSE' ||
          currentPhase.value === 'OPPONENT_DISCARD_ACTION')
      ) {
        logTurn('advanceTurnToNext:blocked-response', {
          phase: currentPhase.value,
          afterSeat,
        })
        return { blocked: true, reason: 'response-window' }
      }

      const nxt = nextSeat(afterSeat || currentTurnSeat.value)
      currentTurnSeat.value = nxt
      const drawInfo = await awaitCurrentSession(epoch, ensureGodViewDrawForSeat(nxt, {
        bypassLoading: opts.bypassLoading !== false,
      }))
      syncPhaseFromTurn({ force: true })
      // 守恒断言：轮转完成后行动方应处于出牌张数（荒牌除外）
      if (!drawInfo?.exhausted && godViewWallMode.value) {
        const info = seatHandSlots(nxt)
        console.assert(
          info.handLen === info.discardNeed,
          `[advanceTurnToNext] ${nxt} 暗手 ${info.handLen} ≠ 待切 ${info.discardNeed}（副露 ${info.meldsN}）`,
        )
      }
      logTurn('advanceTurnToNext', {
        afterSeat,
        next: nxt,
        drawn: drawInfo?.tile || null,
        exhausted: !!drawInfo?.exhausted,
        hand: seatHandSlots(nxt),
      })
      return { nextSeat: nxt, draw: drawInfo }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 取某座暗手与副露（供响应检测）。
   * @param {string} seat
   */
  function getSeatClosedState(seat) {
    if (seat === roundState.seatWind) {
      return {
        hand: [...roundState.handTiles],
        melds: cloneMelds(roundState.melds),
      }
    }
    const opp = roundState.opponents.find((o) => o.seat_wind === seat)
    return {
      hand: [...(opp?.hand_tiles || [])],
      melds: cloneMelds(opp?.melds || []),
    }
  }

  /**
   * 出牌后扫描全桌可响应动作。
   * @param {string} providerSeat
   * @param {string} discardedTile
   */
  function scanTableResponses(providerSeat, discardedTile) {
    return detectTableResponses({
      providerSeat,
      discardedTile,
      dealerTile: roundState.dealerTile,
      selfSeat: roundState.seatWind,
      getSeat: getSeatClosedState,
      godView: !!godViewWallMode.value,
    })
  }

  /**
   * 打牌后流转：
   * 1) 若有任一家可吃/碰/杠/胡（或后端要求自家 CALL）→ WAIT_RESPONSE，禁止摸牌
   * 2) 否则逆时针下一家并自动摸牌
   */
  async function resolveAfterDiscard(actorSeat, stepResult) {
    const epoch = sessionEpoch
    try {
      lastDiscardSeat.value = actorSeat

      const discardedTile = (() => {
        if (actorSeat === roundState.seatWind) {
          const river = roundState.discards || []
          return river.length ? river[river.length - 1] : ''
        }
        const opp = roundState.opponents.find((o) => o.seat_wind === actorSeat)
        return opp?.discards?.length
          ? opp.discards[opp.discards.length - 1]
          : ''
      })()

      const selfCall =
        !!stepResult?.need_self_action &&
        stepResult?.action_phase === 'CALL' &&
        !!stepResult?.call_decision

      const detection = scanTableResponses(actorSeat, discardedTile)
      const needWindow =
        selfCall ||
        shouldEnterResponseWindow(detection, {
          godView: !!godViewWallMode.value,
        })

      if (needWindow) {
        // 自家有后端 CALL 决策时保留 ActionPrompt；否则纯 WAIT_RESPONSE
        currentPhase.value = selfCall
          ? 'OPPONENT_DISCARD_ACTION'
          : 'WAIT_RESPONSE'
        // 行动权暂留出牌方，禁止下家提前「出牌中」/摸牌
        currentTurnSeat.value = actorSeat
        const backendActions = stepResult?.call_decision?.available_actions ||
          (stepResult?.call_decision?.candidates || []).map((c) => c.action)
        const selfCanHu = backendActions.some((a) => ['hu', 'catch_win'].includes(a?.action_type))
        const catchSeats = buildPendingHuQueue(actorSeat, [
          ...(detection.catchWinSeats || []), ...(selfCanHu ? [roundState.seatWind] : []),
        ])
        const catchNote =
          catchSeats.length > 0
            ? `【捉铳】${catchSeats.map(windLabel).join('、')} 可胡 ${discardedTile}（点炮方 ${windLabel(actorSeat)}）· 禁止摸牌`
            : `${windLabel(actorSeat)} 打出 ${discardedTile} · 等待副露响应（勿摸牌）`
        lastStepResult.value = {
          ...(lastStepResult.value && typeof lastStepResult.value === 'object'
            ? lastStepResult.value
            : {}),
          ...(stepResult && typeof stepResult === 'object' ? stepResult : {}),
          action_phase: selfCall ? 'CALL' : 'WAIT',
          need_self_action: selfCall,
          call_decision: selfCall
            ? stepResult.call_decision
            : lastStepResult.value?.call_decision ?? null,
          note: selfCall
            ? lastStepResult.value?.note || catchNote
            : catchNote,
          _table_responses: detection.options,
          _catch_win_seats: catchSeats,
          pending_hu_queue: catchSeats,
          _self_call_decision: selfCall ? stepResult.call_decision : null,
          _response_tile: discardedTile,
        }
        syncHuResponseWindow()
        logTurn('resolveAfterDiscard:WAIT_RESPONSE', {
          actorSeat,
          discardedTile,
          selfCall,
          catchWinSeats: catchSeats,
          options: detection.options,
          untracked: detection.untracked,
        })
        return {
          deferred: true,
          responseWindow: true,
          options: detection.options,
          catchWinSeats: catchSeats,
        }
      }

      const adv = await awaitCurrentSession(epoch, advanceTurnToNext(actorSeat, {
        bypassLoading: true,
        force: true,
      }))
      // 放行后清除出牌标记，避免响应按钮残留
      lastDiscardSeat.value = null
      logTurn('resolveAfterDiscard:advance', { actorSeat })
      return adv


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 座位暗手守恒指标（rule_2.md §3）。
   * - waitNeed = 13 - 3*melds：摸牌前暗手张数
   * - discardNeed = 14 - 3*melds：出牌阶段暗手张数
   * - slots = handLen + 3*melds：相对「满手 14」的槽位（仅用于 slots===13/14 语义）
   * 禁止把 slots 与 discardNeed 直接比较（量纲不同）。
   * @param {string} seat
   */
  function seatHandSlots(seat) {
    if (seat === roundState.seatWind) {
      const meldsN = roundState.melds?.length || 0
      const handLen = roundState.handTiles.length
      return {
        handLen,
        meldsN,
        slots: handLen + 3 * meldsN,
        waitNeed: 13 - 3 * meldsN,
        discardNeed: 14 - 3 * meldsN,
      }
    }
    const opp = roundState.opponents.find((o) => o.seat_wind === seat)
    const meldsN = opp?.melds?.length || 0
    const handLen = (opp?.hand_tiles || []).length
    return {
      handLen,
      meldsN,
      slots: handLen + 3 * meldsN,
      waitNeed: 13 - 3 * meldsN,
      discardNeed: 14 - 3 * meldsN,
    }
  }

  /** 该座是否已达出牌张数（可点亮「出牌中」） */
  function isSeatReadyToDiscard(seat) {
    const info = seatHandSlots(seat)
    return info.handLen === info.discardNeed
  }

  /** 该座是否处于待摸（自然轮转后应自动摸 1） */
  function isSeatWaitingDraw(seat) {
    const info = seatHandSlots(seat)
    return info.handLen === info.waitNeed
  }

  /**
   * 上帝视角：轮到 seat 时若待摸则从牌墙自动摸 1 张。
   * 场景 A（副露当巡吃/碰）：handLen === discardNeed → 跳过摸牌，直接切。
   * 场景 B（逆时针轮转，含副露后的后续巡）：handLen === waitNeed → 必须先摸再 DISCARD。
   * 严禁用 handLen===13 或 slots>=discardNeed（量纲错误）判断。
   * 严禁在 WAIT_RESPONSE 窗口内摸牌。
   */
  async function ensureGodViewDrawForSeat(seat, opts = {}) {
    const epoch = sessionEpoch
    try {
      if (!godViewWallMode.value || gameState.value !== 'PLAYING') {
        return null
      }
      if (gameState.value === 'GAME_OVER') return null
      if (
        !opts.force &&
        (currentPhase.value === 'WAIT_RESPONSE' ||
          currentPhase.value === 'OPPONENT_DISCARD_ACTION')
      ) {
        logTurn('ensureGodViewDraw:blocked-response', { seat })
        return { skipped: true, seat, reason: 'response-window' }
      }

      const info = seatHandSlots(seat)

      // 场景 A / 已摸完：暗手已达出牌张数
      if (info.handLen === info.discardNeed) {
        if (seat === roundState.seatWind) {
          currentPhase.value = 'MY_TURN_DISCARD'
        }
        return { skipped: true, seat, reason: 'discard-ready', ...info }
      }

      // 多于出牌张数：异常
      if (info.handLen > info.discardNeed) {
        logTurn('ensureGodViewDraw:over-discard', { seat, ...info })
        return { skipped: true, seat, reason: 'over-discard', ...info }
      }

      // 场景 B：必须恰好为待摸张数才自动摸
      if (info.handLen !== info.waitNeed) {
        logTurn('ensureGodViewDraw:skip-odd', { seat, ...info })
        return { skipped: true, seat, reason: 'odd-count', ...info }
      }

      if (!wallTiles.value.length) {
        logTurn('ensureGodViewDraw:exhaust', { seat, ...info })
        await awaitCurrentSession(epoch, declareDraw('荒牌流局（牌墙摸尽）'))
        return { exhausted: true, seat }
      }

      if (seat === roundState.seatWind) {
        return applyGodViewSelfDrawFast({ rinshan: !!opts.rinshan })
      }

      const drawn = drawFromWallLocal(seat, { rinshan: !!opts.rinshan })
      logTurn('ensureGodViewDraw:opp', { seat, tile: drawn, ...info })
      return { tile: drawn, seat }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 自家上帝视角摸牌快路径：append + 右挂，不做全量 sort / 不阻塞 await 后端。
   */
  function applyGodViewSelfDrawFast(opts = {}) {
    console.time('draw-to-render')
    const self = roundState.seatWind
    const meldsN = roundState.melds?.length || 0
    const beforeNeed = 13 - 3 * meldsN
    const afterNeed = 14 - 3 * meldsN
    if (roundState.handTiles.length !== beforeNeed) {
      console.timeEnd('draw-to-render')
      throw new Error(
        `非待摸状态：需要 ${beforeNeed} 张，当前 ${roundState.handTiles.length}`,
      )
    }
    if (!wallTiles.value.length) {
      console.timeEnd('draw-to-render')
      throw new Error('牌墙已空，无法摸牌')
    }

    const drawn = opts.rinshan ? wallTiles.value.at(-1) : wallTiles.value[0]
    wallTiles.value = opts.rinshan ? wallTiles.value.slice(0, -1) : wallTiles.value.slice(1)

    // 快照供撤回（同步，但在 mutate 前一次即可）
    pushSnapshot()

    // 轻量入账：摸牌时解除百搭锁定并先规整前 N 张，再挂右
    clearHandLayoutPin(self)
    roundState.handTiles = sortHandTiles(
      roundState.handTiles,
      roundState.dealerTile,
      undefined,
    )
    roundState.handTiles = [...roundState.handTiles, drawn]
    setDrawnMarker(self, drawn)
    currentTurnSeat.value = self
    currentPhase.value = 'MY_TURN_DISCARD'
    lastDiscardSeat.value = null
    lastStepResult.value = {
      ...(lastStepResult.value && typeof lastStepResult.value === 'object'
        ? lastStepResult.value
        : {}),
      action_phase: 'DISCARD',
      need_self_action: true,
      recommend_discard: null,
      call_decision: null,
      can_self_win: false,
      self_win_info: null,
    }

    console.assert(
      roundState.handTiles.length === afterNeed,
      `[applyGodViewSelfDrawFast] 摸后应为 ${afterNeed}，实际 ${roundState.handTiles.length}`,
    )
    console.log('[draw-fast] hand=', [...roundState.handTiles], 'drawn=', drawn)
    console.timeEnd('draw-to-render')

    appendGameLogStep({
      seat: self,
      action: 'DRAW',
      tile: drawn,
    })

    // 通知 App：下一帧后拉推荐（与 DOM/响应式对齐）
    recommendDrawToken.value += 1

    // 后端 DRAW 同步：不阻塞上屏与推荐
    void syncSelfDrawBackend(drawn).catch((e) => {
      console.warn('[applyGodViewSelfDrawFast] 后端同步失败（本地已摸入）', e)
    })

    return { tile: drawn, seat: self, needRecommend: true }
  }

  /**
   * 后台同步 DRAW（用摸前快照作请求体，避免把暗手多传）。
   */
  async function syncSelfDrawBackend(tileCode) {
    const epoch = sessionEpoch
    try {
      const snap = historyStack.value[historyStack.value.length - 1]
      if (!snap?.roundState) return null
      const prePayload = {
        hand_tiles: [...snap.roundState.handTiles],
        melds: (snap.roundState.melds || []).map((m) => ({
          ...m,
          meld_type: m.meld_type,
          tiles: [...(m.tiles || [])],
        })),
        discards: [...(snap.roundState.discards || [])],
        dealer_tile: snap.roundState.dealerTile,
        is_dealer: !!snap.roundState.isDealer,
        seat_wind: snap.roundState.seatWind,
        round_wind: snap.roundState.roundWind,
        opponents: (snap.roundState.opponents || []).map((o) => ({
          seat_wind: o.seat_wind,
          is_dealer: !!o.is_dealer,
          melds: (o.melds || []).map((m) => ({
            ...m,
            meld_type: m.meld_type,
            tiles: [...(m.tiles || [])],
          })),
          discards: [...(o.discards || [])],
        })),
        discarded_tiles: [],
      }
      const result = await awaitCurrentSession(epoch, postGameStep(prePayload, {
        actor_seat: roundState.seatWind,
        event_type: 'DRAW',
        tile: tileCode,
      }))
      // 仅合并自摸提示等元数据；禁止 API 回写打乱本地已挂右的手牌
      if (result && lastStepResult.value) {
        lastStepResult.value = {
          ...lastStepResult.value,
          can_self_win: !!result.can_self_win,
          self_win_info: result.self_win_info || null,
          // 若步进已带 recommend，可先露出；App 仍会用完整 14 张再拉一次
          recommend_discard:
            result.recommend_discard || lastStepResult.value.recommend_discard,
        }
      }
      return result


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 对手在行动权轮到自己时打出一张（禁止任意添加弃牌）。
   */
  async function opponentDiscardTile(seat, tile, clickedIndex) {
    const epoch = sessionEpoch
    try {
      if (loading.value) return null
      if (!tableLocked.value || gameState.value !== 'PLAYING') {
        throw new Error('请先「开始对局」')
      }
      if (seat !== currentTurnSeat.value) {
        throw new Error(
          `当前行动权在 ${windLabel(currentTurnSeat.value)}，${windLabel(seat)} 不能出牌`,
        )
      }
      if (seat === roundState.seatWind) {
        throw new Error('自家请用手牌区切牌')
      }
      if (!tile) throw new Error('缺少打出张')

      loading.value = true
      errorMsg.value = ''
      let didPush = false
      try {
        assertVisibleTileLimit(roundState)
        const counts = countVisibleTiles(roundState)
        if ((counts[tile] || 0) >= MAX_PER_TILE) {
          throw new Error(`${tile} 全场可见已满 4 张，无法打出`)
        }

        pushSnapshot()
        didPush = true
        logTurn('opponentDiscard:before', { seat, tile, clickedIndex })

        const opps = roundState.opponents.map((o) => ({
          ...o,
          melds: cloneMelds(o.melds),
          discards: [...(o.discards || [])],
          hand_tiles: [...(o.hand_tiles || [])],
        }))
        const oi = opps.findIndex((o) => o.seat_wind === seat)
        if (oi < 0) throw new Error(`找不到座位 ${seat}`)
        // 按展示下标切出，避免同名牌/插嵌后 indexOf 错位
        const hand = opps[oi].hand_tiles
        let hi = clickedIndex
        if (
          typeof hi !== 'number' ||
          hi < 0 ||
          hi >= hand.length ||
          hand[hi] !== tile
        ) {
          hi = hand.indexOf(tile)
        }
        if (hi >= 0) {
          hand.splice(hi, 1)
        }
        opps[oi].discards.push(tile)
        // 切后立即理顺（闭合空缺）
        opps[oi].hand_tiles = sortHandTiles(
          opps[oi].hand_tiles,
          roundState.dealerTile,
          undefined,
        )
        roundState.opponents = opps
        emitPveAction('DISCARD', seat, tile)
        clearDrawnMarker(seat)
        clearHandLayoutPin(seat)

        try {
          const payload = toHandRequestPayload()
          const preOpps = payload.opponents.map((o) =>
            o.seat_wind === seat
              ? { ...o, discards: o.discards.slice(0, -1) }
              : o,
          )
          const stepResult = await awaitCurrentSession(epoch, postGameStep(
            { ...payload, opponents: preOpps },
            { actor_seat: seat, event_type: 'DISCARD', tile },
          ))
          lastStepResult.value = stepResult
          if (stepResult.updated_state) {
            // 合并对手牌河，禁止 API 抹掉刚 push 的弃牌
            applyUpdatedStateFromApi(stepResult.updated_state)
          }
        } catch (e) {
        if (epoch !== sessionEpoch) return
          console.warn('[opponentDiscardTile] 后端同步失败，保留本地', e)
          errorMsg.value = e?.message
            ? `${e.message}（本地已记入牌河）`
            : '后端同步失败（本地已记入牌河）'
          lastStepResult.value = {
            next_turn_seat: nextSeat(seat),
            need_self_action: false,
            action_phase: 'WAIT',
            call_decision: null,
            recommend_discard: null,
          }
        }

        await awaitCurrentSession(epoch, resolveAfterDiscard(seat, lastStepResult.value))
        logTurn('opponentDiscard:after', { seat, tile })
        appendGameLogStep({
          seat,
          action: 'DISCARD',
          tile,
        })
        return lastStepResult.value
      } catch (e) {
        if (epoch !== sessionEpoch) return
        rollbackLastSnapshot(didPush)
        errorMsg.value = e?.message || String(e)
        logTurn('opponentDiscard:rollback', { err: errorMsg.value })
        throw e
      } finally {
        if (epoch !== sessionEpoch) return
        loading.value = false
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 代录对手副露（打断时序）：吃/碰/明杠取牌河；暗杠仅公开记面子。
   * 副露后行动权跳到该对手，等待录入其切牌。
   *
   * @param {{
   *   seat: string,
   *   meld_type: 'chi'|'pong'|'ming_gang'|'an_gang',
   *   tiles: string[],
   *   provider_seat?: string,
   *   claimed_tile?: string,
   * }} payload
   */
  async function executeOpponentMeld(payload) {
    const epoch = sessionEpoch
    try {
      if (currentHuSeat.value || huResolutionBusy.value) throw new Error('请先完成顺位胡牌响应')
      if (payload?.meld_type === 'bu_gang') return executeOpponentBuGang(payload)
      if (loading.value) return null
      if (gameState.value !== 'PLAYING' || !tableLocked.value) {
        throw new Error('请先「开始对局」')
      }
      const seat = payload?.seat
      const meldType = payload?.meld_type
      let tiles = sanitizeTileList(payload?.tiles || [])
      if (!seat || seat === roundState.seatWind) {
        throw new Error('请指定对手座位')
      }
      if (!['chi', 'pong', 'ming_gang', 'an_gang'].includes(meldType)) {
        throw new Error(`不支持的对手副露类型：${meldType}`)
      }

      const dealer = roundState.dealerTile
      const isAnGang = meldType === 'an_gang'
      let provider = isAnGang ? null : lastDiscardSeat.value
      let claimed = sanitizeTileCode(
        payload.claimed_tile || (isAnGang ? '' : ''),
      )

      if (!isAnGang) {
        if (!provider) {
          throw new Error('没有待响应的出牌事件，无法代录吃碰明杠')
        }
        if (payload.provider_seat && payload.provider_seat !== provider) {
          throw new Error('副露供牌方与最近出牌方不一致')
        }
        if (provider === seat) {
          throw new Error('不能副露自己的出牌')
        }
        // 吃：仅出牌方之下家（claimer 的上家 = provider）
        if (meldType === 'chi') {
          if (prevSeat(seat) !== provider) {
            throw new Error(
              `跨家吃牌非法：仅 ${windLabel(nextSeat(provider))} 可吃 ${windLabel(provider)} 的牌`,
            )
          }
        }
        if (!claimed) {
          const pOpp = roundState.opponents.find((o) => o.seat_wind === provider)
          if (provider === roundState.seatWind) {
            const river = roundState.discards || []
            claimed = river.length ? river[river.length - 1] : ''
          } else if (pOpp?.discards?.length) {
            claimed = pOpp.discards[pOpp.discards.length - 1]
          }
        }
        claimed = sanitizeTileCode(claimed)
        if (!claimed) throw new Error('缺少被副露的牌河张')
        if (lastStepResult.value?._response_tile && claimed !== lastStepResult.value._response_tile) {
          throw new Error('副露牌与最近出牌张不一致')
        }

        if (meldType === 'pong') {
          tiles = [claimed, claimed, claimed]
        } else if (meldType === 'ming_gang') {
          tiles = [claimed, claimed, claimed, claimed]
        } else if (meldType === 'chi') {
          if (tiles.length !== 3 || !tiles.includes(claimed)) {
            throw new Error('吃牌须提供含打出张的 3 张顺子')
          }
          // 得不可作百搭进顺；打出张本身为得时除外（实牌进顺）
          for (const t of tiles) {
            if (t === dealer && claimed !== dealer) {
              throw new Error('台州规则：吃牌顺子不得用百搭（得）')
            }
          }
        }
        if (meldType === 'ming_gang') {
          if (claimed === dealer || tiles.some((t) => t === dealer)) {
            throw new Error('台州规则：百搭（得）不可用于开杠')
          }
        }
      } else {
        // 暗杠：须在该对手行动权（摸打窗口）
        if (currentTurnSeat.value !== seat) {
          throw new Error(
            `仅轮到 ${windLabel(seat)} 时可代录暗杠（当前 ${windLabel(currentTurnSeat.value)}）`,
          )
        }
        if (tiles.length !== 4 || tiles.some((t) => t !== tiles[0])) {
          throw new Error('暗杠须为 4 张同名牌')
        }
        if (tiles[0] === dealer) {
          throw new Error('台州规则：百搭（得）不可用于开杠')
        }
        claimed = ''
        provider = null
      }

      // 牌池：非牌河提供的张将新占用可见额度
      const counts = countVisibleTiles(roundState)
      const needExtra = Object.create(null)
      for (const t of tiles) needExtra[t] = (needExtra[t] || 0) + 1
      if (!isAnGang && claimed) {
        needExtra[claimed] = (needExtra[claimed] || 0) - 1
        if (needExtra[claimed] <= 0) delete needExtra[claimed]
      }
      for (const [t, n] of Object.entries(needExtra)) {
        if ((counts[t] || 0) + n > MAX_PER_TILE) {
          throw new Error(`${t} 全场可见将超过 4 张，无法副露`)
        }
      }

      const oi = roundState.opponents.findIndex((o) => o.seat_wind === seat)
      if (oi < 0) throw new Error(`找不到对手 ${seat}`)
      if ((roundState.opponents[oi].melds || []).length >= 4) {
        throw new Error('该对手副露已满 4 组')
      }

      loading.value = true
      errorMsg.value = ''
      let didPush = false
      try {
        pushSnapshot()
        didPush = true
        const meldSource = historyStack.value.at(-1).roundState
        logTurn('executeOpponentMeld:before', {
          seat,
          meldType,
          tiles,
          provider,
          claimed,
        })

        if (!isAnGang) {
          removeClaimedFromRiver(claimed, provider)
        }

        const opps = roundState.opponents.map((o) => ({
          ...o,
          melds: cloneMelds(o.melds),
          discards: [...(o.discards || [])],
          hand_tiles: [...(o.hand_tiles || [])],
        }))
        const idx = opps.findIndex((o) => o.seat_wind === seat)
        opps[idx].melds.push({ meld_type: meldType, tiles: [...tiles], claimed_tile: claimed || null, provider_seat: provider || null })

        // 上帝视角：从暗手扣除副露用张（缺张则硬失败，禁止静默跳过导致张数错乱）
        {
          const hand = opps[idx].hand_tiles
          const tracked = hand.length > 0 || godViewWallMode.value
          /** @type {string[]} */
          let fromHand = []
          if (isAnGang) {
            fromHand = [...tiles]
          } else {
            fromHand = [...tiles]
            if (claimed) {
              const ci = fromHand.indexOf(claimed)
              if (ci >= 0) fromHand.splice(ci, 1)
            }
          }
          if (tracked && fromHand.length) {
            for (const t of fromHand) {
              const hi = hand.indexOf(t)
              if (hi < 0) {
                throw new Error(
                  `${windLabel(seat)} 暗手缺少副露用张 ${t}，无法代录${meldType}`,
                )
              }
              hand.splice(hi, 1)
            }
            opps[idx].hand_tiles = sortHandTiles(
              hand,
              roundState.dealerTile,
              undefined,
            )
          }
        }
        roundState.opponents = opps
        clearDrawnMarker(seat)
        clearHandLayoutPin(seat)

        // 【核心】吃/碰后不摸牌，行动权立刻归副露方并进入切牌；杠后待补张
        currentTurnSeat.value = seat
        lastDiscardSeat.value = null
        // 强制离开 CALL 挂起，避免 ActionPrompt / callPending 继续挡键盘
        currentPhase.value = 'WAITING'
        const meldsN = opps[idx].melds.length
        const handLen = (opps[idx].hand_tiles || []).length
        const discardNeed = 14 - 3 * meldsN
        const waitNeed = 13 - 3 * meldsN
        const trackedHand = handLen > 0 || godViewWallMode.value

        if (!isAnGang && meldType !== 'ming_gang') {
          // 吃/碰：暗手须已达出牌张数（有暗手追踪时）
          if (trackedHand && handLen !== discardNeed) {
            throw new Error(
              `${windLabel(seat)} 副露后暗手应为 ${discardNeed} 张（待切），实际 ${handLen}`,
            )
          }
        } else if (trackedHand && !isAnGang && handLen !== waitNeed) {
          // 明杠后待岭上
          throw new Error(
            `${windLabel(seat)} 明杠后暗手应为 ${waitNeed} 张（待补），实际 ${handLen}`,
          )
        }
        emitPveAction(meldActionLabel(meldType), seat, claimed || tiles[0] || null)

        const note = isAnGang
          ? `${windLabel(seat)} 宣告暗杠，正在补牌，请录入其切出的牌`
          : meldType === 'ming_gang'
            ? `${windLabel(seat)} 明杠成功，正在补牌，请录入其切出的牌`
            : `${windLabel(seat)} 副露成功，请打出 1 张牌`
        lastStepResult.value = {
          next_turn_seat: seat,
          need_self_action: false,
          action_phase:
            isAnGang || meldType === 'ming_gang' ? 'DRAW' : 'DISCARD',
          call_decision: null,
          recommend_discard: null,
          note,
        }
        syncPhaseFromTurn({ force: true })

        // 上帝视角：杠后自动岭上摸；吃/碰已满切牌张数，严禁再摸
        if (
          godViewWallMode.value &&
          (isAnGang || meldType === 'ming_gang')
        ) {
          await awaitCurrentSession(epoch, ensureGodViewDrawForSeat(seat, { rinshan: true }))
          lastStepResult.value = {
            ...lastStepResult.value,
            action_phase: 'DISCARD',
            note: `${windLabel(seat)} 杠后补张完成，请打出 1 张牌`,
          }
        }

        logTurn('executeOpponentMeld:after', { seat, meldType })
        appendGameLogStep({
          seat,
          action: meldActionLabel(meldType),
          tile: claimed || tiles[0] || null,
          details: { meld_type: meldType, tiles: [...tiles], claimed_tile: claimed || null },
        })

        // 本地已进入该座切牌态：先释放 loading，避免 OpponentPanel 因 disabled 卡死
        loading.value = false

        try {
          const prePayload = {
            hand_tiles: [...meldSource.handTiles],
            melds: meldSource.melds.map((m) => ({
              ...m,
              meld_type: m.meld_type,
              tiles: [...m.tiles],
            })),
            discards: [...meldSource.discards],
            dealer_tile: meldSource.dealerTile,
            is_dealer: meldSource.isDealer,
            seat_wind: meldSource.seatWind,
            round_wind: meldSource.roundWind,
            opponents: meldSource.opponents.map((o) => ({
              seat_wind: o.seat_wind,
              is_dealer: !!o.is_dealer,
              melds: (o.melds || []).map((m) => ({
                ...m,
                meld_type: m.meld_type,
                tiles: [...(m.tiles || [])],
              })),
              discards: [...(o.discards || [])],
            })),
            discarded_tiles: [],
          }
          await awaitCurrentSession(epoch, postGameStep(prePayload, {
            actor_seat: seat,
            event_type: 'MELD',
            tile: claimed || tiles[0] || null,
            provider_seat: provider,
            claimed_discard_index: provider ? responseDiscardIndex(meldSource, provider, claimed) : null,
            meld: { meld_type: meldType, tiles: [...tiles], claimed_tile: claimed || null, provider_seat: provider || null },
          }))
        } catch (e) {
        if (epoch !== sessionEpoch) return
          console.warn('[executeOpponentMeld] 后端同步失败，保留本地', e)
          if (!recoverProviderSyncError(e)) {
            errorMsg.value = e?.message
              ? `${e.message}（本地已代录副露）`
              : '后端同步失败（本地已代录副露）'
          }
        }

        return lastStepResult.value
      } catch (e) {
        if (epoch !== sessionEpoch) return
        rollbackLastSnapshot(didPush)
        errorMsg.value = e?.message || String(e)
        logTurn('executeOpponentMeld:rollback', { err: errorMsg.value })
        throw e
      } finally {
        if (epoch !== sessionEpoch) return
        loading.value = false
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 代录对手暗杠：扣 4 张同名物理牌 → an_gang 面子 → 保留该对手出牌权（补牌后切）。
   * @param {string} seat
   * @param {string} tile
   */
  async function executeOpponentAnGang(seat, tile) {
    const epoch = sessionEpoch
    try {
      const code = sanitizeTileCode(tile)
      if (!seat || !code) {
        throw new Error('暗杠须指定座位与牌面')
      }
      return executeOpponentMeld({
        seat,
        meld_type: 'an_gang',
        tiles: [code, code, code, code],
      })


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 全员过牌：关闭响应窗，行动权交出牌方之下家并自动摸牌。
   * 快照在过牌时压入，固化「上家已出牌」局面。
   */
  async function passCall(discardedTile, responderSeat = roundState.seatWind) {
    const epoch = sessionEpoch
    try {
      if (huResolutionBusy.value) return false
      let passLogged = false
      if (lastStepResult.value?._pending_add_kong) {
        if (responderSeat !== currentHuSeat.value) throw new Error('尚未轮到该家过抢杠胡')
        pushSnapshot()
        appendGameLogStep({ seat: responderSeat, action: 'PASS', tile: discardedTile || null,
          details: { provider_seat: lastDiscardSeat.value, response: 'rob_kong' } })
        lastStepResult.value = { ...lastStepResult.value, pending_hu_queue: pendingHuQueue.value.slice(1) }
        if (pendingHuQueue.value.length) {
          syncHuResponseWindow()
          return true
        }
        return finalizeAddKong()
      }
      if (currentHuSeat.value) {
        if (responderSeat !== currentHuSeat.value) throw new Error('尚未轮到该家过胡')
        pushSnapshot()
        appendGameLogStep({ seat: responderSeat, action: 'PASS', tile: discardedTile || null,
          details: { provider_seat: lastDiscardSeat.value, response: 'hu' } })
        passLogged = true
        lastStepResult.value = {
          ...lastStepResult.value,
          pending_hu_queue: pendingHuQueue.value.slice(1),
        }
        syncHuResponseWindow()
        if (currentHuSeat.value || (lastStepResult.value?._table_responses || [])
          .some((option) => option.types.some((type) => type !== 'catch_win'))) return true
      }
      const provider = lastDiscardSeat.value
      if (!provider) {
        throw new Error('无待响应的出牌方')
      }
      pushSnapshot()
      logTurn('passCall', { provider, discardedTile })
      if (!passLogged) appendGameLogStep({ seat: responderSeat, action: 'PASS', tile: discardedTile || null,
        details: { provider_seat: provider } })
      try {
        await awaitCurrentSession(epoch, postGameStep(toHandRequestPayload(), {
          actor_seat: roundState.seatWind,
          event_type: 'PASS',
          tile: discardedTile || null,
          provider_seat: provider,
        }))
      } catch (e) {
        if (epoch !== sessionEpoch) return
        console.warn('[passCall]', e)
      }
      if (lastStepResult.value) {
        lastStepResult.value = {
          ...lastStepResult.value,
          call_decision: null,
          need_self_action: false,
          action_phase: 'WAIT',
          _table_responses: [],
          pending_hu_queue: [],
          _catch_win_seats: [],
          note: '',
        }
      }
      // 先离开响应窗，再允许 advance 摸牌
      currentPhase.value = 'WAITING'
      await awaitCurrentSession(epoch, advanceTurnToNext(provider, { bypassLoading: true, force: true }))
      lastDiscardSeat.value = null
      logTurn('passCall:advanced')


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /** 与 passCall 同义：响应窗「全员过牌 / 继续摸牌」 */
  async function passAllCalls(discardedTile) {
    const epoch = sessionEpoch
    try {
      return passCall(discardedTile, currentHuSeat.value || roundState.seatWind)


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  const isResponseWindow = computed(
    () =>
      gameState.value === 'PLAYING' &&
      (currentPhase.value === 'WAIT_RESPONSE' ||
        currentPhase.value === 'OPPONENT_DISCARD_ACTION'),
  )

  /** 当前响应窗内可捉铳的座位 */
  const huResolutionBusy = ref(false)
  const pendingHuQueue = computed(() => isResponseWindow.value
    ? lastStepResult.value?.pending_hu_queue || [] : [])
  const currentHuSeat = computed(() => pendingHuQueue.value[0] || null)
  const catchWinSeats = computed(() => currentHuSeat.value ? [currentHuSeat.value] : [])

  function syncHuResponseWindow() {
    const result = lastStepResult.value
    const seat = result?.pending_hu_queue?.[0]
    const base = result?._self_call_decision
    let decision = null
    if (seat === roundState.seatWind) {
      const actions = ['hu', 'pass'].map((action_type) => ({
        action_type, tiles: [result._response_tile], provider_seat: lastDiscardSeat.value,
      }))
      decision = { ...base, available_actions: actions,
        candidates: actions.map((action) => ({ action })), recommended_action: actions[0] }
    } else if (!seat && base) {
      const allowed = (action) => action && !['hu', 'catch_win'].includes(action.action_type)
      const actions = (base.available_actions || (base.candidates || []).map((c) => c.action)).filter(allowed)
      if (actions.some((a) => a.action_type !== 'pass')) {
        decision = { ...base, available_actions: actions,
          candidates: (base.candidates || []).filter((c) => allowed(c.action)),
          recommended_action: allowed(base.recommended_action) ? base.recommended_action : actions[0] }
      }
    }
    lastStepResult.value = { ...result, call_decision: decision,
      need_self_action: !!decision, action_phase: decision ? 'CALL' : 'WAIT',
      note: seat ? `等待${windLabel(seat)}风决定${result?._pending_add_kong ? '抢杠胡' : '捉铳'}或过牌，后续顺位尚未解锁` : '胡牌响应结束，等待吃碰杠或全员过牌' }
    currentPhase.value = decision ? 'OPPONENT_DISCARD_ACTION' : 'WAIT_RESPONSE'
  }

  function assertHuTurn(seat, winType, tile, provider) {
    if (!isResponseWindow.value) return
    if (['zimo', 'self_draw_win'].includes(winType)) throw new Error('响应窗口不能自摸')
    if (lastStepResult.value?.pending_hu_queue && seat !== currentHuSeat.value) {
      throw new Error('尚未轮到该家胡牌，或该家已过胡')
    }
    if (tile !== lastStepResult.value?._response_tile || provider !== lastDiscardSeat.value) {
      throw new Error('胡牌响应已失效')
    }
  }

  /**
   * 副露成功后：关闭 CALL 面板，行动权归自家，进入切牌态。
   * @param {object|null} [stepResult] 后端 MELD 响应（含 recommend_discard）
   */
  function takeTurnAfterMeld(stepResult = null) {
    currentTurnSeat.value = roundState.seatWind
    lastDiscardSeat.value = null
    latestDrawnTile.value = null

    const base = stepResult
      ? cloneStepResult(stepResult) || stepResult
      : lastStepResult.value
        ? { ...lastStepResult.value }
        : {}

    lastStepResult.value = {
      ...base,
      call_decision: null,
      need_self_action: true,
      action_phase: 'DISCARD',
      recommend_discard:
        base?.recommend_discard ??
        lastStepResult.value?.recommend_discard ??
        null,
    }

    syncPhaseFromTurn({ force: true })
    const need = 14 - 3 * (roundState.melds?.length || 0)
    if (roundState.handTiles.length === need) {
      currentPhase.value = 'MY_TURN_DISCARD'
    }
    logTurn('takeTurnAfterMeld', {
      handLen: roundState.handTiles.length,
      need,
      phase: currentPhase.value,
      hasRecommend: !!lastStepResult.value?.recommend_discard?.best_tile,
    })
  }

  /**
   * 杠成功后：关闭 CALL，进入岭上补牌（DRAW），不可直接切牌推荐。
   * 上帝视角：立即从牌墙自动摸岭上张并进入切牌推荐。
   */
  async function enterKongReplaceDraw(stepResult = null) {
    const epoch = sessionEpoch
    try {
      currentTurnSeat.value = roundState.seatWind
      lastDiscardSeat.value = null
      clearDrawnMarker(roundState.seatWind)

      const base = stepResult
        ? cloneStepResult(stepResult) || stepResult
        : {}

      lastStepResult.value = {
        ...base,
        call_decision: null,
        need_self_action: true,
        action_phase: 'DRAW',
        recommend_discard: null,
      }

      syncPhaseFromTurn({ force: true })
      // 强制待摸：slots 应为 13
      currentPhase.value = 'WAITING'
      logTurn('enterKongReplaceDraw', {
        handLen: roundState.handTiles.length,
        melds: roundState.melds.length,
        waitNeed: 13 - 3 * (roundState.melds?.length || 0),
      })

      if (godViewWallMode.value) {
        await awaitCurrentSession(epoch, ensureGodViewDrawForSeat(roundState.seatWind, {
          rinshan: true,
        }))
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 规范化明杠面子：保证 4 张同名（含牌河 claimed）。
   */
  function normalizeMingGangTiles(tiles, claimed) {
    const clean = sanitizeTileList(tiles)
    if (clean.length === 4) return clean
    if (!claimed) return clean
    // 兜底：三手一打
    return [claimed, claimed, claimed, claimed]
  }

  /** 开杠禁止用「得」当百搭凑张（rule.md §7） */
  function assertKongNotUsingJoker(tiles, claimed, dealer) {
    const face = claimed
    for (const t of tiles) {
      if (t === dealer && t !== face) {
        throw new Error('台州规则：百搭（得）不可用于开杠')
      }
    }
  }

  /**
   * 自家吃/碰/明杠（唯一入口）。
   * - 吃/碰：副露后立即切牌（slots=14）
   * - 明杠：副露后待岭上补牌（slots=13）→ DRAW
   */
  async function applySelfMeld(payload) {
    const epoch = sessionEpoch
    try {
      if (currentHuSeat.value || huResolutionBusy.value) throw new Error('请先完成顺位胡牌响应')
      if (loading.value) return null
      if (gameState.value !== 'PLAYING' || !tableLocked.value) {
        throw new Error('请先「开始对局」')
      }
      const meldType = payload?.meld_type
      let tiles = sanitizeTileList(payload?.tiles || [])
      const claimed = sanitizeTileCode(payload?.claimed_tile)
      if (!meldType || !['chi', 'pong', 'ming_gang'].includes(meldType)) {
        throw new Error(`不支持的副露类型：${meldType}`)
      }
      if (!claimed) throw new Error('缺少被吃碰杠的牌河张')

      if (meldType === 'ming_gang') {
        tiles = normalizeMingGangTiles(tiles, claimed)
        assertKongNotUsingJoker(tiles, claimed, roundState.dealerTile)
      }
      if (meldType === 'chi' && tiles.length !== 3) {
        throw new Error('吃牌须提供 3 张面子')
      }
      if (meldType === 'pong' && tiles.length !== 3) {
        throw new Error('碰牌须提供 3 张面子')
      }
      if (meldType === 'ming_gang' && tiles.length !== 4) {
        throw new Error('明杠须提供 4 张面子')
      }

      const isKong = meldType === 'ming_gang'
      loading.value = true
      errorMsg.value = ''
      let didPush = false
      try {
        pushSnapshot()
        didPush = true
        const meldSource = historyStack.value.at(-1).roundState
        logTurn('applySelfMeld:before', { meldType, claimed, tiles, isKong })

        const provider = lastDiscardSeat.value
        if (!provider || (payload.provider_seat && payload.provider_seat !== provider)) {
          throw new Error('副露供牌方与最近出牌方不一致')
        }
        if (meldType === 'chi' && prevSeat(roundState.seatWind) !== provider) {
          throw new Error('吃牌只能取直接上家刚打出的牌')
        }
        if (lastStepResult.value?._response_tile && claimed !== lastStepResult.value._response_tile) {
          throw new Error('副露牌与最近出牌张不一致')
        }
        removeClaimedFromRiver(claimed, provider)

        // 从暗手扣除：牌河提供 claimed，其余从手牌拿
        const needFromHand = Object.create(null)
        for (const t of tiles) needFromHand[t] = (needFromHand[t] || 0) + 1
        needFromHand[claimed] = (needFromHand[claimed] || 0) - 1
        if (needFromHand[claimed] <= 0) delete needFromHand[claimed]

        const hand = sanitizeTileList(roundState.handTiles)
        for (const [t, cnt] of Object.entries(needFromHand)) {
          for (let n = 0; n < cnt; n++) {
            const idx = hand.indexOf(t)
            if (idx < 0) {
              throw new Error(`自家手牌缺少副露用张 ${t}`)
            }
            hand.splice(idx, 1)
          }
        }

        roundState.handTiles = sortHandTiles(
          hand,
          roundState.dealerTile,
          undefined,
        )
        roundState.melds = [
          ...cloneMelds(roundState.melds),
          { meld_type: meldType, tiles: [...tiles], claimed_tile: claimed || null, provider_seat: provider || null },
        ]

        const meldsN = roundState.melds.length
        const discardNeed = 14 - 3 * meldsN
        const waitNeed = 13 - 3 * meldsN

        if (isKong) {
          // 杠后 slots=13，进入补牌
          if (roundState.handTiles.length !== waitNeed) {
            throw new Error(
              `明杠后暗手应为 ${waitNeed} 张（待补牌），实际 ${roundState.handTiles.length}`,
            )
          }
          emitPveAction('GANG', roundState.seatWind, claimed)
          await awaitCurrentSession(epoch, enterKongReplaceDraw({
            action_phase: 'DRAW',
            need_self_action: true,
            call_decision: null,
          }))
        } else {
          if (roundState.handTiles.length !== discardNeed) {
            throw new Error(
              `副露后暗手应为 ${discardNeed} 张（待切），实际 ${roundState.handTiles.length}`,
            )
          }
          emitPveAction(meldActionLabel(meldType), roundState.seatWind, claimed)
          takeTurnAfterMeld({
            action_phase: 'DISCARD',
            need_self_action: true,
            call_decision: null,
            recommend_discard: null,
          })
        }

        // 同步后端
        try {
          const prePayload = {
            hand_tiles: [...meldSource.handTiles],
            melds: meldSource.melds.map((m) => ({
              ...m,
              meld_type: m.meld_type,
              tiles: [...m.tiles],
            })),
            discards: [...meldSource.discards],
            dealer_tile: meldSource.dealerTile,
            is_dealer: meldSource.isDealer,
            seat_wind: meldSource.seatWind,
            round_wind: meldSource.roundWind,
            opponents: meldSource.opponents.map((o) => ({
              seat_wind: o.seat_wind,
              is_dealer: !!o.is_dealer,
              melds: (o.melds || []).map((m) => ({
                ...m,
                meld_type: m.meld_type,
                tiles: [...(m.tiles || [])],
              })),
              discards: [...(o.discards || [])],
            })),
            discarded_tiles: [],
          }
          const result = await awaitCurrentSession(epoch, postGameStep(prePayload, {
            actor_seat: roundState.seatWind,
            event_type: 'MELD',
            tile: claimed,
            provider_seat: provider,
            claimed_discard_index: responseDiscardIndex(meldSource, provider, claimed),
            meld: { meld_type: meldType, tiles: [...tiles], claimed_tile: claimed || null, provider_seat: provider || null },
          }))
          if (result.updated_state) {
            const apiHand = sanitizeTileList(
              result.updated_state.hand_tiles || [],
            )
            const apiMelds = result.updated_state.melds
            if (
              Array.isArray(apiMelds) &&
              apiMelds.length >= roundState.melds.length
            ) {
              roundState.melds = apiMelds.map((m) => ({
                ...m,
                meld_type: m.meld_type,
                tiles: sanitizeTileList(m.tiles || []),
              }))
            }
            const expect = isKong
              ? 13 - 3 * roundState.melds.length
              : 14 - 3 * roundState.melds.length
            if (apiHand.length === expect && roundState.handTiles.length === expect) {
              roundState.handTiles = sortHandTiles(
                apiHand,
                roundState.dealerTile,
                undefined,
              )
            }
          }
          if (!isKong && result.action_phase === 'DRAW') {
            await awaitCurrentSession(epoch, enterKongReplaceDraw(result))
          } else if (!isKong) {
            takeTurnAfterMeld(result)
          }
        } catch (e) {
        if (epoch !== sessionEpoch) return
          console.warn('[applySelfMeld] 后端同步失败，保留本地副露', e)
          if (!recoverProviderSyncError(e)) {
            errorMsg.value = e?.message
              ? `${e.message}（本地已副露${isKong ? '，请补牌' : '，请切牌'}）`
              : '后端同步失败（本地已副露）'
          }
        }

        applyHandSort({
          keepDrawn: isKong && roundState.handTiles.length === 14 - 3 * (roundState.melds?.length || 0),
        })
        if (isKong) {
          currentTurnSeat.value = roundState.seatWind
          const discardNeed = 14 - 3 * (roundState.melds?.length || 0)
          currentPhase.value = roundState.handTiles.length === discardNeed
            ? 'MY_TURN_DISCARD' : 'WAITING'
        } else {
          const need2 = 14 - 3 * (roundState.melds?.length || 0)
          if (roundState.handTiles.length === need2) {
            currentPhase.value = 'MY_TURN_DISCARD'
            currentTurnSeat.value = roundState.seatWind
          }
        }
        logTurn('applySelfMeld:after', {
          meldType,
          handLen: roundState.handTiles.length,
          phase: currentPhase.value,
        })
        appendGameLogStep({
          seat: roundState.seatWind,
          action: meldActionLabel(meldType),
          tile: claimed || tiles[0] || null,
          details: { meld_type: meldType, tiles: [...tiles], claimed_tile: claimed || null },
        })
        return lastStepResult.value
      } catch (e) {
        if (epoch !== sessionEpoch) return
        rollbackLastSnapshot(didPush)
        errorMsg.value = e?.message || String(e)
        logTurn('applySelfMeld:rollback', { err: errorMsg.value })
        throw e
      } finally {
        if (epoch !== sessionEpoch) return
        loading.value = false
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /** @deprecated 别名：明杠入口 */
  async function executeGang(action) {
    const epoch = sessionEpoch
    try {
      return applySelfMeld({
        meld_type: action?.action_type || action?.meld_type || 'ming_gang',
        tiles: action?.tiles || [],
        claimed_tile: action?.claimed_tile || action?.tile,
        provider_seat: action?.provider_seat,
      })


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 自家暗杠 / 补杠（摸牌后或吃碰后、切牌前）。
   * - an_gang：扣 4 张 → an_gang 面子 → DRAW 补牌
   * - bu_gang：扣 1 张 → 升级已有 pong 为 ming_gang → DRAW 补牌
   */
  async function applySelfKong(payload) {
    const epoch = sessionEpoch
    try {
      if (loading.value) return null
      if (gameState.value !== 'PLAYING' || !tableLocked.value) {
        throw new Error('请先「开始对局」')
      }
      const kind = payload?.action_type || payload?.meld_type
      const face = sanitizeTileCode(payload?.tile || payload?.tiles?.[0])
      if (!face) throw new Error('缺少开杠牌面')
      if (face === roundState.dealerTile) {
        throw new Error('台州规则：百搭（得）不可用于开杠')
      }
      if (kind !== 'an_gang' && kind !== 'bu_gang') {
        throw new Error(`不支持的自家杠类型：${kind}`)
      }
      if (kind === 'bu_gang') return startAddKong(roundState.seatWind, face)

      const meldsN = roundState.melds?.length || 0
      const discardNeed = 14 - 3 * meldsN
      if (roundState.handTiles.length !== discardNeed) {
        throw new Error(
          `仅待切时可暗杠/补杠：需要 ${discardNeed} 张暗手，当前 ${roundState.handTiles.length}`,
        )
      }

      loading.value = true
      errorMsg.value = ''
      let didPush = false
      try {
        pushSnapshot()
        didPush = true
        const kongSource = historyStack.value.at(-1).roundState
        logTurn('applySelfKong:before', { kind, face })

        let hand = sanitizeTileList(roundState.handTiles)
        let nextMelds = cloneMelds(roundState.melds)
        const apiMeldType = 'an_gang'
        const apiTiles = [face, face, face, face]
        for (let n = 0; n < 4; n++) {
          const idx = hand.indexOf(face)
          if (idx < 0) throw new Error(`手牌缺少暗杠用张 ${face}`)
          hand.splice(idx, 1)
        }
        nextMelds = [
          ...nextMelds,
          { meld_type: 'an_gang', tiles: [face, face, face, face] },
        ]

        roundState.handTiles = sortHandTiles(
          hand,
          roundState.dealerTile,
          undefined,
        )
        roundState.melds = nextMelds

        const waitNeed = 13 - 3 * roundState.melds.length
        if (roundState.handTiles.length !== waitNeed) {
          throw new Error(
            `开杠后暗手应为 ${waitNeed} 张（待补牌），实际 ${roundState.handTiles.length}`,
          )
        }
        emitPveAction('GANG', roundState.seatWind, face)

        await awaitCurrentSession(epoch, enterKongReplaceDraw({
          action_phase: 'DRAW',
          need_self_action: true,
          call_decision: null,
        }))

        try {
          const prePayload = {
            hand_tiles: [...kongSource.handTiles],
            melds: kongSource.melds.map((m) => ({
              ...m,
              meld_type: m.meld_type,
              tiles: [...m.tiles],
            })),
            discards: [...kongSource.discards],
            dealer_tile: kongSource.dealerTile,
            is_dealer: kongSource.isDealer,
            seat_wind: kongSource.seatWind,
            round_wind: kongSource.roundWind,
            opponents: kongSource.opponents.map((o) => ({
              seat_wind: o.seat_wind,
              is_dealer: !!o.is_dealer,
              melds: (o.melds || []).map((m) => ({
                ...m,
                meld_type: m.meld_type,
                tiles: [...(m.tiles || [])],
              })),
              discards: [...(o.discards || [])],
            })),
            discarded_tiles: [],
          }
          const result = await awaitCurrentSession(epoch, postGameStep(prePayload, {
            actor_seat: roundState.seatWind,
            event_type: 'MELD',
            tile: face,
            meld: { meld_type: apiMeldType, tiles: apiTiles },
          }))
          if (result.updated_state) {
            const apiHand = sanitizeTileList(
              result.updated_state.hand_tiles || [],
            )
            const apiMelds = result.updated_state.melds
            if (Array.isArray(apiMelds)) {
              roundState.melds = apiMelds.map((m) => ({
                ...m,
                meld_type: m.meld_type,
                tiles: sanitizeTileList(m.tiles || []),
              }))
            }
            const expect = 13 - 3 * roundState.melds.length
            if (apiHand.length === expect && roundState.handTiles.length === expect) {
              roundState.handTiles = sortHandTiles(
                apiHand,
                roundState.dealerTile,
                undefined,
              )
            }
          }
          // 岭上补牌已在上方 enterKongReplaceDraw 处理（上帝视角自动摸）
        } catch (e) {
        if (epoch !== sessionEpoch) return
          console.warn('[applySelfKong] 后端同步失败，保留本地开杠', e)
          errorMsg.value = e?.message
            ? `${e.message}（本地已开杠，请补牌）`
            : '后端同步失败（本地已开杠，请补牌）'
        }

        currentTurnSeat.value = roundState.seatWind
        const afterKong = seatHandSlots(roundState.seatWind)
        // 补杠/暗杠后应为 waitNeed，再摸岭上；勿用 slots===discardNeed（量纲错误）
        if (afterKong.handLen === afterKong.discardNeed) {
          applyHandSort({ keepDrawn: !!latestDrawnTile.value })
          currentPhase.value = 'MY_TURN_DISCARD'
        } else {
          applyHandSort({ keepDrawn: false })
          currentPhase.value = 'WAITING'
          if (godViewWallMode.value) {
            await awaitCurrentSession(epoch, ensureGodViewDrawForSeat(roundState.seatWind, {
              rinshan: true,
            }))
          }
        }
        logTurn('applySelfKong:after', {
          kind,
          handLen: roundState.handTiles.length,
          phase: currentPhase.value,
        })
        appendGameLogStep({
          seat: roundState.seatWind,
          action: 'GANG',
          tile: face,
        })
        return lastStepResult.value
      } catch (e) {
        if (epoch !== sessionEpoch) return
        rollbackLastSnapshot(didPush)
        errorMsg.value = e?.message || String(e)
        logTurn('applySelfKong:rollback', { err: errorMsg.value })
        throw e
      } finally {
        if (epoch !== sessionEpoch) return
        loading.value = false
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /** 仅从当前出牌方牌河末尾取牌；不得搜索其他座位或旧弃牌。 */
  function responseDiscardIndex(snapshot, providerSeat, claimed) {
    const river = providerSeat === snapshot.seatWind
      ? snapshot.discards
      : snapshot.opponents.find((o) => o.seat_wind === providerSeat)?.discards
    if (!river?.length || river.at(-1) !== claimed) {
      throw new Error('供牌方原响应位置已失效')
    }
    return river.length - 1
  }

  function recoverProviderSyncError(error) {
    const message = error?.message || String(error)
    if (gameMode.value !== 'PVE' || !/供牌方.*(?:牌河末张|原响应位置)/.test(message)) return false
    // 步进 API 是无状态的；本地已持有完整桌面，下一步请求会提交这份全量局面。
    toHandRequestPayload()
    errorMsg.value = ''
    lastStepResult.value = {
      ...lastStepResult.value,
      note: '副露已完成；后续动作将携当前全桌局面继续校验',
    }
    return true
  }

  function removeClaimedFromRiver(claimed, providerSeat) {
    if (!isResponseWindow.value || lastStepResult.value?._pending_add_kong) {
      throw new Error('当前没有可副露的出牌响应窗口')
    }
    if (!providerSeat || providerSeat !== lastDiscardSeat.value) {
      throw new Error('副露供牌方已失效')
    }
    if (claimed !== lastStepResult.value?._response_tile) {
      throw new Error('副露牌与当前响应出牌张不一致')
    }
    if (providerSeat === roundState.seatWind) {
      const river = [...(roundState.discards || [])]
      if (river.at(-1) !== claimed) throw new Error('供牌方牌河末张与副露牌不符')
      river.pop()
      roundState.discards = river
      return
    }
    const oi = roundState.opponents.findIndex((o) => o.seat_wind === providerSeat)
    if (oi < 0) throw new Error('找不到副露供牌方')
    const river = [...(roundState.opponents[oi].discards || [])]
    if (river.at(-1) !== claimed) throw new Error('供牌方牌河末张与副露牌不符')
    river.pop()
    roundState.opponents = roundState.opponents.map((o, i) => i === oi
      ? { ...o, discards: river } : o)
  }

  /**
   * 自家摸牌（唯一入口）：本地先入账，再同步后端。
   * 失败时绝不回滚上家出牌快照；保持 14 张切牌态。
   */
  async function selfDrawTile(tile, opts = {}) {
    const epoch = sessionEpoch
    try {
      const bypassLoading = !!opts.bypassLoading
      if (!bypassLoading && loading.value) return null
      if (gameState.value !== 'PLAYING' || !tableLocked.value) {
        throw new Error('请先「开始对局」')
      }
      const tileCode = sanitizeTileCode(tile)
      if (!tileCode) {
        throw new Error(
          `摸入张无效（期望牌码字符串，收到 ${typeof tile}）`,
        )
      }
      if (currentTurnSeat.value !== roundState.seatWind) {
        throw new Error(
          `当前行动权在 ${windLabel(currentTurnSeat.value)}，尚轮不到自家摸牌`,
        )
      }
      if (isResponseWindow.value) {
        throw new Error('请先完成吃碰过响应')
      }

      const meldsN = roundState.melds?.length || 0
      const beforeNeed = 13 - 3 * meldsN
      const afterNeed = 14 - 3 * meldsN
      if (roundState.handTiles.length !== beforeNeed) {
        throw new Error(
          `非待摸状态：需要 ${beforeNeed} 张暗手，当前 ${roundState.handTiles.length}`,
        )
      }

      const counts = countVisibleTiles(roundState)
      if ((counts[tileCode] || 0) >= MAX_PER_TILE) {
        throw new Error(`${tileCode} 全场可见已满 4 张，无法摸入`)
      }

      if (!bypassLoading) {
        loading.value = true
      }
      errorMsg.value = ''
      let didPush = false
      try {
        pushSnapshot()
        didPush = true
        logTurn('selfDraw:before', { tile: tileCode, fromWall: !!opts.fromWall })
        lastDiscardSeat.value = null

        // 本地先摸入：fromWall / fastAppend 时只挂最右，避免整手 sort 卡顿
        const fastAppend = !!opts.fromWall || !!opts.fastAppend
        if (fastAppend) {
          roundState.handTiles = [...roundState.handTiles, tileCode]
        } else {
          roundState.handTiles = sortHandTiles(
            sanitizeTileList([...roundState.handTiles, tileCode]),
            roundState.dealerTile,
            tileCode,
          )
        }
        latestDrawnTile.value = tileCode
        setDrawnMarker(roundState.seatWind, tileCode)
        currentPhase.value = 'MY_TURN_DISCARD'

        console.assert(
          roundState.handTiles.length === afterNeed,
          `[selfDrawTile] 摸后张数应为 ${afterNeed}，实际 ${roundState.handTiles.length}`,
        )

        try {
          const snap = historyStack.value[historyStack.value.length - 1]
          const prePayload = {
            hand_tiles: [...snap.roundState.handTiles],
            melds: snap.roundState.melds.map((m) => ({
              ...m,
              meld_type: m.meld_type,
              tiles: [...m.tiles],
            })),
            discards: [...snap.roundState.discards],
            dealer_tile: snap.roundState.dealerTile,
            is_dealer: snap.roundState.isDealer,
            seat_wind: snap.roundState.seatWind,
            round_wind: snap.roundState.roundWind,
            opponents: snap.roundState.opponents.map((o) => ({
              seat_wind: o.seat_wind,
              is_dealer: !!o.is_dealer,
              melds: (o.melds || []).map((m) => ({
                ...m,
                meld_type: m.meld_type,
                tiles: [...(m.tiles || [])],
              })),
              discards: [...(o.discards || [])],
            })),
            discarded_tiles: [],
          }
          const result = await awaitCurrentSession(epoch, postGameStep(prePayload, {
            actor_seat: roundState.seatWind,
            event_type: 'DRAW',
            tile: tileCode,
          }))
          if (result.updated_state) {
            applyUpdatedStateFromApi(result.updated_state, {
              keepLocalOpponents: true,
            })
            // 快摸路径：禁止 API 回写打乱「挂右」结构
            if (fastAppend) {
              if (!roundState.handTiles.includes(tileCode)) {
                roundState.handTiles = [...roundState.handTiles, tileCode]
              } else if (roundState.handTiles[roundState.handTiles.length - 1] !== tileCode) {
                const rest = roundState.handTiles.filter((t, i, a) =>
                  !(t === tileCode && i === a.lastIndexOf(tileCode)),
                )
                roundState.handTiles = [...rest, tileCode]
              }
              setDrawnMarker(roundState.seatWind, tileCode)
            } else if (roundState.handTiles.length === afterNeed - 1) {
              roundState.handTiles = sortHandTiles(
                sanitizeTileList([...roundState.handTiles, tileCode]),
                roundState.dealerTile,
                tileCode,
              )
            } else if (roundState.handTiles.length === afterNeed) {
              applyHandSort({ keepDrawn: true })
            }
          }
          // 禁止把 reactive opponents 写进 lastStepResult；摸后必须清旧推荐
          lastStepResult.value = cloneStepResult({
            ...result,
            action_phase: 'DISCARD',
            need_self_action: true,
            recommend_discard: result?.recommend_discard ?? null,
            updated_state: {
              hand_tiles: sanitizeTileList(roundState.handTiles),
              discards: sanitizeTileList(roundState.discards),
              melds: cloneMelds(roundState.melds),
            },
          })
          currentPhase.value = 'MY_TURN_DISCARD'
        } catch (e) {
        if (epoch !== sessionEpoch) return
          console.warn('[selfDrawTile] 后端同步失败，保留本地摸牌', e)
          errorMsg.value = e?.message
            ? `${e.message}（本地已摸入，可用撤回）`
            : '后端同步失败（本地已摸入，可用撤回）'
          lastStepResult.value = {
            action_phase: 'DISCARD',
            need_self_action: true,
            recommend_discard: null,
            call_decision: null,
          }
        }

        logTurn('selfDraw:after', { tile: tileCode })
        appendGameLogStep({
          seat: roundState.seatWind,
          action: 'DRAW',
          tile: tileCode,
        })
        if (fastAppend) {
          recommendDrawToken.value += 1
        }
        return lastStepResult.value
      } catch (e) {
        if (epoch !== sessionEpoch) return
        rollbackLastSnapshot(didPush)
        errorMsg.value = e?.message || String(e)
        logTurn('selfDraw:rollback', { err: errorMsg.value })
        throw e
      } finally {
        if (epoch !== sessionEpoch) return
        if (!bypassLoading) {
          loading.value = false
        }
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 自家切牌（唯一入口）：按 clickedIndex 只删 1 张 → 入河 → 清 drawn 标记 → 理牌。
   */
  async function discardTile(tile, clickedIndex) {
    const epoch = sessionEpoch
    try {
      // 人为切牌优先：立刻打断后台 EV，不因 analyzeLoading 阻塞
      abortCurrentRecommend()
      if (loading.value) return null
      if (!tableLocked.value || gameState.value !== 'PLAYING') {
        throw new Error('请先「开始对局」')
      }
      if (currentTurnSeat.value !== roundState.seatWind) {
        throw new Error(
          `当前行动权在 ${windLabel(currentTurnSeat.value)}，尚轮不到自家`,
        )
      }
      if (currentPhase.value === 'OPPONENT_DISCARD_ACTION') {
        throw new Error('请先完成吃碰过响应')
      }
      loading.value = true
      errorMsg.value = ''

      try {
      const meldsN = roundState.melds?.length || 0
      const beforeNeed = 14 - 3 * meldsN
      const afterNeed = 13 - 3 * meldsN
      const discardsBefore = roundState.discards.length
      const handBefore = roundState.handTiles

      console.assert(
        handBefore.length === beforeNeed,
        `[discardTile] 切牌前张数应为 ${beforeNeed}，实际 ${handBefore.length}`,
      )
      if (handBefore.length !== beforeNeed) {
        throw new Error(
          `非待切状态：需要 ${beforeNeed} 张暗手，当前 ${handBefore.length}`,
        )
      }

      let i = clickedIndex
      if (
        typeof i !== 'number' ||
        i < 0 ||
        i >= handBefore.length ||
        handBefore[i] !== tile
      ) {
        const matches = []
        for (let k = 0; k < handBefore.length; k++) {
          if (handBefore[k] === tile) matches.push(k)
        }
        if (matches.length === 1) i = matches[0]
        else {
          throw new Error(
            `切牌索引无效：index=${clickedIndex}, tile=${tile}, hand[${clickedIndex}]=${handBefore[clickedIndex]}`,
          )
        }
      }

      console.assert(
        handBefore[i] === tile,
        `[discardTile] hand[${i}] !== ${tile}`,
      )

      pushSnapshot()

      const nextHand = handBefore.slice()
      nextHand.splice(i, 1)

      latestDrawnTile.value = null
      clearDrawnMarker(roundState.seatWind)
      clearHandLayoutPin(roundState.seatWind)

      const nextDiscards = roundState.discards.concat([tile])
      const sorted = sortHandTiles(
        nextHand,
        roundState.dealerTile,
        undefined,
      )

      console.assert(
        sorted.length === afterNeed,
        `[discardTile] 切牌后张数应为 ${afterNeed}，实际 ${sorted.length}`,
      )
      console.assert(
        nextDiscards.length === discardsBefore + 1,
        `[discardTile] 牌河应 +1：${discardsBefore} → ${nextDiscards.length}`,
      )

      if (sorted.length !== afterNeed) {
        const snap = historyStack.value.pop()
        if (snap) {
          applyRoundState(snap.roundState)
          currentPhase.value = snap.currentPhase
          currentTurnSeat.value = snap.currentTurnSeat ?? DEALER_SEAT
          lastDiscardSeat.value = snap.lastDiscardSeat ?? null
          latestDrawnTile.value = snap.latestDrawnTile ?? null
          lastStepResult.value = snap.lastStepResult
        }
        throw new Error(
          `切牌后手牌张数异常：期望 ${afterNeed}，得到 ${sorted.length}`,
        )
      }

      roundState.handTiles = sorted
      roundState.discards = nextDiscards
      emitPveAction('DISCARD', roundState.seatWind, tile)

      lastStepResult.value = {
        next_turn_seat: nextSeat(roundState.seatWind),
        need_self_action: false,
        action_phase: 'WAIT',
        recommend_discard: null,
        call_decision: null,
        updated_state: null,
      }

      try {
        const snap = historyStack.value[historyStack.value.length - 1]
        if (snap) {
          const prePayload = {
            hand_tiles: [...snap.roundState.handTiles],
            melds: snap.roundState.melds.map((m) => ({
              ...m,
              meld_type: m.meld_type,
              tiles: [...m.tiles],
            })),
            discards: [...snap.roundState.discards],
            dealer_tile: snap.roundState.dealerTile,
            is_dealer: snap.roundState.isDealer,
            seat_wind: snap.roundState.seatWind,
            round_wind: snap.roundState.roundWind,
            opponents: snap.roundState.opponents.map((o) => ({
              seat_wind: o.seat_wind,
              is_dealer: !!o.is_dealer,
              melds: (o.melds || []).map((m) => ({
                ...m,
                meld_type: m.meld_type,
                tiles: [...m.tiles],
              })),
              discards: [...(o.discards || [])],
            })),
            discarded_tiles: [],
          }

          const result = await awaitCurrentSession(epoch, postGameStep(prePayload, {
            actor_seat: roundState.seatWind,
            event_type: 'DISCARD',
            tile,
          }))

          lastStepResult.value = cloneStepResult({
            ...result,
            updated_state: {
              hand_tiles: sanitizeTileList(roundState.handTiles),
              discards: sanitizeTileList(roundState.discards),
              melds: cloneMelds(roundState.melds),
            },
          }) || {
            action_phase: 'WAIT',
            need_self_action: false,
            recommend_discard: result?.recommend_discard ?? null,
            call_decision: result?.call_decision ?? null,
          }
        }
      } catch (e) {
        if (epoch !== sessionEpoch) return
        console.warn('[discardTile] 后端同步失败，保留本地切牌结果', e)
        errorMsg.value = e?.message
          ? `${e.message}（本地已切出，可用撤回）`
          : '后端同步失败（本地已切出，可用撤回）'
      }

      await awaitCurrentSession(epoch, resolveAfterDiscard(roundState.seatWind, lastStepResult.value))

      const selfRec = pendingSelfRecommend.value
        ? { ...pendingSelfRecommend.value }
        : lastStepResult.value?.recommend_discard?.best_tile
          ? {
              best_tile: lastStepResult.value.recommend_discard.best_tile,
              net_ev:
                lastStepResult.value.recommend_discard.candidates?.find(
                  (c) =>
                    c.tile ===
                    lastStepResult.value.recommend_discard.best_tile,
                )?.ev_score ?? null,
            }
          : null
      appendGameLogStep({
        seat: roundState.seatWind,
        action: 'DISCARD',
        tile,
        self_recommendation: selfRec,
      })
      pendingSelfRecommend.value = null

      console.assert(
        roundState.handTiles.length === afterNeed,
        `[discardTile] 结束时手牌张数 ${roundState.handTiles.length} !== ${afterNeed}`,
      )
      console.assert(
        roundState.discards.length === discardsBefore + 1,
        `[discardTile] 结束时牌河未 +1`,
      )

      return lastStepResult.value
      } finally {
        if (epoch !== sessionEpoch) return
        loading.value = false
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /** @deprecated 使用 discardTile；保留别名避免旧调用报错 */
  async function discardSelfTile(tile, index) {
    const epoch = sessionEpoch
    try {
      return discardTile(tile, index)


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /** @deprecated 使用 discardTile */
  function applyLocalDiscard(tile, index) {
    // 同步路径：不走网络
    const meldsN = roundState.melds?.length || 0
    const beforeNeed = 14 - 3 * meldsN
    const afterNeed = 13 - 3 * meldsN
    const discardsBefore = roundState.discards.length
    console.assert(roundState.handTiles.length === beforeNeed)
    console.assert(roundState.handTiles[index] === tile)
    pushSnapshot()
    const hand = roundState.handTiles.slice()
    hand.splice(index, 1)
    latestDrawnTile.value = null
    roundState.handTiles = sortHandTiles(hand, roundState.dealerTile, undefined)
    roundState.discards = roundState.discards.concat([tile])
    console.assert(roundState.handTiles.length === afterNeed)
    console.assert(roundState.discards.length === discardsBefore + 1)
    currentPhase.value = 'WAITING'
  }

  /**
   * 发送一步事件到后端，更新局面并压入历史栈。
   * @param {{
   *   actor_seat: string,
   *   event_type: 'DRAW'|'DISCARD'|'MELD'|'PASS',
   *   tile?: string|null,
   *   meld?: { meld_type: string, tiles: string[] }|null,
   * }} event
   */
  async function dispatchStep(event) {
    const epoch = sessionEpoch
    try {
      if (loading.value) return null
      errorMsg.value = ''
      loading.value = true
      let didPush = false

      try {
        if (event.event_type === 'DISCARD') {
          if (event.actor_seat !== currentTurnSeat.value) {
            throw new Error(
              `当前行动权在 ${windLabel(currentTurnSeat.value)}，${windLabel(event.actor_seat)} 不能出牌`,
            )
          }
        }
        if (
          event.event_type === 'DRAW' &&
          event.actor_seat === roundState.seatWind &&
          currentTurnSeat.value !== roundState.seatWind
        ) {
          throw new Error(
            `当前行动权在 ${windLabel(currentTurnSeat.value)}，尚轮不到自家摸牌`,
          )
        }

        if (
          event.event_type === 'DISCARD' &&
          event.actor_seat === roundState.seatWind &&
          event.tile &&
          !roundState.handTiles.includes(event.tile)
        ) {
          throw new Error(`自家手牌中无 ${event.tile}，无法切出`)
        }

        assertVisibleTileLimit(roundState)

        pushSnapshot()
        didPush = true
        logTurn('dispatchStep:before', {
          type: event.event_type,
          seat: event.actor_seat,
          tile: event.tile,
        })

        const result = await awaitCurrentSession(epoch, postGameStep(toHandRequestPayload(), {
          actor_seat: event.actor_seat,
          event_type: event.event_type,
          tile: event.tile ?? null,
          provider_seat: event.provider_seat || event.meld?.provider_seat ||
            (['MELD', 'PASS'].includes(event.event_type) ? lastDiscardSeat.value : null),
          meld: event.meld ?? null,
        }))

        if (result.updated_state) {
          applyUpdatedStateFromApi(result.updated_state, {
            // DRAW/PASS/MELD 后以本地牌河为准，防 API 抹掉/回灌弃牌
            keepLocalOpponents:
              event.event_type === 'DRAW' ||
              event.event_type === 'PASS' ||
              event.event_type === 'MELD',
          })
        }
        assertVisibleTileLimit(roundState)

        lastStepResult.value = result

        if (event.event_type === 'DISCARD') {
          await awaitCurrentSession(epoch, resolveAfterDiscard(event.actor_seat, result))
        } else if (event.event_type === 'MELD') {
          if (result.action_phase === 'DRAW') {
            await awaitCurrentSession(epoch, enterKongReplaceDraw(result))
          } else {
            takeTurnAfterMeld(result)
          }
        } else if (event.event_type === 'PASS') {
          const provider = lastDiscardSeat.value || currentTurnSeat.value
          await awaitCurrentSession(epoch, advanceTurnToNext(provider, { bypassLoading: true }))
        } else {
          currentPhase.value = mapActionPhase(
            result.action_phase,
            !!result.need_self_action,
          )
          if (
            event.event_type === 'DRAW' &&
            event.actor_seat === roundState.seatWind
          ) {
            currentPhase.value = 'MY_TURN_DISCARD'
          }
        }

        afterStepSort(event, result)
        logTurn('dispatchStep:after', { type: event.event_type })
        return result
      } catch (e) {
        if (epoch !== sessionEpoch) return
        // 关键：仅当本步已 pushSnapshot 才回滚，否则会误弹上家出牌快照
        rollbackLastSnapshot(didPush)
        errorMsg.value = e?.message || String(e)
        logTurn('dispatchStep:rollback', {
          type: event.event_type,
          didPush,
          err: errorMsg.value,
        })
        throw e
      } finally {
        if (epoch !== sessionEpoch) return
        loading.value = false
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /** 弹出最近快照，恢复上手牌况 */
  function undoLastStep() {
    if (!historyStack.value.length || loading.value) return false
    const snap = historyStack.value.pop()
    applyRoundState(snap.roundState)
    currentPhase.value = snap.currentPhase
    currentTurnSeat.value = snap.currentTurnSeat ?? DEALER_SEAT
    lastDiscardSeat.value = snap.lastDiscardSeat ?? null
    latestDrawnTile.value = snap.latestDrawnTile ?? null
    latestDrawnBySeat.value = {
      E: null,
      S: null,
      W: null,
      N: null,
      ...(snap.latestDrawnBySeat || {}),
    }
    if (snap.latestDrawnTile && !latestDrawnBySeat.value[roundState.seatWind]) {
      latestDrawnBySeat.value = {
        ...latestDrawnBySeat.value,
        [roundState.seatWind]: snap.latestDrawnTile,
      }
    }
    lastStepResult.value = snap.lastStepResult
    restoreGameLogSnapshot(snap)
    errorMsg.value = ''
    try {
      assertVisibleTileLimit(roundState)
    } catch (e) {
      errorMsg.value = e?.message || String(e)
    }
    return true
  }

  /** 重开本局：取消旧请求，重新洗牌翻得发牌；clearHistory 才清空跨局计分。 */
  async function resetGame({ clearHistory = false } = {}) {
    reopenTable()
    const epoch = sessionEpoch
    if (clearHistory) {
      cumulativeScores.value = { E: 0, S: 0, W: 0, N: 0 }
      roundHistory.value = []
      roundIndex.value = 0
    }
    resetInProgress.value = true
    loading.value = true
    try {
      await applyAutoDeal()
      if (epoch !== sessionEpoch) return false
      if (!startPlaying()) throw new Error(errorMsg.value)
      return true
    } catch (error) {
      if (epoch !== sessionEpoch) return false
      errorMsg.value = error.message
      throw error
    } finally {
      if (epoch === sessionEpoch) {
        resetInProgress.value = false
        loading.value = false
      }
    }
  }

  /**
   * 按「我的门风」重算四方庄闲（东风永远是庄）。
   * @param {string} newSeat
   * @param {{ preserveOpen?: boolean }} [opts]
   */
  function setSeatWind(newSeat, opts = {}) {
    if (gameState.value === 'PLAYING' || tableLocked.value) {
      errorMsg.value = '对局进行中，请先「重新开局」再改门风'
      return
    }
    if (newSeat === roundState.seatWind && opts.force !== true) {
      applyEastDealerFlags()
      trimHandToTarget()
      return
    }
    const preserve = opts.preserveOpen !== false
    const prev = preserve ? roundState.opponents : []
    const table = buildTableFromSelfWind(newSeat)
    roundState.seatWind = table.selfWind
    roundState.isDealer = table.isDealer
    roundState.opponents = rebuildOpponentsPreservingOpen(
      table.selfWind,
      prev,
    )
    trimHandToTarget()
    errorMsg.value = ''
  }

  /** 换门风导致庄/闲目标张数变化时，截断超额暗手 */
  function trimHandToTarget() {
    const need = roundState.isDealer ? 14 : 13
    if (roundState.handTiles.length > need) {
      roundState.handTiles = roundState.handTiles.slice(0, need)
    }
  }

  /** 确保东=庄、其余闲（不改换门风） */
  function applyEastDealerFlags() {
    if (gameMode.value === 'PVE') {
      roundState.dealerSeat = dealerSeat.value
      roundState.isDealer = roundState.seatWind === dealerSeat.value
      roundState.opponents = roundState.opponents.map((o) => ({
        ...o,
        is_dealer: o.seat_wind === dealerSeat.value,
      }))
      return
    }
    const table = buildTableFromSelfWind(roundState.seatWind)
    roundState.isDealer = table.isDealer
    const openBySeat = Object.fromEntries(
      roundState.opponents.map((o) => [o.seat_wind, o]),
    )
    roundState.opponents = table.opponents.map((o) => {
      const prev = openBySeat[o.seat_wind]
      return {
        ...o,
        melds: prev?.melds ? cloneMelds(prev.melds) : [],
        discards: prev?.discards ? [...prev.discards] : [],
        hand_tiles: prev?.hand_tiles ? [...prev.hand_tiles] : [],
      }
    })
  }

  /**
   * 后端自动发牌 → 写入四家暗手 + 得 + 牌墙（上帝视角）。
   */
  async function applyAutoDeal() {
    const epoch = sessionEpoch
    try {
      if (gameState.value === 'PLAYING') {
        throw new Error('对局中请先结束或重置后再自动发牌')
      }
      // The current dealer is always East. PVE rotates player-to-wind mapping,
      // never the dealer wind itself.
      const activeDealer = DEALER_SEAT
      const deal = await awaitCurrentSession(epoch, postAutoDeal({ dealer_seat: activeDealer }))
      initialDeal.value = {
        hands: Object.fromEntries(Object.entries(deal.hands || {}).map(([seat, tiles]) => [seat, [...tiles]])),
        wall_tiles: [...(deal.wall_tiles || [])],
      }
      const self = roundState.seatWind
      roundState.dealerTile = deal.dealer_tile
      roundState.handTiles = sortHandTiles(
        [...(deal.hands[self] || [])],
        deal.dealer_tile,
        undefined,
      )
      roundState.melds = []
      roundState.discards = []
      roundState.dealerSeat = activeDealer
      roundState.isDealer = self === activeDealer
      roundState.opponents = roundState.opponents.map((o) => ({
        ...o,
        is_dealer: o.seat_wind === activeDealer,
        melds: [],
        discards: [],
        hand_tiles: sortHandTiles(
          [...(deal.hands[o.seat_wind] || [])],
          deal.dealer_tile,
          undefined,
        ),
      }))
      wallTiles.value = [...(deal.wall_tiles || [])]
      godViewWallMode.value = true
      clearAllDrawnMarkers()
      clearHandLayoutPin()
      lastStepResult.value = null
      lastDiscardSeat.value = null
      currentTurnSeat.value = deal.first_turn_seat || activeDealer
      gameState.value = 'SETUP'
      tableLocked.value = false
      errorMsg.value = ''
      logTurn('applyAutoDeal', {
        dealer_tile: deal.dealer_tile,
        wall: deal.wall_count,
        selfCount: roundState.handTiles.length,
      })
      return deal


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 上帝视角：从本地牌墙摸 1 张入指定座位暗手（不上传暗手）。
   * @returns {string} 摸入牌码
   */
  function drawFromWallLocal(seat, opts = {}) {
    if (!wallTiles.value.length) {
      throw new Error('牌墙已空，无法摸牌（可宣告荒牌流局）')
    }
    const drawn = opts.rinshan ? wallTiles.value.at(-1) : wallTiles.value[0]
    wallTiles.value = opts.rinshan ? wallTiles.value.slice(0, -1) : wallTiles.value.slice(1)
    if (seat === roundState.seatWind) {
      setDrawnMarker(seat, drawn)
      return drawn
    }
    const oi = roundState.opponents.findIndex((o) => o.seat_wind === seat)
    if (oi < 0) throw new Error(`找不到座位 ${seat}`)
    // 轻量：只追加到末尾挂右，不整手重排
    const opps = roundState.opponents.map((o, i) => {
      if (i !== oi) {
        return {
          ...o,
          melds: cloneMelds(o.melds),
          discards: [...(o.discards || [])],
          hand_tiles: [...(o.hand_tiles || [])],
        }
      }
      return {
        ...o,
        melds: cloneMelds(o.melds),
        discards: [...(o.discards || [])],
        hand_tiles: [...(o.hand_tiles || []), drawn],
      }
    })
    roundState.opponents = opps
    setDrawnMarker(seat, drawn)
    appendGameLogStep({
      seat,
      action: 'DRAW',
      tile: drawn,
    })
    return drawn
  }

  /**
   * 上帝视角：点击当前行动方暗手牌 →（必要时先摸）打出并流转。
   */
  async function discardFromGodView(seat, tile, index) {
    const epoch = sessionEpoch
    try {
      if (seat !== currentTurnSeat.value) {
        throw new Error(
          `当前行动权在 ${windLabel(currentTurnSeat.value)}，${windLabel(seat)} 不能出牌`,
        )
      }

      if (seat === roundState.seatWind) {
        const info = seatHandSlots(seat)
        if (info.handLen === info.waitNeed) {
          if (godViewWallMode.value) {
            applyGodViewSelfDrawFast()
          } else {
            const drawn = drawFromWallLocal(seat)
            await awaitCurrentSession(epoch, selfDrawTile(drawn, { bypassLoading: true, fromWall: true }))
          }
        } else if (info.handLen !== info.discardNeed) {
          throw new Error(
            `自家暗手张数异常：待摸 ${info.waitNeed} / 待切 ${info.discardNeed}，实际 ${info.handLen}（副露 ${info.meldsN}）`,
          )
        }
        const hand = roundState.handTiles
        let idx = index
        let code = tile
        if (typeof idx === 'number' && idx >= 0 && idx < hand.length) {
          code = hand[idx]
        } else {
          idx = hand.lastIndexOf(code)
          if (idx < 0) throw new Error(`自家暗手中无 ${code}`)
        }
        return discardTile(code, idx)
      }

      const oi = roundState.opponents.findIndex((o) => o.seat_wind === seat)
      if (oi < 0) throw new Error(`找不到座位 ${seat}`)
      const info = seatHandSlots(seat)
      if (info.handLen === info.waitNeed) {
        drawFromWallLocal(seat)
      } else if (info.handLen !== info.discardNeed) {
        throw new Error(
          `${windLabel(seat)} 暗手张数异常：待摸 ${info.waitNeed} / 待切 ${info.discardNeed}，实际 ${info.handLen}（副露 ${info.meldsN}）`,
        )
      }
      let hand = [...(roundState.opponents[oi].hand_tiles || [])]
      let code = tile
      let idx = index
      if (typeof idx === 'number' && idx >= 0 && idx < hand.length) {
        code = hand[idx]
      } else if (!hand.includes(code)) {
        throw new Error(`${windLabel(seat)} 暗手中无 ${code}`)
      } else {
        idx = hand.lastIndexOf(code)
      }
      return opponentDiscardTile(seat, code, idx)


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 开始对局：SETUP → PLAYING。
   * 要求起手已满 targetInitialCount；理牌后行动权从东风庄开始。
   */
  function startPlaying() {
    if (gameState.value === 'PLAYING') return true
    applyEastDealerFlags()
    const need = targetInitialCount.value
    if (roundState.handTiles.length !== need) {
      errorMsg.value = `请先录入满 ${need} 张起手（当前 ${roundState.handTiles.length}）`
      return false
    }
    try {
      assertVisibleTileLimit(roundState)
    } catch (e) {
      errorMsg.value = e?.message || String(e)
      return false
    }

    clearAllDrawnMarkers()
    sortAllClosedHands()

    gameState.value = 'PLAYING'
    tableLocked.value = true
    lastDiscardSeat.value = null
    currentTurnSeat.value = gameMode.value === 'PVE' ? dealerSeat.value : DEALER_SEAT
    historyStack.value = []
    lastStepResult.value = null
    errorMsg.value = ''
    resetGameLog()
    syncPhaseFromTurn()
    return true
  }

  /** @deprecated 使用 startPlaying；保留别名 */
  function confirmStartGame() {
    return startPlaying()
  }

  /** 重新开局：回到 SETUP，清空牌面（保留门风与财神；保留累计分/历史） */
  function reopenTable() {
    invalidateSessionRequests()
    loading.value = false
    huResolutionBusy.value = false
    resetInProgress.value = false
    recommendDrawToken.value = 0
    clearHandLayoutPin()
    const keep = {
      seatWind: roundState.seatWind,
      dealerSeat: gameMode.value === 'PVE' ? dealerSeat.value : 'E',
      dealerTile: roundState.dealerTile,
      roundWind: roundState.roundWind,
    }
    const fresh = createInitialRoundState(keep)
    applyRoundState(fresh)
    historyStack.value = []
    currentPhase.value = 'IDLE'
    lastStepResult.value = null
    clearAllDrawnMarkers()
    lastDiscardSeat.value = null
    currentTurnSeat.value = DEALER_SEAT
    gameState.value = 'SETUP'
    tableLocked.value = false
    selfWinSettlement.value = null
    showGameOverModal.value = false
    showRoundSummaryModal.value = false
    pveRoundOverPending.value = false
    wallTiles.value = []
    godViewWallMode.value = false
    errorMsg.value = ''
    gameRoundId.value = ''
    gameLogSteps.value = []
    initialDeal.value = null
    pendingSelfRecommend.value = null
    pendingAiRecommendations.value = {}
  }

  /**
   * 下庄一轮的门风映射：新庄=原下家变东（东永远为庄）。
   * 旧 E→N，S→E，W→S，N→W
   */
  const ROTATE_WIND_MAP = Object.freeze({
    E: 'N',
    S: 'E',
    W: 'S',
    N: 'W',
  })

  function rotateScoreMap(scores, map) {
    const next = { E: 0, S: 0, W: 0, N: 0 }
    for (const old of ['E', 'S', 'W', 'N']) {
      const neu = map[old] || old
      next[neu] = Number(scores?.[old] ?? 0)
    }
    return next
  }

  /**
   * 开始下一局：轮庄 + 清空牌面，保留累计分与历史；无需刷新页面。
   *
   * @param {string|null} lastWinnerSeat 上局赢家门风；流局传 null
   * @param {boolean} isDealerWin 上局是否庄家和牌（连庄）
   * @param {{ isDraw?: boolean }} [opts]
   */
  function startNextRound(lastWinnerSeat, isDealerWin, opts = {}) {
    if (gameMode.value === 'PVE') return startNextPveRound(lastWinnerSeat, isDealerWin, opts)
    invalidateSessionRequests()
    loading.value = false
    huResolutionBusy.value = false
    resetInProgress.value = false
    recommendDrawToken.value = 0
    clearHandLayoutPin()
    const isDraw = !!opts.isDraw || lastWinnerSeat == null
    // 连庄：庄家和牌；下庄：闲家和或流局（东风位永远是庄，下庄=门风逆时针重映射）
    const keepDealer = !isDraw && !!isDealerWin

    if (!keepDealer) {
      const map = ROTATE_WIND_MAP
      cumulativeScores.value = rotateScoreMap(cumulativeScores.value, map)
      const newSelf = map[roundState.seatWind] || roundState.seatWind
      // 换门风并重建对手座位（东仍为庄）
      const table = buildTableFromSelfWind(newSelf)
      roundState.seatWind = table.selfWind
      roundState.isDealer = table.isDealer
      roundState.opponents = table.opponents.map((o) => ({
        ...o,
        melds: [],
        discards: [],
      }))
    }

    // 清空四方牌面与推荐，进入 SETUP
    roundState.handTiles = []
    roundState.melds = []
    roundState.discards = []
    roundState.opponents = roundState.opponents.map((o) => ({
      ...o,
      melds: [],
      discards: [],
      hand_tiles: [],
    }))
    applyEastDealerFlags()

    historyStack.value = []
    currentPhase.value = 'IDLE'
    lastStepResult.value = null
    clearAllDrawnMarkers()
    lastDiscardSeat.value = null
    currentTurnSeat.value = DEALER_SEAT
    gameState.value = 'SETUP'
    tableLocked.value = false
    selfWinSettlement.value = null
    wallTiles.value = []
    godViewWallMode.value = false
    errorMsg.value = ''
    gameRoundId.value = ''
    gameLogSteps.value = []
    initialDeal.value = null
    pendingSelfRecommend.value = null
    pendingAiRecommendations.value = {}
    logTurn('startNextRound', {
      keepDealer,
      isDraw,
      lastWinnerSeat,
      selfWind: roundState.seatWind,
      isDealer: roundState.isDealer,
    })
    return true
  }

  async function startPveGame() {
    gameMode.value = 'PVE'
    dealerPlayerId.value = 0
    roundState.seatWind = 'E'
    dealerSeat.value = 'E'
    roundCount.value = 1
    dealerRotationHistory.value = [0]
    showGameOverModal.value = false
    showRoundSummaryModal.value = false
    pveRoundOverPending.value = false
    cumulativeScores.value = { E: 0, S: 0, W: 0, N: 0 }
    roundHistory.value = []
    roundIndex.value = 0
    reopenTable()
    roundState.seatWind = pveWindForPlayer(0, dealerPlayerId.value)
    roundState.opponents = pveOpponentsForDealer(dealerPlayerId.value)
    applyEastDealerFlags()
    await applyAutoDeal()
    return startPlaying()
  }

  async function startNextPveRound(lastWinnerSeat, isDealerWin, opts = {}) {
    const isDraw = !!opts.isDraw || lastWinnerSeat == null
    if (pveCircleSummary.value) return false
    const previousDealerPlayerId = dealerPlayerId.value
    let nextDealerPlayerId = previousDealerPlayerId
    if (!opts.newCircle && (isDraw || !isDealerWin)) {
      nextDealerPlayerId = (previousDealerPlayerId + 1) % WIND_ORDER.length
    } else if (opts.newCircle) {
      nextDealerPlayerId = 0
    }
    if (nextDealerPlayerId !== previousDealerPlayerId) {
      cumulativeScores.value = remapPveScores(
        cumulativeScores.value,
        previousDealerPlayerId,
        nextDealerPlayerId,
      )
    }
    showGameOverModal.value = false
    showRoundSummaryModal.value = false
    pveRoundOverPending.value = false
    dealerPlayerId.value = nextDealerPlayerId
    dealerSeat.value = DEALER_SEAT
    if (!dealerRotationHistory.value.includes(nextDealerPlayerId)) {
      dealerRotationHistory.value = [...dealerRotationHistory.value, nextDealerPlayerId]
    }
    pveCircleSummary.value = false
    reopenTable()
    gameMode.value = 'PVE'
    roundState.seatWind = pveWindForPlayer(0, dealerPlayerId.value)
    roundState.opponents = pveOpponentsForDealer(dealerPlayerId.value)
    applyEastDealerFlags()
    await applyAutoDeal()
    return startPlaying()
  }

  /** 补杠先亮出第四张并逐家问胡；无人抢胡才升级碰并摸岭上张。 */
  async function startAddKong(seat, tile) {
    if (loading.value || gameState.value !== 'PLAYING' || !tableLocked.value ||
      isResponseWindow.value || currentTurnSeat.value !== seat) throw new Error('仅当前待切玩家可补杠')
    const face = sanitizeTileCode(tile)
    if (!face || face === roundState.dealerTile) throw new Error('百搭（得）不可补杠')
    const self = seat === roundState.seatWind
    const actor = self ? { hand_tiles: roundState.handTiles, melds: roundState.melds }
      : roundState.opponents.find((o) => o.seat_wind === seat)
    const meldIndex = actor?.melds?.findIndex((m) => ['pong', 'peng'].includes(m.meld_type) &&
      m.tiles?.length === 3 && m.tiles.every((t) => t === face)) ?? -1
    if (meldIndex < 0 || !actor.hand_tiles?.includes(face)) throw new Error('手牌没有已碰牌的第四张')
    if (actor.hand_tiles.length + 3 * actor.melds.length !== 14) throw new Error('补杠须在摸牌后的待切窗口')
    if (godViewWallMode.value && !wallTiles.value.length) throw new Error('牌墙已空，无法补杠摸岭上牌')

    const prePayload = toHandRequestPayload()
    // 用其他三家的暗手判胡；吃、碰、明杠均不得响应补杠牌。
    const queue = scanTableResponses(seat, face).catchWinSeats
    pushSnapshot()
    const hand = [...actor.hand_tiles]
    hand.splice(hand.indexOf(face), 1)
    if (self) roundState.handTiles = hand
    else roundState.opponents = roundState.opponents.map((o) => o.seat_wind === seat
      ? { ...o, hand_tiles: hand } : o)
    clearDrawnMarker(seat)
    lastDiscardSeat.value = seat
    currentPhase.value = 'WAIT_RESPONSE'
    lastStepResult.value = {
      action_phase: 'WAIT', need_self_action: false, call_decision: null,
      recommend_discard: null, _table_responses: [], _response_tile: face,
      pending_hu_queue: queue, _catch_win_seats: queue,
      _pending_add_kong: { seat, tile: face, meldIndex, prePayload },
      note: `${windLabel(seat)}风声明补杠 ${face}，等待抢杠胡`,
    }
    if (queue.length) {
      syncHuResponseWindow()
      return lastStepResult.value
    }
    return finalizeAddKong()
  }

  async function finalizeAddKong() {
    const pending = lastStepResult.value?._pending_add_kong
    if (!pending || pendingHuQueue.value.length) throw new Error('抢杠胡尚未仲裁完毕')
    const { seat, tile, meldIndex, prePayload } = pending
    const epoch = sessionEpoch
    const self = seat === roundState.seatWind
    const melds = self ? cloneMelds(roundState.melds)
      : cloneMelds(roundState.opponents.find((o) => o.seat_wind === seat)?.melds || [])
    if (!['pong', 'peng'].includes(melds[meldIndex]?.meld_type) || melds[meldIndex]?.tiles?.[0] !== tile) {
      throw new Error('待补杠的碰牌已失效')
    }
    melds[meldIndex] = { ...melds[meldIndex], meld_type: 'ming_gang', tiles: [tile, tile, tile, tile] }
    if (self) roundState.melds = melds
    else roundState.opponents = roundState.opponents.map((o) => o.seat_wind === seat
      ? { ...o, melds } : o)
    lastDiscardSeat.value = null
    currentTurnSeat.value = seat
    currentPhase.value = 'WAITING'
    lastStepResult.value = { next_turn_seat: seat, need_self_action: self,
      action_phase: 'DRAW', call_decision: null, recommend_discard: null,
      note: `${windLabel(seat)}风补杠成功，正在摸岭上牌` }
    emitPveAction('GANG', seat, tile)
    appendGameLogStep({ seat, action: 'GANG', tile })
    if (self) await awaitCurrentSession(epoch, enterKongReplaceDraw(lastStepResult.value))
    else await awaitCurrentSession(epoch, ensureGodViewDrawForSeat(seat, { force: true, rinshan: true }))
    if (gameState.value === 'PLAYING' && !self) {
      lastStepResult.value = { ...lastStepResult.value, action_phase: 'DISCARD', note: `${windLabel(seat)}风补杠后请切牌` }
    }
    try {
      await awaitCurrentSession(epoch, postGameStep(prePayload, {
        actor_seat: seat, event_type: 'MELD', tile,
        meld: { meld_type: 'ming_gang', tiles: [tile, tile, tile, tile] },
      }))
    } catch (error) {
      if (epoch !== sessionEpoch) return
      console.warn('[finalizeAddKong] 后端同步失败，保留本地补杠', error)
      errorMsg.value = `${error?.message || error}（本地已补杠）`
    }
    return lastStepResult.value
  }

  async function executeOpponentBuGang({ seat, tile }) {
    if (seat === roundState.seatWind) throw new Error('请使用自家补杠入口')
    return startAddKong(seat, tile)
  }

  async function continuePveCircle() {
    roundCount.value += 1
    dealerRotationHistory.value = []
    showGameOverModal.value = false
    showRoundSummaryModal.value = false
    pveRoundOverPending.value = false
    return startNextPveRound(null, false, { isDraw: true, newCircle: true })
  }

  async function exitPveGame() {
    gameMode.value = 'SANDBOX'
    showGameOverModal.value = false
    showRoundSummaryModal.value = false
    pveRoundOverPending.value = false
    dealerPlayerId.value = 0
    dealerSeat.value = 'E'
    roundCount.value = 1
    dealerRotationHistory.value = [0]
    const homeTable = buildTableFromSelfWind('E')
    roundState.seatWind = homeTable.selfWind
    roundState.isDealer = homeTable.isDealer
    roundState.opponents = homeTable.opponents
    return resetGame({ clearHistory: true })
  }

  /** @deprecated 兼容旧名 → startNextRound */
  function startNewRoundAfterWin() {
    const info = selfWinSettlement.value
    const dealerWin =
      !!info?.is_dealer_win ||
      (!info?.is_draw && info?.winner_seat === DEALER_SEAT)
    return startNextRound(
      info?.is_draw ? null : info?.winner_seat || null,
      dealerWin,
      { isDraw: !!info?.is_draw },
    )
  }

  function applyRoundScoresFromSettlement(settlement) {
    const net = settlement?.net_by_seat || {}
    const next = { ...cumulativeScores.value }
    for (const seat of ['E', 'S', 'W', 'N']) {
      next[seat] = Number(next[seat] || 0) + Number(net[seat] || 0)
    }
    cumulativeScores.value = next
  }

  function pushRoundHistory(settlement) {
    roundIndex.value += 1
    const isDraw = !!settlement?.is_draw
    const winner = settlement?.winner_seat
    let summary = '荒牌流局'
    if (!isDraw && winner) {
      const who = windLabel(winner)
      if (settlement.is_zimo) summary = `${who}风自摸`
      else if (settlement.discarder_seat) {
        summary = settlement.win_type_label === '抢杠胡'
          ? `${who}风抢${windLabel(settlement.discarder_seat)}风杠胡`
          : `${who}风捉${windLabel(settlement.discarder_seat)}铳`
      }
    }
    roundHistory.value = [
      ...roundHistory.value,
      {
        roundIndex: roundIndex.value,
        winner_seat: winner || null,
        win_type: settlement?.win_type,
        is_draw: isDraw,
        is_zimo: !!settlement?.is_zimo,
        discarder_seat: settlement?.discarder_seat || null,
        points: settlement?.points ?? settlement?.final_hu ?? 0,
        net_by_seat: { ...(settlement?.net_by_seat || {}) },
        is_dealer_win: !!settlement?.is_dealer_win,
        summary,
        headline: summary,
      },
    ]
    pveRoundOverPending.value = gameMode.value === 'PVE' &&
      [0, 1, 2, 3].every((playerId) => dealerRotationHistory.value.includes(playerId))
  }

  /** 清空起手（仅 SETUP） */
  function clearSetupHand() {
    if (gameState.value !== 'SETUP') return false
    roundState.handTiles = []
    latestDrawnTile.value = null
    errorMsg.value = ''
    return true
  }

  /** PLAYING 中庄家满手时进入切牌（兼容旧入口） */
  function enterSelfDiscardPhase() {
    if (gameState.value !== 'PLAYING') {
      errorMsg.value = '请先「开始对局」'
      return false
    }
    if (currentTurnSeat.value !== roundState.seatWind) {
      errorMsg.value = `当前行动权在 ${windLabel(currentTurnSeat.value)}，尚轮不到自家`
      return false
    }
    const slots =
      roundState.handTiles.length + 3 * (roundState.melds?.length || 0)
    if (slots !== 14) {
      errorMsg.value =
        `进入切牌需手牌位满：暗手 ${roundState.handTiles.length}/` +
        `${14 - 3 * (roundState.melds?.length || 0)}` +
        `（melds=${roundState.melds?.length || 0}，slots=${slots}，须=14）`
      return false
    }
    try {
      assertVisibleTileLimit(roundState)
    } catch (e) {
      errorMsg.value = e?.message || String(e)
      return false
    }
    errorMsg.value = ''
    latestDrawnTile.value = null
    applyHandSort({ keepDrawn: false })
    currentPhase.value = 'MY_TURN_DISCARD'
    return true
  }

  /**
   * 组装四家结算快照（自家 + 三对手）。
   */
  function buildPlayersForSettle() {
    return [
      {
        seat_wind: roundState.seatWind,
        is_dealer: !!roundState.isDealer,
        melds: cloneMelds(roundState.melds),
        hand_tiles: [...(roundState.handTiles || [])],
      },
      ...roundState.opponents.map((o) => ({
        seat_wind: o.seat_wind,
        is_dealer: !!o.is_dealer,
        melds: cloneMelds(o.melds),
        hand_tiles: [...(o.hand_tiles || [])],
      })),
    ]
  }

  /**
   * 统一终局宣告：自摸 / 捉铳（自家或代录对手）→ GAME_OVER + 结算明细。
   * @param {{
   *   winnerSeat: string,
   *   winType: 'zimo'|'ron'|'self_draw_win'|'catch_win'|'hu',
   *   winTile?: string,
   *   points?: number,
   *   handTiles?: string[],
   *   melds?: object[],
   *   discarderSeat?: string,
   *   winInfo?: object,
   * }} opts
   */
  async function declareTableWin(opts) {
    const epoch = sessionEpoch
    try {
      if (huResolutionBusy.value) return false
      assertHuTurn(opts?.winnerSeat, opts?.winType, opts?.winTile || opts?.winInfo?.win_tile,
        opts?.discarderSeat || lastDiscardSeat.value)
      const winnerSeat = opts?.winnerSeat
      const winType = lastStepResult.value?._pending_add_kong
        ? 'rob_kong'
        : opts?.winType || (opts?.winInfo?.is_zimo ? 'zimo' : 'ron')
      if (!winnerSeat) {
        errorMsg.value = '缺少胡牌座位'
        return false
      }
      if (gameState.value === 'GAME_OVER') return false

      const winInfo = opts.winInfo || {}
      const points =
        opts.points ??
        winInfo.final_hu ??
        winInfo.final_points ??
        winInfo.points ??
        null

      huResolutionBusy.value = true
      const previousLoading = loading.value
      loading.value = true
      try {
        let settlement = null
        try {
          settlement = await awaitCurrentSession(epoch, postSettle({
            winner_seat: winnerSeat,
            win_type: winType,
            dealer_tile: roundState.dealerTile,
            players: buildPlayersForSettle(),
            points: points != null ? Number(points) : null,
            hand_tiles: opts.handTiles ?? null,
            melds: opts.melds ?? null,
            win_tile: opts.winTile || winInfo.win_tile || null,
            discarder_seat: opts.discarderSeat || null,
            wrap_penalty: false,
            restored_jokers: winInfo.restored_jokers || 0,
            round_wind: roundState.roundWind || 'E',
          }))
        } catch (e) {
        if (epoch !== sessionEpoch) return
          // 后端不可用时本地兜底：仅主支付估算
          console.warn('[declareTableWin] settle API failed', e)
          const pts = Number(points) || 0
          const winnerIsDealer =
            winnerSeat === roundState.seatWind
              ? !!roundState.isDealer
              : !!roundState.opponents.find((o) => o.seat_wind === winnerSeat)
                  ?.is_dealer
          settlement = {
            winner_seat: winnerSeat,
            win_type: winType === 'zimo' || winType === 'self_draw_win' ? 'zimo' : 'ron',
            win_type_label:
              winType === 'rob_kong' ? '抢杠胡' : (winType === 'zimo' || winType === 'self_draw_win' ? '自摸' : '捉铳'),
            is_zimo: winType === 'zimo' || winType === 'self_draw_win',
            is_dealer_win: winnerIsDealer,
            points: pts,
            final_hu: pts,
            final_points: pts,
            wrap_penalty: false,
            net_by_seat: {},
            transfers: [],
            payments: {
              label: winnerIsDealer
                ? '庄家和牌：三闲各付全额'
                : '闲家和牌：庄全额、两闲半额',
              points: pts,
                winner_income: winnerIsDealer ? Math.min(pts, 100) * 3 : Math.min(pts, 100) + Math.min(pts / 2, 100) * 2,
                from_dealer: winnerIsDealer ? 0 : Math.min(pts, 100),
                from_each_xian: Math.min(winnerIsDealer ? pts : pts / 2, 100),
                payment_cap: 100,
            },
          }
        }

        selfWinSettlement.value = {
          ...winInfo,
          ...settlement,
          win_type_label: winType === 'rob_kong' ? '抢杠胡' : settlement.win_type_label,
          is_win: true,
          is_draw: false,
          is_zimo: !!settlement.is_zimo,
          winner_seat: winnerSeat,
          hard_hu_label:
            winInfo.hard_hu_label ||
            (winInfo.is_hard_hu
              ? '硬碰硬'
              : winInfo.is_hard_hu === false
                ? '软胡'
                : ''),
          win_tile: opts.winTile || winInfo.win_tile || settlement.win_tile,
          fan: winInfo.fan,
          details: winInfo.details || settlement.hu_detail?.details,
          base_hu: winInfo.base_hu ?? settlement.hu_detail?.base_hu,
          tile_hu: winInfo.tile_hu ?? settlement.hu_detail?.tile_hu,
          restored_jokers: winInfo.restored_jokers ?? 0,
          hu_detail: settlement.hu_detail || null,
        }
        applyRoundScoresFromSettlement(selfWinSettlement.value)
        pushRoundHistory(selfWinSettlement.value)
        gameState.value = 'GAME_OVER'
        emitPveAction('WIN', winnerSeat, opts.winTile || winInfo.win_tile || null)
        showGameOverModal.value = true
        currentPhase.value = 'IDLE'
        latestDrawnTile.value = null
        lastDiscardSeat.value = null
        if (lastStepResult.value) {
          lastStepResult.value = {
            ...lastStepResult.value,
            can_self_win: false,
            self_win_info: null,
            call_decision: null,
            recommend_discard: null,
            need_self_action: false,
            action_phase: 'WAIT',
            pending_hu_queue: [],
            _catch_win_seats: [],
          }
        }
        appendGameLogStep({
          seat: winnerSeat,
          action: 'WIN',
          tile: opts.winTile || winInfo.win_tile || null,
        })
        const archived = await awaitCurrentSession(epoch, submitGameRecord({
          winner_seat: winnerSeat,
          win_type: settlement.win_type,
          points: settlement.points ?? settlement.final_hu ?? null,
          deal_in_seat:
            settlement.is_zimo
              ? null
              : opts.discarderSeat || settlement.discarder_seat || null,
          details: {
            hu_detail: settlement.hu_detail || null,
            payments: settlement.payments || null,
            net_by_seat: settlement.net_by_seat || null,
            transfers: settlement.transfers || null,
            is_dealer_win: settlement.is_dealer_win,
            win_type_label: settlement.win_type_label,
          },
        }))
        selfWinSettlement.value = {
          ...selfWinSettlement.value,
          game_id: archived?.game_id || null,
          archive_error: !archived?.game_id,
        }
        logTurn('declareTableWin', {
          winnerSeat,
          winType: settlement.win_type,
          points: settlement.points,
        })
        if (lastStepResult.value) {
          lastStepResult.value = { ...lastStepResult.value, pending_hu_queue: [], _catch_win_seats: [] }
        }
        return true
      } finally {
        if (epoch !== sessionEpoch) return
        huResolutionBusy.value = false
        loading.value = previousLoading
      }


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 荒牌流局：进入 GAME_OVER，下局下庄。
   */
  async function declareDraw(note = '荒牌流局') {
    const epoch = sessionEpoch
    try {
      if (gameState.value === 'GAME_OVER') return false
      const settlement = {
        is_draw: true,
        is_win: false,
        is_zimo: false,
        win_type: 'draw',
        win_type_label: '流局',
        winner_seat: null,
        points: 0,
        final_hu: 0,
        final_points: 0,
        is_dealer_win: false,
        wrap_penalty: false,
        net_by_seat: { E: 0, S: 0, W: 0, N: 0 },
        transfers: [],
        payments: { label: note || '荒牌流局' },
      }
      selfWinSettlement.value = settlement
      pushRoundHistory(settlement)
      gameState.value = 'GAME_OVER'
      showGameOverModal.value = true
      currentPhase.value = 'IDLE'
      latestDrawnTile.value = null
      lastDiscardSeat.value = null
      if (lastStepResult.value) {
        lastStepResult.value = {
          ...lastStepResult.value,
          call_decision: null,
          recommend_discard: null,
          need_self_action: false,
          action_phase: 'WAIT',
        }
      }
      appendGameLogStep({
        seat: currentTurnSeat.value || roundState.seatWind,
        action: 'WIN',
        tile: null,
      })
      const archived = await awaitCurrentSession(epoch, submitGameRecord({
        winner_seat: null,
        win_type: 'draw',
        points: 0,
        deal_in_seat: null,
        details: { note: note || '荒牌流局', payments: settlement.payments },
      }))
      selfWinSettlement.value = {
        ...selfWinSettlement.value,
        game_id: archived?.game_id || null,
        archive_error: !archived?.game_id,
      }
      logTurn('declareDraw', {})
      return true


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 宣告自摸：进入 GAME_OVER，展示结算。
   * @param {object} info check_self_drawn_win / self_win_info
   */
  async function declareSelfWin(info) {
    const epoch = sessionEpoch
    try {
      if (!info?.is_win && info?.final_hu == null && info?.final_points == null) {
        errorMsg.value = '无有效自摸信息'
        return false
      }
      const remain = [...roundState.handTiles]
      const wt = info.win_tile
      if (wt && remain.includes(wt)) {
        remain.splice(remain.indexOf(wt), 1)
      }
      return declareTableWin({
        winnerSeat: roundState.seatWind,
        winType: 'self_draw_win',
        winTile: wt,
        points: info.final_hu ?? info.final_points,
        handTiles: remain,
        melds: cloneMelds(roundState.melds),
        winInfo: { ...info, is_zimo: true },
      })


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 自家捉铳胡牌（CALL 面板选胡）。
   */
  async function declareSelfRon(discardedTile, providerSeat) {
    const epoch = sessionEpoch
    try {
      assertHuTurn(roundState.seatWind, 'catch_win', discardedTile, providerSeat || lastDiscardSeat.value)
      const response = isResponseWindow.value ? lastStepResult.value : null
      const tile = discardedTile || ''
      const hand = [...roundState.handTiles]
      const melds = cloneMelds(roundState.melds)
      let winInfo = { is_zimo: false, win_tile: tile }
      try {
        const hu = await awaitCurrentSession(epoch, calculateHuPoints({
          hand_tiles: hand,
          melds,
          win_tile: tile,
          is_zimo: false,
          seat_wind: roundState.seatWind,
          dealer_tile: roundState.dealerTile,
          is_dealer: !!roundState.isDealer,
          // 后端 calculate-hu / settle 会枚举得还原；此处传 0 仅占位
          restored_jokers: 0,
        }))
        winInfo = {
          ...hu,
          is_zimo: false,
          win_tile: tile,
          hard_hu_label: hu.is_hard_hu ? '硬碰硬' : '软胡',
        }
      } catch (e) {
        if (epoch !== sessionEpoch) return
        console.warn('[declareSelfRon] calculate-hu failed, settle will recompute', e)
      }
      if (response && response !== lastStepResult.value) throw new Error('胡牌响应已变更，请重新操作')
      return declareTableWin({
        winnerSeat: roundState.seatWind,
        winType: response?._pending_add_kong ? 'rob_kong' : 'catch_win',
        winTile: tile,
        handTiles: hand,
        melds,
        discarderSeat: providerSeat || lastDiscardSeat.value || null,
        // 不预先锁死 points，让 /settle 枚举得还原取最高胡
        points: null,
        winInfo,
      })


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /**
   * 代录对手自摸 / 捉铳（无暗手时按副露估算点数）。
   */
  async function declareOpponentWin({
    seat,
    winType = 'self_draw_win',
    winTile = null,
    discarderSeat = null,
    points = null,
  }) {
    const epoch = sessionEpoch
    try {
      if (!seat || seat === roundState.seatWind) {
        throw new Error('请指定对手座位')
      }
      const opp = roundState.opponents.find((o) => o.seat_wind === seat)
      if (!opp) throw new Error(`找不到对手 ${seat}`)
      return declareTableWin({
        winnerSeat: seat,
        winType,
        winTile,
        points,
        melds: cloneMelds(opp.melds),
        discarderSeat,
        winInfo: {
          is_zimo: winType === 'zimo' || winType === 'self_draw_win',
          win_tile: winTile,
        },
      })


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /** 确认胡牌后收起 CALL 面板，行动权交出牌方下家（仅「过胡」不结算时用） */
  async function acknowledgeHu() {
    const epoch = sessionEpoch
    try {
      if (isResponseWindow.value) return passCall(lastStepResult.value?._response_tile)
      if (lastStepResult.value) {
        lastStepResult.value = {
          ...lastStepResult.value,
          call_decision: null,
          recommend_discard: lastStepResult.value.recommend_discard ?? null,
          action_phase: 'WAIT',
          need_self_action: false,
        }
      }
      const provider = lastDiscardSeat.value || currentTurnSeat.value
      await awaitCurrentSession(epoch, advanceTurnToNext(provider, { bypassLoading: true }))


    } catch (error) {
      if (epoch !== sessionEpoch) return
      throw error
    }
  }

  /** 强制一键理牌（忽略开关） */
  function manualSortHand() {
    clearHandLayoutPin(roundState.seatWind)
    applyHandSort({
      force: true,
      keepDrawn: !!latestDrawnTile.value,
    })
  }

  return {
    roundState,
    historyStack,
    currentPhase,
    currentTurnSeat,
    lastDiscardSeat,
    lastStepResult,
    latestDrawnTile,
    latestDrawnBySeat,
    autoSortEnabled,
    tableLocked,
    gameState,
    targetInitialCount,
    canStartPlaying,
    isSetup,
    isPlaying,
    isGameOver,
    showGameOverModal,
    showRoundSummaryModal,
    pveRoundOverPending,
    loading,
    errorMsg,
    phaseLabel,
    isSelfTurn,
    canUndo,
    historyDepth,
    PHASE_LABEL,
    dispatchStep,
    undoLastStep,
    resetGame,
    resetInProgress,
    validateRoundState,
    assertVisibleTileLimit,
    countVisibleTiles,
    setSeatWind,
    applyEastDealerFlags,
    startPlaying,
    confirmStartGame,
    reopenTable,
    clearSetupHand,
    syncPhaseFromTurn,
    advanceTurnToNext,
    opponentDiscardTile,
    passCall,
    passAllCalls,
    isResponseWindow,
    catchWinSeats,
    pendingHuQueue,
    currentHuSeat,
    scanTableResponses,
    executeOpponentMeld,
    executeOpponentAnGang,
    takeTurnAfterMeld,
    enterKongReplaceDraw,
    applySelfMeld,
    executeGang,
    applySelfKong,
    toHandRequestPayload,
    cloneRoundState,
    enterSelfDiscardPhase,
    acknowledgeHu,
    declareSelfWin,
    declareSelfRon,
    declareOpponentWin,
    declareTableWin,
    declareDraw,
    startNextRound,
    startPveGame,
    startNextPveRound,
    continuePveCircle,
    exitPveGame,
    gameMode,
    dealerPlayerId,
    dealerSeat,
    roundCount,
    dealerRotationHistory,
    pveCircleSummary,
    startNewRoundAfterWin,
    selfWinSettlement,
    cumulativeScores,
    roundHistory,
    roundIndex,
    wallTiles,
    godViewWallMode,
    recommendDrawToken,
    currentRecommendAbortController,
    abortCurrentRecommend,
    beginRecommendFetch,
    clearRecommendAbortController,
    handLayoutPinned,
    moveJokerInHand,
    clearHandLayoutPin,
    applyAutoDeal,
    discardFromGodView,
    ensureGodViewDrawForSeat,
    seatHandSlots,
    isSeatReadyToDiscard,
    isSeatWaitingDraw,
    applyGodViewSelfDrawFast,
    setPendingSelfRecommend,
    setPendingAiRecommend,
    gameRoundId,
    gameLogSteps,
    applyHandSort,
    sortSeatClosedHand,
    sortAllClosedHands,
    manualSortHand,
    discardTile,
    selfDrawTile,
    discardSelfTile,
    applyLocalDiscard,
  }
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function cloneMelds(melds) {
  return (melds || []).map((m) => ({
    ...m,
    meld_type: m.meld_type,
    tiles: [...(m.tiles || [])],
  }))
}

function createInitialRoundState(initial = {}) {
  const seatWind = initial.seatWind || initial.seat_wind || 'E'
  const table = buildTableFromSelfWind(seatWind)
  return {
    seatWind: table.selfWind,
    isDealer: table.isDealer,
    dealerSeat: initial.dealerSeat || initial.dealer_seat || 'E',
    dealerTile: initial.dealerTile || initial.dealer_tile || '5m',
    roundWind: initial.roundWind || initial.round_wind || 'E',
    handTiles: [],
    melds: [],
    discards: [],
    opponents: table.opponents.map((o) => ({
      ...o,
      hand_tiles: [...(o.hand_tiles || [])],
    })),
  }
}

export { PHASE_LABEL, createInitialRoundState }
