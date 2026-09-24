<script setup>
/**
 * 对局结束结算面板：四方门风卡片、赢家拆解（含得代入）、未和固有底胡、筹码收支
 */
import { computed, ref } from 'vue'
import MahjongTile from './MahjongTile.vue'
import MeldTiles from './MeldTiles.vue'
import { relativeOpponents, tileLabel, tileSuitClass } from '../constants/tiles.js'
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
  dealerSeat: { type: String, default: 'E' },
  opponents: {
    type: Array,
    default: () => [],
  },
  cumulativeScores: {
    type: Object,
    default: () => ({ E: 0, S: 0, W: 0, N: 0 }),
  },
  roundHistory: {
    type: Array,
    default: () => [],
  },
  isRoundOver: { type: Boolean, default: false },
})

const emit = defineEmits(['next-round', 'review-history'])

const showHistory = ref(false)
const expandedInherent = ref({})
const isMinimized = ref(false)

const isDraw = computed(
  () =>
    !!props.info?.is_draw ||
    props.info?.win_type === 'draw' ||
    props.info?.result === 'draw',
)

const finalHu = computed(
  () =>
    props.info?.final_hu ??
    props.info?.final_points ??
    props.info?.points ??
    0,
)

const winnerSeat = computed(() => props.info?.winner_seat || '')

const discarderSeat = computed(
  () => props.info?.discarder_seat || props.info?.provider_seat || '',
)

const dealerTile = computed(
  () => props.info?.dealer_tile || props.info?.hu_detail?.best_decomposition?.dealer_tile || '',
)

const winnerNet = computed(() => {
  const seat = winnerSeat.value
  if (!seat) return 0
  const details = props.info?.seat_details?.[seat]
  if (details && details.net != null) return Number(details.net)
  return Number(props.info?.net_by_seat?.[seat] ?? 0)
})

const dealerStatusLabel = computed(() => {
  const dealerWin = !!props.info?.is_dealer_win
  if (isDraw.value) return '流局 · 连庄'
  return dealerWin ? '庄家连庄' : '庄家下庄'
})

const capsuleSummary = computed(() => {
  if (isDraw.value) return `荒牌流局 · ${dealerStatusLabel.value}`
  const who = formatSeat(winnerSeat.value)
  const sign = winnerNet.value >= 0 ? '+' : ''
  return `${who} 和牌 (${sign}${winnerNet.value}) · ${dealerStatusLabel.value}`
})

const headline = computed(() => {
  if (isDraw.value) return '荒牌流局'
  const who = formatSeat(winnerSeat.value)
  if (props.info?.is_zimo || props.info?.win_type === 'zimo') {
    return `${who} 自摸和牌`
  }
  const gun = discarderSeat.value
    ? formatSeat(discarderSeat.value)
    : '他家'
  return `${who} 捉${gun}的铳和牌`
})

const hardLabel = computed(
  () =>
    props.info?.hard_hu_label ||
    (props.info?.is_hard_hu
      ? '硬碰硬'
      : props.info?.is_hard_hu === false
        ? '软胡'
        : ''),
)

const huDetail = computed(() => {
  const d = props.info?.hu_detail?.details || props.info?.details || {}
  const fans = d.fans || props.info?.hu_detail?.details?.fans || {}
  const fanItems =
    d.fan_items ||
    props.info?.hu_detail?.details?.fan_items ||
    []
  return {
    baseHu: props.info?.base_hu ?? props.info?.hu_detail?.base_hu ?? 10,
    tileHu: props.info?.tile_hu ?? props.info?.hu_detail?.tile_hu ?? null,
    fan: props.info?.hu_detail?.fan ?? props.info?.fan ?? 0,
    fans,
    fanItems,
    pairs: d.pairs || [],
    melds: d.melds || [],
    restored: props.info?.restored_jokers ?? d.restored_jokers ?? 0,
    zimo: d.zimo ?? 0,
    kanzhang: d.kanzhang ?? 0,
  }
})

const fanEntries = computed(() =>
  Object.entries(huDetail.value.fans || {}).filter(([, v]) => Number(v) > 0),
)

const FAN_LABELS = {
  hard_hu: '硬碰硬',
  dragon_pung_kong: '三元刻/杠',
  seat_wind_pung_kong: '门风刻/杠',
  round_wind_pung_kong: '圈风刻/杠',
  restored_jokers: '得还原',
  half_flush: '混一色',
  full_flush: '清一色',
}

const bestDecomposition = computed(() => {
  return (
    props.info?.hu_detail?.best_decomposition ||
    props.info?.details?.best_decomposition ||
    props.info?.best_decomposition ||
    props.info?.seat_details?.[winnerSeat.value]?.best_decomposition ||
    null
  )
})

const winBadge = computed(() => props.info.win_type_label === '抢杠胡' ? '抢杠胡' : (props.info.is_zimo || props.info.win_type === 'zimo' ? '自摸' : '胡'))
function tileNote(dt) {
  if (dt.is_substitute) return '替' + tileLabel(dt.substituted_as)
  if (dt.is_restored) return hardLabel.value === '硬碰硬' ? '得作本牌' : '得还原'
  if (dt.is_joker) return '得代' + tileLabel(dt.substituted_as || dt.code)
  return undefined
}

/** 相对自家顺序：自家 → 下家 → 对家 → 上家 */
function winnerGroups(details) {
  const deco = bestDecomposition.value
  const groups = details.winning_hand_groups || props.info?.hu_detail?.winning_hand_groups ||
    props.info?.winning_hand_groups || deco?.winning_hand_groups ||
    (deco ? [...(deco.melds_and_sequences || []), ...(deco.head ? [deco.head] : [])] : [])
  return groups.map((group) => ({
    ...group,
    kind: group.kind || (group.type === 'PAIR' ? 'head' : group.type?.toLowerCase()),
    display_tiles: group.display_tiles || (group.tiles || []).map((code, index) => ({
      code,
      is_win_tile: group.winning_tile_index === index,
      is_substitute: !!group.substitutions?.[code],
      substituted_as: group.substitutions?.[code],
    })),
  })).map((group) => {
    // Only reorder the presentation; the scored physical decomposition stays intact.
    if (group.kind === 'chi' && group.source === 'open' && group.claimed_tile) {
      const display = [...group.display_tiles]
      const index = display.findIndex(tile => tile.code === group.claimed_tile)
      if (index >= 0 && index !== 1) display.splice(1, 0, ...display.splice(index, 1))
      return { ...group, display_tiles: display }
    }
    return group
  }).sort((a, b) => Number(a.kind === 'head') - Number(b.kind === 'head'))
}

const seatCards = computed(() => {
  const self = props.seatWind
  const rel = relativeOpponents(self)
  const order = [
    { seat: self, role: '自家' },
    { seat: rel[2].seat_wind, role: '下家' },
    { seat: rel[1].seat_wind, role: '对家' },
    { seat: rel[0].seat_wind, role: '上家' },
  ]
  const details = props.info?.seat_details || {}
  const net = props.info?.net_by_seat || {}
  const inherentMap =
    props.info?.payments?.inherent_detail ||
    props.info?.payments?.inherent_hu ||
    {}

  return order.map(({ seat, role }) => {
    const d = details[seat] || {}
    const inherentRaw = d.inherent || inherentMap[seat]
    const inherent =
      inherentRaw && typeof inherentRaw === 'object'
        ? {
            total_base_hu: Number(inherentRaw.total_base_hu ?? 0),
            base_hu: Number(
              inherentRaw.base_hu ?? inherentRaw.total_base_hu ?? 0,
            ),
            fan_count: Number(inherentRaw.fan_count ?? inherentRaw.fan ?? 0),
            calculated_points: Number(
              inherentRaw.calculated_points ??
                inherentRaw.total_base_hu ??
                0,
            ),
            items: inherentRaw.items || [],
            breakdown: inherentRaw.breakdown || inherentRaw.hu_details || [],
            fan_details: inherentRaw.fan_details || [],
            fans: inherentRaw.fans || {},
          }
        : {
            total_base_hu: Number(inherentRaw) || 0,
            base_hu: Number(inherentRaw) || 0,
            fan_count: 0,
            calculated_points: Number(inherentRaw) || 0,
            items: [],
            breakdown: [],
            fan_details: [],
            fans: {},
          }
    const isWinner = !isDraw.value && seat === winnerSeat.value
    const isDealerSeat = seat === props.dealerSeat || !!d.is_dealer
    return {
      seat,
      role,
      badge: `${role} · ${windLabel(seat)}风(${isDealerSeat ? '庄' : '闲'})`,
      isWinner,
      isDealer: isDealerSeat,
      isSelf: seat === self,
      net: Number(d.net ?? net[seat] ?? 0),
      paymentCapped: !!d.payment_capped || (props.info?.payments?.capped_seats || []).includes(seat),
      paymentCap: d.payment_cap ?? props.info?.payments?.payment_cap ?? 100,
      total: Number(props.cumulativeScores?.[seat] ?? 0),
      handTiles:
        d.hand_tiles_with_win ||
        (isWinner && props.info?.win_tile
          ? [...(d.hand_tiles || []), props.info.win_tile]
          : d.hand_tiles || []),
      winTile: d.win_tile || (isWinner ? props.info?.win_tile : null),
      melds: d.melds || [],
      inherent,
      winningGroups: isWinner ? winnerGroups(d) : [],
      hu: isWinner ? huDetail.value : null,
    }
  })
})

const transfers = computed(() => props.info?.transfers || [])
const payoutTransfers = computed(() => transfers.value.filter(t => (t.transaction_type || 'winner_payout') === 'winner_payout'))
const mutualTransfers = computed(() => props.info?.payments?.mutual_settlement_transactions || transfers.value.filter(t => t.transaction_type === 'mutual_settlement'))

const historyNewestFirst = computed(() =>
  [...(props.roundHistory || [])].reverse(),
)

function formatSeat(seat) {
  if (!seat) return '—'
  if (seat === props.seatWind) return `自家(${windLabel(seat)})`
  const o = props.opponents.find((x) => x.seat_wind === seat)
  const role = o?.role ? `${o.role}·` : ''
  return `${role}${windLabel(seat)}风`
}

function fanLabel(key) {
  return FAN_LABELS[key] || key
}

function meldTypeLabel(kind) {
  return (
    {
      chi: '吃',
      anko: '暗刻',
      pong: '碰',
      ming_gang: '明杠',
      an_gang: '暗杠',
      head: '雀头',
    }[kind] || kind
  )
}

function groupCaption(grp) {
  const base = grp.source === 'concealed' && grp.kind === 'pong'
    ? '明刻'
    : meldTypeLabel(grp.kind)
  if (grp.contains_win_tile || (grp.display_tiles || []).some((d) => d.is_win_tile)) {
    return `和 · ${base}`
  }
  if (grp.source === 'open') return base
  return `暗 · ${base}`
}

function toggleInherent(seat) {
  expandedInherent.value = {
    ...expandedInherent.value,
    [seat]: !expandedInherent.value[seat],
  }
}

function onNextRound() {
  emit('next-round', {
    lastWinnerSeat: isDraw.value ? null : winnerSeat.value,
    isDealerWin: !!props.info?.is_dealer_win,
    isDraw: isDraw.value,
    isRoundOver: props.isRoundOver,
  })
}

function onToggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) emit('review-history')
}

function minimizePanel() {
  isMinimized.value = true
}

function expandPanel() {
  isMinimized.value = false
}
</script>

<template>
  <!-- 最小化：右下角胶囊，沙盘完全可操作 -->
  <div
    v-if="isMinimized"
    class="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-end p-3 sm:p-4"
  >
    <div
      class="pointer-events-auto flex max-w-[min(100%,28rem)] flex-col gap-2 rounded-2xl border border-amber-400/60 bg-teal-950/95 px-3 py-2.5 shadow-2xl shadow-black/40 backdrop-blur-md"
      role="status"
      aria-label="结算摘要（已最小化）"
    >
      <div class="flex items-start gap-2">
        <span class="mt-0.5 text-base leading-none" aria-hidden="true">🏆</span>
        <div class="min-w-0 flex-1">
          <p class="text-[11px] font-bold uppercase tracking-wide text-amber-200/80">
            结算摘要
          </p>
          <p class="mt-0.5 text-sm font-semibold leading-snug text-amber-50">
            {{ capsuleSummary }}
          </p>
          <p v-if="!isDraw" class="mt-0.5 text-[11px] text-teal-200/75">
            {{ finalHu }} 胡
            <span v-if="huDetail.fan"> · {{ huDetail.fan }} 翻</span>
          </p>
        </div>
        <button
          type="button"
          class="shrink-0 rounded-lg border border-teal-500/45 bg-teal-900/80 px-2 py-1 text-[11px] font-semibold text-teal-50 transition hover:border-amber-300/60 hover:bg-teal-800"
          title="展开结算明细"
          @click="expandPanel"
        >
          🗖 展开
        </button>
      </div>
      <div class="flex gap-2">
        <button
          type="button"
          class="flex-1 rounded-xl bg-gradient-to-r from-amber-400 to-yellow-300 px-3 py-2 text-xs font-black text-amber-950 shadow transition hover:brightness-105"
          @click="onNextRound"
        >
          {{ isRoundOver ? '查看本圈总结' : '开始下一局' }}
        </button>
      </div>
    </div>
  </div>

  <!-- 完整结算面板 -->
  <div
    v-else
    class="fixed inset-0 z-50 flex items-center justify-center bg-emerald-950/80 p-2 backdrop-blur-sm sm:p-4"
    role="dialog"
    aria-modal="true"
    aria-label="对局结束结算"
  >
    <div
      class="flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-amber-400/55 bg-teal-950 shadow-2xl"
    >
      <header
        class="relative shrink-0 bg-gradient-to-r from-rose-700 via-amber-500 to-yellow-400 px-4 py-4 text-center sm:px-6 sm:py-5"
      >
        <div class="absolute right-2 top-2 flex gap-1 sm:right-3 sm:top-3">
          <button
            type="button"
            class="rounded-lg border border-amber-950/25 bg-amber-950/15 px-2 py-1 text-[11px] font-bold text-amber-950/90 transition hover:bg-amber-950/25"
            title="最小化，查看牌桌"
            @click="minimizePanel"
          >
            🗕 收起
          </button>
        </div>
        <p
          class="text-[11px] font-bold uppercase tracking-[0.22em] text-amber-950/65"
        >
          GAME_OVER · 台州无包牌
        </p>
        <h2 class="mt-1.5 text-2xl font-black text-amber-950 sm:text-3xl">
          {{ headline }}
        </h2>
        <p v-if="!isDraw" class="mt-1 text-sm text-amber-950/85">
          {{ finalHu }} 胡
          <span v-if="hardLabel"> · {{ hardLabel }}</span>
          <span v-if="info.win_tile">
            · 胡张 {{ tileLabel(info.win_tile) }}
          </span>
          <span v-if="huDetail.fan"> · {{ huDetail.fan }} 翻</span>
          <span v-if="dealerTile" class="ml-1">
            · 得 {{ tileLabel(dealerTile) }}
          </span>
        </p>
        <p v-else class="mt-1 text-sm text-amber-950/80">
          本局无人胡牌 · 不计主支付（固有胡头互结若有则已计入）
        </p>
        <p
          v-if="info.payments?.label"
          class="mt-1 text-xs text-amber-950/70"
        >
          {{ info.payments.label }}
        </p>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto px-3 py-3 sm:px-5 sm:py-4">
        <!-- 四方门风卡片 -->
        <section class="mb-4">
          <h3 class="mb-2 text-sm font-semibold text-amber-100">
            四方结算明细
          </h3>
          <div
            class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
          >
            <article
              v-for="card in seatCards"
              :key="card.seat"
              class="flex flex-col rounded-xl border p-3"
              :class="
                card.isWinner
                  ? 'border-amber-400/60 bg-amber-950/40 sm:col-span-2 lg:col-span-3'
                  : card.isSelf
                    ? 'border-teal-500/45 bg-teal-950/55'
                    : 'border-teal-800/50 bg-emerald-950/45'
              "
            >
              <div class="mb-2 flex items-start justify-between gap-1">
                <span
                  class="rounded-md px-2 py-0.5 text-[11px] font-bold"
                  :class="
                    card.isWinner
                      ? 'bg-amber-400 text-amber-950'
                      : 'bg-teal-800/80 text-teal-50'
                  "
                >
                  {{ card.badge }}
                </span>
                <span
                  v-if="card.isWinner"
                  class="text-[10px] font-black uppercase tracking-wide text-amber-200"
                >
                  胡
                </span>
              </div>

              <!-- 赢家：成胡拆解 -->
              <div v-if="card.isWinner && card.winningGroups.length" class="mb-2">
                <p class="mb-1 text-[10px] font-semibold text-amber-200/90">
                  最佳成胡牌型
                  <span
                    v-if="info.win_tile"
                    class="ml-1 font-normal text-amber-100/70"
                  >
                    · 胡张 {{ tileLabel(info.win_tile) }}
                  </span>
                </p>
                <div class="flex flex-wrap items-end gap-x-3 gap-y-3" aria-label="成牌面子与雀头">
                  <div
                    v-for="(grp, gi) in card.winningGroups"
                    :key="gi"
                    class="inline-flex shrink-0 flex-col rounded-lg border px-2 pb-2 pt-1"
                    :class="grp.kind === 'head' ? 'border-sky-400/60 bg-sky-950/40' : 'border-amber-500/35 bg-amber-950/30'"
                  >
                    <p class="mb-3 text-[10px] text-amber-100/80">
                      {{ groupCaption(grp) }} <span v-if="grp.hu">+{{ grp.hu }}</span>
                    </p>
                    <div class="inline-flex flex-nowrap items-end gap-1 pb-3 pt-1">
                      <MahjongTile v-for="(dt, di) in grp.display_tiles" :key="di" :code="dt.code"
                        :sideways="dt.is_win_tile || (grp.kind === 'chi' && grp.source === 'open' && dt.code === grp.claimed_tile)"
                        :badge="dt.is_win_tile ? winBadge : undefined"
                        :note="tileNote(dt)" />
                    </div>
                  </div>
                </div>

                <div
                  class="mt-2 grid grid-cols-3 gap-1 rounded-lg border border-teal-700/40 bg-teal-950/50 p-1.5 text-center text-[10px]"
                >
                  <div>
                    <p class="text-teal-400/75">底胡</p>
                    <p class="font-bold text-amber-100">
                      {{ card.hu?.baseHu ?? 10 }}
                    </p>
                  </div>
                  <div>
                    <p class="text-teal-400/75">牌型</p>
                    <p class="font-bold text-amber-100">
                      {{ card.hu?.tileHu ?? '—' }}
                    </p>
                  </div>
                  <div>
                    <p class="text-teal-400/75">翻</p>
                    <p class="font-bold text-amber-100">
                      {{ card.hu?.fan ?? 0 }}
                    </p>
                  </div>
                </div>
                <ul
                  v-if="fanEntries.length"
                  class="mt-1.5 flex flex-wrap gap-1"
                >
                  <li
                    v-for="[name, n] in fanEntries"
                    :key="name"
                    class="rounded border border-amber-500/35 bg-amber-950/45 px-1.5 py-0.5 text-[9px] text-amber-100"
                  >
                    {{ fanLabel(name) }} +{{ n }}
                    <span>（×{{ 2 ** Number(n) }}）</span>
                  </li>
                </ul>
                <ul
                  v-if="(card.hu?.fanItems || []).length"
                  class="mt-1 space-y-0.5"
                >
                  <li
                    v-for="(item, fi) in card.hu.fanItems"
                    :key="`fi-${fi}`"
                    class="text-[9px] leading-snug text-amber-200/85"
                  >
                    · {{ item }}
                  </li>
                </ul>
                <p
                  v-if="card.hu?.zimo || card.hu?.kanzhang"
                  class="mt-1 text-[9px] text-teal-300/75"
                >
                  <span v-if="card.hu.zimo">自摸 +{{ card.hu.zimo }} </span>
                  <span v-if="card.hu.kanzhang"
                    >嵌档 +{{ card.hu.kanzhang }}</span
                  >
                </p>
              </div>

              <!-- 未和 / 无拆解：暗手 + 副露 + 固有底胡 -->
              <div v-else class="mb-2 flex-1">
                <div v-if="card.melds?.length" class="mb-1.5">
                  <p class="mb-0.5 text-[9px] text-teal-400/70">副露</p>
                  <div class="flex flex-wrap gap-1">
                    <MeldTiles v-for="(m, mi) in card.melds" :key="mi" :meld="m" :dealer-tile="dealerTile" />
                  </div>
                </div>
                <div v-if="card.handTiles?.length" class="mb-1.5">
                  <p class="mb-0.5 text-[9px] text-teal-400/70">暗手</p>
                  <div class="flex flex-wrap gap-0.5">
                    <span
                      v-for="(t, ti) in card.handTiles"
                      :key="`h-${ti}`"
                      class="flex h-7 w-5 items-center justify-center rounded border text-[9px] font-bold"
                      :class="tileSuitClass(t)"
                    >
                      {{ tileLabel(t) }}
                    </span>
                  </div>
                </div>
                <div
                  class="rounded-lg border border-violet-500/30 bg-violet-950/35 px-2 py-1.5"
                >
                  <button
                    type="button"
                    class="flex w-full items-center justify-between text-left"
                    @click="toggleInherent(card.seat)"
                  >
                    <span class="text-[11px] font-bold leading-snug text-violet-100">
                      <template v-if="(card.inherent.fan_count || 0) > 0">
                        【固有底胡：{{ card.inherent.base_hu ?? card.inherent.total_base_hu ?? 0 }} 胡】
                        × 【{{ card.inherent.fan_count }} 番】
                        ➔ 【结算胡数：{{ card.inherent.calculated_points ?? 0 }} 胡】
                      </template>
                      <template v-else>
                        固有底胡：{{ card.inherent.total_base_hu ?? 0 }} 胡
                      </template>
                    </span>
                    <span class="ml-1 shrink-0 text-[10px] text-violet-300/80">
                      {{ expandedInherent[card.seat] ? '▾' : '▸' }}
                    </span>
                  </button>
                  <div
                    v-if="(card.inherent.fan_details || []).length"
                    class="mt-1 flex flex-wrap gap-1"
                  >
                    <span
                      v-for="(fd, fi) in card.inherent.fan_details"
                      :key="`fan-${fi}`"
                      class="rounded bg-amber-900/45 px-1 py-0.5 text-[9px] font-medium text-amber-100/95"
                    >
                      {{ fd.label || fd.name }}
                    </span>
                    <span
                      v-if="(card.inherent.fan_count || 0) > 1"
                      class="rounded bg-amber-800/50 px-1 py-0.5 text-[9px] font-bold text-amber-50"
                    >
                      合计 {{ card.inherent.fan_count }} 番 (×{{
                        2 ** (card.inherent.fan_count || 0)
                      }})
                    </span>
                  </div>
                  <ul
                    v-if="
                      expandedInherent[card.seat] &&
                      (card.inherent.items || []).length
                    "
                    class="mt-1 space-y-0.5 border-t border-violet-500/20 pt-1"
                  >
                    <li
                      v-for="(it, ii) in card.inherent.items"
                      :key="ii"
                      class="text-[10px] text-violet-100/85"
                    >
                      {{ it }}
                    </li>
                    <li
                      v-if="(card.inherent.fan_count || 0) > 0"
                      class="pt-0.5 text-[10px] font-semibold text-amber-200/90"
                    >
                      加番后结算：{{ card.inherent.base_hu ?? 0 }} × 2^{{
                        card.inherent.fan_count
                      }}
                      = {{ card.inherent.calculated_points ?? 0 }} 胡
                    </li>
                  </ul>
                  <div
                    v-else-if="
                      !(card.inherent.fan_details || []).length &&
                      (card.inherent.items || []).length
                    "
                    class="mt-1 flex flex-wrap gap-1"
                  >
                    <span
                      v-for="(it, ii) in card.inherent.items.slice(0, 4)"
                      :key="ii"
                      class="rounded bg-violet-900/50 px-1 py-0.5 text-[9px] text-violet-100/90"
                    >
                      {{ it.replace(/\s*\(\+\d+胡\)/, '') }}
                    </span>
                  </div>
                  <p
                    v-else-if="!(card.inherent.items || []).length"
                    class="mt-0.5 text-[9px] text-violet-300/60"
                  >
                    无确定暗刻 / 役牌雀头 / 高分副露
                  </p>
                </div>
              </div>

              <!-- 本盘收支 -->
              <div
                class="mt-auto border-t border-teal-800/40 pt-2 text-right tabular-nums"
              >
                <p
                  class="text-sm font-bold"
                  :class="
                    card.net > 0
                      ? 'text-amber-200'
                      : card.net < 0
                        ? 'text-rose-300'
                        : 'text-teal-300/80'
                  "
                >
                  本盘 {{ card.net >= 0 ? '+' : '' }}{{ card.net }}
                  <span v-if="card.paymentCapped" class="block text-[10px] text-amber-300">
                    和牌赔付已封顶 ({{ card.paymentCap }})
                  </span>
                </p>
                <p class="text-[10px] text-teal-400/70">
                  累计 {{ card.total >= 0 ? '+' : '' }}{{ card.total }}
                </p>
              </div>
            </article>
          </div>
        </section>

        <!-- 支付流水 -->
        <section v-if="payoutTransfers.length" class="mb-4">
          <h3 class="mb-2 text-sm font-semibold text-amber-100">支付明细</h3>
          <ul
            class="max-h-28 space-y-1 overflow-y-auto text-[11px] text-teal-200/85"
          >
            <li
              v-for="(t, i) in payoutTransfers"
              :key="i"
              class="rounded-lg border border-teal-800/40 bg-teal-950/40 px-2 py-1"
            >
              {{ windLabel(t.from) }} → {{ windLabel(t.to) }}：{{ t.amount }}
              <span v-if="t.capped" class="text-amber-300"> · 和牌赔付已封顶 ({{ info.payments?.payment_cap ?? 100 }})，原应付 {{ t.raw_amount }}</span>
              <span class="text-teal-500/80">（{{ t.note }}）</span>
            </li>
          </ul>
        </section>

        <section v-if="mutualTransfers.length" class="mb-4" aria-label="固有胡头互结明细">
          <h3 class="mb-2 text-sm font-semibold text-amber-100">未胡家固有胡头互结（独立结算）</h3>
          <ul class="max-h-32 space-y-1 overflow-y-auto text-[11px] text-teal-200/85">
            <li v-for="(t,i) in mutualTransfers" :key="`mutual-${i}`" class="rounded-lg border border-violet-700/40 bg-violet-950/25 px-2 py-1">
              {{ windLabel(t.from) }} → {{ windLabel(t.to) }}：{{ t.amount }}
              <span class="text-teal-400/80">（{{ t.note }}）</span>
            </li>
          </ul>
        </section>

        <section v-if="showHistory" class="mb-2">
          <h3 class="mb-2 text-sm font-semibold text-amber-100">
            复盘历史（{{ roundHistory.length }} 局）
          </h3>
          <ul
            v-if="historyNewestFirst.length"
            class="max-h-40 space-y-1.5 overflow-y-auto text-[11px]"
          >
            <li
              v-for="(h, i) in historyNewestFirst"
              :key="h.roundIndex ?? i"
              class="rounded-lg border border-teal-800/50 bg-emerald-950/40 px-2.5 py-2 text-teal-100"
            >
              <span class="font-semibold text-amber-100/90">
                第 {{ h.roundIndex ?? historyNewestFirst.length - i }} 局
              </span>
              · {{ h.summary || h.headline || '—' }}
              <span class="text-teal-400/75">
                （{{ h.is_draw ? '流局' : `${h.points ?? 0} 胡` }}）
              </span>
            </li>
          </ul>
          <p v-else class="text-[11px] text-teal-500/80">暂无历史局</p>
        </section>
      </div>

      <footer
        class="shrink-0 space-y-2 border-t border-teal-800/55 px-4 py-4 sm:px-5"
      >
        <button
          type="button"
          class="w-full rounded-xl bg-gradient-to-r from-amber-400 to-yellow-300 px-4 py-3.5 text-base font-black text-amber-950 shadow-lg transition hover:brightness-105"
          @click="onNextRound"
        >
          {{ isRoundOver ? '查看本圈总结' : '开始下一局' }}
        </button>
        <button
          type="button"
          class="w-full rounded-xl border border-teal-500/50 bg-teal-950/70 px-4 py-2.5 text-sm font-semibold text-teal-100 transition hover:border-teal-300/70 hover:bg-teal-900/80"
          @click="onToggleHistory"
        >
          {{ showHistory ? '收起复盘' : '查看复盘历史' }}
        </button>
      </footer>
    </div>
  </div>
</template>
