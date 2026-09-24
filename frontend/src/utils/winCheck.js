/**
 * 白板替身预处理 + 完整和牌判定（捉铳用）。
 * 对齐 backend mapper.preprocess_hand / evaluator._can_win。
 */

import { ALL_TILES } from '../constants/tiles.js'

const JOKER = 'JOKER'

/**
 * 情况 A：dealer≠P → dealer→JOKER，P→dealer（白板替身）。
 * 情况 B：dealer=P → P→JOKER。
 * @param {string[]} handTiles
 * @param {string} dealerTile
 * @returns {string[]}
 */
export function preprocessHand(handTiles, dealerTile) {
  const result = []
  if (dealerTile === 'P') {
    for (const tile of handTiles || []) {
      result.push(tile === 'P' ? JOKER : tile)
    }
  } else {
    for (const tile of handTiles || []) {
      if (tile === dealerTile) result.push(JOKER)
      else if (tile === 'P') result.push(dealerTile)
      else result.push(tile)
    }
  }
  return result
}

/** @deprecated 别名，文档/调用对齐 rule「normalize_hand_for_eval」 */
export function normalizeHandForEval(handTiles, dealerTile) {
  return preprocessHand(handTiles, dealerTile)
}

/**
 * 听牌暗手 + 铳张是否可和（needed_melds = 4 - melds.length）。
 * @param {string[]} handTiles 未含铳张
 * @param {unknown[]} melds
 * @param {string} discardedTile
 * @param {string} dealerTile
 */
export function canRon(
  handTiles,
  melds,
  discardedTile,
  dealerTile,
) {
  const meldN = Array.isArray(melds) ? melds.length : 0
  const needed = 4 - meldN
  if (needed < 0 || needed > 4) return false
  const expect = needed * 3 + 1
  if (!Array.isArray(handTiles) || handTiles.length !== expect) return false
  if (!discardedTile) return false
  const logical = preprocessHand([...handTiles, discardedTile], dealerTile)
  return canCompleteWin(logical, needed)
}

/**
 * 逻辑手牌（可含 JOKER）是否已和：needed 面子 + 1 雀头。
 * @param {string[]} logicalTiles
 * @param {number} neededMelds
 */
export function canCompleteWin(logicalTiles, neededMelds) {
  const counts = Object.create(null)
  for (const t of ALL_TILES) counts[t] = 0
  let jokers = 0
  for (const t of logicalTiles) {
    if (t === JOKER) jokers += 1
    else counts[t] = (counts[t] || 0) + 1
  }
  const total = Object.values(counts).reduce((a, b) => a + b, 0) + jokers
  if (total !== neededMelds * 3 + 2) return false
  return canWin(counts, jokers, neededMelds)
}

function canWin(counts, jokers, neededMelds) {
  for (const tile of ALL_TILES) {
    if (counts[tile] >= 2) {
      counts[tile] -= 2
      const ok = canFormNMelds(counts, jokers, neededMelds)
      counts[tile] += 2
      if (ok) return true
    } else if (counts[tile] === 1 && jokers >= 1) {
      counts[tile] -= 1
      const ok = canFormNMelds(counts, jokers - 1, neededMelds)
      counts[tile] += 1
      if (ok) return true
    }
  }
  if (jokers >= 2 && canFormNMelds(counts, jokers - 2, neededMelds)) {
    return true
  }
  return false
}

function canFormNMelds(counts, jokers, meldsLeft) {
  if (meldsLeft < 0) return false
  const tile = firstNonzero(counts)
  if (tile == null) return jokers === meldsLeft * 3
  if (meldsLeft === 0) return false

  const have = counts[tile]

  if (have + jokers >= 3) {
    const use = Math.min(have, 3)
    const need = 3 - use
    counts[tile] -= use
    if (canFormNMelds(counts, jokers - need, meldsLeft - 1)) {
      counts[tile] += use
      return true
    }
    counts[tile] += use
  }

  if (isSuited(tile) && trySequences(counts, jokers, tile, meldsLeft)) {
    return true
  }
  return false
}

function trySequences(counts, jokers, tile, meldsLeft) {
  const num = Number(tile[0])
  const suit = tile[1]
  for (const start of [num, num - 1, num - 2]) {
    if (start < 1 || start > 7) continue
    const seq = [`${start}${suit}`, `${start + 1}${suit}`, `${start + 2}${suit}`]
    if (!seq.includes(tile)) continue
    let need = 0
    const taken = []
    for (const t of seq) {
      if (counts[t] > 0) {
        counts[t] -= 1
        taken.push(t)
      } else need += 1
    }
    if (need <= jokers && canFormNMelds(counts, jokers - need, meldsLeft - 1)) {
      for (const t of taken) counts[t] += 1
      return true
    }
    for (const t of taken) counts[t] += 1
  }
  return false
}

function firstNonzero(counts) {
  for (const t of ALL_TILES) {
    if (counts[t] > 0) return t
  }
  return null
}

function isSuited(tile) {
  return typeof tile === 'string' && tile.length === 2 && 'mps'.includes(tile[1])
}
