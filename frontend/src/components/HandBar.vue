<script setup>
/**
 * 手牌槽位：
 * - SETUP / 编辑态：点击移出录入（绝不切牌）
 * - PLAYING 切牌态（discardMode）：点击派发 discard-tile(tile, index)
 */
import { computed, ref, watch } from 'vue'
import MahjongTile from './MahjongTile.vue'
import { tileLabel } from '../constants/tiles.js'
import {
  handTilesWithKeys,
  isJokerPhysical,
  isWhiteboardProxy,
  sortHandTiles,
} from '../utils/tileSorter.js'

const tiles = defineModel({
  type: Array,
  default: () => [],
})

/** 自动理牌开关（与会话同步） */
const autoSort = defineModel('autoSort', {
  type: Boolean,
  default: true,
})

const props = defineProps({
  wallDriven: Boolean,
  /** 槽位数量：SETUP=13|14；PLAYING=14−3×副露 */
  capacity: {
    type: Number,
    default: 14,
  },
  dealerTile: {
    type: String,
    default: '',
  },
  latestDrawnTile: {
    type: String,
    default: '',
  },
  highlightTile: {
    type: String,
    default: '',
  },
  /**
   * 切牌模式（仅 PLAYING 且轮到自家时由父组件显式打开）。
   * 不再用「张数===capacity」自动切牌，避免 SETUP 录满后误切。
   */
  discardMode: {
    type: Boolean,
    default: false,
  },
  /** 开局准备：强制点击=移除，禁止切牌 */
  setupMode: {
    type: Boolean,
    default: false,
  },
  /** 自家行动权聚焦：ring-emerald + shadow */
  turnFocused: {
    type: Boolean,
    default: false,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  /** 当前座位已手动插嵌锁定（展示「组牌」提示） */
  layoutPinned: {
    type: Boolean,
    default: false,
  },
  /** 可自摸时提示文案 */
  canSelfWin: {
    type: Boolean,
    default: false,
  },
  /**
   * 后台 EV 推演中：手牌仍可切，仅展示轻量提示（不禁用点击）
   */
  evCalculating: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits({
  /**
   * 切牌：必须带绝对下标，避免同名牌被 filter 清空
   * @param {string} tile
   * @param {number} index
   */
  'discard-tile': (tile, index) =>
    typeof tile === 'string' &&
    tile.length > 0 &&
    typeof index === 'number' &&
    index >= 0,
  'manual-sort': () => true,
  /**
   * 百搭插嵌：插入到 toIndex 之前（由会话层 moveJokerInHand 落盘并 pin）
   * @param {{ fromIndex: number, toIndex: number }} payload
   */
  'move-joker': (payload) =>
    payload &&
    typeof payload.fromIndex === 'number' &&
    typeof payload.toIndex === 'number',
  'reorder-tile': (payload) =>
    payload && Number.isInteger(payload.fromIndex) && Number.isInteger(payload.toIndex),
})

/** 仅当父组件显式开启 discardMode 且非 SETUP 时才切牌 */
const isDiscardReady = computed(
  () => !props.setupMode && !!props.discardMode,
)

const keyedTiles = computed(() => handTilesWithKeys(tiles.value))

const splitHand = computed(() => {
  const items = keyedTiles.value
  const drawn = props.latestDrawnTile
  if (
    drawn &&
    items.length > 0 &&
    items[items.length - 1].code === drawn
  ) {
    return {
      main: items.slice(0, -1),
      drawn: items[items.length - 1],
    }
  }
  return { main: items, drawn: null }
})

const emptySlotCount = computed(() =>
  Math.max(0, props.capacity - tiles.value.length),
)

const dragFrom = ref(null)
const dropHover = ref(null)
const handAnchor = ref(null)
const pointerDrag = ref(null)
let suppressClickUntil = 0
const selectedTileIndex = ref(null)
watch(tiles, () => { selectedTileIndex.value = null })

/** 百搭可挪：有财神即可插嵌（切牌/移除仍受 disabled 约束） */
const canArrangeJoker = computed(() => !!props.dealerTile)
const canArrangeTile = computed(() => props.wallDriven && tiles.value.length > 1)

function isHighlight(code) {
  return !!code && !!props.highlightTile && code === props.highlightTile
}

function isJoker(code) {
  return isJokerPhysical(code, props.dealerTile)
}

function isProxy(code) {
  return isWhiteboardProxy(code, props.dealerTile)
}

/**
 * @param {{ code: string, index: number }} item
 */
function handleTileClick(item) {
  if (Date.now() < suppressClickUntil) return
  if (!item?.code) return
  // 百搭在只读座位：点击不移除/不切
  if (props.disabled && isJoker(item.code)) return
  if (props.disabled) return
  if (isDiscardReady.value) {
    if (props.wallDriven && typeof window !== 'undefined' && window.matchMedia('(orientation: portrait) and (max-width: 768px)').matches) {
      if (selectedTileIndex.value !== item.index) {
        selectedTileIndex.value = item.index
        return
      }
    }
    selectedTileIndex.value = null
    emit('discard-tile', item.code, item.index)
    return
  }
  // 编辑态：按索引移出一张（录入修正）
  removeAt(item.index)
}

function removeAt(index) {
  if (index < 0 || index >= tiles.value.length) return
  const next = tiles.value.slice()
  next.splice(index, 1)
  tiles.value = next
}

function toggleAutoSort() {
  autoSort.value = !autoSort.value
}

function emitMoveJoker(fromIndex, toIndex) {
  if (fromIndex === toIndex) return
  emit('move-joker', { fromIndex, toIndex })
}

function insertionAt(clientX, clientY) {
  const buttons = [...(handAnchor.value?.querySelectorAll('button[data-hand-index]') || [])]
  if (!buttons.length) return null
  const centers = buttons.map((button) => {
    const rect = button.getBoundingClientRect()
    return { index: Number(button.dataset.handIndex), x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
  })
  const first = centers[0]
  const last = centers[centers.length - 1]
  const distance = Math.hypot(last.x - first.x, last.y - first.y) || 1
  const axisX = (last.x - first.x) / distance
  const axisY = (last.y - first.y) / distance
  const pointerPosition = (clientX - first.x) * axisX + (clientY - first.y) * axisY
  const closest = centers.reduce((best, center) => {
    const position = (center.x - first.x) * axisX + (center.y - first.y) * axisY
    const gap = Math.abs(pointerPosition - position)
    return gap < best.gap ? { center, position, gap } : best
  }, { center: first, position: 0, gap: Infinity })
  return Math.max(0, Math.min(tiles.value.length,
    closest.center.index + (pointerPosition > closest.position ? 1 : 0)))
}

function onTilePointerDown(event, item) {
  if (!canArrangeTile.value || event.button !== 0) return
  pointerDrag.value = { id: event.pointerId, fromIndex: item.index, x: event.clientX, y: event.clientY, active: false, insertAt: null }
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function onTilePointerMove(event) {
  const drag = pointerDrag.value
  if (!drag || drag.id !== event.pointerId) return
  if (!drag.active && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 8) return
  drag.active = true
  drag.insertAt = insertionAt(event.clientX, event.clientY)
  event.preventDefault()
}

function onTilePointerUp(event) {
  const drag = pointerDrag.value
  if (!drag || drag.id !== event.pointerId) return
  if (drag.active) {
    event.preventDefault()
    suppressClickUntil = Date.now() + 350
    if (drag.insertAt != null) emit('reorder-tile', { fromIndex: drag.fromIndex, toIndex: drag.insertAt })
  }
  pointerDrag.value = null
}

function onTilePointerCancel(event) {
  if (pointerDrag.value?.id === event.pointerId) pointerDrag.value = null
}

function onDragStart(e, item) {
  if (!isJoker(item.code) || !canArrangeJoker.value) {
    e.preventDefault()
    return
  }
  dragFrom.value = item.index
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', String(item.index))
}

function onDragOver(e, item) {
  if (dragFrom.value == null) return
  e.preventDefault()
  dropHover.value = item.index
}

function onDragLeave() {
  dropHover.value = null
}

function onDrop(e, item) {
  e.preventDefault()
  const from =
    dragFrom.value != null
      ? dragFrom.value
      : Number(e.dataTransfer.getData('text/plain'))
  dropHover.value = null
  dragFrom.value = null
  if (Number.isNaN(from) || from === item.index) return
  emitMoveJoker(from, item.index)
}

function onDragEnd() {
  dragFrom.value = null
  dropHover.value = null
}

function nudge(item, dir, e) {
  e?.stopPropagation?.()
  e?.preventDefault?.()
  if (!canArrangeJoker.value || !isJoker(item.code)) return
  const toIndex = dir > 0 ? item.index + 2 : item.index - 1
  if (toIndex < 0 || toIndex > tiles.value.length) return
  emitMoveJoker(item.index, toIndex)
}

function manualSort() {
  tiles.value = sortHandTiles(
    tiles.value,
    props.dealerTile,
    props.latestDrawnTile || undefined,
  )
  emit('manual-sort')
}

function tileButtonClass(item, { drawn = false } = {}) {
  return [
    'relative h-14 w-10 rounded-lg text-center transition select-none',
    isDiscardReady.value
      ? 'cursor-pointer shadow-md hover:-translate-y-1 hover:scale-105 hover:shadow-lg active:scale-95 active:translate-y-0'
      : 'cursor-pointer shadow-md hover:scale-105 hover:ring-2 hover:ring-rose-400/50 active:scale-95',
    drawn ? 'ring-2 ring-sky-400/60' : '',
    isHighlight(item.code)
      ? 'hand-champ-glow ring-2 ring-amber-300 scale-105 z-[1]'
      : '',
    isJoker(item.code)
      ? 'ring-2 ring-fuchsia-400/70 cursor-grab active:cursor-grabbing'
      : '',
    dropHover.value === item.index ? 'ring-2 ring-lime-300/80 scale-105' : '',
    pointerDrag.value?.active && pointerDrag.value.fromIndex === item.index ? 'hand-dragging' : '',
    pointerDrag.value?.active && pointerDrag.value.insertAt === item.index && pointerDrag.value.fromIndex !== item.index ? 'hand-insert-before' : '',
    pointerDrag.value?.active && pointerDrag.value.insertAt === tiles.value.length && item.index === tiles.value.length - 1 && pointerDrag.value.fromIndex !== item.index ? 'hand-insert-after' : '',
    selectedTileIndex.value === item.index ? 'hand-tile-selected -translate-y-2 ring-2 ring-amber-200 z-[2]' : '',
  ]
}
</script>

<template>
  <section
    class="w-full rounded-2xl border border-teal-700/40 bg-teal-950/50 p-5 sm:p-6 shadow-xl backdrop-blur-sm transition-[box-shadow,opacity] duration-300"
    :class="[
      wallDriven ? 'max-w-none' : 'max-w-2xl',
      wallDriven ? 'pve-stable-hand' : '',
      turnFocused
        ? 'ring-2 ring-emerald-500 shadow-lg opacity-100'
        : isDiscardReady
          ? 'ring-1 ring-amber-400/35'
          : '',
      disabled && !turnFocused ? 'opacity-75' : '',
    ]"
  >
    <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="text-lg font-semibold tracking-wide text-amber-50">
          手牌（{{ tiles.length }}/{{ capacity }}）
        </h2>
        <p v-if="wallDriven" class="pve-hand-caption mt-0.5 text-xs text-teal-300/80">
          {{ isDiscardReady ? (disabled ? '等待响应 · 手牌只读' : '切牌阶段 · 点击手牌打出') : '等待摸牌 · 手牌只读' }}
        </p>
        <p v-else class="mt-0.5 text-xs text-teal-300/70">
          <template v-if="setupMode">
            开局录入：点击牌面
            <span class="font-medium text-amber-200/90">移除</span>
            该张 · 目标 {{ capacity }} 张（{{ tiles.length }}/{{ capacity }}）
          </template>
          <template v-else-if="disabled && isDiscardReady">
            <span class="text-teal-400/80">非自家行动权 · 手牌只读</span>
          </template>
          <template v-else-if="isDiscardReady">
            <span class="font-medium text-amber-200/95">切牌阶段：</span>
            点击任意一张打出至牌河
            <span v-if="highlightTile" class="text-amber-200/90">
              · 冠军高亮
            </span>
            <span
              v-if="canSelfWin"
              class="ml-1 font-bold text-rose-200"
            >
              · 亦可宣告自摸
            </span>
            <span
              v-if="evCalculating"
              class="mt-1 block text-[11px] font-medium text-sky-200/90"
            >
              正在推演切牌 EV… 也可直接点击手牌快速切出
            </span>
          </template>
          <template v-else-if="tiles.length < capacity">
            <span class="font-medium text-sky-200/95">待摸 / 岭上补牌：</span>
            目标暗手 {{ capacity }} 张（当前 {{ tiles.length }}）· {{ wallDriven ? '轮到自家时自动摸牌' : '用选牌键盘摸入' }}
          </template>
          <template v-else>点击牌面可移出（录入中）</template>
          <span v-if="latestDrawnTile" class="text-sky-200/80">
            · 右侧为刚摸入
          </span>
          <span v-if="layoutPinned" class="ml-1 text-fuchsia-300/90">
            · 组牌锁定（摸/切/一键理牌后恢复）
          </span>
          <span v-else class="ml-1 text-fuchsia-300/70">
            · 「得」可拖拽或 ◀▶ 插嵌
          </span>
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          class="rounded-lg border px-2.5 py-1 text-[11px] font-medium transition"
          :class="
            autoSort
              ? 'border-amber-400/60 bg-amber-500/20 text-amber-100'
              : 'border-teal-600/45 text-teal-200/80 hover:border-teal-400/50'
          "
          @click="toggleAutoSort"
        >
          自动理牌 · {{ autoSort ? '开' : '关' }}
        </button>
        <button
          type="button"
          class="rounded-lg border border-teal-600/50 px-2.5 py-1 text-[11px] font-medium text-teal-100 transition hover:border-amber-400/50 hover:text-amber-100 disabled:opacity-40"
          :disabled="!tiles.length || disabled"
          @click="manualSort"
        >
          一键理牌
        </button>
      </div>
    </div>

    <div
      ref="handAnchor"
      class="flex flex-wrap items-end gap-1.5 sm:gap-2"
      :class="wallDriven ? 'pve-hand-anchor' : ''"
      role="list"
      aria-label="手牌槽位"
    >
      <TransitionGroup
        name="hand-move"
        tag="div"
        class="flex flex-wrap items-end gap-1.5 sm:gap-2"
      >
        <div
          v-for="item in splitHand.main"
          :key="item.uid"
          class="relative inline-flex flex-col items-center"
        >
          <div
            v-if="isJoker(item.code) && canArrangeJoker"
            class="mb-0.5 flex gap-0.5"
          >
            <button
              type="button"
              class="rounded bg-fuchsia-800/80 px-1 text-[9px] leading-none text-fuchsia-50 hover:bg-fuchsia-600 disabled:opacity-30"
              :disabled="item.index <= 0"
              title="左移「得」"
              @click="nudge(item, -1, $event)"
            >
              ◀
            </button>
            <button
              type="button"
              class="rounded bg-fuchsia-800/80 px-1 text-[9px] leading-none text-fuchsia-50 hover:bg-fuchsia-600 disabled:opacity-30"
              :disabled="item.index >= tiles.length - 1 - (splitHand.drawn ? 1 : 0)"
              title="右移「得」"
              @click="nudge(item, 1, $event)"
            >
              ▶
            </button>
          </div>
          <button
            type="button"
            role="listitem"
            :class="tileButtonClass(item)"
            :data-hand-index="item.index"
            :aria-pressed="wallDriven && isDiscardReady ? selectedTileIndex === item.index : undefined"
            :draggable="!wallDriven && isJoker(item.code) && canArrangeJoker"
            :aria-disabled="disabled && !isJoker(item.code)"
            :title="
              setupMode
                ? `移除 ${tileLabel(item.code)}`
                : isDiscardReady
                  ? `${selectedTileIndex === item.index ? '确认打出' : '打出'} ${tileLabel(item.code)}`
                  : `移出 ${tileLabel(item.code)}`
            "
            @click="handleTileClick(item)"
            @pointerdown="onTilePointerDown($event, item)"
            @pointermove="onTilePointerMove"
            @pointerup="onTilePointerUp"
            @pointercancel="onTilePointerCancel"
            @dragstart="onDragStart($event, item)"
            @dragover="onDragOver($event, item)"
            @dragleave="onDragLeave"
            @drop="onDrop($event, item)"
            @dragend="onDragEnd"
          >
            <span
              v-if="isJoker(item.code)"
              class="absolute -left-1 -top-1 z-[2] rounded bg-fuchsia-500 px-1 py-px text-[8px] font-bold text-white shadow"
            >
              得
            </span>
            <span
              v-else-if="isProxy(item.code)"
              class="absolute -left-1 -top-1 z-[2] rounded bg-slate-600/90 px-1 py-px text-[8px] font-bold text-amber-100 shadow"
              :title="`白板替身 → ${dealerTile}`"
            >
              替
            </span>
            <MahjongTile :code="item.code" />
          </button>
        </div>
      </TransitionGroup>

      <div
        v-if="splitHand.drawn"
        class="pve-drawn-slot ml-2 flex border-l border-dashed border-sky-400/40 pl-3 sm:ml-3 sm:pl-4"
      >
        <button
          :key="splitHand.drawn.uid"
          type="button"
          role="listitem"
          :class="tileButtonClass(splitHand.drawn, { drawn: true })"
          :data-hand-index="splitHand.drawn.index"
          :aria-pressed="wallDriven && isDiscardReady ? selectedTileIndex === splitHand.drawn.index : undefined"
          :draggable="!wallDriven && isJoker(splitHand.drawn.code) && canArrangeJoker"
          :aria-disabled="disabled && !isJoker(splitHand.drawn.code)"
          :title="
            isDiscardReady
              ? `${selectedTileIndex === splitHand.drawn.index ? '确认打出摸入张' : '打出摸入张'} ${tileLabel(splitHand.drawn.code)}`
              : tileLabel(splitHand.drawn.code)
          "
          @click="handleTileClick(splitHand.drawn)"
          @pointerdown="onTilePointerDown($event, splitHand.drawn)"
          @pointermove="onTilePointerMove"
          @pointerup="onTilePointerUp"
          @pointercancel="onTilePointerCancel"
          @dragstart="onDragStart($event, splitHand.drawn)"
          @dragover="onDragOver($event, splitHand.drawn)"
          @dragleave="onDragLeave"
          @drop="onDrop($event, splitHand.drawn)"
          @dragend="onDragEnd"
        >
          <span
            class="absolute -right-1 -top-1 z-[2] rounded bg-sky-500 px-1 py-px text-[8px] font-bold text-white shadow"
          >
            摸
          </span>
          <span
            v-if="isJoker(splitHand.drawn.code)"
            class="absolute -left-1 -top-1 z-[2] rounded bg-fuchsia-500 px-1 py-px text-[8px] font-bold text-white shadow"
          >
            得
          </span>
          <MahjongTile :code="splitHand.drawn.code" />
        </button>
      </div>

      <div
        v-for="n in emptySlotCount"
        :key="`empty-${n}`"
        class="aspect-[2/3] w-[2.65rem] min-h-[3.25rem] rounded-lg border border-dashed border-teal-700/40 bg-emerald-950/30 sm:w-11"
        aria-hidden="true"
      >
        <span
          class="flex h-full items-center justify-center text-[10px] text-teal-700/60"
        >
          {{ tiles.length + n }}
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.pve-stable-hand { position: relative; }
.pve-stable-hand button[role="listitem"] { touch-action:none; user-select:none; }
.pve-stable-hand button[role="listitem"].hand-dragging { z-index:5; opacity:.55; transform:translateY(-9px) scale(1.05); box-shadow:0 12px 22px #0008; }
.pve-stable-hand button[role="listitem"].hand-insert-before { transform:translateX(9px); outline:3px solid #fcd34d; outline-offset:2px; }
.pve-stable-hand button[role="listitem"].hand-insert-after { outline:3px solid #fcd34d; outline-offset:2px; }
.pve-stable-hand button[role="listitem"].hand-insert-before::before,
.pve-stable-hand button[role="listitem"].hand-insert-after::after { content:""; position:absolute; z-index:6; top:4px; bottom:4px; width:4px; border-radius:4px; background:#fcd34d; box-shadow:0 0 9px #fbbf24; pointer-events:none; }
.pve-stable-hand button[role="listitem"].hand-insert-before::before { left:-11px; }
.pve-stable-hand button[role="listitem"].hand-insert-after::after { right:-9px; }
.pve-stable-hand .hand-move-move,
.pve-stable-hand .hand-move-enter-active,
.pve-stable-hand .hand-move-leave-active { transition: none !important; }

.hand-champ-glow {
  animation: champ-glow 1.8s ease-in-out infinite;
  box-shadow:
    0 0 0 2px rgba(252, 211, 77, 0.55),
    0 0 18px 4px rgba(251, 191, 36, 0.45);
}

@keyframes champ-glow {
  0%,
  100% {
    box-shadow:
      0 0 0 2px rgba(252, 211, 77, 0.5),
      0 0 14px 2px rgba(251, 191, 36, 0.35);
  }
  50% {
    box-shadow:
      0 0 0 3px rgba(253, 224, 71, 0.85),
      0 0 22px 6px rgba(251, 191, 36, 0.55);
  }
}

.hand-move-move {
  transition: transform 0.35s cubic-bezier(0.22, 1, 0.36, 1);
}

.hand-move-enter-active,
.hand-move-leave-active {
  transition:
    opacity 0.28s ease,
    transform 0.28s ease;
}

.hand-move-enter-from,
.hand-move-leave-to {
  opacity: 0;
  transform: scale(0.85);
}

.hand-move-leave-active {
  position: absolute;
}

@media (prefers-reduced-motion: reduce) {
  .hand-champ-glow,
  .hand-move-move,
  .hand-move-enter-active,
  .hand-move-leave-active {
    animation: none;
    transition: none;
  }
}
</style>
