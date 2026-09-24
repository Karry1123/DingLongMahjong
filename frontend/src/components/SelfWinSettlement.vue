<script setup>
/**
 * 终局结算弹窗：§6 庄闲收支 + 固有胡头互结 + 开始新一局
 */
import { computed } from 'vue'
import { tileLabel } from '../constants/tiles.js'
import { windLabel } from '../utils/seatLayout.js'

const props = defineProps({
  info: {
    type: Object,
    required: true,
  },
  seatWind: {
    type: String,
    default: 'E',
  },
  isDealer: {
    type: Boolean,
    default: false,
  },
  opponents: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['new-game'])

const finalHu = computed(
  () => props.info?.final_hu ?? props.info?.final_points ?? props.info?.points ?? 0,
)

const winTypeLabel = computed(
  () =>
    props.info?.win_type_label ||
    (props.info?.is_zimo ? '自摸' : '捉铳'),
)

const winnerSeat = computed(
  () => props.info?.winner_seat || props.seatWind,
)

const seatRole = (seat) => {
  if (seat === props.seatWind) return '自家'
  const o = props.opponents.find((x) => x.seat_wind === seat)
  return o?.role || windLabel(seat)
}

const rows = computed(() => {
  const net = props.info?.net_by_seat
  if (net && typeof net === 'object' && Object.keys(net).length) {
    return Object.entries(net).map(([seat, amount]) => ({
      seat,
      role: `${seatRole(seat)}·${windLabel(seat)}`,
      amount: Number(amount),
      note: seat === winnerSeat.value ? '胡牌收入（含互结）' : '支付/互结',
    }))
  }
  // 兼容旧 payments 结构
  const pts = finalHu.value
  const pay = props.info?.payments || {}
  const out = []
  const winnerIsDealer =
    props.info?.is_dealer_win ??
    (winnerSeat.value === props.seatWind ? props.isDealer : false)
  if (winnerIsDealer) {
    for (const o of props.opponents) {
      out.push({
        seat: o.seat_wind,
        role: windLabel(o.seat_wind),
        amount: -(pay.from_each_xian ?? pts),
        note: '闲家全额支付庄家',
      })
    }
    out.push({
      seat: winnerSeat.value,
      role: '庄家胡',
      amount: pay.winner_income ?? pts * 3,
      note: '通吃三家',
    })
  } else {
    for (const o of props.opponents) {
      const isDealerOpp = !!o.is_dealer
      const amt = isDealerOpp
        ? -(pay.from_dealer ?? pts)
        : -(pay.from_each_xian ?? Math.floor(pts / 2))
      out.push({
        seat: o.seat_wind,
        role: `${windLabel(o.seat_wind)}${isDealerOpp ? '·庄' : '·闲'}`,
        amount: amt,
        note: isDealerOpp ? '庄家全额' : '闲家半额',
      })
    }
    if (winnerSeat.value === props.seatWind) {
      out.push({
        seat: props.seatWind,
        role: '自家（闲）',
        amount: pay.winner_income ?? pts * 2,
        note: '庄全额 + 两闲半额',
      })
    }
  }
  return out
})

const transfers = computed(() => props.info?.transfers || [])
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-emerald-950/75 p-4 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-label="终局结算"
  >
    <div
      class="w-full max-w-md overflow-hidden rounded-2xl border border-amber-400/50 bg-teal-950 shadow-2xl"
    >
      <header
        class="bg-gradient-to-r from-rose-600 via-amber-500 to-yellow-400 px-5 py-6 text-center"
      >
        <p class="text-xs font-bold uppercase tracking-[0.2em] text-amber-950/70">
          对局终结 · GAME_OVER · 无包牌
        </p>
        <h2 class="mt-2 text-2xl font-black text-amber-950">
          {{ winTypeLabel }} {{ finalHu }} 胡
        </h2>
        <p class="mt-1 text-sm text-amber-950/80">
          {{ windLabel(winnerSeat) }}风
          <span v-if="info.hard_hu_label"> · {{ info.hard_hu_label }}</span>
          <span v-if="info.win_tile">
            · 胡张 {{ tileLabel(info.win_tile) }}
          </span>
          <span v-if="info.fan != null"> · {{ info.fan }} 翻</span>
        </p>
        <p
          v-if="info.payments?.label"
          class="mt-1 text-xs text-amber-950/70"
        >
          {{ info.payments.label }}
        </p>
      </header>

      <div class="max-h-[50vh] overflow-y-auto px-5 py-4">
        <h3 class="mb-2 text-sm font-semibold text-amber-50">四人净收支</h3>
        <ul class="space-y-2">
          <li
            v-for="row in rows"
            :key="row.seat + row.role"
            class="flex items-center justify-between rounded-xl border border-teal-700/40 bg-emerald-950/50 px-3 py-2 text-sm"
          >
            <span class="text-teal-100">
              {{ row.role }}
              <span class="ml-1 text-[11px] text-teal-300/70">{{ row.note }}</span>
            </span>
            <span
              class="font-bold tabular-nums"
              :class="row.amount >= 0 ? 'text-amber-200' : 'text-rose-300'"
            >
              {{ row.amount >= 0 ? '+' : '' }}{{ row.amount }}
            </span>
          </li>
        </ul>

        <div v-if="transfers.length" class="mt-4">
          <h3 class="mb-2 text-sm font-semibold text-amber-50">支付明细</h3>
          <ul class="space-y-1.5 text-[11px] text-teal-200/85">
            <li
              v-for="(t, i) in transfers"
              :key="i"
              class="rounded-lg border border-teal-800/40 bg-teal-950/40 px-2 py-1.5"
            >
              {{ windLabel(t.from) }} → {{ windLabel(t.to) }}：{{ t.amount }}
              <span class="text-teal-400/70">（{{ t.note }}）</span>
            </li>
          </ul>
        </div>
      </div>

      <footer class="border-t border-teal-800/50 px-5 py-4">
        <button
          type="button"
          class="w-full rounded-xl bg-gradient-to-r from-amber-400 to-yellow-300 px-4 py-3 text-base font-black text-amber-950 shadow-lg transition hover:brightness-105"
          @click="emit('new-game')"
        >
          开始新一局
        </button>
      </footer>
    </div>
  </div>
</template>
