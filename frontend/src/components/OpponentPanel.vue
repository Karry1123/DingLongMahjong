<script setup>
/**
 * 三方对手公开信息：弃牌河 + 副露。
 * - 串行出牌：仅 currentTurnSeat 对手可打出
 * - 代录副露：出牌后可为合法对手录入吃/碰/明杠；行动权对手可录暗杠
 */
import { computed, ref, watch } from 'vue'
import {
  MAX_PER_TILE,
  SEAT_WINDS,
  TILE_GROUPS,
  relativeOpponents,
  tileLabel,
  tileSuitClass,
} from '../constants/tiles.js'
import { prevSeat } from '../utils/seatLayout.js'
import { chiCombosFor, substituteTileLabel } from '../utils/callDetector.js'

/**
 * @typedef {{ meld_type: string, tiles: string[] }} Meld
 * @typedef {{
 *   seat_wind: string,
 *   is_dealer: boolean,
 *   melds: Meld[],
 *   discards: string[],
 *   role?: string,
 * }} Opponent
 */

const opponents = defineModel({
  type: Array,
  default: () => [],
})

/** 自家是否庄家（与对手庄标记互斥） */
const selfIsDealer = defineModel('selfIsDealer', {
  type: Boolean,
  default: false,
})

const props = defineProps({
  /** 自家门风 */
  seatWind: {
    type: String,
    default: 'E',
  },
  /**
   * 当前行动权门风（E/S/W/N）
   */
  currentTurnSeat: {
    type: String,
    default: 'E',
  },
  /**
   * 牌池已占用（不含 opponents；本组件内部再扣三方）
   * @type {string[]}
   */
  baseOccupied: {
    type: Array,
    default: () => [],
  },
  /**
   * 已确认开局、进入严格串行时序
   */
  tableLocked: {
    type: Boolean,
    default: false,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  /**
   * 响应吃碰阶段：禁止对手出牌，但仍可代录副露
   */
  callPending: {
    type: Boolean,
    default: false,
  },
  /** 出牌后副露响应窗（显示全员过牌） */
  responseWindow: {
    type: Boolean,
    default: false,
  },
  /** 可捉铳的座位列表 */
  catchWinSeats: {
    type: Array,
    default: () => [],
  },
  /** 最近出牌方（副露窗口） */
  lastDiscardSeat: {
    type: String,
    default: '',
  },
  /** 最近打出张 */
  lastDiscardedTile: {
    type: String,
    default: '',
  },
  dealerTile: {
    type: String,
    default: '',
  },
  /** 最近一步提示（暗杠补牌文案等） */
  lastStepNote: {
    type: String,
    default: '',
  },
})

const emit = defineEmits({
  /**
   * @param {{ seat_wind: string, tile: string }} payload
   */
  'opponent-discard': (payload) =>
    payload &&
    typeof payload.seat_wind === 'string' &&
    typeof payload.tile === 'string',
  /**
   * @param {{
   *   seat: string,
   *   meld_type: string,
   *   tiles: string[],
   *   provider_seat?: string,
   *   claimed_tile?: string,
   * }} payload
   */
  'opponent-meld': (payload) =>
    payload &&
    typeof payload.seat === 'string' &&
    typeof payload.meld_type === 'string',
  /**
   * @param {{
   *   seat: string,
   *   winType: 'self_draw_win'|'catch_win',
   *   winTile?: string,
   *   discarderSeat?: string,
   * }} payload
   */
  'opponent-win': (payload) =>
    payload &&
    typeof payload.seat === 'string' &&
    typeof payload.winType === 'string',
  'pass-all-calls': () => true,
})

const MELD_MODES = [
  { type: 'pong', label: '碰', need: 3 },
  { type: 'ming_gang', label: '明杠', need: 4 },
  { type: 'chi', label: '吃', need: 3 },
]

const MELD_TYPE_LABEL = {
  chi: '吃',
  pong: '碰',
  ming_gang: '明杠',
  an_gang: '暗杠',
}

const windLabel = (code) =>
  SEAT_WINDS.find((w) => w.code === code)?.label || code

/** 副露录入展开：仅开局前允许 */
const activeMeld = ref(null)

function emptyOpponent(role, seat_wind) {
  return {
    role,
    seat_wind,
    is_dealer: seat_wind === 'E',
    melds: [],
    discards: [],
  }
}

function syncSeatsFromSelfWind() {
  const seats = relativeOpponents(props.seatWind)
  const byRole = Object.create(null)
  for (const o of opponents.value) {
    if (o.role) byRole[o.role] = o
  }
  opponents.value = seats.map(({ role, seat_wind }) => {
    const prev = byRole[role]
    if (prev) {
      return {
        ...prev,
        role,
        seat_wind,
        is_dealer: seat_wind === 'E',
      }
    }
    return emptyOpponent(role, seat_wind)
  })
}

watch(
  () => props.seatWind,
  () => syncSeatsFromSelfWind(),
  { immediate: true },
)

watch(selfIsDealer, () => {
  opponents.value = opponents.value.map((o) => ({
    ...o,
    is_dealer: o.seat_wind === 'E',
  }))
})

const isSelfTurn = computed(
  () =>
    props.tableLocked && props.currentTurnSeat === props.seatWind,
)

const activeOpponentSeat = computed(() => {
  if (!props.tableLocked || props.disabled) return null
  if (props.callPending) return null
  if (props.currentTurnSeat === props.seatWind) return null
  return props.currentTurnSeat
})

/**
 * 代录键盘「出牌中」：只看行动权（currentTurnSeat）。
 * 不因暗手张数卡死——OpponentPanel 用选牌键盘录入切牌，不依赖点选暗手。
 * 上帝视角点选手牌切牌仍由 GodViewTable 的 isDiscardReady 把关。
 */
function isTurnActive(seat) {
  return activeOpponentSeat.value === seat
}

/** 暗手是否已达出牌张数（仅提示；不挡键盘） */
function isOppHandDiscardReady(opp) {
  if (!opp) return false
  if (!Object.prototype.hasOwnProperty.call(opp, 'hand_tiles')) return true
  const hand = opp.hand_tiles
  if (!Array.isArray(hand) || hand.length === 0) return true
  const need = 14 - 3 * (opp.melds?.length || 0)
  return hand.length === need
}

const claimProvider = computed(() => props.lastDiscardSeat || '')
const claimTile = computed(() => props.lastDiscardedTile || '')
/** 有出牌标记且（响应窗开启 或 尚未被清空）时可代录吃碰 */
const claimWindowOpen = computed(
  () =>
    props.tableLocked &&
    !!claimProvider.value &&
    !!claimTile.value &&
    !props.disabled &&
    (props.responseWindow || props.callPending),
)

const totalOccupied = computed(() => {
  const map = Object.create(null)
  const bump = (t) => {
    map[t] = (map[t] || 0) + 1
  }
  for (const t of props.baseOccupied) bump(t)
  for (const o of opponents.value) {
    for (const t of o.discards || []) bump(t)
    for (const m of o.melds || []) {
      for (const t of m.tiles || []) bump(t)
    }
  }
  return map
})

function remaining(code) {
  return MAX_PER_TILE - (totalOccupied.value[code] || 0)
}

function findOppIndex(seat) {
  return opponents.value.findIndex((o) => o.seat_wind === seat)
}

/** 仅行动权对手可通过键盘打出 1 张 */
function pushDiscard(seat, code) {
  if (props.disabled || props.callPending) return
  if (!props.tableLocked) return
  if (!isTurnActive(seat)) return
  if (remaining(code) <= 0) return
  emit('opponent-discard', { seat_wind: seat, tile: code })
}

function toggleMeldPicker(seat, meldType) {
  // SETUP 预录任意；PLAYING 仅暗杠代录
  if (props.tableLocked && meldType !== 'an_gang') return
  if (
    activeMeld.value?.seat === seat &&
    activeMeld.value?.meldType === meldType
  ) {
    activeMeld.value = null
    return
  }
  activeMeld.value = { seat, meldType }
}

function buildMeldTiles(mode, code) {
  if (mode === 'pong') return [code, code, code]
  if (mode === 'ming_gang' || mode === 'an_gang')
    return [code, code, code, code]
  if (mode === 'chi') {
    if (code.length !== 2 || !'mps'.includes(code[1])) return null
    const n = Number(code[0])
    if (n < 1 || n > 7) return null
    const s = code[1]
    return [`${n}${s}`, `${n + 1}${s}`, `${n + 2}${s}`]
  }
  return null
}

function canAddMeld(mode, code) {
  if (props.catchWinSeats.length) return false
  const tiles = buildMeldTiles(mode, code)
  if (!tiles) return false
  if (
    (mode === 'ming_gang' || mode === 'an_gang') &&
    code === props.dealerTile
  ) {
    return false
  }
  const need = Object.create(null)
  for (const t of tiles) need[t] = (need[t] || 0) + 1
  for (const t of Object.keys(need)) {
    if (need[t] > remaining(t)) return false
  }
  return true
}

function addMeld(seat, mode, code) {
  if (props.tableLocked) return
  if (!canAddMeld(mode, code)) return
  const tiles = buildMeldTiles(mode, code)
  const i = findOppIndex(seat)
  if (i < 0) return
  const next = opponents.value.map((o) => ({
    ...o,
    melds: [...(o.melds || [])],
    discards: [...(o.discards || [])],
  }))
  if (next[i].melds.length >= 4) return
  next[i].melds.push({ meld_type: mode, tiles })
  opponents.value = next
  activeMeld.value = null
}

function removeMeld(seat, meldIndex) {
  if (props.tableLocked) return
  const i = findOppIndex(seat)
  if (i < 0) return
  const next = opponents.value.map((o) => ({
    ...o,
    melds: [...(o.melds || [])],
    discards: [...(o.discards || [])],
  }))
  next[i].melds.splice(meldIndex, 1)
  opponents.value = next
}

function tilesForMeldMode(group, mode) {
  if (mode !== 'chi') return group.tiles
  if (group.key === 'z') return []
  return group.tiles.filter((c) => Number(c[0]) >= 1 && Number(c[0]) <= 7)
}

function isMeldPickerOpen(seat, meldType) {
  return (
    !!activeMeld.value &&
    activeMeld.value.seat === seat &&
    activeMeld.value.meldType === meldType
  )
}

function remForNewMeld(tiles, claimed) {
  const need = Object.create(null)
  for (const t of tiles) need[t] = (need[t] || 0) + 1
  if (claimed) {
    need[claimed] = (need[claimed] || 0) - 1
    if (need[claimed] <= 0) delete need[claimed]
  }
  for (const t of Object.keys(need)) {
    if (need[t] > remaining(t)) return false
  }
  return true
}

function canChiSeat(seat) {
  if (props.catchWinSeats.length) return false
  if (!claimWindowOpen.value) return false
  if (seat === claimProvider.value) return false
  return prevSeat(seat) === claimProvider.value
}

function canPongOrGangSeat(seat) {
  if (props.catchWinSeats.length) return false
  if (!claimWindowOpen.value) return false
  return seat !== claimProvider.value
}

function canAnGangSeat(seat) {
  return (
    props.tableLocked &&
    !props.disabled &&
    isTurnActive(seat) &&
    !props.callPending
  )
}

/** 对手行动权：可代录宣布自摸 */
function canZimoSeat(seat) {
  return (
    props.tableLocked &&
    !props.disabled &&
    isTurnActive(seat) &&
    !props.callPending
  )
}

/** 出牌响应窗：仅对检测到可捉铳的座位显示代录按钮 */
function canRonSeat(seat) {
  if (!claimWindowOpen.value) return false
  if (seat === claimProvider.value) return false
  const list = props.catchWinSeats || []
  if (list.length) return list.includes(seat)
  // 无精确列表时保守不展示（避免误点）；有 catch_win 检测后应总有列表
  return false
}

function emitOpponentWin(seat, winType) {
  if (props.disabled) return
  emit('opponent-win', {
    seat,
    winType,
    winTile: winType === 'catch_win' ? claimTile.value : null,
    discarderSeat: winType === 'catch_win' ? claimProvider.value : null,
  })
}

/** 吃牌候选顺子（含打出张；禁「得」入顺） */
function chiCombosForClaim(seat) {
  const opp = opponents.value.find((o) => o.seat_wind === seat)
  if (opp?.hand_tiles?.length) {
    return chiCombosFor(opp.hand_tiles, claimTile.value, props.dealerTile)
  }
  // 无暗手追踪时保留代录模式，使用公开余量约束。
  const available = TILE_GROUPS.flatMap((group) => group.tiles || [])
  return chiCombosFor(available, claimTile.value, props.dealerTile)
    .filter((tiles) => remForNewMeld(tiles, claimTile.value))
}

function emitClaim(seat, meldType, tiles) {
  if (props.disabled) return
  emit('opponent-meld', {
    seat,
    meld_type: meldType,
    tiles: [...tiles],
    provider_seat: claimProvider.value,
    claimed_tile: claimTile.value,
  })
  activeMeld.value = null
}

function onQuickPong(seat) {
  if (!canPongOrGangSeat(seat)) return
  const t = claimTile.value
  if (!remForNewMeld([t, t, t], t)) return
  emitClaim(seat, 'pong', [t, t, t])
}

function onQuickMingGang(seat) {
  if (!canPongOrGangSeat(seat)) return
  const t = claimTile.value
  if (t === props.dealerTile) return
  if (!remForNewMeld([t, t, t, t], t)) return
  emitClaim(seat, 'ming_gang', [t, t, t, t])
}

function onQuickChi(seat, tiles) {
  if (!canChiSeat(seat)) return
  emitClaim(seat, 'chi', tiles)
}

function onQuickAnGang(seat, code) {
  if (!canAnGangSeat(seat)) return
  if (!canAddMeld('an_gang', code)) return
  emit('opponent-meld', {
    seat,
    meld_type: 'an_gang',
    tiles: [code, code, code, code],
  })
  activeMeld.value = null
}

function claimHint(seat) {
  if (!claimWindowOpen.value) return ''
  const who = windLabel(claimProvider.value)
  const tile = tileLabel(claimTile.value)
  if (canChiSeat(seat)) return `${who} 打出 ${tile} · 可吃/碰/杠`
  if (canPongOrGangSeat(seat)) return `${who} 打出 ${tile} · 可碰/杠`
  return ''
}
</script>

<template>
  <section
    class="w-full max-w-2xl rounded-2xl border border-teal-700/40 bg-teal-950/50 p-5 sm:p-6 shadow-xl backdrop-blur-sm"
    aria-label="对手公开信息"
  >
    <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="text-lg font-semibold tracking-wide text-amber-50">
          三方对手
        </h2>
        <p class="mt-0.5 text-xs text-teal-300/70">
          <template v-if="tableLocked">
            串行出牌 · 出牌后须先过响应窗再摸牌
            <span v-if="claimWindowOpen" class="text-amber-200/90">
              · 响应 {{ windLabel(claimProvider) }} 的
              {{ tileLabel(claimTile) }}
            </span>
          </template>
          <template v-else>
            确认开局前可预录副露 · 弃牌仅在行动权轮到时打出
          </template>
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          v-if="responseWindow || claimWindowOpen"
          type="button"
          class="rounded-lg border border-teal-400/55 bg-teal-900/70 px-2.5 py-1 text-[11px] font-bold text-teal-50 transition hover:border-amber-300 disabled:opacity-40"
          :disabled="disabled"
          @click="emit('pass-all-calls')"
        >
          {{ catchWinSeats.length ? windLabel(catchWinSeats[0]) + '风过胡 · 下一顺位' : '全员过牌 / 继续摸牌' }}
        </button>
        <p
          v-if="tableLocked && isSelfTurn"
          class="rounded-lg border border-amber-400/50 bg-amber-500/15 px-2.5 py-1 text-xs font-semibold text-amber-100"
        >
          轮到自家切牌
        </p>
      </div>
    </div>

    <div class="space-y-4">
      <article
        v-for="opp in opponents"
        :key="opp.role + opp.seat_wind"
        class="rounded-xl border bg-emerald-950/35 p-3 sm:p-4 transition-[box-shadow,opacity] duration-300"
        :class="
          isTurnActive(opp.seat_wind)
            ? 'ring-2 ring-emerald-500 shadow-lg border-emerald-400/60 opacity-100 turn-active-glow'
            : claimWindowOpen &&
                (canChiSeat(opp.seat_wind) || canPongOrGangSeat(opp.seat_wind))
              ? 'border-amber-500/45 ring-1 ring-amber-400/30 opacity-100'
              : tableLocked
                ? 'border-teal-800/50 opacity-75'
                : 'border-teal-800/50'
        "
      >
        <!-- 标题行 -->
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <span
              class="rounded-md bg-teal-800/70 px-2 py-0.5 text-sm font-semibold text-amber-100"
            >
              {{ opp.role }}
            </span>
            <span class="text-sm text-teal-200/90">
              {{ windLabel(opp.seat_wind) }}风
              <span class="text-teal-400/70">({{ opp.seat_wind }})</span>
            </span>
            <span
              v-if="isTurnActive(opp.seat_wind)"
              class="rounded bg-amber-400/90 px-1.5 py-0.5 text-[10px] font-bold text-emerald-950"
            >
              出牌中
            </span>
          </div>
          <span
            class="rounded-lg px-3 py-1 text-xs font-medium"
            :class="
              opp.is_dealer
                ? 'bg-amber-500 text-emerald-950 shadow'
                : 'border border-teal-700/50 text-teal-400/80'
            "
            :title="
              opp.is_dealer
                ? '东风位固定为庄家（rule.md §1）'
                : '闲家'
            "
          >
            {{ opp.is_dealer ? '庄家' : '闲家' }}
          </span>
        </div>

        <!-- PLAYING：代录吃碰杠 / 暗杠 -->
        <div
          v-if="tableLocked && opp.melds.length < 4"
          class="mb-3 flex flex-wrap gap-1.5"
        >
          <template v-if="canChiSeat(opp.seat_wind)">
            <button
              v-for="(combo, ci) in chiCombosForClaim(opp.seat_wind)"
              :key="'chi-' + ci"
              type="button"
              class="rounded-lg border border-emerald-400/50 bg-emerald-950/70 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-50 transition hover:border-emerald-300 disabled:opacity-40"
              :disabled="disabled"
              @click="onQuickChi(opp.seat_wind, combo)"
            >
              {{ opp.role }}吃 {{ combo.map((t) => substituteTileLabel(t, dealerTile)).join('·') }}
            </button>
          </template>
          <button
            v-if="canPongOrGangSeat(opp.seat_wind)"
            type="button"
            class="rounded-lg border border-amber-400/50 bg-amber-950/70 px-2.5 py-1.5 text-[11px] font-semibold text-amber-50 transition hover:border-amber-300 disabled:opacity-40"
            :disabled="
              disabled ||
              !remForNewMeld([claimTile, claimTile, claimTile], claimTile)
            "
            @click="onQuickPong(opp.seat_wind)"
          >
            {{ opp.role }}碰 {{ tileLabel(claimTile) }}
          </button>
          <button
            v-if="canPongOrGangSeat(opp.seat_wind)"
            type="button"
            class="rounded-lg border border-violet-400/50 bg-violet-950/70 px-2.5 py-1.5 text-[11px] font-semibold text-violet-50 transition hover:border-violet-300 disabled:opacity-40"
            :disabled="
              disabled ||
              claimTile === dealerTile ||
              !remForNewMeld(
                [claimTile, claimTile, claimTile, claimTile],
                claimTile,
              )
            "
            @click="onQuickMingGang(opp.seat_wind)"
          >
            {{ opp.role }}明杠 {{ tileLabel(claimTile) }}
          </button>
          <button
            v-if="canAnGangSeat(opp.seat_wind)"
            type="button"
            class="rounded-lg border border-fuchsia-400/55 bg-fuchsia-900/70 px-3 py-1.5 text-[11px] font-bold text-fuchsia-50 shadow-sm transition hover:border-fuchsia-200 hover:bg-fuchsia-800/80"
            :disabled="disabled"
            :class="
              isMeldPickerOpen(opp.seat_wind, 'an_gang')
                ? 'ring-2 ring-fuchsia-300'
                : ''
            "
            @click="toggleMeldPicker(opp.seat_wind, 'an_gang')"
          >
            录入暗杠
          </button>
          <button
            v-if="canZimoSeat(opp.seat_wind)"
            type="button"
            class="rounded-lg border border-rose-400/60 bg-rose-800/80 px-3 py-1.5 text-[11px] font-bold text-rose-50 shadow transition hover:border-rose-200 hover:bg-rose-700"
            :disabled="disabled"
            @click="emitOpponentWin(opp.seat_wind, 'self_draw_win')"
          >
            宣布自摸
          </button>
          <button
            v-if="canRonSeat(opp.seat_wind)"
            type="button"
            class="rounded-lg border-2 border-amber-300 bg-amber-600 px-3 py-2 text-[12px] font-bold text-amber-50 shadow-lg ring-2 ring-amber-200/50 transition hover:bg-amber-500"
            :disabled="disabled || !claimTile"
            @click="emitOpponentWin(opp.seat_wind, 'catch_win')"
          >
            🎉 代录{{ opp.role }}（{{ windLabel(opp.seat_wind) }}）捉铳和牌
            <span v-if="claimTile" class="opacity-95">
              · {{ tileLabel(claimTile) }}
            </span>
          </button>
          <p
            v-if="claimHint(opp.seat_wind)"
            class="w-full text-[10px] text-amber-200/75"
          >
            {{ claimHint(opp.seat_wind) }}
          </p>
        </div>

        <!-- 弃牌河（只读展示；无「添加弃牌」） -->
        <div class="mb-3">
          <div class="mb-1.5 flex items-center justify-between gap-2">
            <p class="text-xs font-medium text-teal-300/80">
              弃牌河（{{ opp.discards.length }}）
            </p>
            <p
              v-if="isSelfTurn"
              class="text-[10px] text-teal-500/80"
            >
              轮到自家切牌
            </p>
            <p
              v-else-if="tableLocked && !isTurnActive(opp.seat_wind)"
              class="text-[10px] text-teal-500/70"
            >
              等待 {{ windLabel(currentTurnSeat) }}风
            </p>
          </div>
          <div
            v-if="opp.discards.length"
            class="flex flex-wrap gap-1"
            role="list"
          >
            <span
              v-for="(t, ti) in opp.discards"
              :key="`${opp.seat_wind}-d-${ti}-${t}`"
              role="listitem"
              class="inline-flex h-8 w-6 items-center justify-center rounded border text-[10px] font-bold"
              :class="[
                tileSuitClass(t),
                ti === opp.discards.length - 1
                  ? 'ring-2 ring-amber-400/70'
                  : 'opacity-90',
              ]"
              :title="tileLabel(t)"
            >
              {{ substituteTileLabel(t, dealerTile) }}
            </span>
          </div>
          <p v-else class="text-xs text-teal-500/70">尚无弃牌</p>

          <!-- 行动权对手：紧凑选牌键盘（副露后立刻可切，不依赖暗手张数） -->
          <div
            v-if="isTurnActive(opp.seat_wind) && !callPending"
            class="mt-2 space-y-2 rounded-lg border border-amber-400/40 bg-amber-950/25 p-2"
          >
            <p class="text-[11px] font-semibold text-amber-100/95">
              {{
                props.lastStepNote?.includes('补')
                  ? '补牌完成 · 请打出 1 张牌'
                  : '请打出 1 张牌'
              }}
              <span
                v-if="claimWindowOpen"
                class="font-normal text-amber-200/70"
              >
                （亦可先代录他家吃碰）
              </span>
            </p>
            <p
              v-if="
                Array.isArray(opp.hand_tiles) &&
                opp.hand_tiles.length > 0 &&
                !isOppHandDiscardReady(opp)
              "
              class="text-[10px] text-rose-200/90"
            >
              暗手张数异常（{{ opp.hand_tiles.length }}/{{
                14 - 3 * (opp.melds?.length || 0)
              }}），仍可用键盘代录切牌
            </p>
            <div v-for="group in TILE_GROUPS" :key="group.key">
              <p class="mb-1 text-[10px] text-teal-400/70">{{ group.label }}</p>
              <div class="grid grid-cols-5 gap-1 sm:grid-cols-9">
                <button
                  v-for="code in group.tiles"
                  :key="code"
                  type="button"
                  class="rounded-md border px-0.5 py-1.5 text-[11px] font-medium transition"
                  :class="
                    remaining(code) > 0 && !disabled
                      ? 'border-amber-500/50 bg-emerald-900/60 text-amber-50 hover:border-amber-300 hover:bg-amber-500/20'
                      : 'cursor-not-allowed border-slate-700/40 text-slate-600'
                  "
                  :disabled="remaining(code) <= 0 || disabled"
                  @click="pushDiscard(opp.seat_wind, code)"
                >
                  {{ tileLabel(code) }}
                  <span class="block text-[9px] opacity-70">
                    {{ remaining(code) }}
                  </span>
                </button>
              </div>
            </div>
          </div>

          <!-- 暗杠选牌 -->
          <div
            v-if="
              tableLocked &&
              isMeldPickerOpen(opp.seat_wind, 'an_gang') &&
              canAnGangSeat(opp.seat_wind)
            "
            class="mt-2 space-y-2 rounded-lg border border-fuchsia-400/40 bg-fuchsia-950/30 p-2"
          >
            <p class="text-[10px] text-fuchsia-100/85">
              选择同名牌录入暗杠（禁得）
            </p>
            <div v-for="group in TILE_GROUPS" :key="'ag-' + group.key">
              <p class="mb-1 text-[10px] text-teal-400/70">{{ group.label }}</p>
              <div class="grid grid-cols-5 gap-1 sm:grid-cols-9">
                <button
                  v-for="code in group.tiles"
                  :key="code"
                  type="button"
                  class="rounded-md border px-0.5 py-1.5 text-[11px] transition"
                  :class="
                    canAddMeld('an_gang', code)
                      ? 'border-fuchsia-500/50 bg-fuchsia-900/50 text-amber-50'
                      : 'cursor-not-allowed border-slate-700/40 text-slate-600'
                  "
                  :disabled="!canAddMeld('an_gang', code) || disabled"
                  @click="onQuickAnGang(opp.seat_wind, code)"
                >
                  {{ tileLabel(code) }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 副露：开局前可录；锁定后只读 -->
        <div>
          <div class="mb-1.5 flex flex-wrap items-center justify-between gap-2">
            <p class="text-xs font-medium text-teal-300/80">
              副露（{{ opp.melds.length }}/4）
            </p>
            <div v-if="!tableLocked" class="flex flex-wrap gap-1">
              <button
                v-for="mode in MELD_MODES"
                :key="mode.type"
                type="button"
                class="rounded-md px-2 py-0.5 text-[11px] font-medium transition"
                :class="
                  opp.melds.length >= 4
                    ? 'cursor-not-allowed text-slate-500'
                    : isMeldPickerOpen(opp.seat_wind, mode.type)
                      ? 'bg-amber-500 text-emerald-950'
                      : 'border border-teal-600/45 text-teal-100 hover:border-amber-400/50'
                "
                :disabled="opp.melds.length >= 4"
                @click="toggleMeldPicker(opp.seat_wind, mode.type)"
              >
                {{ mode.label }}
              </button>
            </div>
          </div>

          <div v-if="opp.melds.length" class="mb-2 space-y-1">
            <component
              :is="tableLocked ? 'div' : 'button'"
              v-for="(m, mi) in opp.melds"
              :key="`${opp.seat_wind}-m-${mi}`"
              type="button"
              class="flex w-full items-center gap-2 rounded-lg border border-teal-800/40 bg-teal-950/40 px-2 py-1.5 text-left"
              :class="
                tableLocked
                  ? ''
                  : 'hover:border-rose-400/40 cursor-pointer'
              "
              @click="!tableLocked && removeMeld(opp.seat_wind, mi)"
            >
              <span class="text-[10px] text-amber-100/90">
                {{ MELD_TYPE_LABEL[m.meld_type] || m.meld_type }}
              </span>
              <span class="flex flex-wrap gap-0.5">
                <span
                  v-for="(t, ti) in m.tiles"
                  :key="ti"
                  class="inline-flex h-7 min-w-5 px-1 items-center justify-center rounded border text-[9px] font-bold"
                  :class="tileSuitClass(t)"
                >
                  {{ substituteTileLabel(t, dealerTile) }}
                </span>
              </span>
              <span
                v-if="!tableLocked"
                class="ml-auto text-[10px] text-teal-500"
              >
                删
              </span>
            </component>
          </div>
          <p v-else class="mb-2 text-xs text-teal-500/70">尚无副露</p>

          <div
            v-if="
              !tableLocked &&
              activeMeld?.seat === opp.seat_wind &&
              opp.melds.length < 4
            "
            class="space-y-2 border-t border-teal-800/40 pt-2"
          >
            <p class="text-[10px] text-teal-300/75">
              选择牌面添加{{ MELD_TYPE_LABEL[activeMeld.meldType] }}
            </p>
            <div v-for="group in TILE_GROUPS" :key="group.key">
              <template
                v-if="tilesForMeldMode(group, activeMeld.meldType).length"
              >
                <p class="mb-1 text-[10px] text-teal-400/70">
                  {{ group.label }}
                </p>
                <div class="grid grid-cols-5 gap-1 sm:grid-cols-9">
                  <button
                    v-for="code in tilesForMeldMode(
                      group,
                      activeMeld.meldType,
                    )"
                    :key="code"
                    type="button"
                    class="rounded-md border px-0.5 py-1.5 text-[11px] transition"
                    :class="
                      canAddMeld(activeMeld.meldType, code)
                        ? 'border-teal-600/45 bg-emerald-900/50 text-amber-50'
                        : 'cursor-not-allowed border-slate-700/40 text-slate-600'
                    "
                    :disabled="!canAddMeld(activeMeld.meldType, code)"
                    @click="
                      addMeld(opp.seat_wind, activeMeld.meldType, code)
                    "
                  >
                    {{ tileLabel(code) }}
                  </button>
                </div>
              </template>
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.turn-active-glow {
  animation: turn-breathe 1.6s ease-in-out infinite;
}

@keyframes turn-breathe {
  0%,
  100% {
    box-shadow:
      0 0 0 2px rgba(16, 185, 129, 0.55),
      0 0 14px 2px rgba(52, 211, 153, 0.3);
  }
  50% {
    box-shadow:
      0 0 0 3px rgba(52, 211, 153, 0.85),
      0 0 22px 4px rgba(16, 185, 129, 0.45);
  }
}

@media (prefers-reduced-motion: reduce) {
  .turn-active-glow {
    animation: none;
  }
}
</style>
