/**
 * 台州麻将座次 / 庄闲布局（rule.md §1）
 *
 * - 逆时针：东(E) → 南(S) → 西(W) → 北(N)
 * - **当盘庄家永远是东风位**；其余三方为闲家
 * - 庄家起手 14 张并拥有第一手出牌权；闲家起手 13 张
 */

import { SEAT_WINDS, WIND_ORDER, relativeOpponents } from '../constants/tiles.js'

/** 庄家门风（锁定） */
export const DEALER_SEAT = 'E'

/**
 * @param {string} seat
 * @returns {string} 中文门风名
 */
export function windLabel(seat) {
  return SEAT_WINDS.find((w) => w.code === seat)?.label || seat
}

/**
 * 下一家（逆时针）
 * @param {string} seat
 */
export function nextSeat(seat) {
  const i = WIND_ORDER.indexOf(seat)
  const idx = i >= 0 ? i : 0
  return WIND_ORDER[(idx + 1) % 4]
}

/**
 * 上一家（逆时针上一手 = 吃牌合法 provider）
 * @param {string} seat
 */
export function prevSeat(seat) {
  const i = WIND_ORDER.indexOf(seat)
  const idx = i >= 0 ? i : 0
  return WIND_ORDER[(idx + 3) % 4]
}

/**
 * 根据「我的门风」推导全桌座次、庄闲与开局出牌权。
 *
 * @param {string} selfWind 我的门风 E/S/W/N
 * @returns {{
 *   selfWind: string,
 *   isDealer: boolean,
 *   dealerSeat: 'E',
 *   firstTurnSeat: 'E',
 *   openingHandSize: number,
 *   opponents: Array<{
 *     role: string,
 *     seat_wind: string,
 *     is_dealer: boolean,
 *     melds: [],
 *     discards: [],
 *   }>,
 *   seats: Array<{
 *     seat_wind: string,
 *     label: string,
 *     role: string,
 *     is_dealer: boolean,
 *     is_self: boolean,
 *   }>,
 *   summary: string,
 * }}
 *
 * @example
 * // 我是南风：上家东(庄)、对家北、下家西；起手 13；出牌权在东
 * buildTableFromSelfWind('S')
 */
export function buildTableFromSelfWind(selfWind) {
  const self = WIND_ORDER.includes(selfWind) ? selfWind : 'E'
  const isDealer = self === DEALER_SEAT

  const opponents = relativeOpponents(self).map(({ role, seat_wind }) => ({
    role,
    seat_wind,
    is_dealer: seat_wind === DEALER_SEAT,
    melds: [],
    discards: [],
    /** 上帝视角暗手（仅本地；严禁进入 /api/recommend） */
    hand_tiles: [],
  }))

  const roleBySeat = Object.create(null)
  roleBySeat[self] = '自家'
  for (const o of opponents) {
    roleBySeat[o.seat_wind] = o.role
  }

  const seats = WIND_ORDER.map((seat_wind) => ({
    seat_wind,
    label: windLabel(seat_wind),
    role: roleBySeat[seat_wind] || '',
    is_dealer: seat_wind === DEALER_SEAT,
    is_self: seat_wind === self,
  }))

  const openingHandSize = isDealer ? 14 : 13
  const firstTurnSeat = DEALER_SEAT

  let summary
  if (isDealer) {
    summary = '你是东风庄：起手 14 张，拥有第一手出牌权'
  } else {
    const kamicha = opponents.find((o) => o.role === '上家')
    summary = `你是${windLabel(self)}风闲家：起手 13 张；庄家为东风（${kamicha?.role || '上家'}），开局出牌权归东`
  }

  return {
    selfWind: self,
    isDealer,
    dealerSeat: DEALER_SEAT,
    firstTurnSeat,
    openingHandSize,
    opponents,
    seats,
    summary,
  }
}

/**
 * 将已有对手公开数据合并进新座次（换门风时保留同座位的河/副露）。
 * 庄标记一律按东风位重算。
 *
 * @param {string} selfWind
 * @param {Array<{ seat_wind: string, melds?: any[], discards?: any[] }>} [prevOpponents]
 */
export function rebuildOpponentsPreservingOpen(selfWind, prevOpponents = []) {
  const table = buildTableFromSelfWind(selfWind)
  const prevBySeat = Object.fromEntries(
    (prevOpponents || []).map((o) => [o.seat_wind, o]),
  )
  return table.opponents.map((o) => {
    const prev = prevBySeat[o.seat_wind]
    return {
      ...o,
      melds: prev?.melds ? prev.melds.map((m) => ({
        meld_type: m.meld_type,
        tiles: [...(m.tiles || [])],
      })) : [],
      discards: prev?.discards ? [...prev.discards] : [],
    }
  })
}
