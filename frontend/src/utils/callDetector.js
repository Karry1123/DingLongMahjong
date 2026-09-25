/**
 * 出牌后全桌副露/捉铳响应检测（对齐 rule_2.md §3 / action_generator）。
 * 有暗手追踪时按牌面判定（含白板替身捉铳）；无暗手时保守挂起。
 */

import { WIND_ORDER, tileLabel } from '../constants/tiles.js'
import { prevSeat } from './seatLayout.js'
import { canRon } from './winCheck.js'

export function buildPendingHuQueue(providerSeat, seats) {
  const provider = WIND_ORDER.indexOf(providerSeat)
  if (provider < 0) return []
  const distance = (seat) => (WIND_ORDER.indexOf(seat) - provider + 4) % 4
  return [...new Set(seats)].filter((seat) => WIND_ORDER.includes(seat) && seat !== providerSeat)
    .sort((a, b) => distance(a) - distance(b))
}

/**
 * @typedef {{
 *   seat: string,
 *   types: string[],
 *   chiCombos?: string[][],
 * }} SeatCallOption
 */

/**
 * @param {object} opts
 * @param {string} opts.providerSeat 出牌方
 * @param {string} opts.discardedTile 打出张
 * @param {string} opts.dealerTile 财神
 * @param {string} opts.selfSeat 自家门风
 * @param {(seat: string) => { hand: string[], melds: unknown[] }} opts.getSeat
 * @param {boolean} [opts.godView] 上帝视角（有暗手）
 * @returns {{
 *   hasResponse: boolean,
 *   hasCatchWin: boolean,
 *   catchWinSeats: string[],
 *   options: SeatCallOption[],
 *   untracked: boolean,
 * }}
 */
export function detectTableResponses({
  providerSeat,
  discardedTile,
  dealerTile,
  selfSeat,
  getSeat,
  godView = false,
}) {
  const tile = discardedTile
  if (!providerSeat || !tile || tile === dealerTile) {
    return {
      hasResponse: false,
      hasCatchWin: false,
      catchWinSeats: [],
      options: [],
      untracked: false,
    }
  }

  const options = []
  const catchWinSeats = []
  let untracked = false
  void selfSeat
  void godView

  for (const seat of WIND_ORDER) {
    if (seat === providerSeat) continue
    const { hand, melds } = getSeat(seat) || { hand: [], melds: [] }
    const handList = Array.isArray(hand) ? hand : []
    const meldList = Array.isArray(melds) ? melds : []

    if (handList.length === 0) {
      untracked = true
      continue
    }

    const types = []
    /** @type {string[][]} */
    const chiCombos = []
    const cnt = handList.filter((t) => t === tile).length

    if (cnt >= 2) types.push('pong')
    if (cnt >= 3 && tile !== dealerTile) types.push('ming_gang')

    if (prevSeat(seat) === providerSeat) {
      for (const combo of chiCombosFor(handList, tile, dealerTile)) {
        chiCombos.push(combo)
      }
      if (chiCombos.length) types.push('chi')
    }

    // 捉铳：白板替身已在 canRon → preprocessHand 中处理
    if (canRon(handList, meldList, tile, dealerTile)) {
      types.push('catch_win')
      catchWinSeats.push(seat)
    }

    if (types.length) {
      options.push({
        seat,
        types,
        chiCombos: chiCombos.length ? chiCombos : undefined,
      })
    }
  }

  return {
    hasResponse: options.length > 0,
    hasCatchWin: catchWinSeats.length > 0,
    catchWinSeats: buildPendingHuQueue(providerSeat, catchWinSeats),
    options,
    untracked,
  }
}

/**
 * 是否应进入 WAIT_RESPONSE（禁止下家立刻摸牌）。
 * 任意捉铳 / 吃碰杠 → 必须挂起。
 */
export function shouldEnterResponseWindow(detection, { godView }) {
  if (!detection) return false
  if (detection.hasCatchWin) return true
  if (detection.hasResponse) return true
  if (!godView && detection.untracked) return true
  if (godView && detection.untracked) return true
  return false
}

/**
 * @param {string[]} hand
 * @param {string} disc
 * @param {string} dealer
 * @returns {string[][]}
 */
export function chiCombosFor(hand, disc, dealer) {
  const face = (tile) => tile === 'P' && dealer !== 'P' ? dealer : tile
  const target = face(disc)
  if (!target || !/^[1-9][mps]$/.test(target)) return []
  const combos = []
  const digit = Number(target[0])
  const suit = target[1]
  for (let start = Math.max(1, digit - 2); start <= Math.min(7, digit); start++) {
    const available = hand.filter((tile) => tile !== dealer)
    const combo = []
    for (let n = start; n < start + 3; n++) {
      const needed = String(n) + suit
      if (needed === target) {
        combo.push(disc)
      } else {
        const index = available.findIndex((tile) => face(tile) === needed)
        if (index < 0) break
        combo.push(available.splice(index, 1)[0])
      }
    }
    if (combo.length === 3) combos.push(combo)
  }
  return combos
}

/** 展示替身身份；存储和扣牌仍使用物理编码。 */
export function substituteTileLabel(tile, dealer) {
  return tile === 'P' && dealer && dealer !== 'P'
    ? `${tileLabel(tile)}(替${tileLabel(dealer)})`
    : tileLabel(tile)
}
