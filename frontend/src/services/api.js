/**
 * 后端 API 客户端。
 * - POST /api/recommend      切牌 EV 推荐
 * - POST /api/calculate-hu   算胡明细
 * - POST /api/game/step      牌局时序步进
 * - POST /api/settle         终局筹码结算
 */
import { ref } from 'vue'

// 开发环境走 Vite /api 代理；生产环境由 Vercel 构建变量指定 Render 域名。
const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '')
const WAKE_MESSAGE = '云端计算引擎唤醒中，首次加载约需数十秒，请稍候...'
const slowRequests = new Set()
let requestSequence = 0
export const cloudWakeMessage = ref('')

/** 等待 Render 冷启动时给出提示；失败或超时后释放加载状态。 */
export async function fetchWithWakeNotice(url, options = {}, timings = {}) {
  const wakeDelayMs = timings.wakeDelayMs ?? 2000
  const timeoutMs = timings.timeoutMs ?? 90000
  const requestId = ++requestSequence
  const controller = new AbortController()
  const callerSignal = options.signal
  const abortFromCaller = () => controller.abort(callerSignal.reason)
  if (callerSignal?.aborted) abortFromCaller()
  else callerSignal?.addEventListener('abort', abortFromCaller, { once: true })

  let timedOut = false
  const wakeTimer = setTimeout(() => {
    slowRequests.add(requestId)
    cloudWakeMessage.value = WAKE_MESSAGE
  }, wakeDelayMs)
  const timeoutTimer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } catch (error) {
    if (timedOut) throw new Error('云端计算引擎响应超时，请稍后重试')
    if (!isAbortError(error) && error instanceof TypeError) {
      throw new Error('云端计算引擎暂时无法连接，请检查网络后重试')
    }
    throw error
  } finally {
    clearTimeout(wakeTimer)
    clearTimeout(timeoutTimer)
    callerSignal?.removeEventListener('abort', abortFromCaller)
    slowRequests.delete(requestId)
    if (slowRequests.size === 0) cloudWakeMessage.value = ''
  }
}

/**
 * 是否为请求取消（AbortController / fetch AbortError）。
 * @param {unknown} err
 * @returns {boolean}
 */
export function isAbortError(err) {
  if (!err) return false
  if (err.name === 'AbortError') return true
  if (err.code === 20 /* DOMException.ABORT_ERR */) return true
  const msg = String(err.message || err)
  return /abort|canceled|cancelled/i.test(msg)
}

/**
 * 请求切牌推荐决策。
 *
 * @param {{
 *   hand_tiles: string[],
 *   melds?: Array<{ meld_type: string, tiles: string[] }>,
 *   discards?: string[],
 *   dealer_tile: string,
 *   is_dealer: boolean,
 *   seat_wind: 'E'|'S'|'W'|'N',
 *   round_wind?: 'E'|'S'|'W'|'N',
 *   opponents?: Array<object>,
 *   discarded_tiles?: string[],
 * }} payload
 * @param {{ signal?: AbortSignal }} [options] 传入 AbortSignal 可随时取消请求
 * @returns {Promise<{ best_tile: string, candidates: Array<{
 *   tile: string,
 *   ev_score: number,
 *   attack_ev: number,
 *   defense_loss: number,
 *   deal_in_risks: Record<string, number>,
 *   defense_details?: Record<string, object>,
 *   is_safe_all: boolean,
 *   effective_count: number,
 *   is_hard_hu: boolean,
 *   est_base_points: number,
 *   est_final_points: number,
 * }> }>}
 */
export async function getRecommendDecision(payload, options = {}) {
  const body = {
    hand_tiles: payload.hand_tiles,
    melds: payload.melds ?? [],
    discards: payload.discards ?? [],
    dealer_tile: payload.dealer_tile,
    is_dealer: payload.is_dealer,
    seat_wind: payload.seat_wind,
    round_wind: payload.round_wind ?? 'E',
    opponents: payload.opponents ?? [],
    discarded_tiles: payload.discarded_tiles ?? [],
  }

  const res = await fetchWithWakeNotice(`${API_BASE}/api/recommend`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body),
    signal: options.signal,
  })

  if (!res.ok) {
    throw new Error(`推荐接口失败：${await _readError(res)}`)
  }

  return res.json()
}

/**
 * 请求算胡明细（完整 details）。
 *
 * @param {{
 *   hand_tiles: string[],
 *   melds?: Array<{ meld_type: string, tiles: string[] }>,
 *   win_tile: string,
 *   is_zimo: boolean,
 *   seat_wind: 'E'|'S'|'W'|'N',
 *   dealer_tile: string,
 *   restored_jokers?: number,
 *   base_hu?: number,
 *   is_dealer?: boolean,
 * }} payload
 * @returns {Promise<{
 *   tile_hu: number,
 *   base_hu: number,
 *   fan: number,
 *   final_hu: number,
 *   is_hard_hu: boolean,
 *   details: object,
 *   others_hu?: number,
 *   settlement_factor?: number,
 *   settlement_income?: number,
 * }>}
 */
export async function calculateHuPoints(payload, options = {}) {
  const body = {
    hand_tiles: payload.hand_tiles,
    melds: payload.melds ?? [],
    win_tile: payload.win_tile,
    is_zimo: payload.is_zimo,
    seat_wind: payload.seat_wind,
    dealer_tile: payload.dealer_tile,
    restored_jokers: payload.restored_jokers ?? 0,
    base_hu: payload.base_hu ?? 10,
    is_dealer: payload.is_dealer ?? false,
  }

  const res = await fetchWithWakeNotice(`${API_BASE}/api/calculate-hu`, {
    signal: options.signal,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    throw new Error(`算胡接口失败：${await _readError(res)}`)
  }

  return res.json()
}

/**
 * 牌局时序步进。
 *
 * @param {object} state  当前局面（HandRequest 字段）
 * @param {{
 *   actor_seat: 'E'|'S'|'W'|'N',
 *   event_type: 'DRAW'|'DISCARD'|'MELD'|'PASS',
 *   tile?: string|null,
 *   meld?: { meld_type: string, tiles: string[] }|null,
 * }} event
 * @returns {Promise<{
 *   next_turn_seat: string,
 *   need_self_action: boolean,
 *   action_phase: 'DISCARD'|'CALL'|'WAIT',
 *   recommend_discard?: object|null,
 *   call_decision?: object|null,
 *   updated_state?: object|null,
 * }>}
 */
export async function postGameStep(state, event, options = {}) {
  const body = {
    hand_tiles: state.hand_tiles,
    melds: state.melds ?? [],
    discards: state.discards ?? [],
    dealer_tile: state.dealer_tile,
    is_dealer: state.is_dealer,
    seat_wind: state.seat_wind,
    round_wind: state.round_wind ?? 'E',
    opponents: state.opponents ?? [],
    discarded_tiles: state.discarded_tiles ?? [],
    event,
  }

  const res = await fetchWithWakeNotice(`${API_BASE}/api/game/step`, {
    signal: options.signal,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    throw new Error(`步进接口失败：${await _readError(res)}`)
  }

  return res.json()
}

/**
 * 自动发牌：洗牌 + 翻得 + 庄14/闲13。
 * @param {{ dealer_seat: string }} payload
 */
export async function postAutoDeal(payload, options = {}) {
  const res = await fetchWithWakeNotice(`${API_BASE}/api/game/auto-deal`, {
    signal: options.signal,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ dealer_seat: payload.dealer_seat }),
  })
  if (!res.ok) {
    throw new Error(`自动发牌失败：${await _readError(res)}`)
  }
  return res.json()
}

/**
 * 终局筹码结算（§6 无包牌）。
 * @param {object} payload
 */
export async function postSettle(payload, options = {}) {
  const res = await fetchWithWakeNotice(`${API_BASE}/api/settle`, {
    signal: options.signal,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    throw new Error(`结算接口失败：${await _readError(res)}`)
  }
  return res.json()
}

/**
 * 对局终局轨迹落盘。
 * @param {{
 *   round_id: string,
 *   config: { dealer_seat: string, dealer_tile: string, seat_wind: string },
 *   steps: Array<object>,
 *   final_result?: object|null,
 * }} payload
 */
export async function postGameRecord(payload, options = {}) {
  const res = await fetchWithWakeNotice(`${API_BASE}/api/game/record`, {
    signal: options.signal,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    throw new Error(`轨迹落盘失败：${await _readError(res)}`)
  }
  return res.json()
}

async function _readError(res) {
  let detail = `HTTP ${res.status}`
  try {
    const errBody = await res.json()
    detail =
      typeof errBody.detail === 'string'
        ? errBody.detail
        : JSON.stringify(errBody.detail ?? errBody)
  } catch {
    /* 非 JSON 错误体则沿用 status */
  }
  return detail
}
