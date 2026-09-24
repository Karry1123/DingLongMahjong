/**
 * 台州麻将手牌理牌排序。
 *
 * 规则对齐 rule.md §2：
 * - 「得」(dealerTile) 为百搭，排在最左
 * - 翻出非白板时，白板 (P) 按 dealerTile 的花色点数插入对应位置
 * - 序数：万 → 筒 → 条；字牌：东南西北中发白
 * - latestDrawnTile：待切状态下单独挂在最右侧
 */

import { HONORS } from '../constants/tiles.js'

/** 字牌稳定序 */
const HONOR_RANK = Object.fromEntries(HONORS.map((h, i) => [h, i]))

/**
 * 判断物理牌是否为本局「得」（万能百搭）
 * @param {string} tile
 * @param {string} dealerTile
 */
export function isJokerPhysical(tile, dealerTile) {
  return !!tile && !!dealerTile && tile === dealerTile
}

/**
 * 白板是否作为 dealer 的替身（情况 A）
 * @param {string} tile
 * @param {string} dealerTile
 */
export function isWhiteboardProxy(tile, dealerTile) {
  return tile === 'P' && !!dealerTile && dealerTile !== 'P'
}

/**
 * 排序用身份：百搭 / 替身映射后的可比键
 * @returns {{ joker: boolean, suit: number, rank: number, proxy: boolean }}
 */
export function tileSortKey(tile, dealerTile) {
  if (isJokerPhysical(tile, dealerTile)) {
    return { joker: true, suit: -1, rank: -1, proxy: false }
  }

  // 情况 A：白板按原物理牌（dealer）花色点数插入
  let identity = tile
  let proxy = false
  if (isWhiteboardProxy(tile, dealerTile)) {
    identity = dealerTile
    proxy = true
  }

  if (identity.length === 2 && 'mps'.includes(identity[1])) {
    const suitMap = { m: 0, p: 1, s: 2 }
    return {
      joker: false,
      suit: suitMap[identity[1]],
      rank: Number(identity[0]),
      proxy,
    }
  }

  // 字牌（含情况 B 下非百搭的其它字；P 为得时已在 joker 分支）
  const hr = HONOR_RANK[identity]
  if (hr != null) {
    return { joker: false, suit: 3, rank: hr, proxy }
  }

  // 未知编码垫底
  return { joker: false, suit: 9, rank: 99, proxy: false }
}

/**
 * @param {string} a
 * @param {string} b
 * @param {string} dealerTile
 */
export function compareTiles(a, b, dealerTile) {
  const ka = tileSortKey(a, dealerTile)
  const kb = tileSortKey(b, dealerTile)
  if (ka.joker !== kb.joker) return ka.joker ? -1 : 1
  if (ka.suit !== kb.suit) return ka.suit - kb.suit
  if (ka.rank !== kb.rank) return ka.rank - kb.rank
  // 同键时：实体 dealer 张略优于白板替身（视觉上替身仍插在同点数处）
  if (ka.proxy !== kb.proxy) return ka.proxy ? 1 : -1
  return 0
}

/**
 * 理牌排序。
 *
 * @param {string[]} tiles 当前暗手物理编码
 * @param {string} dealerTile 本局财神
 * @param {string} [latestDrawnTile] 刚摸入、需挂在最右侧的那张（待切时）
 * @returns {string[]} 新数组，不修改入参；张数与入参严格相等
 */
export function sortHandTiles(tiles, dealerTile, latestDrawnTile) {
  const list = Array.isArray(tiles) ? [...tiles] : []
  const n0 = list.length
  if (!n0) return list

  let drawn = null
  if (latestDrawnTile) {
    // 仅重排位置：把「摸进张」挪到末尾，绝不丢弃
    const idx = list.lastIndexOf(latestDrawnTile)
    if (idx >= 0) {
      drawn = list.splice(idx, 1)[0]
    }
  }

  list.sort((a, b) => compareTiles(a, b, dealerTile || ''))

  if (drawn != null) {
    list.push(drawn)
  }

  if (list.length !== n0) {
    // 防御：排序不得改变张数
    console.error(
      '[sortHandTiles] 张数被改变',
      n0,
      '→',
      list.length,
      tiles,
      latestDrawnTile,
    )
  }
  return list
}

/**
 * 在列表中移动一张牌（用于百搭自由插嵌）。
 * toIndex 语义：插入到「原数组该下标之前」；若 from < to，删除后按下标校正。
 * @param {string[]} tiles
 * @param {number} fromIndex
 * @param {number} toIndex
 * @returns {string[]} 新数组
 */
export function moveTileInList(tiles, fromIndex, toIndex) {
  const list = Array.isArray(tiles) ? [...tiles] : []
  const n = list.length
  if (n === 0) return list
  if (
    typeof fromIndex !== 'number' ||
    typeof toIndex !== 'number' ||
    fromIndex < 0 ||
    fromIndex >= n
  ) {
    return list
  }
  let dest = Math.max(0, Math.min(toIndex, n))
  if (fromIndex === dest || fromIndex === dest - 1) {
    // 同位置或已在目标左侧紧邻 → 无变化
    if (fromIndex === dest) return list
  }
  const [item] = list.splice(fromIndex, 1)
  if (fromIndex < dest) dest -= 1
  dest = Math.max(0, Math.min(dest, list.length))
  list.splice(dest, 0, item)
  return list
}

/**
 * 将指定张挪到数组末尾（摸入挂右），不改变其余相对序。
 * @param {string[]} tiles
 * @param {string} drawn
 */
export function ensureTileAtEnd(tiles, drawn) {
  if (!drawn || !Array.isArray(tiles) || !tiles.length) {
    return Array.isArray(tiles) ? [...tiles] : []
  }
  const list = [...tiles]
  const i = list.lastIndexOf(drawn)
  if (i < 0 || i === list.length - 1) return list
  list.splice(i, 1)
  list.push(drawn)
  return list
}

/**
 * 为 TransitionGroup 生成稳定 uid，并保留原数组下标（供按索引切牌）。
 * @param {string[]} tiles
 * @returns {{ code: string, uid: string, index: number }[]}
 */
export function handTilesWithKeys(tiles) {
  /** @type {Record<string, number>} */
  const seen = Object.create(null)
  return (tiles || []).map((code, index) => {
    seen[code] = (seen[code] || 0) + 1
    return { code, uid: `${code}#${seen[code]}`, index }
  })
}
