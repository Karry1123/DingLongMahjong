<script setup>
/**
 * 对局结束结算面板：四方门风卡片、赢家拆解（含得代入）、未和固有底胡、筹码收支
 */
import { computed, ref } from 'vue'
import MahjongTile from './MahjongTile.vue'
import MeldTiles from './MeldTiles.vue'
import GameHistoryModal from './GameHistoryModal.vue'
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
const copyStatus = ref('')
async function copyGameId() {
  const id = props.info?.game_id
  if (!id) return
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(id)
    else {
      const field = document.createElement('textarea')
      field.value = id
      document.body.appendChild(field)
      field.select()
      if (!document.execCommand('copy')) throw new Error('copy unavailable')
      field.remove()
    }
    copyStatus.value = '已复制对局编号'
  } catch { copyStatus.value = '复制失败，请手动选择编号' }
  setTimeout(() => { copyStatus.value = '' }, 2500)
}

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
    scoreItems: d.score_items || [],
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
const winningCard = computed(() => seatCards.value.find((card) => card.isWinner) || null)
const settlementSideCards = computed(() => isDraw.value ? seatCards.value : seatCards.value.filter((card) => !card.isWinner))
const fullTileName = (tile) => ({ E: '东风', S: '南风', W: '西风', N: '北风', C: '红中', F: '发财', P: '白板' })[tile] || tileLabel(tile)
const winnerBreakdown = computed(() => {
  if (huDetail.value.scoreItems.length) return huDetail.value.scoreItems
    .filter((item) => item.kind !== 'base')
    .map((item) => item.hu != null ? `${item.label} (+${item.hu}胡)` : item.label)
  // Older archived rounds predate score_items; reconstruct labels from scored details.
  const items = huDetail.value.melds.filter((item) => Number(item.hu) > 0).map((item) => {
    const kind = ({ pong: '明刻', anko: '暗刻', ming_gang: '明杠', an_gang: '暗杠' })[item.type] || item.type
    return `${kind} ${fullTileName(item.identity || item.tiles?.[0])} (+${item.hu}胡)`
  })
  items.push(...huDetail.value.pairs.filter((item) => Number(item.hu) > 0)
    .map((item) => `${fullTileName(item.tile)}雀头 (+${item.hu}胡)`))
  if (huDetail.value.zimo) items.push(`自摸 (+${huDetail.value.zimo}胡)`)
  if (huDetail.value.kanzhang) items.push(`嵌档 (+${huDetail.value.kanzhang}胡)`)
  items.push(...huDetail.value.fanItems)
  return items
})

function inherentItemLabel(item) {
  if (item == null) return ''
  if (typeof item === 'string') return item.replaceAll('明碰', '明刻')
  if (typeof item === 'object') {
    const label = item.label || item.name || item.reason || item.title || ''
    const hu = item.hu ?? item.base_hu ?? item.points
    return label ? `${label.replaceAll('明碰', '明刻')}${hu != null ? ` (+${hu}胡)` : ''}` : JSON.stringify(item)
  }
  return String(item)
}

const transfers = computed(() => props.info?.transfers || [])
const payoutTransfers = computed(() => transfers.value.filter(t => (t.transaction_type || 'winner_payout') === 'winner_payout'))
const mutualTransfers = computed(() => props.info?.payments?.mutual_settlement_transactions || transfers.value.filter(t => t.transaction_type === 'mutual_settlement'))


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
      pong: '明刻',
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

function settlementReason(card) {
  if (isDraw.value) return `流局 · 固有底胡 ${card.inherent.calculated_points} 胡`
  if (card.isWinner) return `${winBadge.value} · ${finalHu.value} 胡${huDetail.value.fan ? ` · ${huDetail.value.fan} 翻` : ''}`
  const payment = payoutTransfers.value.find((entry) => entry.from === card.seat)
  if (props.info?.payments?.is_lazi && payment) return `辣子封顶 · 基础赔付 ${payment.amount} 分`
  if (payment) return `${payment.capped ? '赔付封顶' : '和牌赔付'} · ${payment.amount} 分`
  return `固有底胡 ${card.inherent.calculated_points} 胡`
}
</script>

<template>
  <GameHistoryModal v-if="showHistory" :current-game-id="info.game_id || ''" @close="showHistory = false" />
  <!-- 最小化：右下角胶囊，沙盘完全可操作 -->
  <div
    v-if="isMinimized"
    class="settlement-capsule pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-end p-3 sm:p-4"
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
          <p v-if="info.game_id" class="mt-1 text-[11px] text-amber-200">牌谱编号：{{ info.game_id }} <button type="button" class="underline" @click="copyGameId">复制</button></p>
          <p v-if="copyStatus" role="status" class="text-[11px] text-teal-200">{{ copyStatus }}</p>
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
    class="game-over-overlay fixed inset-0 z-50 flex items-center justify-center bg-emerald-950/80 p-2 backdrop-blur-sm sm:p-4"
    role="dialog"
    aria-modal="true"
    aria-label="对局结束结算"
  >
    <div
      class="game-over-panel flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-amber-400/55 bg-teal-950 shadow-2xl"
    >
      <div class="landscape-settlement" aria-label="横屏四方结算看板">
        <section class="landscape-settlement-summary">
          <div class="landscape-settlement-topline">
            <span>本局结算</span>
            <button type="button" title="最小化，查看牌桌" @click="minimizePanel">收起</button>
          </div>
          <h2>{{ headline }}</h2>
          <p class="landscape-settlement-score" v-if="!isDraw">
            <strong>{{ finalHu }} 胡</strong>
            <span v-if="huDetail.fan">{{ huDetail.fan }} 翻</span>
            <span v-if="info.win_tile">胡张 {{ tileLabel(info.win_tile) }}</span>
            <span v-if="dealerTile">得 {{ tileLabel(dealerTile) }}</span>
          </p>
          <p class="landscape-settlement-score" v-else>四家本局得分见右侧</p>
          <p v-if="hardLabel && !isDraw" class="landscape-settlement-note">{{ hardLabel }}</p>
          <div class="landscape-settlement-id">
            <template v-if="info.game_id"><span>牌谱 {{ info.game_id }}</span><button type="button" @click="copyGameId">复制</button></template>
            <span v-else>{{ info.archive_error ? '牌谱归档失败' : '牌谱归档中…' }}</span>
          </div>
          <div v-if="winningCard" class="landscape-winner-hand" aria-label="和牌者最终成牌">
            <p>成牌面子与雀头 <span v-if="info.win_tile || winningCard.winTile">胡张 {{ tileLabel(info.win_tile || winningCard.winTile) }}</span></p>
            <div class="landscape-winner-groups">
              <div v-for="(group, index) in winningCard.winningGroups" :key="index" class="landscape-winner-group" :title="groupCaption(group)">
                <span v-for="(tile, tileIndex) in group.display_tiles" :key="tileIndex" class="settlement-mini-tile" :class="[tileSuitClass(tile.code), { 'is-winning-tile': tile.is_win_tile }]" :title="tileNote(tile) || tileLabel(tile.code)">{{ tileLabel(tile.code) }}</span>
              </div>
            </div>
            <div class="landscape-winner-breakdown">
              <span>底胡 {{ huDetail.baseHu }}胡</span>
              <span v-for="(item, index) in winnerBreakdown" :key="index">{{ item }}</span>
              <strong>合计 {{ finalHu }}胡 · {{ huDetail.fan }}番</strong>
            </div>
          </div>
          <p v-if="copyStatus" role="status" class="landscape-settlement-copy">{{ copyStatus }}</p>
          <div class="landscape-settlement-actions">
            <button type="button" class="landscape-settlement-next" @click="onNextRound">{{ isRoundOver ? '查看本圈总结' : '开始下一局' }}</button>
            <button type="button" class="landscape-settlement-history-button" @click="onToggleHistory">{{ showHistory ? '返回结算明细' : '查看复盘历史' }}</button>
          </div>
        </section>
        <section class="landscape-settlement-details">
          <h3>四方结算明细</h3>
          <div class="landscape-settlement-seats">
            <article v-for="card in settlementSideCards" :key="card.seat" class="landscape-settlement-seat" :class="{ 'is-winner': card.isWinner }">
              <div class="landscape-settlement-seat-main">
                <strong>{{ card.role }} · {{ windLabel(card.seat) }}风<span v-if="card.isDealer"> · 庄</span></strong>
                <b :class="card.net > 0 ? 'positive' : card.net < 0 ? 'negative' : ''">{{ card.net >= 0 ? '+' : '' }}{{ card.net }}</b>
              </div>
              <p>{{ settlementReason(card) }} · 累计 {{ card.total >= 0 ? '+' : '' }}{{ card.total }}</p>
              <div class="landscape-seat-tiles" :aria-label="`${card.role}最终持牌与副露`">
                <span v-for="(tile, index) in card.handTiles" :key="`hand-${index}`" class="settlement-mini-tile" :class="tileSuitClass(tile)">{{ tileLabel(tile) }}</span>
                <span v-for="(meld, meldIndex) in card.melds" :key="`meld-${meldIndex}`" class="landscape-seat-meld">
                  <span v-for="(tile, tileIndex) in meld.tiles" :key="tileIndex" class="settlement-mini-tile" :class="tileSuitClass(tile)">{{ tileLabel(tile) }}</span>
                </span>
              </div>
              <div class="landscape-seat-breakdown">
                <span v-for="(item, index) in card.inherent.items" :key="index">{{ inherentItemLabel(item) }}</span>
                <span v-if="!card.inherent.items.length">固有底胡 {{ card.inherent.calculated_points }}胡</span>
                <span v-for="(fan, index) in card.inherent.fan_details" :key="`fan-${index}`">{{ fan.label || fan.name }}</span>
              </div>
            </article>
          </div>
        </section>
      </div>
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
        <p class="mt-2 text-xs font-semibold text-amber-950">
          <template v-if="info.game_id">牌谱编号：<b>{{ info.game_id }}</b> <button type="button" class="ml-1 rounded bg-amber-950/15 px-2 py-0.5 hover:bg-amber-950/25" @click="copyGameId">复制</button></template>
          <template v-else-if="info.archive_error">牌谱归档失败，请检查网络后再开下一局</template>
          <template v-else>牌谱归档中…</template>
        </p>
        <p v-if="info.game_id" class="mt-1 text-[11px] text-amber-950/75">如遇不合理 EV 推荐，可将编号与截图反馈排查。</p>
        <p v-if="copyStatus" role="status" class="mt-1 text-xs text-emerald-950">{{ copyStatus }}</p>
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
                      {{ inherentItemLabel(it) }}
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
                      {{ inherentItemLabel(it).replace(/\s*\(\+\d+胡\)/, '') }}
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

<style scoped>
.landscape-settlement { display:none; }
/* The outer game stage is always 1280×720, regardless of physical orientation. */
.game-over-overlay { padding:16px; }
.game-over-panel { width:1080px; max-width:none; height:560px; max-height:none; overflow:hidden; }
  .game-over-panel > header, .game-over-panel > footer,
  .game-over-panel > div:not(.landscape-settlement) { display:none; }
  .landscape-settlement { display:flex; flex-direction:row; gap:20px; width:100%; height:100%; min-height:0; padding:20px; color:#fef3c7; }
  .landscape-settlement-summary { display:flex; flex:0 0 42%; flex-direction:column; min-width:0; min-height:0; }
  .landscape-settlement-topline { display:flex; align-items:center; justify-content:space-between; gap:8px; color:#fbbf24; font-size:13px; font-weight:800; letter-spacing:.12em; }
  .landscape-settlement-topline button { flex:none; border:1px solid #fbbf2470; border-radius:7px; padding:3px 7px; color:#fde68a; letter-spacing:0; }
  .landscape-settlement-summary h2 { margin-top:10px; color:#fff7e1; font-size:27px; font-weight:900; line-height:1.2; }
  .landscape-settlement-score { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 9px; margin-top:10px; color:#fde68a; font-size:15px; line-height:1.3; }
  .landscape-settlement-score strong { font-size:25px; }
  .landscape-settlement-note { margin-top:5px; color:#d1fae5; font-size:13px; }
  .landscape-settlement-id { display:flex; align-items:center; gap:7px; margin-top:16px; color:#fef3c7; font-size:14px; font-weight:700; white-space:nowrap; }
  .landscape-settlement-id button { border:1px solid #fbbf2470; border-radius:6px; padding:2px 6px; color:#fde68a; font-size:10px; }
  .landscape-settlement-copy { margin-top:3px; color:#86efac; font-size:10px; }
  .landscape-settlement-actions { display:grid; gap:9px; margin-top:auto; }
  .landscape-settlement-actions button { min-height:48px; border-radius:9px; padding:9px 12px; font-size:15px; font-weight:800; line-height:1.2; cursor:pointer; }
  .landscape-settlement-next { background:#fbbf24; color:#422006; }
  .landscape-settlement-history-button { border:1px solid #5eead477; color:#d1fae5; }
  .landscape-settlement-details { display:flex; flex:1 1 0; flex-direction:column; min-width:0; min-height:0; border-left:1px solid #fbbf2440; padding-left:20px; }
  .landscape-settlement-details h3 { flex:none; margin:0 0 12px; color:#fef3c7; font-size:18px; font-weight:800; }
  .landscape-settlement-seats { display:grid; grid-template-rows:repeat(3,minmax(0,1fr)); gap:9px; flex:1; min-height:0; }
  .landscape-settlement-seats:has(>article:nth-child(4)) { grid-template-rows:repeat(4,minmax(0,1fr)); }
  .landscape-settlement-seat { display:flex; flex-direction:column; justify-content:center; gap:5px; min-width:0; min-height:0; border:1px solid #28695b; border-radius:9px; padding:9px 12px; background:#063a34; overflow:hidden; }
  .landscape-settlement-seat.is-winner { border-color:#fbbf24a0; background:#49350d; }
  .landscape-settlement-seat-main { display:flex; align-items:baseline; justify-content:space-between; gap:8px; font-size:15px; line-height:1.25; }
  .landscape-settlement-seat-main strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .landscape-settlement-seat-main b { flex:none; color:#cbd5d1; font-size:19px; }
  .landscape-settlement-seat-main b.positive { color:#86efac; }
  .landscape-settlement-seat-main b.negative { color:#fda4af; }
  .landscape-settlement-seat p { overflow:hidden; margin-top:3px; color:#cbd5d1; font-size:13px; line-height:1.3; text-overflow:ellipsis; white-space:nowrap; }
  .landscape-winner-hand { min-height:0; margin-top:12px; border-top:1px solid #fbbf243b; padding-top:9px; overflow:auto; }
  .landscape-winner-hand > p { display:flex; justify-content:space-between; gap:5px; font-size:10px; font-weight:700; }
  .landscape-winner-groups, .landscape-seat-tiles { display:flex; flex-wrap:wrap; align-items:center; gap:2px; min-width:0; }
  .landscape-winner-groups { margin-top:5px; }
  .landscape-winner-group, .landscape-seat-meld { display:inline-flex; align-items:center; gap:1px; flex:none; border:1px solid #fbbf2455; border-radius:4px; padding:1px; }
  .settlement-mini-tile { display:inline-flex; flex:none; align-items:center; justify-content:center; width:18px; height:24px; overflow:hidden; border:1px solid #d4cbb8; border-radius:3px; background:#fffdf0; box-shadow:1px 2px 0 #b2cbb5; font-size:10px; font-weight:800; line-height:1; }
  .landscape-winner-group .settlement-mini-tile { width:28px; height:38px; font-size:15px; }
  .settlement-mini-tile.is-winning-tile { position:relative; overflow:visible; outline:2px solid #fbbf24; outline-offset:1px; }
  .settlement-mini-tile.is-winning-tile::after { content:'胡'; position:absolute; top:-9px; right:-7px; z-index:2; border:1px solid #fcd34d; border-radius:4px; padding:1px 2px; background:linear-gradient(135deg,#be123c,#7f1d1d); color:#fff7d6; font-size:8px; line-height:1; }
  .landscape-winner-breakdown, .landscape-seat-breakdown { display:flex; flex-wrap:wrap; gap:2px 6px; min-width:0; color:#d1fae5; font-size:9px; line-height:1.15; }
  .landscape-winner-breakdown { margin-top:9px; gap:5px 9px; font-size:13px; line-height:1.3; }
  .landscape-winner-breakdown strong { color:#fde68a; }
  .landscape-seat-tiles { margin-top:3px; }
  .landscape-seat-meld { border-color:#5eead477; }
  .landscape-seat-breakdown { margin-top:4px; color:#c4b5fd; font-size:13px; line-height:1.2; }
  .landscape-settlement-history { display:grid; align-content:start; gap:5px; overflow:hidden; font-size:11px; line-height:1.2; }
  .landscape-settlement-history p { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .landscape-settlement-history-pages { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:3px; color:#fde68a; }
  .landscape-settlement-history-pages button { border:1px solid #5eead477; border-radius:5px; padding:3px 7px; color:#d1fae5; }
  .landscape-settlement-history-pages button:disabled { opacity:.4; }
</style>
