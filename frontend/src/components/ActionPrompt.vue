<script setup>
/**
 * 副露 / 和牌 / 过牌决策面板；PvE 中嵌在手牌下方。
 * 数据源：后端 call_decision（candidates + recommended_action + reason）。
 */
import { computed } from 'vue'
import {
  SEAT_WINDS,
  relativeOpponents,
  tileLabel,
  tileSuitClass,
} from '../constants/tiles.js'
import { substituteTileLabel } from '../utils/callDetector.js'

const ACTION_META = {
  chi: { label: '吃', short: '吃', tone: 'chi' },
  pong: { label: '碰', short: '碰', tone: 'pong' },
  ming_gang: { label: '明杠', short: '杠', tone: 'gang' },
  an_gang: { label: '暗杠', short: '暗杠', tone: 'gang' },
  hu: { label: '捉铳', short: '胡', tone: 'hu' },
  catch_win: { label: '捉铳', short: '胡', tone: 'hu' },
  self_draw_win: { label: '自摸', short: '自摸', tone: 'hu' },
  pass: { label: '过牌', short: '过', tone: 'pass' },
}

const props = defineProps({
  /**
   * 后端 CallDecisionResponse
   * @type {{
   *   recommended_action?: { action_type: string, tiles?: string[], provider_seat?: string },
   *   reason?: string,
   *   candidates?: Array<{ action: object, net_ev: number, note?: string }>,
   *   available_actions?: Array<object>,
   *   est_final_points?: number,
   * }}
   */
  callDecision: {
    type: Object,
    required: true,
  },
  /** 自家门风，用于上/对/下家标签 */
  seatWind: {
    type: String,
    default: 'E',
  },
  /** 显式指定打出张（缺省从动作 tiles / provider 推断） */
  discardedTile: {
    type: String,
    default: '',
  },
  /** 显式指定出牌方（缺省从 recommended / candidates 推断） */
  providerSeat: {
    type: String,
    default: '',
  },
  dealerTile: {
    type: String,
    default: '',
  },
  /** 预估胡数（胡牌卡片）；也可放在 callDecision.est_final_points */
  estHuPoints: {
    type: Number,
    default: null,
  },
  /** 是否禁用按钮（步进请求中） */
  disabled: {
    type: Boolean,
    default: false,
  },
  inline: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits({
  /**
   * @param {{
   *   action_type: string,
   *   tiles: string[],
   *   provider_seat: string,
   *   net_ev: number|null,
   *   note?: string,
   * }} payload
   */
  'action-selected': (payload) =>
    payload && typeof payload.action_type === 'string',
  dismiss: () => true,
})

const seatRoleMap = computed(() => {
  const map = Object.create(null)
  for (const s of relativeOpponents(props.seatWind)) {
    map[s.seat_wind] = s.role
  }
  return map
})

function windLabel(code) {
  return SEAT_WINDS.find((w) => w.code === code)?.label || code
}

function roleOf(seat) {
  if (!seat) return '对手'
  return seatRoleMap.value[seat] || `${windLabel(seat)}家`
}

/** 统一动作列表：优先 available_actions，否则用 candidates */
const actionRows = computed(() => {
  const cd = props.callDecision || {}
  const candByKey = new Map()
  for (const c of cd.candidates || []) {
    const a = c.action || {}
    const key = actionKey(a)
    candByKey.set(key, c)
  }

  const rawList =
    Array.isArray(cd.available_actions) && cd.available_actions.length
      ? cd.available_actions
      : (cd.candidates || []).map((c) => c.action)

  const seen = new Set()
  const rows = []
  for (const raw of rawList) {
    if (!raw) continue
    const action = normalizeAction(raw)
    const key = actionKey(action)
    if (seen.has(key)) continue
    seen.add(key)
    const matched = candByKey.get(key)
    rows.push({
      action,
      net_ev:
        matched?.net_ev ??
        (typeof raw.net_ev === 'number' ? raw.net_ev : null),
      note: matched?.note || raw.note || '',
      isRecommended: isSameAction(action, cd.recommended_action),
    })
  }

  // 推荐动作置顶，其余按 EV 降序（inf 胡牌最前）
  rows.sort((a, b) => {
    if (a.isRecommended !== b.isRecommended) return a.isRecommended ? -1 : 1
    return evSortValue(b.net_ev) - evSortValue(a.net_ev)
  })
  return rows
})

const recommended = computed(() => {
  const a = props.callDecision?.recommended_action
  return a ? normalizeAction(a) : null
})

const recommendedType = computed(
  () => recommended.value?.action_type || '',
)

const resolvedProvider = computed(() => {
  if (props.providerSeat) return props.providerSeat
  if (recommended.value?.provider_seat) return recommended.value.provider_seat
  for (const row of actionRows.value) {
    if (row.action.provider_seat) return row.action.provider_seat
  }
  return ''
})

const resolvedDiscard = computed(() => {
  if (props.discardedTile) return props.discardedTile
  // HU / 碰 / 杠：tiles 含打出张；吃：需 props 或取与手牌组合中出现在河的那张
  const rec = recommended.value
  if (rec?.tiles?.length) {
    if (rec.action_type === 'hu') return rec.tiles[0]
    if (rec.action_type === 'pong' || rec.action_type === 'ming_gang') {
      return rec.tiles[0]
    }
  }
  for (const row of actionRows.value) {
    const t = row.action.tiles || []
    if (row.action.action_type === 'hu' && t[0]) return t[0]
    if (
      (row.action.action_type === 'pong' ||
        row.action.action_type === 'ming_gang') &&
      t[0]
    ) {
      return t[0]
    }
  }
  return ''
})

const hasHu = computed(() =>
  actionRows.value.some((r) => r.action.action_type === 'hu'),
)

const recommendPass = computed(() => recommendedType.value === 'pass')

const huPoints = computed(() => {
  if (props.estHuPoints != null && !Number.isNaN(Number(props.estHuPoints))) {
    return Number(props.estHuPoints)
  }
  const fromCd = props.callDecision?.est_final_points
  if (fromCd != null && !Number.isNaN(Number(fromCd))) return Number(fromCd)
  return null
})

const huActionEv = computed(() =>
  actionRows.value.find((r) => r.action.action_type === 'hu')?.net_ev ?? null,
)
const passActionEv = computed(() =>
  actionRows.value.find((r) => r.action.action_type === 'pass')?.net_ev ?? null,
)

function displayTile(tile) {
  return substituteTileLabel(tile, props.dealerTile)
}

const passReason = computed(() => {
  const reason = props.callDecision?.reason || ''
  if (recommendPass.value && reason) return reason
  const passRow = actionRows.value.find(
    (r) => r.action.action_type === 'pass',
  )
  return passRow?.note || reason || '保留硬胡 / 门清期望更高'
})

function normalizeAction(raw) {
  return {
    action_type: raw.action_type || raw.type || '',
    tiles: Array.isArray(raw.tiles) ? [...raw.tiles] : [],
    provider_seat: raw.provider_seat || '',
  }
}

function actionKey(a) {
  if (!a) return ''
  return `${a.action_type}|${(a.tiles || []).join(',')}|${a.provider_seat || ''}`
}

function isSameAction(a, b) {
  if (!a || !b) return false
  return actionKey(normalizeAction(a)) === actionKey(normalizeAction(b))
}

function evSortValue(ev) {
  if (ev == null || Number.isNaN(Number(ev))) return Number.NEGATIVE_INFINITY
  if (!Number.isFinite(Number(ev))) return Number.POSITIVE_INFINITY
  return Number(ev)
}

function formatEv(score) {
  if (score == null || Number.isNaN(Number(score))) return '—'
  const n = Number(score)
  if (!Number.isFinite(n)) return n > 0 ? '+∞' : '−∞'
  const abs = Math.abs(n)
  const body = Number.isInteger(abs) ? String(abs) : abs.toFixed(1)
  if (n > 0) return `+${body}`
  if (n < 0) return `−${body}`
  return '0'
}

function actionLabel(type) {
  return ACTION_META[type]?.label || type
}

function buttonClass(row) {
  const type = row.action.action_type
  const base =
    'group relative flex min-w-[5.5rem] flex-1 flex-col items-center gap-1 rounded-2xl px-3 py-3 text-center transition duration-200 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/80 disabled:cursor-not-allowed disabled:opacity-45'
  const recommendedRing = row.isRecommended
    ? ' ring-2 ring-offset-2 ring-offset-emerald-950 scale-[1.03]'
    : ' hover:-translate-y-0.5 hover:shadow-lg'

  if (type === 'hu') {
    return `${base}${recommendedRing} bg-gradient-to-b from-rose-500 to-amber-500 text-amber-50 shadow-lg shadow-rose-900/40 ring-amber-300`
  }
  if (type === 'pass') {
    return `${base}${recommendedRing} border border-sky-400/50 bg-sky-950/80 text-sky-50 ring-sky-300/80`
  }
  if (type === 'pong') {
    return `${base}${recommendedRing} border border-amber-400/45 bg-amber-950/70 text-amber-50 ring-amber-400/70`
  }
  if (type === 'ming_gang' || type === 'an_gang') {
    return `${base}${recommendedRing} border border-violet-400/45 bg-violet-950/70 text-violet-50 ring-violet-400/70`
  }
  // chi
  return `${base}${recommendedRing} border border-emerald-400/45 bg-emerald-950/70 text-emerald-50 ring-emerald-400/70`
}

function selectAction(row) {
  if (props.disabled) return
  const action = row.action || {}
  const type = action.action_type
  // 明杠：确保 emit 含 4 张（含打出张）
  let tiles = [...(action.tiles || [])]
  if (type === 'ming_gang' && tiles.length !== 4) {
    const disc =
      props.discardedTile ||
      resolvedDiscard.value ||
      tiles[0]
    if (disc) tiles = [disc, disc, disc, disc]
  }
  emit('action-selected', {
    action_type: type,
    tiles,
    provider_seat: action.provider_seat || resolvedProvider.value,
    net_ev: row.net_ev,
    note: row.note,
  })
}
</script>

<template>
  <Teleport to="body" :disabled="inline">
    <div
      class="action-prompt-wrap flex w-full"
      :class="inline ? 'relative justify-start pt-4 pb-2' : 'pointer-events-none fixed inset-x-0 bottom-0 z-50 justify-center p-3 sm:p-5'"
      role="dialog"
      :aria-modal="inline ? undefined : 'true'"
      aria-label="副露与和牌决策"
    >
      <div
        class="action-prompt-panel pointer-events-auto w-full max-w-xl origin-bottom overflow-hidden rounded-3xl border border-rose-400/50 bg-emerald-950/95 shadow-2xl shadow-rose-950/40 ring-2 ring-rose-500 backdrop-blur-md"
      >
        <!-- 顶栏：对手打出 -->
        <header
          class="relative border-b border-amber-500/20 bg-gradient-to-r from-teal-900/90 via-emerald-900/80 to-slate-900/90 px-4 py-3.5 sm:px-5"
        >
          <div
            class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(251,191,36,0.18),_transparent_55%)]"
          />
          <p
            class="relative text-[11px] font-medium uppercase tracking-[0.18em] text-amber-200/70"
          >
            系统综合推荐
          </p>
          <div
            class="relative mt-1.5 flex flex-wrap items-center gap-2 text-sm text-amber-50 sm:text-base"
          >
            <span class="font-medium text-teal-100/90">
              对手（{{ roleOf(resolvedProvider) }}·{{
                windLabel(resolvedProvider) || '—'
              }}）打出
            </span>
            <span
              v-if="resolvedDiscard"
              class="inline-flex h-9 w-7 items-center justify-center rounded-md border text-sm font-bold shadow-md"
              :class="tileSuitClass(resolvedDiscard)"
            >
              {{ tileLabel(resolvedDiscard) }}
            </span>
            <span v-else class="text-teal-300/70">（未知张）</span>
          </div>
          <p
            v-if="callDecision.reason && !recommendPass && !hasHu"
            class="relative mt-2 text-xs leading-relaxed text-teal-200/80"
          >
            {{ callDecision.reason }}
          </p>
        </header>

        <div class="space-y-3 px-4 py-4 sm:px-5 sm:py-5">
          <!-- 可胡：红金大卡 -->
          <div
            v-if="hasHu"
            class="hu-banner relative overflow-hidden rounded-2xl border-2 border-amber-300/80 bg-gradient-to-br from-rose-600 via-red-600 to-amber-500 px-4 py-5 text-center shadow-xl shadow-rose-950/50 sm:px-6 sm:py-6"
          >
            <div
              class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,_rgba(255,255,255,0.35),_transparent_50%)]"
            />
            <p
              class="relative text-xs font-semibold uppercase tracking-[0.25em] text-amber-100/90"
            >
              台州 · 无振听 · 无包牌
            </p>
            <p
              class="relative mt-2 text-2xl font-black tracking-wide text-amber-50 drop-shadow sm:text-3xl"
            >
              即时和牌！
            </p>
            <p class="relative mt-2 text-lg font-semibold text-amber-100 sm:text-xl">
              预估胡数
              <span class="ml-1 font-black text-white">
                {{ huPoints != null ? huPoints : '—' }}
              </span>
            </p>
            <p class="relative mt-2 text-xs font-semibold text-amber-50/95 sm:text-sm">
              捉铳 Net EV
              <span class="ml-1 font-black">{{ formatEv(callDecision.hu_ev ?? huActionEv) }}</span>
              <span class="mx-1 text-amber-100/60">·</span>
              过牌 Net EV
              <span class="ml-1 font-black">{{ formatEv(callDecision.pass_ev ?? passActionEv) }}</span>
            </p>
          </div>

          <!-- 建议过牌 -->
          <div
            v-if="recommendPass"
            class="pass-banner rounded-2xl border border-sky-400/50 bg-gradient-to-r from-sky-950/90 to-cyan-950/80 px-4 py-3.5 shadow-inner shadow-sky-900/40"
          >
            <p class="text-base font-bold text-sky-100 sm:text-lg">
              建议过牌！
            </p>
            <p class="mt-1 text-sm leading-relaxed text-sky-200/90">
              原因：{{ passReason }}
            </p>
          </div>

          <!-- 动作按钮 -->
          <div
            class="flex flex-wrap gap-2.5"
            role="group"
            aria-label="可选响应动作"
          >
            <button
              v-for="row in actionRows"
              :key="actionKey(row.action)"
              type="button"
              :disabled="disabled"
              :class="buttonClass(row)"
              @click="selectAction(row)"
            >
              <span
                v-if="row.isRecommended"
                class="absolute -top-2 right-2 rounded-full bg-amber-400 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-950"
              >
                荐
              </span>
              <span class="text-base font-bold tracking-wide sm:text-lg">
                {{ actionLabel(row.action.action_type) }}
              </span>
              <span
                v-if="row.action.tiles?.length && row.action.action_type !== 'pass'"
                class="flex flex-wrap justify-center gap-0.5"
              >
                <span
                  v-for="(t, i) in row.action.tiles"
                  :key="`${t}-${i}`"
                  class="inline-flex h-6 w-5 items-center justify-center rounded border text-[10px] font-semibold opacity-95"
                  :class="tileSuitClass(t)"
                >
                  {{ displayTile(t) }}
                </span>
              </span>
              <span
                class="text-[11px] font-medium tabular-nums opacity-90"
                :class="
                  row.action.action_type === 'hu'
                    ? 'text-amber-50'
                    : 'text-white/75'
                "
              >
                {{ actionLabel(row.action.action_type) }} EV
                {{ formatEv(row.net_ev) }}
              </span>
            </button>
          </div>

          <p
            v-if="actionRows.length"
            class="text-center text-[11px] text-teal-300/65"
          >
            点击按钮确认动作 · Net EV 为该选择相对期望
          </p>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.action-prompt-panel {
  animation: prompt-rise 0.38s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.hu-banner {
  animation: hu-pulse 1.6s ease-in-out infinite;
}

.pass-banner {
  animation: pass-glow 2s ease-in-out infinite;
}

@keyframes prompt-rise {
  from {
    opacity: 0;
    transform: translateY(1.25rem) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes hu-pulse {
  0%,
  100% {
    box-shadow:
      0 0 0 0 rgba(251, 191, 36, 0.35),
      0 12px 28px rgba(127, 29, 29, 0.45);
  }
  50% {
    box-shadow:
      0 0 0 8px rgba(251, 191, 36, 0),
      0 16px 36px rgba(127, 29, 29, 0.55);
  }
}

@keyframes pass-glow {
  0%,
  100% {
    border-color: rgba(56, 189, 248, 0.45);
  }
  50% {
    border-color: rgba(125, 211, 252, 0.85);
  }
}

@media (prefers-reduced-motion: reduce) {
  .action-prompt-panel,
  .hu-banner,
  .pass-banner {
    animation: none;
  }
}
</style>
