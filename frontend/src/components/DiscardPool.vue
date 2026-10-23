<script setup>
import MahjongTile from './MahjongTile.vue'
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
    class="w-full max-w-2xl overflow-hidden rounded-md border border-line/[.16] bg-ink-950/55 shadow-xl backdrop-blur-sm"
  >
    <!-- 折叠标题栏 -->
    <button
      type="button"
      class="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left transition hover:bg-ink-800/40 sm:px-6"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <div class="min-w-0">
        <h2 class="text-lg font-semibold tracking-wide text-fog-100">
          自家牌河
        </h2>
        <p class="mt-0.5 truncate text-xs text-fog-400/80">
          {{
            discarded.length
              ? `已记录 ${discarded.length} 张 · 点击展开编辑`
              : '折叠面板 · 记录自家打出的牌'
          }}
        </p>
      </div>
      <span
        class="shrink-0 text-fog-400 transition"
        :class="expanded ? 'rotate-180' : ''"
        aria-hidden="true"
      >
        ▾
      </span>
    </button>

    <!-- 已见摘要条（折叠时也可瞥见） -->
    <div
      v-if="discarded.length && !expanded"
      class="flex flex-wrap gap-1 border-t border-accent-line/[.16] px-5 py-2.5 sm:px-6"
    >
      <span
        v-for="(code, i) in discarded"
        :key="`sum-${code}-${i}`"
        class="rounded-md border border-fog-600/40 bg-ink-800/50 px-1.5 py-0.5 text-[10px] text-fog-300"
      >
        <MahjongTile :code="code" style="--tw:22px; --th:calc(var(--tw)*4/3); margin-bottom:0" />
      </span>
    </div>

    <!-- 展开：紧凑选牌键盘 -->
    <div
      v-show="expanded"
      class="border-t border-accent-line/[.16] px-4 pb-4 pt-3 sm:px-5"
    >
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p class="text-xs text-fog-400/80">
          单击添加；已选中的再点减一张。同种不超过壁牌剩余。
        </p>
        <button
          type="button"
          class="rounded-lg border border-accent-line/30 px-2.5 py-1 text-xs text-fog-100 transition hover:border-danger/50 hover:text-danger disabled:opacity-40"
          :disabled="discarded.length === 0"
          @click="clearAll"
        >
          清空已见
        </button>
      </div>

      <div
        v-if="discarded.length"
        class="mb-3 flex flex-wrap gap-1 rounded-lg border border-accent-line/[.16] bg-ink-900/40 p-2"
      >
        <button
          v-for="(code, i) in discarded"
          :key="`d-${code}-${i}`"
          type="button"
          class="rounded-md border border-fog-600/40 bg-ink-700/40 px-2 py-0.5 text-[11px] text-fog-100 transition hover:bg-danger/20"
          :title="`移除 ${tileLabel(code)}`"
          @click="removeOne(code)"
        >
          <MahjongTile :code="code" style="--tw:22px; --th:calc(var(--tw)*4/3); margin-bottom:0" />
        </button>
      </div>

      <div class="space-y-3">
        <div v-for="group in TILE_GROUPS" :key="group.key">
          <p class="mb-1.5 text-[10px] font-medium tracking-wider text-fog-500/80">
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
                  ? 'cursor-not-allowed border-fog-600/40 bg-ink-900/40 text-fog-600'
                  : countOf(code) > 0
                    ? 'border-gilt-500/50 bg-gilt-500/20 text-fog-100'
                    : 'border-accent-line/[.16] bg-ink-900/50 text-fog-100 hover:border-accent-line/45'
              "
              :disabled="isFull(code) && countOf(code) === 0"
              :aria-label="`${tileLabel(code)} 已见 ${countOf(code)}`"
              @click="onKeyClick(code)"
            >
              <MahjongTile :code="code" style="--tw:22px; --th:calc(var(--tw)*4/3); margin-bottom:0" />
              <span
                v-if="countOf(code)"
                class="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-gilt-400 px-0.5 text-[9px] font-bold text-bronze-900"
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
