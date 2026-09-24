/** 台州麻将 34 种牌面（与 backend rule.md §1 / constants 对齐） */

export const MANS = Array.from({ length: 9 }, (_, i) => `${i + 1}m`)
export const PINS = Array.from({ length: 9 }, (_, i) => `${i + 1}p`)
export const SOUS = Array.from({ length: 9 }, (_, i) => `${i + 1}s`)
export const HONORS = ['E', 'S', 'W', 'N', 'C', 'F', 'P']

/** 门风 / 自风四选一 */
export const SEAT_WINDS = [
  { code: 'E', label: '东' },
  { code: 'S', label: '南' },
  { code: 'W', label: '西' },
  { code: 'N', label: '北' },
]

/** 逆时针座次顺序（东→南→西→北） */
export const WIND_ORDER = ['E', 'S', 'W', 'N']

/**
 * 相对自家的三家座次：上家 / 对家 / 下家
 * @param {string} selfWind
 * @returns {{ role: string, seat_wind: string }[]}
 */
export function relativeOpponents(selfWind) {
  const i = WIND_ORDER.indexOf(selfWind)
  const idx = i >= 0 ? i : 0
  return [
    { role: '上家', seat_wind: WIND_ORDER[(idx + 3) % 4] },
    { role: '对家', seat_wind: WIND_ORDER[(idx + 2) % 4] },
    { role: '下家', seat_wind: WIND_ORDER[(idx + 1) % 4] },
  ]
}

export const ALL_TILES = [...MANS, ...PINS, ...SOUS, ...HONORS]

export const TILE_GROUPS = [
  { key: 'm', label: '万', tiles: MANS },
  { key: 'p', label: '筒', tiles: PINS },
  { key: 's', label: '条', tiles: SOUS },
  { key: 'z', label: '字', tiles: HONORS },
]

const HONOR_LABELS = {
  E: '东',
  S: '南',
  W: '西',
  N: '北',
  C: '中',
  F: '发',
  P: '白',
}

const NUM_CN = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九']

/** 将牌面编码转为中文短标签 */
export function tileLabel(code) {
  if (HONOR_LABELS[code]) return HONOR_LABELS[code]
  const n = Number(code[0])
  const suit = code[1]
  if (suit === 'm') return `${NUM_CN[n]}万`
  if (suit === 'p') return `${NUM_CN[n]}筒`
  if (suit === 's') return `${NUM_CN[n]}条`
  return code
}

/** 每种牌最多 4 张（全副各 4 张） */
export const MAX_PER_TILE = 4

/** 决策请求手牌张数（摸牌后待切） */
export const HAND_SIZE = 14

/** 牌面「图标」配色（按花色区分） */
export function tileSuitClass(code) {
  if (!code) return ''
  if (code.endsWith('m')) {
    return 'border-rose-400/50 bg-gradient-to-b from-rose-50 to-rose-100 text-rose-800'
  }
  if (code.endsWith('p')) {
    return 'border-sky-400/50 bg-gradient-to-b from-sky-50 to-sky-100 text-sky-900'
  }
  if (code.endsWith('s')) {
    return 'border-emerald-500/50 bg-gradient-to-b from-emerald-50 to-emerald-100 text-emerald-900'
  }
  // 字牌
  if (code === 'C') {
    return 'border-red-500/60 bg-gradient-to-b from-red-50 to-red-100 text-red-700'
  }
  if (code === 'F') {
    return 'border-green-600/50 bg-gradient-to-b from-green-50 to-green-100 text-green-800'
  }
  return 'border-slate-400/50 bg-gradient-to-b from-slate-50 to-slate-200 text-slate-800'
}
