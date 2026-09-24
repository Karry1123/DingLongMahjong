<script setup>
/**
 * 自摸和牌醒目横幅 + 明细展开 + 宣告按钮
 */
import { computed, ref } from 'vue'
import { tileLabel } from '../constants/tiles.js'

const props = defineProps({
  info: {
    type: Object,
    required: true,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['declare', 'dismiss'])

const showDetails = ref(false)

const hardLabel = computed(
  () => props.info?.hard_hu_label || (props.info?.is_hard_hu ? '硬胡' : '软胡'),
)

const finalHu = computed(
  () => props.info?.final_hu ?? props.info?.final_points ?? 0,
)

const winTileLabel = computed(() =>
  props.info?.win_tile ? tileLabel(props.info.win_tile) : '—',
)

const fans = computed(() => props.info?.details?.fans || {})

const fanEntries = computed(() =>
  Object.entries(fans.value).filter(([, v]) => Number(v) > 0),
)

const paymentNote = computed(
  () => props.info?.payments?.label || '',
)
</script>

<template>
  <section
    class="relative overflow-hidden rounded-2xl border-2 border-amber-300/90 bg-gradient-to-br from-rose-700 via-amber-600 to-yellow-500 p-4 shadow-2xl shadow-rose-900/50 sm:p-5"
    aria-live="assertive"
    aria-label="自摸和牌提醒"
  >
    <div
      class="pointer-events-none absolute -right-6 -top-6 h-28 w-28 rounded-full bg-white/20 blur-2xl"
    />
    <div
      class="pointer-events-none absolute -bottom-8 left-10 h-24 w-24 rounded-full bg-rose-400/30 blur-2xl"
    />

    <div class="relative flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <p
          class="text-xs font-bold uppercase tracking-[0.22em] text-amber-100/90"
        >
          自摸达成
        </p>
        <h2 class="mt-1 text-xl font-black tracking-wide text-amber-50 sm:text-2xl">
          已达成自摸和牌！预估
          <span class="text-yellow-100">{{ finalHu }}</span>
          胡（{{ hardLabel }}）
        </h2>
        <p class="mt-1 text-sm text-amber-50/85">
          胡张 {{ winTileLabel }}
          <span v-if="info.fan != null"> · {{ info.fan }} 翻</span>
          <span v-if="paymentNote"> · {{ paymentNote }}</span>
        </p>
      </div>

      <div class="flex flex-shrink-0 flex-wrap gap-2">
        <button
          type="button"
          class="rounded-xl bg-amber-50 px-5 py-3 text-base font-black text-rose-800 shadow-lg transition hover:scale-[1.03] hover:bg-white active:scale-95 disabled:opacity-50"
          :disabled="disabled"
          @click="emit('declare')"
        >
          宣告自摸和牌
        </button>
        <button
          type="button"
          class="rounded-xl border border-amber-100/50 bg-rose-950/30 px-3 py-3 text-sm font-semibold text-amber-50/90 transition hover:bg-rose-950/50"
          :disabled="disabled"
          @click="emit('dismiss')"
        >
          暂不胡 · 继续切牌
        </button>
      </div>
    </div>

    <button
      type="button"
      class="relative mt-3 text-left text-xs font-semibold text-amber-100/90 underline-offset-2 hover:underline"
      @click="showDetails = !showDetails"
    >
      {{ showDetails ? '收起算胡明细' : '展开算胡明细' }}
    </button>

    <div
      v-if="showDetails"
      class="relative mt-2 rounded-xl border border-amber-100/35 bg-rose-950/35 px-3 py-3 text-sm text-amber-50"
    >
      <dl class="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div>
          <dt class="text-[11px] text-amber-100/70">底胡</dt>
          <dd class="font-bold tabular-nums">{{ info.base_hu }}</dd>
        </div>
        <div>
          <dt class="text-[11px] text-amber-100/70">牌型胡</dt>
          <dd class="font-bold tabular-nums">{{ info.tile_hu }}</dd>
        </div>
        <div>
          <dt class="text-[11px] text-amber-100/70">翻数</dt>
          <dd class="font-bold tabular-nums">{{ info.fan }}</dd>
        </div>
        <div>
          <dt class="text-[11px] text-amber-100/70">终局 H_final</dt>
          <dd class="font-bold tabular-nums">{{ finalHu }}</dd>
        </div>
      </dl>
      <ul v-if="fanEntries.length" class="mt-2 space-y-0.5 text-xs text-amber-100/85">
        <li v-for="([k, v]) in fanEntries" :key="k">
          {{ k }}：+{{ v }} 翻
        </li>
      </ul>
      <p
        v-if="info.restored_jokers"
        class="mt-2 text-xs text-amber-100/80"
      >
        得还原 {{ info.restored_jokers }} 张
      </p>
      <p class="mt-1 text-[11px] text-amber-100/65">
        自摸 +2 胡（不加翻）· {{ hardLabel }}
        {{ info.is_hard_hu ? '（硬碰硬 +1 翻）' : '' }}
      </p>
    </div>
  </section>
</template>
