<script setup>
/**
 * 开局配置：只选「我的门风」+ 财神；庄家固定东风位（rule.md §1）。
 * SETUP：可改配置；录满起手后高亮「开始对局」。
 */
import { computed } from 'vue'
import { ALL_TILES, SEAT_WINDS, tileLabel } from '../constants/tiles.js'
import { buildTableFromSelfWind, DEALER_SEAT } from '../utils/seatLayout.js'

const dealerTile = defineModel('dealerTile', {
  type: String,
  default: '5m',
})

/** 我的门风 */
const seatWind = defineModel('seatWind', {
  type: String,
  default: 'E',
})

const props = defineProps({
  /** 对局进行中（PLAYING） */
  locked: {
    type: Boolean,
    default: false,
  },
  /** 起手是否已录满目标张数 */
  canStart: {
    type: Boolean,
    default: false,
  },
  /** 目标起手张数提示 */
  targetHandCount: {
    type: Number,
    default: 14,
  },
  /** 当前已录入张数 */
  handCount: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits({
  /** 开始对局：SETUP → PLAYING */
  'confirm-start': () => true,
  /** 重新开局：回到 SETUP */
  'reopen-table': () => true,
})

const table = computed(() => buildTableFromSelfWind(seatWind.value))

const selfIsDealer = computed(() => table.value.isDealer)

function onPickWind(code) {
  if (props.locked) return
  seatWind.value = code
}

function onConfirmStart() {
  if (props.locked || !props.canStart) return
  emit('confirm-start')
}

function onReopen() {
  if (!props.locked) return
  const ok = window.confirm(
    '重新开局将清空手牌、副露、牌河与推演历史，并解锁门风选择。确定吗？',
  )
  if (ok) emit('reopen-table')
}
</script>

<template>
  <section
    class="w-full max-w-2xl rounded-2xl border border-accent-line/45 bg-ink-800 p-5 sm:p-6 shadow-xl backdrop-blur-sm"
  >
    <div class="relative mb-4 flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-lg font-semibold tracking-wide text-fog-100">
        顶龙麻将 · 对局配置
      </h2>
        <span class="ui-huiwen game-config-huiwen" aria-hidden="true" />
      <span
        class="rounded-lg px-2.5 py-1 text-[11px] font-medium"
        :class="
          locked
            ? 'bg-gilt-500/20 text-gilt-200 ring-1 ring-accent-line/40'
            : 'bg-ink-700/50 text-fog-300/80'
        "
      >
        {{ locked ? '对局进行中' : '开局准备' }}
      </span>
    </div>

    <!-- 财神 -->
    <div class="mb-6">
      <label class="mb-2 block text-sm text-fog-300/90" for="dealer-tile">
        当盘财神（得）
      </label>
      <select
        id="dealer-tile"
        v-model="dealerTile"
        class="w-full cursor-pointer rounded-xl border border-line/50 bg-ink-900/80 px-4 py-2.5 text-fog-100 outline-none transition focus:border-accent-line/70 focus:ring-2 focus:ring-accent-line/30 disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="locked"
      >
        <option v-for="code in ALL_TILES" :key="code" :value="code">
          {{ tileLabel(code) }}（{{ code }}）
        </option>
      </select>
      <p class="mt-2 text-xs text-fog-300/70">
        当前：{{ tileLabel(dealerTile) }} · 编码 {{ dealerTile }}
        · 公示占用 1 张（不可透支）
      </p>
    </div>

    <!-- 我的门风（唯一手动项） -->
    <div class="mb-6">
      <p class="mb-2 text-sm text-fog-300/90">我的门风</p>
      <div
        class="inline-flex flex-wrap gap-1 rounded-xl border border-line/50 bg-ink-900/60 p-1"
        role="radiogroup"
        aria-label="我的门风"
      >
        <button
          v-for="w in SEAT_WINDS"
          :key="w.code"
          type="button"
          role="radio"
          :aria-checked="seatWind === w.code"
          class="rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed"
          :disabled="locked"
          :class="
            seatWind === w.code
              ? 'bg-gilt-500 text-fg-on-accent shadow'
              : 'text-fog-300/80 hover:text-gilt-200 disabled:opacity-50'
          "
          @click="onPickWind(w.code)"
        >
          {{ w.label }}
        </button>
      </div>
      <p class="mt-2 text-xs leading-relaxed text-fog-300/75">
        庄家固定为
        <span class="font-semibold text-gilt-200/90">东风位（{{ DEALER_SEAT }}）</span>
        · 逆时针东→南→西→北（rule.md §1）
      </p>
    </div>

    <!-- 自动推导：庄闲与相对座次 -->
    <div
      class="mb-6 rounded-xl border border-line/40 bg-ink-900/40 px-3 py-3 sm:px-4"
    >
      <p class="mb-2 text-xs font-medium uppercase tracking-wider text-fog-400/80">
        自动座次
      </p>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div
          v-for="s in table.seats"
          :key="s.seat_wind"
          class="rounded-lg border px-2 py-2 text-center"
          :class="
            s.is_self
              ? 'border-accent-line/50 bg-gilt-500/15'
              : 'border-line/50 bg-ink-800/40'
          "
        >
          <p class="text-[10px] text-fog-400/80">{{ s.role }}</p>
          <p class="text-sm font-semibold text-fog-100">
            {{ s.label }}风
            <span class="text-fog-400/70">({{ s.seat_wind }})</span>
          </p>
          <p
            class="mt-0.5 text-[10px] font-medium"
            :class="s.is_dealer ? 'text-gilt-300' : 'text-fog-400/70'"
          >
            {{ s.is_dealer ? '庄家' : '闲家' }}
          </p>
        </div>
      </div>
      <p class="mt-3 text-xs leading-relaxed text-info/90">
        {{ table.summary }}
      </p>
      <p class="mt-1 text-[11px] text-fog-300/65">
        开局出牌权：{{ table.firstTurnSeat }}（东）· 你起手目标
        <span class="font-semibold text-gilt-200/90"
          >{{ handCount }}/{{ targetHandCount }}</span
        >
        张 · 身份 {{ selfIsDealer ? '庄家' : '闲家' }}
      </p>
    </div>

    <!-- 开始对局 / 重新开局 -->
    <div class="flex flex-wrap items-center gap-2">
      <button
        v-if="!locked"
        type="button"
        class="rounded-xl px-5 py-2.5 text-sm font-semibold shadow-lg transition disabled:cursor-not-allowed"
        :class="
          canStart
            ? 'bg-gilt-500 text-fg-on-accent shadow-ink-950/30 hover:bg-gilt-400 ring-2 ring-accent-line/70'
            : 'bg-ink-700/50 text-fog-400/70 shadow-none'
        "
        :disabled="!canStart"
        :title="
          canStart
            ? '开始对局'
            : `请先用选牌键盘录满 ${targetHandCount} 张起手`
        "
        @click="onConfirmStart"
      >
        开始对局
      </button>
      <button
        v-else
        type="button"
        class="rounded-xl border border-danger/45 px-5 py-2.5 text-sm font-medium text-danger transition hover:bg-danger/40"
        @click="onReopen"
      >
        重新开局
      </button>
      <p v-if="!locked && !canStart" class="text-xs text-fog-400/75">
        还需录入
        {{ Math.max(0, targetHandCount - handCount) }} 张起手
      </p>
    </div>
  </section>
</template>

<style scoped>
.game-config-huiwen { position:absolute; top:calc(100% + 2px); left:0; right:0; height:12px; pointer-events:none; }
</style>
