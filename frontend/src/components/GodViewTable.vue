<script setup>
/**
 * 全景上帝视角沙盘：四方俯视，四家暗手明牌。
 * 「得」可拖拽 / ◀▶ 微调插嵌；摸切后恢复默认理牌。
 */
import { computed } from 'vue'
import { substituteTileLabel } from '../utils/callDetector.js'
import {
  relativeOpponents,
  tileLabel,
} from '../constants/tiles.js'
import { windLabel } from '../utils/seatLayout.js'
import {
  handTilesWithKeys,
} from '../utils/tileSorter.js'
import ResultCard from './ResultCard.vue'
import GodViewHandStrip from './GodViewHandStrip.vue'

const props = defineProps({
  seatWind: { type: String, required: true },
  isDealer: { type: Boolean, default: false },
  dealerTile: { type: String, default: '' },
  currentTurnSeat: { type: String, default: 'E' },
  selfHand: { type: Array, default: () => [] },
  selfMelds: { type: Array, default: () => [] },
  selfDiscards: { type: Array, default: () => [] },
  opponents: { type: Array, default: () => [] },
  latestDrawnBySeat: { type: Object, default: () => ({}) },
  /** @type {Record<string, boolean>} */
  handLayoutPinned: { type: Object, default: () => ({}) },
  recommend: { type: Object, default: null },
  recommendLoading: { type: Boolean, default: false },
  bestTile: { type: String, default: '' },
  selfGangCandidates: { type: Array, default: () => [] },
  tableLocked: { type: Boolean, default: false },
  callPending: { type: Boolean, default: false },
  /** 出牌后副露响应窗 */
  responseWindow: { type: Boolean, default: false },
  tableResponses: { type: Array, default: () => [] },
  /** 可捉铳座位 */
  catchWinSeats: { type: Array, default: () => [] },
  lastDiscardSeat: { type: String, default: '' },
  lastDiscardedTile: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  wallCount: { type: Number, default: 0 },
})

const emit = defineEmits([
  'close',
  'discard-tile',
  'select-self-gang',
  'move-joker',
  'pass-all-calls',
  'catch-win',
])

const byRole = computed(() => {
  const map = { 上家: null, 对家: null, 下家: null }
  for (const o of props.opponents || []) {
    if (o.role && map[o.role] === null) map[o.role] = o
  }
  if (!map['上家'] || !map['对家'] || !map['下家']) {
    const rel = relativeOpponents(props.seatWind)
    for (const r of rel) {
      const found = (props.opponents || []).find(
        (o) => o.seat_wind === r.seat_wind,
      )
      if (found) map[r.role] = found
    }
  }
  return map
})

const kamicha = computed(() => byRole.value['上家'])
const toimen = computed(() => byRole.value['对家'])
const shimocha = computed(() => byRole.value['下家'])

function isActive(seat) {
  return (
    props.tableLocked &&
    !props.disabled &&
    !props.callPending &&
    props.currentTurnSeat === seat &&
    isDiscardReady(seat)
  )
}

/**
 * 出牌阶段暗手须 = 14 - 3*副露数。
 * 无暗手追踪（hand_tiles 空/缺省）时：仅按行动权放行（与 OpponentPanel 键盘一致）。
 */
function isDiscardReady(seat) {
  if (!seat) return false
  if (seat === props.seatWind) {
    const meldsN = props.selfMelds?.length || 0
    return (props.selfHand?.length || 0) === 14 - 3 * meldsN
  }
  const opp = (props.opponents || []).find((o) => o.seat_wind === seat)
  if (!opp) return false
  const meldsN = opp.melds?.length || 0
  if (!Array.isArray(opp.hand_tiles) || opp.hand_tiles.length === 0) {
    // 未托管暗手：允许点亮行动权（切牌走 OpponentPanel 键盘）
    return true
  }
  return opp.hand_tiles.length === 14 - 3 * meldsN
}

function isPinned(seat) {
  return !!props.handLayoutPinned?.[seat]
}

/**
 * 展示序 ≡ 会话暗手数组成员序（含手动插嵌后的 displayOrder）。
 * 禁止在此二次 sort：否则切牌 index 会与底层 hand 错位。
 * 默认「得」靠左由 useGameSession.applyHandSort / sortSeatClosedHand 写入会话。
 */
function buildHandView(seat, rawTiles) {
  const drawn =
    isActive(seat) && props.latestDrawnBySeat?.[seat]
      ? props.latestDrawnBySeat[seat]
      : null
  const tiles = Array.isArray(rawTiles) ? [...rawTiles] : []
  const drawnIndex =
    drawn && tiles.length && tiles[tiles.length - 1] === drawn
      ? tiles.length - 1
      : -1

  return {
    tiles,
    drawnIndex,
    sorted: tiles,
    keys: handTilesWithKeys(tiles),
  }
}

const selfHandView = computed(() =>
  buildHandView(props.seatWind, props.selfHand),
)
const toimenHandView = computed(() =>
  buildHandView(toimen.value?.seat_wind, toimen.value?.hand_tiles || []),
)
const kamichaHandView = computed(() =>
  buildHandView(kamicha.value?.seat_wind, kamicha.value?.hand_tiles || []),
)
const shimochaHandView = computed(() =>
  buildHandView(shimocha.value?.seat_wind, shimocha.value?.hand_tiles || []),
)

function onDiscard(payload) {
  emit('discard-tile', payload)
}

function onMoveJoker(payload) {
  emit('move-joker', payload)
}

function onClickRecommendTile(tile) {
  const sorted = selfHandView.value.sorted || []
  const index = sorted.lastIndexOf(tile)
  emit('discard-tile', {
    seat_wind: props.seatWind,
    tile,
    index: index >= 0 ? index : sorted.length - 1,
  })
}

function seatRole(seat) {
  return seat === props.seatWind ? '自家' : relativeOpponents(props.seatWind).find((o) => o.seat_wind === seat)?.role || windLabel(seat)
}

const responseSummary = computed(() => props.tableResponses.map((o) => {
  const labels = { chi: '吃', pong: '碰', ming_gang: '杠', catch_win: '胡' }
  return `${seatRole(o.seat)}可${o.types.map((t) => labels[t] || t).join('、')}`
}).join(' · '))

function meldLabel(m) {
  const t = m?.meld_type || ''
  const map = {
    chi: '吃',
    pong: '碰',
    ming_gang: '明杠',
    an_gang: '暗杠',
  }
  return map[t] || t
}
</script>

<template>
  <Teleport to="body">
    <button
      type="button"
      class="god-view-return"
      aria-label="返回模式选择"
      @click="emit('close')"
    >
      <span aria-hidden="true">←</span>
      <span>返回模式选择</span>
    </button>
  </Teleport>
  <section
    class="god-view overflow-hidden rounded-2xl border border-teal-600/40 bg-gradient-to-br from-emerald-950 via-teal-950 to-slate-950 shadow-xl"
    aria-label="上帝视角沙盘"
  >
    <header
      class="flex flex-wrap items-center justify-between gap-2 border-b border-teal-800/50 px-3 py-2"
    >
      <p class="text-xs font-semibold text-amber-100/90">
        上帝视角 · 四家暗手明牌
      </p>
      <p class="text-[11px] text-teal-300/80">
        得 {{ dealerTile ? tileLabel(dealerTile) : '—' }}
        · 牌墙 {{ wallCount }}
        · 当前
        <span class="font-bold text-amber-200">{{
          windLabel(currentTurnSeat)
        }}</span>
      </p>
    </header>

    <p class="px-3 pt-2 text-[10px] text-teal-400/75">
      「得」可拖拽或点 ◀▶ 插嵌组牌；摸/切/一键理牌后恢复默认排序
    </p>

    <!-- 副露响应窗：禁止下家摸牌，需吃碰/捉铳或全员过牌 -->
    <div
      v-if="responseWindow && tableLocked"
      class="mx-3 mt-2 space-y-2 rounded-xl border border-amber-400/50 bg-amber-950/40 px-3 py-2"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-[11px] font-semibold text-amber-100">
          等待副露响应 ·
          <span class="text-amber-200">{{ seatRole(lastDiscardSeat) }}</span>
          打出
          <span class="text-amber-50">{{ tileLabel(lastDiscardedTile) }}</span>
          · {{ responseSummary || '下家尚未摸牌' }}
        </p>
        <button
          type="button"
          class="rounded-lg border border-teal-400/50 bg-teal-900/80 px-3 py-1.5 text-[11px] font-bold text-teal-50 transition hover:border-amber-300 hover:bg-amber-900/50 disabled:opacity-40"
          :disabled="disabled"
          @click="emit('pass-all-calls')"
        >
          {{ catchWinSeats.length ? windLabel(catchWinSeats[0]) + '风过胡 · 下一顺位' : '放弃 / 全员过牌' }}
        </button>
      </div>
      <div
        v-if="(catchWinSeats || []).length"
        class="flex flex-wrap gap-2"
      >
        <button
          v-for="seat in catchWinSeats.slice(0, 1)"
          :key="'cw-' + seat"
          type="button"
          class="rounded-lg border-2 border-rose-400 bg-rose-700/90 px-3 py-2 text-[12px] font-bold text-rose-50 shadow-lg transition hover:bg-rose-600 disabled:opacity-40"
          :disabled="disabled"
          @click="
            emit('catch-win', {
              seat,
              winType: 'catch_win',
              winTile: lastDiscardedTile,
              discarderSeat: lastDiscardSeat,
            })
          "
        >
          🎉 {{ windLabel(seat) }}风 捉铳和牌（点炮
          {{ windLabel(lastDiscardSeat) }} ·
          {{ tileLabel(lastDiscardedTile) }}）
        </button>
      </div>
    </div>

    <div
      class="grid grid-cols-1 gap-2 p-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_minmax(0,1fr)] lg:grid-rows-[auto_minmax(220px,1fr)_auto] lg:gap-3 lg:p-3"
    >
      <!-- 对家 -->
      <div
        class="order-1 rounded-xl border p-2 transition duration-200 lg:col-start-2 lg:row-start-1"
        :class="
          isActive(toimen?.seat_wind)
            ? 'border-amber-400/70 bg-amber-950/35 ring-2 ring-amber-400/40'
            : 'border-teal-800/45 bg-teal-950/40'
        "
      >
        <div class="mb-1.5 flex items-center justify-between gap-2">
          <span class="text-[11px] font-bold text-teal-100">
            对家 · {{ windLabel(toimen?.seat_wind) }}
            <span
              v-if="toimen?.is_dealer"
              class="ml-1 rounded bg-amber-400 px-1 text-[9px] text-amber-950"
              >庄</span
            >
            <span
              v-if="isPinned(toimen?.seat_wind)"
              class="ml-1 rounded bg-fuchsia-700/80 px-1 text-[9px] text-fuchsia-50"
              >组牌</span
            >
          </span>
          <span
            v-if="isActive(toimen?.seat_wind)"
            class="text-[10px] font-bold text-amber-200"
            >出牌中</span
          >
        </div>
        <GodViewHandStrip
          v-if="toimen?.seat_wind"
          :seat="toimen.seat_wind"
          :tiles="toimenHandView.tiles"
          :drawn-index="toimenHandView.drawnIndex"
          :dealer-tile="dealerTile"
          :active="isActive(toimen.seat_wind)"
          :disabled="disabled"
          justify="center"
          @discard-tile="onDiscard"
          @move-joker="onMoveJoker"
        />
        <div class="flex flex-wrap justify-center gap-0.5 opacity-80">
          <span
            v-for="(t, i) in toimen?.discards || []"
            :key="'t-d-' + i"
            class="rounded border border-teal-800/30 px-1 py-0.5 text-[9px] text-teal-200/80"
            >{{ tileLabel(t) }}</span
          >
        </div>
        <div
          v-if="(toimen?.melds || []).length"
          class="mt-1 flex flex-wrap justify-center gap-1"
        >
          <span
            v-for="(m, mi) in toimen.melds"
            :key="'t-m-' + mi"
            class="rounded bg-teal-900/60 px-1.5 py-0.5 text-[9px] text-teal-100"
          >
            {{ meldLabel(m) }}
            {{ (m.tiles || []).map((t) => substituteTileLabel(t, dealerTile)).join(' / ') }}
          </span>
        </div>
      </div>

      <!-- 上家 -->
      <div
        class="order-2 rounded-xl border p-2 transition duration-200 lg:col-start-1 lg:row-start-2"
        :class="
          isActive(kamicha?.seat_wind)
            ? 'border-amber-400/70 bg-amber-950/35 ring-2 ring-amber-400/40'
            : 'border-teal-800/45 bg-teal-950/40'
        "
      >
        <div class="mb-1.5 flex items-center justify-between gap-2">
          <span class="text-[11px] font-bold text-teal-100">
            上家 · {{ windLabel(kamicha?.seat_wind) }}
            <span
              v-if="kamicha?.is_dealer"
              class="ml-1 rounded bg-amber-400 px-1 text-[9px] text-amber-950"
              >庄</span
            >
            <span
              v-if="isPinned(kamicha?.seat_wind)"
              class="ml-1 rounded bg-fuchsia-700/80 px-1 text-[9px] text-fuchsia-50"
              >组牌</span
            >
          </span>
        </div>
        <GodViewHandStrip
          v-if="kamicha?.seat_wind"
          :seat="kamicha.seat_wind"
          :tiles="kamichaHandView.tiles"
          :drawn-index="kamichaHandView.drawnIndex"
          :dealer-tile="dealerTile"
          :active="isActive(kamicha.seat_wind)"
          :disabled="disabled"
          @discard-tile="onDiscard"
          @move-joker="onMoveJoker"
        />
        <div class="mt-1 flex flex-wrap gap-1">
          <span v-for="(m, mi) in kamicha?.melds || []" :key="mi" class="text-[10px] text-teal-100">
            {{ meldLabel(m) }} {{ (m.tiles || []).map((t) => substituteTileLabel(t, dealerTile)).join(' / ') }}
          </span>
        </div>
        <div class="flex flex-wrap gap-0.5 opacity-80">
          <span
            v-for="(t, i) in kamicha?.discards || []"
            :key="'k-d-' + i"
            class="rounded border border-teal-800/30 px-1 py-0.5 text-[9px] text-teal-200/80"
            >{{ tileLabel(t) }}</span
          >
        </div>
      </div>

      <!-- 中央 -->
      <div
        class="order-4 flex flex-col justify-center gap-2 rounded-xl border border-teal-700/35 bg-emerald-950/30 p-2 lg:order-3 lg:col-start-2 lg:row-start-2"
      >
        <p class="text-center text-[11px] text-teal-200/75">
          高亮座位点击切牌 · 「得」拖拽/◀▶ 插嵌
        </p>
        <ResultCard
          v-if="
            isActive(seatWind) &&
            (recommendLoading ||
              (recommend?.best_tile && (recommend.candidates || []).length))
          "
          class="max-h-[40vh] min-h-[7.5rem] overflow-y-auto"
          :best-tile="recommend?.best_tile || ''"
          :best-action="recommend?.best_action || null"
          :candidates="recommend?.candidates || []"
          :self-gang-candidates="selfGangCandidates"
          :seat-wind="seatWind"
          :is-dealer="isDealer"
          :loading="recommendLoading"
          :interactive="!recommendLoading && !!recommend?.best_tile"
          @select-tile="onClickRecommendTile"
          @select-self-gang="(g) => emit('select-self-gang', g)"
        />
      </div>

      <!-- 下家 -->
      <div
        class="order-3 rounded-xl border p-2 transition duration-200 lg:order-4 lg:col-start-3 lg:row-start-2"
        :class="
          isActive(shimocha?.seat_wind)
            ? 'border-amber-400/70 bg-amber-950/35 ring-2 ring-amber-400/40'
            : 'border-teal-800/45 bg-teal-950/40'
        "
      >
        <div class="mb-1.5 flex items-center justify-between gap-2">
          <span class="text-[11px] font-bold text-teal-100">
            下家 · {{ windLabel(shimocha?.seat_wind) }}
            <span
              v-if="shimocha?.is_dealer"
              class="ml-1 rounded bg-amber-400 px-1 text-[9px] text-amber-950"
              >庄</span
            >
            <span
              v-if="isPinned(shimocha?.seat_wind)"
              class="ml-1 rounded bg-fuchsia-700/80 px-1 text-[9px] text-fuchsia-50"
              >组牌</span
            >
          </span>
        </div>
        <GodViewHandStrip
          v-if="shimocha?.seat_wind"
          :seat="shimocha.seat_wind"
          :tiles="shimochaHandView.tiles"
          :drawn-index="shimochaHandView.drawnIndex"
          :dealer-tile="dealerTile"
          :active="isActive(shimocha.seat_wind)"
          :disabled="disabled"
          @discard-tile="onDiscard"
          @move-joker="onMoveJoker"
        />
        <div class="mt-1 flex flex-wrap gap-1">
          <span v-for="(m, mi) in shimocha?.melds || []" :key="mi" class="text-[10px] text-teal-100">
            {{ meldLabel(m) }} {{ (m.tiles || []).map((t) => substituteTileLabel(t, dealerTile)).join(' / ') }}
          </span>
        </div>
        <div class="flex flex-wrap gap-0.5 opacity-80">
          <span
            v-for="(t, i) in shimocha?.discards || []"
            :key="'s-d-' + i"
            class="rounded border border-teal-800/30 px-1 py-0.5 text-[9px] text-teal-200/80"
            >{{ tileLabel(t) }}</span
          >
        </div>
      </div>

      <!-- 自家 -->
      <div
        class="order-5 rounded-xl border p-2 transition duration-200 lg:col-span-3 lg:col-start-1 lg:row-start-3"
        :class="
          isActive(seatWind)
            ? 'border-amber-400/70 bg-amber-950/35 ring-2 ring-amber-400/40'
            : 'border-emerald-700/45 bg-emerald-950/50'
        "
      >
        <div class="mb-1.5 flex flex-wrap items-center justify-between gap-2">
          <span class="text-[11px] font-bold text-amber-50">
            自家 · {{ windLabel(seatWind) }}
            <span
              v-if="isDealer"
              class="ml-1 rounded bg-amber-400 px-1 text-[9px] text-amber-950"
              >庄</span
            >
            <span
              v-if="isPinned(seatWind)"
              class="ml-1 rounded bg-fuchsia-700/80 px-1 text-[9px] text-fuchsia-50"
              >组牌</span
            >
          </span>
          <span
            v-if="isActive(seatWind)"
            class="text-[10px] font-bold text-amber-200"
            >出牌中</span
          >
        </div>
        <div v-if="selfMelds.length" class="mb-1 flex flex-wrap gap-1">
          <span
            v-for="(m, mi) in selfMelds"
            :key="'self-m-' + mi"
            class="rounded bg-teal-900/60 px-1.5 py-0.5 text-[10px] text-teal-100"
          >
            {{ meldLabel(m) }}
            {{ (m.tiles || []).map((t) => substituteTileLabel(t, dealerTile)).join(' / ') }}
          </span>
        </div>
        <GodViewHandStrip
          :seat="seatWind"
          :tiles="selfHandView.tiles"
          :drawn-index="selfHandView.drawnIndex"
          :dealer-tile="dealerTile"
          :active="isActive(seatWind)"
          :disabled="disabled"
          :best-tile="bestTile"
          @discard-tile="onDiscard"
          @move-joker="onMoveJoker"
        />
        <div class="flex flex-wrap gap-0.5 opacity-85">
          <span
            v-for="(t, i) in selfDiscards"
            :key="'self-d-' + i"
            class="rounded border border-teal-800/30 px-1 py-0.5 text-[9px] text-teal-200/80"
            >{{ tileLabel(t) }}</span
          >
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.god-view-return {
  position: fixed;
  top: max(18px, env(safe-area-inset-top));
  left: max(24px, env(safe-area-inset-left));
  z-index: 120;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 8px 16px;
  border: 1px solid rgba(255, 215, 0, .35);
  border-radius: 999px;
  background: rgba(15, 32, 28, .75);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 6px 20px rgba(0, 0, 0, .28);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  cursor: pointer;
  transition: background-color 150ms ease, border-color 150ms ease, transform 150ms ease;
}
.god-view-return:hover { border-color: rgba(255, 215, 0, .7); background: rgba(28, 64, 52, .9); }
.god-view-return:active { transform: scale(.96); }
.god-view-return:focus-visible { outline: 2px solid #fbbf24; outline-offset: 3px; }
.god-view-return span:first-child { font-size: 20px; line-height: 1; }
@media (prefers-reduced-motion: reduce) { .god-view-return { transition: none; } }
</style>
