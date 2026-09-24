import { computed, getCurrentScope, onScopeDispose, ref, watch } from 'vue'
import { getRecommendDecision } from '../services/api.js'
import { tileLabel } from '../constants/tiles.js'
import { windLabel } from '../utils/seatLayout.js'

const SEATS = ['E', 'S', 'W', 'N']
const AI_THINK_MS = 3000
const priority = (type) => ({ ming_gang: 2, pong: 2, chi: 1 })[type] || 0

/** One serial driver owns all AI actions. Waking during an awaited step is never lost. */
export function usePvEAutomation(session, options = {}) {
  const recommend = options.recommend || getRecommendDecision
  const delayMs = options.delayMs || (() => AI_THINK_MS)
  const sleep = options.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)))
  const busy = ref(false)
  const thinkingSeat = ref('')
  const status = ref('')
  const announcement = ref('')
  const error = ref('')
  let running = false, requested = false, stopped = false, failedKey = null
  let generation = 0, controller = new AbortController(), announcementTimer
  const s = session
  const active = () => !stopped && s.gameMode.value === 'PVE' && s.gameState.value === 'PLAYING'
  const player = (seat) => seat === s.roundState.seatWind
    ? { hand_tiles: s.roundState.handTiles, melds: s.roundState.melds, discards: s.roundState.discards }
    : s.roundState.opponents.find((o) => o.seat_wind === seat)
  const tile = () => s.lastStepResult.value?._response_tile || player(s.lastDiscardSeat.value)?.discards?.at(-1)
  const key = computed(() => JSON.stringify([
    s.gameMode.value, s.gameState.value, s.gameRoundId.value, s.currentTurnSeat.value,
    s.currentPhase.value, s.lastDiscardSeat.value, tile(), s.pendingHuQueue.value,
    s.lastStepResult.value?._table_responses, s.lastStepResult.value?.call_decision,
    SEATS.map((seat) => [player(seat)?.hand_tiles, player(seat)?.melds, player(seat)?.discards]),
    s.wallTiles.value.length,
  ]))
  const announce = (message) => {
    announcement.value = message
    clearTimeout(announcementTimer)
    announcementTimer = setTimeout(() => { announcement.value = '' }, 1800)
  }
  const valid = (epoch, snapshot) => active() && generation === epoch && key.value === snapshot && !s.loading.value

  // A new deal, leaving PvE, or ending a hand invalidates recommendations already in flight.
  const stopEpochWatch = watch(
    () => [s.gameMode.value, s.gameRoundId.value, s.gameState.value],
    () => {
      generation++
      controller.abort()
      controller = new AbortController()
      failedKey = null
      error.value = ''
      status.value = ''
      thinkingSeat.value = ''
      announcement.value = ''
    }, { flush: 'sync' },
  )

  async function step() {
    const self = s.roundState.seatWind
    const epoch = generation
    if (s.isResponseWindow.value) {
      const snapshot = key.value
      const provider = s.lastDiscardSeat.value
      const claimed = tile()
      const huSeat = s.currentHuSeat.value
      if (huSeat === self) return false
      if (huSeat) {
        busy.value = true
        thinkingSeat.value = huSeat
        status.value = `${windLabel(huSeat)}风 AI 正在思考和牌…`
        await sleep(delayMs())
        if (!valid(epoch, snapshot)) return false
        const robKong = !!s.lastStepResult.value?._pending_add_kong
        await s.declareOpponentWin({ seat: huSeat, winType: robKong ? 'rob_kong' : 'catch_win', winTile: claimed, discarderSeat: provider })
        announce(`${windLabel(huSeat)}风 AI ${robKong ? '抢杠胡' : '捉铳和牌'}`)
        return true
      }
      // Passed hu rights remain in the detection snapshot; never reopen them.
      const calls = (s.lastStepResult.value?._table_responses || []).flatMap((row) =>
        row.types.filter((type) => priority(type)).map((type) => ({ ...row, type })))
      const distance = (seat) => (SEATS.indexOf(seat) - SEATS.indexOf(provider) + 4) % 4
      calls.sort((a, b) => priority(b.type) - priority(a.type) || distance(a.seat) - distance(b.seat))
      const call = calls[0]
      if (call?.seat === self) return false
      if (!call) {
        if (s.lastStepResult.value?.need_self_action) return false
        busy.value = true
        await s.passAllCalls(claimed)
        return true
      }
      busy.value = true
      thinkingSeat.value = call.seat
      status.value = `${windLabel(call.seat)}风 AI 正在思考${{ chi: '吃牌', pong: '碰牌', ming_gang: '明杠' }[call.type]}…`
      await sleep(delayMs())
      if (!valid(epoch, snapshot)) return false
      const tiles = call.type === 'chi' ? call.chiCombos[0] : Array(call.type === 'pong' ? 3 : 4).fill(claimed)
      await s.executeOpponentMeld({ seat: call.seat, meld_type: call.type, tiles, provider_seat: provider, claimed_tile: claimed })
      announce(`${windLabel(call.seat)}风 AI ${{ chi: '吃牌', pong: '碰牌', ming_gang: '明杠' }[call.type]}`)
      return true
    }

    const seat = s.currentTurnSeat.value
    if (seat === self) return false
    busy.value = true
    thinkingSeat.value = seat
    status.value = `${windLabel(seat)}风 AI 正在思考切牌…`
    const thinkingTimer = sleep(delayMs())
    // This is idempotent: chi/pong already has a discard-ready hand, so no extra draw.
    await s.ensureGodViewDrawForSeat(seat)
    if (!active() || epoch !== generation || s.currentTurnSeat.value !== seat || s.isResponseWindow.value) return false
    const state = player(seat)
    if (!state || state.hand_tiles.length + 3 * state.melds.length !== 14) {
      throw new Error(`${windLabel(seat)}风 AI 手牌张数异常，无法评估切牌`)
    }
    const snapshot = key.value
    const payload = {
      hand_tiles: [...state.hand_tiles], melds: state.melds, discards: state.discards,
      dealer_tile: s.roundState.dealerTile, seat_wind: seat, round_wind: s.roundState.roundWind,
      is_dealer: seat === s.dealerSeat.value,
      opponents: SEATS.filter((other) => other !== seat).map((other) => ({
        seat_wind: other, is_dealer: other === s.dealerSeat.value,
        melds: player(other).melds, discards: player(other).discards,
      })),
    }
    // Think time overlaps the network request rather than adding latency before it.
    const [rec] = await Promise.all([recommend(payload, { signal: controller.signal }), thinkingTimer])
    if (!valid(epoch, snapshot)) return false
    if (rec.can_self_win || rec.self_win_info?.is_win) {
      await s.declareOpponentWin({ seat, winType: 'self_draw_win', winTile: s.latestDrawnBySeat.value[seat] || state.hand_tiles.at(-1) })
      announce(`${windLabel(seat)}风 AI 自摸和牌`)
    } else if (rec.best_action?.action_type === 'bu_gang') {
      await s.executeOpponentMeld({ seat, meld_type: 'bu_gang', tile: rec.best_action.tile })
      announce(`${windLabel(seat)}风 AI 补杠 ${tileLabel(rec.best_action.tile)}`)
    } else if (rec.best_action?.action_type === 'an_gang') {
      await s.executeOpponentMeld({ seat, meld_type: 'an_gang', tiles: [rec.best_action.tile, rec.best_action.tile, rec.best_action.tile, rec.best_action.tile] })
      announce(`${windLabel(seat)}风 AI 暗杠 ${tileLabel(rec.best_action.tile)}`)
    } else {
      const index = state.hand_tiles.indexOf(rec.best_tile)
      if (index < 0) throw new Error(`${windLabel(seat)}风 AI 未收到有效切牌推荐`)
      await s.discardFromGodView(seat, rec.best_tile, index)
      announce(`${windLabel(seat)}风 AI 打出 ${tileLabel(rec.best_tile)}`)
    }
    return true
  }

  async function drain() {
    if (running || stopped) return
    running = true
    try {
      do {
        requested = false
        if (!active() || s.loading.value || failedKey === key.value) break
        const epoch = generation
        try {
          const progressed = await step()
          if (progressed) requested = true
          else if (!requested) status.value = ''
        } catch (e) {
          if (epoch === generation && active() && e?.name !== 'AbortError') {
            error.value = e?.message || String(e)
            failedKey = key.value
            status.value = 'AI 暂停，请重试'
          }
        } finally { busy.value = false; thinkingSeat.value = '' }
      } while (requested && !stopped)
    } finally {
      running = false
    }
  }

  function wake() {
    requested = true
    if (!running) void drain()
  }
  // Critical: turn changes often happen while the discard step still holds loading.
  const stopStateWatch = watch([key, s.loading], wake, { flush: 'post', immediate: true })
  function retry() { failedKey = null; error.value = ''; wake() }
  function stop() {
    stopped = true
    thinkingSeat.value = ''
    generation++
    controller.abort()
    clearTimeout(announcementTimer)
    stopStateWatch()
    stopEpochWatch()
  }
  if (getCurrentScope()) onScopeDispose(stop)
  return { busy, thinkingSeat, status, announcement, error, retry, stop }
}
