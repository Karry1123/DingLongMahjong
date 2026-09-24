<script setup>
import { computed, ref } from 'vue'
import MeldTiles from './MeldTiles.vue'
import {
  MAX_PER_TILE,
  TILE_GROUPS,
  tileLabel,
} from '../constants/tiles.js'

/** @typedef {{ meld_type: string, tiles: string[] }} Meld */

const melds = defineModel({
  type: Array,
  default: () => [],
})

const props = defineProps({
  readOnly: Boolean,
  compact: Boolean,
  dealerTile: { type: String, default: '' },
  /** 暗手牌，用于校验单种牌全场 ≤4 */
  handTiles: {
    type: Array,
    default: () => [],
  },
  /** 已见废牌（一并计入占用） */
  discardedTiles: {
    type: Array,
    default: () => [],
  },
  /** 对手等其它占用 */
  extraOccupied: {
    type: Array,
    default: () => [],
  },
})

const MAX_MELDS = 4

const MELD_MODES = [
  { type: 'pong', label: '碰', need: 3 },
  { type: 'ming_gang', label: '明杠', need: 4 },
  { type: 'an_gang', label: '暗杠', need: 4 },
  { type: 'chi', label: '吃', need: 3 },
]

const MELD_TYPE_LABEL = {
  chi: '吃',
  pong: '碰',
  ming_gang: '明杠',
  an_gang: '暗杠',
}

/** 当前添加模式；null 表示未展开选牌 */
const addMode = ref(null)

const atMeldCap = computed(() => melds.value.length >= MAX_MELDS)

/** 暗手 + 已见 + 已有副露 的占用 */
const occupied = computed(() => {
  const map = Object.create(null)
  const bump = (t) => {
    map[t] = (map[t] || 0) + 1
  }
  for (const t of props.handTiles) bump(t)
  for (const t of props.discardedTiles) bump(t)
  for (const t of props.extraOccupied) bump(t)
  for (const m of melds.value) {
    for (const t of m.tiles) bump(t)
  }
  return map
})

function remaining(code) {
  return MAX_PER_TILE - (occupied.value[code] || 0)
}

/** 生成副露牌组；不合法返回 null */
function buildMeldTiles(mode, code) {
  if (mode === 'pong') return [code, code, code]
  if (mode === 'ming_gang' || mode === 'an_gang') {
    return [code, code, code, code]
  }
  if (mode === 'chi') {
    if (code.length !== 2 || !'mps'.includes(code[1])) return null
    const n = Number(code[0])
    if (n < 1 || n > 7) return null
    const s = code[1]
    return [`${n}${s}`, `${n + 1}${s}`, `${n + 2}${s}`]
  }
  return null
}

/** 该模式下点选 code 是否可添加 */
function canAddWith(mode, code) {
  if (atMeldCap.value) return false
  const tiles = buildMeldTiles(mode, code)
  if (!tiles) return false
  const need = Object.create(null)
  for (const t of tiles) need[t] = (need[t] || 0) + 1
  for (const t of Object.keys(need)) {
    if (need[t] > remaining(t)) return false
  }
  return true
}

function selectMode(mode) {
  if (props.readOnly) return
  if (atMeldCap.value) return
  addMode.value = addMode.value === mode ? null : mode
}

function onPickTile(code) {
  if (props.readOnly) return
  const mode = addMode.value
  if (!mode || !canAddWith(mode, code)) return
  const tiles = buildMeldTiles(mode, code)
  melds.value = [
    ...melds.value,
    { meld_type: mode, tiles },
  ]
  addMode.value = null
}

function removeMeld(index) {
  if (props.readOnly) return
  if (index < 0 || index >= melds.value.length) return
  const next = melds.value.slice()
  next.splice(index, 1)
  melds.value = next
}

function clearMelds() {
  if (props.readOnly) return
  melds.value = []
  addMode.value = null
}

/** 吃牌键盘只显示可作起点的 1~7 序数牌 */
function tilesForMode(group) {
  if (addMode.value !== 'chi') return group.tiles
  if (group.key === 'z') return []
  return group.tiles.filter((c) => {
    const n = Number(c[0])
    return n >= 1 && n <= 7
  })
}
</script>

<template>
  <section
    class="w-full max-w-2xl rounded-2xl border border-teal-700/40 bg-teal-950/50 shadow-xl backdrop-blur-sm"
    :class="compact ? 'compact-melds p-2.5 sm:p-3' : 'p-5 sm:p-6'"
  >
    <div class="flex flex-wrap items-center justify-between gap-2" :class="compact ? 'mb-1' : 'mb-4'">
      <div>
        <h2 class="font-semibold tracking-wide text-amber-50" :class="compact ? 'text-sm' : 'text-lg'">
          副露（{{ melds.length }}/{{ MAX_MELDS }}）
        </h2>
        <p v-if="!readOnly" class="mt-0.5 text-xs text-teal-300/70">
          每组占 3 个牌位；删除后暗手容量自动回升
        </p>
      </div>
      <button
        v-if="!readOnly"
        type="button"
        class="rounded-lg border border-teal-600/40 px-3 py-1 text-xs text-teal-100 transition hover:border-rose-400/50 hover:text-rose-100 disabled:opacity-40"
        :disabled="melds.length === 0"
        @click="clearMelds"
      >
        清空副露
      </button>
    </div>

    <!-- 已录入副露 -->
    <div
      v-if="melds.length"
      :class="compact ? 'mb-0 space-y-1' : 'mb-4 space-y-2'"
      role="list"
      aria-label="已录入副露"
    >
      <component
        :is="readOnly ? 'div' : 'button'"
        v-for="(m, i) in melds"
        :key="`meld-${i}-${m.meld_type}`"
        type="button"
        role="listitem"
        class="flex w-full items-center gap-3 rounded-xl border border-teal-700/45 bg-emerald-950/40 text-left transition hover:border-rose-400/45 hover:bg-rose-950/20"
        :class="compact ? 'px-2 py-1' : 'px-3 py-2.5'"
        :title="readOnly ? undefined : `删除此组${MELD_TYPE_LABEL[m.meld_type] || m.meld_type}`"
        @click="removeMeld(i)"
      >
        <span
          class="shrink-0 rounded-md bg-teal-800/60 px-2 py-0.5 text-xs font-medium text-amber-100"
        >
          {{ MELD_TYPE_LABEL[m.meld_type] || m.meld_type }}
        </span>
        <MeldTiles :meld="m" :dealer-tile="dealerTile" />
        <span v-if="!readOnly" class="shrink-0 text-xs text-teal-400/80">删除</span>
      </component>
    </div>
    <p v-else class="text-teal-400/70" :class="compact ? 'text-xs' : 'mb-4 text-sm'">
      {{ readOnly ? '尚未声明副露' : '尚未录入副露' }}
    </p>

    <!-- 添加操作 -->
    <div v-if="!readOnly" class="mb-3">
      <p class="mb-2 text-sm text-teal-200/90">添加副露</p>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="mode in MELD_MODES"
          :key="mode.type"
          type="button"
          class="rounded-lg px-3 py-1.5 text-sm font-medium transition"
          :class="
            atMeldCap
              ? 'cursor-not-allowed bg-slate-800/50 text-slate-500'
              : addMode === mode.type
                ? 'bg-amber-500 text-emerald-950 shadow'
                : 'border border-teal-600/50 text-teal-100 hover:border-amber-400/50 hover:text-amber-50'
          "
          :disabled="atMeldCap"
          @click="selectMode(mode.type)"
        >
          {{ mode.label }}
        </button>
      </div>
      <p v-if="atMeldCap" class="mt-2 text-xs text-amber-200/80">
        已达 4 组上限
      </p>
      <p v-else-if="addMode" class="mt-2 text-xs text-teal-300/75">
        <template v-if="addMode === 'chi'">
          选择起始序数牌（如 2 条 → 2–3–4 条）
        </template>
        <template v-else-if="addMode === 'pong'">
          选择一张牌，自动生成三张碰
        </template>
        <template v-else>
          选择一张牌，自动生成四张杠
        </template>
      </p>
    </div>

    <!-- 选牌键盘（添加模式时展开） -->
    <div v-if="!readOnly && addMode && !atMeldCap" class="space-y-3 border-t border-teal-800/40 pt-3">
      <div v-for="group in TILE_GROUPS" :key="group.key">
        <template v-if="tilesForMode(group).length">
          <p class="mb-1.5 text-[10px] font-medium tracking-wider text-teal-400/70">
            {{ group.label }}
          </p>
          <div class="grid grid-cols-5 gap-1.5 sm:grid-cols-9">
            <button
              v-for="code in tilesForMode(group)"
              :key="code"
              type="button"
              class="rounded-lg border px-1 py-2 text-xs font-medium transition"
              :class="
                canAddWith(addMode, code)
                  ? 'border-teal-600/45 bg-emerald-900/55 text-amber-50 hover:border-amber-400/60'
                  : 'cursor-not-allowed border-slate-700/40 bg-slate-900/40 text-slate-600'
              "
              :disabled="!canAddWith(addMode, code)"
              :aria-label="`以 ${tileLabel(code)} 添加${MELD_TYPE_LABEL[addMode]}`"
              @click="onPickTile(code)"
            >
              {{ tileLabel(code) }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>
<style scoped>
.compact-melds :deep(.mahjong-tile) { --tw:33px; --th:47px; --face-font:18px; --honor-font:25px; }
.compact-melds :deep([aria-label="副露牌组"]) { padding-top:0; padding-bottom:2px; gap:3px; }
</style>
