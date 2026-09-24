<script setup>
import { computed } from 'vue'
import {
  MAX_PER_TILE,
  TILE_GROUPS,
  tileLabel,
} from '../constants/tiles.js'

/** 已选暗手牌列表 */
const selected = defineModel({
  type: Array,
  default: () => [],
})

const props = defineProps({
  /** 暗手容量上限（SETUP=13|14；PLAYING 摸牌=当前+1） */
  maxCount: {
    type: Number,
    default: 14,
  },
  /**
   * 副露等已占用的牌（不计入暗手，但占用全场 4 张额度）
   * @type {string[]}
   */
  occupiedTiles: {
    type: Array,
    default: () => [],
  },
  /** 禁用点选（PLAYING 非摸牌时） */
  disabled: {
    type: Boolean,
    default: false,
  },
})

const handCounts = computed(() => {
  const map = Object.create(null)
  for (const t of selected.value) {
    map[t] = (map[t] || 0) + 1
  }
  return map
})

const occupiedCounts = computed(() => {
  const map = Object.create(null)
  for (const t of props.occupiedTiles) {
    map[t] = (map[t] || 0) + 1
  }
  return map
})

const handFull = computed(() => selected.value.length >= props.maxCount)

function handCountOf(code) {
  return handCounts.value[code] || 0
}

function occupiedOf(code) {
  return occupiedCounts.value[code] || 0
}

/** 该牌在暗手中还能再选几张（全场 ≤4） */
function roomLeft(code) {
  return MAX_PER_TILE - occupiedOf(code) - handCountOf(code)
}

function isFull(code) {
  return props.disabled || roomLeft(code) <= 0 || handFull.value
}

function pick(code) {
  if (props.disabled || isFull(code)) return
  // 只推入纯字符串牌码，杜绝 Event 等对象入账
  if (typeof code !== 'string' || !code) return
  selected.value = [...selected.value, code]
}

function clearAll() {
  if (props.disabled) return
  selected.value = []
}
</script>

<template>
  <section
    class="w-full max-w-2xl rounded-2xl border border-teal-700/40 bg-teal-950/50 p-5 sm:p-6 shadow-xl backdrop-blur-sm"
  >
    <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-lg font-semibold tracking-wide text-amber-50">
        选牌键盘
      </h2>
      <div class="flex items-center gap-3 text-sm text-teal-200/80">
        <span>已选 {{ selected.length }}/{{ maxCount }} 张</span>
        <button
          type="button"
          class="rounded-lg border border-teal-600/40 px-3 py-1 text-teal-100 transition hover:border-amber-400/50 hover:text-amber-50 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="selected.length === 0 || disabled"
          @click="clearAll"
        >
          清空重选
        </button>
      </div>
    </div>

    <div class="space-y-5">
      <div v-for="group in TILE_GROUPS" :key="group.key">
        <p class="mb-2 text-xs font-medium uppercase tracking-wider text-teal-300/70">
          {{ group.label }}
        </p>
        <div class="grid grid-cols-5 gap-2 sm:grid-cols-9">
          <button
            v-for="code in group.tiles"
            :key="code"
            type="button"
            class="relative flex flex-col items-center justify-center rounded-xl border px-1 py-2 text-sm font-medium transition"
            :class="
              isFull(code)
                ? 'cursor-not-allowed border-slate-600/40 bg-slate-800/50 text-slate-500'
                : 'border-teal-600/45 bg-emerald-900/55 text-amber-50 hover:border-amber-400/60 hover:bg-emerald-800/70 active:scale-95'
            "
            :disabled="isFull(code)"
            :aria-label="`${tileLabel(code)}，暗手 ${handCountOf(code)}，副露占用 ${occupiedOf(code)}`"
            @click="pick(code)"
          >
            <span>{{ tileLabel(code) }}</span>
            <span
              class="mt-0.5 text-[10px] tabular-nums"
              :class="isFull(code) ? 'text-slate-500' : 'text-teal-300/70'"
            >
              余{{ roomLeft(code) }} · {{ handCountOf(code) + occupiedOf(code) }}/{{ MAX_PER_TILE }}
            </span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
