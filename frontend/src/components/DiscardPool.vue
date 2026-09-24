<script setup>
import { computed, ref } from 'vue'
import {
  MAX_PER_TILE,
  TILE_GROUPS,
  tileLabel,
} from '../constants/tiles.js'

/** 场上已见废牌列表 */
const discarded = defineModel({
  type: Array,
  default: () => [],
})

const props = defineProps({
  /** 当前手牌，用于限制同种牌总量不超过 4（再扣公示） */
  handTiles: {
    type: Array,
    default: () => [],
  },
  /** 当盘财神：同名牌额外占用 1 张公示 */
  dealerTile: {
    type: String,
    default: '',
  },
  /**
   * 其它已占用物理牌（副露、对手河等，不含本面板已见列表）
   * @type {string[]}
   */
  extraOccupied: {
    type: Array,
    default: () => [],
  },
})

const expanded = ref(false)

const counts = computed(() => {
  const map = Object.create(null)
  for (const t of discarded.value) {
    map[t] = (map[t] || 0) + 1
  }
  return map
})

const handCounts = computed(() => {
  const map = Object.create(null)
  for (const t of props.handTiles) {
    map[t] = (map[t] || 0) + 1
  }
  for (const t of props.extraOccupied) {
    map[t] = (map[t] || 0) + 1
  }
  return map
})

function countOf(code) {
  return counts.value[code] || 0
}

/** 该物理牌还能往本河里放几张 */
function maxAddable(code) {
  const otherN = handCounts.value[code] || 0
  const shown = code === props.dealerTile ? 1 : 0
  return Math.max(0, MAX_PER_TILE - otherN - shown - countOf(code))
}

function isFull(code) {
  return maxAddable(code) <= 0
}

function addOne(code) {
  if (isFull(code)) return
  discarded.value = [...discarded.value, code]
}

function removeOne(code) {
  const idx = discarded.value.lastIndexOf(code)
  if (idx < 0) return
  const next = discarded.value.slice()
  next.splice(idx, 1)
  discarded.value = next
}

function onKeyClick(code) {
  if (!isFull(code)) {
    addOne(code)
    return
  }
  // 已达上限：再点则减一张，便于快速修正
  if (countOf(code) > 0) removeOne(code)
}

function clearAll() {
  discarded.value = []
}
</script>

<template>
  <section
    class="w-full max-w-2xl overflow-hidden rounded-2xl border border-teal-700/40 bg-teal-950/50 shadow-xl backdrop-blur-sm"
  >
    <!-- 折叠标题栏 -->
    <button
      type="button"
      class="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left transition hover:bg-teal-900/40 sm:px-6"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <div class="min-w-0">
        <h2 class="text-lg font-semibold tracking-wide text-amber-50">
          自家牌河
        </h2>
        <p class="mt-0.5 truncate text-xs text-teal-300/70">
          {{
            discarded.length
              ? `已记录 ${discarded.length} 张 · 点击展开编辑`
              : '折叠面板 · 记录自家打出的牌'
          }}
        </p>
      </div>
      <span
        class="shrink-0 text-teal-200/80 transition"
        :class="expanded ? 'rotate-180' : ''"
        aria-hidden="true"
      >
        ▾
      </span>
    </button>

    <!-- 已见摘要条（折叠时也可瞥见） -->
    <div
      v-if="discarded.length && !expanded"
      class="flex flex-wrap gap-1 border-t border-teal-800/40 px-5 py-2.5 sm:px-6"
    >
      <span
        v-for="(code, i) in discarded"
        :key="`sum-${code}-${i}`"
        class="rounded-md border border-slate-500/40 bg-slate-800/50 px-1.5 py-0.5 text-[10px] text-slate-200"
      >
        {{ tileLabel(code) }}
      </span>
    </div>

    <!-- 展开：紧凑选牌键盘 -->
    <div
      v-show="expanded"
      class="border-t border-teal-800/40 px-4 pb-4 pt-3 sm:px-5"
    >
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p class="text-xs text-teal-300/75">
          单击添加；已选中的再点减一张。同种不超过壁牌剩余。
        </p>
        <button
          type="button"
          class="rounded-lg border border-teal-600/40 px-2.5 py-1 text-xs text-teal-100 transition hover:border-rose-400/50 hover:text-rose-100 disabled:opacity-40"
          :disabled="discarded.length === 0"
          @click="clearAll"
        >
          清空已见
        </button>
      </div>

      <div
        v-if="discarded.length"
        class="mb-3 flex flex-wrap gap-1 rounded-lg border border-teal-800/50 bg-emerald-950/40 p-2"
      >
        <button
          v-for="(code, i) in discarded"
          :key="`d-${code}-${i}`"
          type="button"
          class="rounded-md border border-slate-500/40 bg-slate-700/40 px-2 py-0.5 text-[11px] text-slate-100 transition hover:bg-rose-500/30"
          :title="`移除 ${tileLabel(code)}`"
          @click="removeOne(code)"
        >
          {{ tileLabel(code) }}
        </button>
      </div>

      <div class="space-y-3">
        <div v-for="group in TILE_GROUPS" :key="group.key">
          <p class="mb-1.5 text-[10px] font-medium tracking-wider text-teal-400/70">
            {{ group.label }}
          </p>
          <div class="grid grid-cols-7 gap-1 sm:grid-cols-9">
            <button
              v-for="code in group.tiles"
              :key="code"
              type="button"
              class="relative rounded-lg border px-0.5 py-1.5 text-[11px] font-medium transition sm:text-xs"
              :class="
                isFull(code) && countOf(code) === 0
                  ? 'cursor-not-allowed border-slate-700/40 bg-slate-900/40 text-slate-600'
                  : countOf(code) > 0
                    ? 'border-amber-500/50 bg-amber-500/20 text-amber-50'
                    : 'border-teal-700/40 bg-emerald-950/50 text-teal-100 hover:border-teal-500/60'
              "
              :disabled="isFull(code) && countOf(code) === 0"
              :aria-label="`${tileLabel(code)} 已见 ${countOf(code)}`"
              @click="onKeyClick(code)"
            >
              {{ tileLabel(code) }}
              <span
                v-if="countOf(code)"
                class="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-amber-400 px-0.5 text-[9px] font-bold text-emerald-950"
              >
                {{ countOf(code) }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
