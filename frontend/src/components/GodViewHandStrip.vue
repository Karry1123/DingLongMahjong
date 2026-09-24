<script setup>
/**
 * 上帝视角单座暗手条：支持「得」拖拽 / ◀▶ 微调插嵌。
 */
import { computed, ref } from 'vue'
import { tileLabel, tileSuitClass } from '../constants/tiles.js'
import {
  handTilesWithKeys,
  isJokerPhysical,
  isWhiteboardProxy,
} from '../utils/tileSorter.js'

const props = defineProps({
  seat: { type: String, required: true },
  /** 已按展示序排好的暗手（含摸入张在末尾的情况） */
  tiles: { type: Array, default: () => [] },
  /** 摸入张下标；无则为 -1 */
  drawnIndex: { type: Number, default: -1 },
  dealerTile: { type: String, default: '' },
  active: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  bestTile: { type: String, default: '' },
  justify: {
    type: String,
    default: 'start', // start | center
  },
})

const emit = defineEmits(['discard-tile', 'move-joker'])

const items = computed(() => handTilesWithKeys(props.tiles || []))

const dragFrom = ref(null)
const dropHover = ref(null)

function isJoker(code) {
  return isJokerPhysical(code, props.dealerTile)
}

function isDrawnItem(item) {
  return props.drawnIndex >= 0 && item.index === props.drawnIndex
}

function tileClass(item) {
  const code = item.code
  const joker = isJoker(code)
  const proxy = isWhiteboardProxy(code, props.dealerTile)
  const drawn = isDrawnItem(item)
  return [
    tileSuitClass(code),
    'relative rounded border px-1 py-1 text-[10px] font-medium transition duration-150 sm:text-[11px]',
    props.active
      ? 'cursor-pointer border-amber-400/60 bg-emerald-900/70 hover:bg-amber-500/25'
      : 'border-teal-800/40 bg-teal-950/50',
    joker ? 'ring-2 ring-fuchsia-400/65 cursor-grab active:cursor-grabbing' : '',
    drawn ? 'ring-2 ring-sky-400/55 ml-1' : '',
    proxy && !joker ? 'outline outline-1 outline-violet-300/50' : '',
    code === props.bestTile && props.active
      ? 'border-amber-300 bg-amber-500/30 ring-2 ring-amber-300'
      : '',
    dropHover.value === item.index
      ? 'ring-2 ring-lime-300/80 scale-105'
      : '',
  ]
}

function onDragStart(e, item) {
  if (!isJoker(item.code) || props.disabled) {
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
  // 插入到目标牌之前
  emit('move-joker', {
    seat_wind: props.seat,
    fromIndex: from,
    toIndex: item.index,
  })
}

function onDragEnd() {
  dragFrom.value = null
  dropHover.value = null
}

function nudge(item, dir, e) {
  e?.stopPropagation?.()
  e?.preventDefault?.()
  if (props.disabled || !isJoker(item.code)) return
  const toIndex = item.index + dir
  if (toIndex < 0 || toIndex > (props.tiles?.length || 0)) return
  // 右移：插入到 index+2 之前 ≡ 与右侧交换感
  emit('move-joker', {
    seat_wind: props.seat,
    fromIndex: item.index,
    toIndex: dir > 0 ? item.index + 2 : item.index - 1,
  })
}

function onTileClick(item) {
  if (props.disabled) return
  // 非行动座：只允许挪百搭（拖拽/箭头），点击不切牌
  if (!props.active) return
  emit('discard-tile', {
    seat_wind: props.seat,
    tile: item.code,
    index: item.index,
  })
}

const wrapClass = computed(() =>
  props.justify === 'center'
    ? 'mb-1 flex flex-wrap items-end justify-center gap-0.5'
    : 'mb-1 flex flex-wrap items-end gap-0.5',
)
</script>

<template>
  <div :class="wrapClass">
    <template v-for="item in items" :key="`${seat}-${item.uid}`">
      <span
        v-if="drawnIndex >= 0 && item.index === drawnIndex"
        class="mx-0.5 hidden h-6 w-px self-center border-l border-dashed border-sky-400/45 sm:inline-block"
        aria-hidden="true"
      />
      <div class="relative inline-flex flex-col items-center">
        <!-- 百搭微调箭头 -->
        <div
          v-if="isJoker(item.code) && !disabled"
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
            :disabled="item.index >= tiles.length - 1"
            title="右移「得」"
            @click="nudge(item, 1, $event)"
          >
            ▶
          </button>
        </div>
        <button
          type="button"
          :class="tileClass(item)"
          :draggable="isJoker(item.code) && !disabled"
          :aria-disabled="disabled || (!active && !isJoker(item.code))"
          @click="onTileClick(item)"
          @dragstart="onDragStart($event, item)"
          @dragover="onDragOver($event, item)"
          @dragleave="onDragLeave"
          @drop="onDrop($event, item)"
          @dragend="onDragEnd"
        >
          <span
            v-if="isJoker(item.code)"
            class="absolute -top-1.5 left-1/2 -translate-x-1/2 rounded bg-fuchsia-500 px-0.5 text-[8px] font-bold text-white"
            >得</span
          >
          {{ tileLabel(item.code) }}
        </button>
      </div>
    </template>
    <span
      v-if="!tiles.length"
      class="text-[10px] text-teal-500/70"
      >无暗手</span
    >
  </div>
</template>
