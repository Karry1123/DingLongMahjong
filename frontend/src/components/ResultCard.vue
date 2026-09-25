<script setup>
/**
 * 切牌推荐可视化：净 EV 冠军卡 + 策略标签 + 候选展开（无包牌攻防拆解）
 */
import { computed, ref } from 'vue'
import {
  SEAT_WINDS,
  relativeOpponents,
  tileLabel,
  tileSuitClass,
} from '../constants/tiles.js'

/**
 * @typedef {{
 *   tile: string,
 *   ev_score: number,
 *   attack_ev?: number,
 *   defense_loss?: number,
 *   deal_in_risks?: Record<string, number>,
 *   defense_details?: Record<string, {
 *     tenpai_prob: number,
 *     deal_in_rate: number,
 *     est_ron_points: number,
 *     loss_if_deal_in: number,
 *     payment_label: string,
 *     is_dealer: boolean,
 *   }>,
 *   is_safe_all?: boolean,
 *   effective_count: number,
 *   is_hard_hu: boolean,
 *   est_base_points: number,
 *   est_final_points: number,
 * }} Candidate
 */

const props = defineProps({
  bestTile: {
    type: String,
    required: true,
  },
  /** @type {Candidate[]} */
  candidates: {
    type: Array,
    default: () => [],
  },
  /** 暗杠 / 补杠候选 */
  selfGangCandidates: {
    type: Array,
    default: () => [],
  },
  bestAction: { type: Object, default: null },
  /** 自家门风，用于上/对/下家标签 */
  seatWind: {
    type: String,
    default: 'E',
  },
  /** 自家是否庄家 */
  isDealer: {
    type: Boolean,
    default: false,
  },
  /** 可点击冠军/候选触发切牌 */
  interactive: {
    type: Boolean,
    default: false,
  },
  /** 后台 EV 推演中（占位，避免高度坍塌） */
  loading: {
    type: Boolean,
    default: false,
  },
  /** 当前亦可自摸 */
  canSelfWinHint: {
    type: Boolean,
    default: false,
  },
  /** PvE 工作台压缩展示，优先露出候选对比。 */
  compact: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits({
  /** @param {string} tile */
  'select-tile': (tile) => typeof tile === 'string' && tile.length > 0,
  /** @param {{ action_type: string, tile: string, tiles?: string[] }} gang */
  'select-self-gang': (gang) =>
    !!gang && typeof gang.tile === 'string' && !!gang.action_type,
})

const expandedTile = ref(null)
const mobileDetailsOpen = ref(false)

const bestMeta = computed(
  () => props.candidates.find((c) => c.tile === props.bestTile) ?? null,
)

/** 列表含冠军，便于对比；展开任意行 */
const rankedCandidates = computed(() => props.candidates)

const seatRoleMap = computed(() => {
  const map = Object.create(null)
  for (const s of relativeOpponents(props.seatWind)) {
    map[s.seat_wind] = s.role
  }
  return map
})

const windLabel = (code) =>
  SEAT_WINDS.find((w) => w.code === code)?.label || code

function formatEv(score) {
  if (score == null || Number.isNaN(Number(score))) return '—'
  const n = Number(score)
  const abs = Math.abs(n)
  const body = Number.isInteger(abs) ? String(abs) : abs.toFixed(2)
  if (n > 0) return `+${body}`
  if (n < 0) return `−${body}`
  return '0'
}

function formatPlain(score) {
  if (score == null || Number.isNaN(Number(score))) return '—'
  const n = Number(score)
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

function formatPct(p) {
  if (p == null || Number.isNaN(Number(p))) return '—'
  return `${(Number(p) * 100).toFixed(1)}%`
}

function maxDealInRisk(item) {
  const risks = Object.values(item?.deal_in_risks || {})
  if (!risks.length) return 0
  return Math.max(0, ...risks.map(Number))
}

/**
 * 策略倾向标签
 * - 绝对安牌：全场现物
 * - 极速进攻：进攻分高且防守损相对可忽略
 * - 战术避险：存在放铳权衡（常对应避庄/避大牌）
 */
function strategyTag(item) {
  if (!item) return { key: 'neutral', label: '均衡', tip: '' }
  if (item.is_safe_all) {
    return {
      key: 'safe',
      label: '绝对安牌',
      tip: '全场现物，零放铳风险（无包牌）',
      className:
        'bg-emerald-950/90 text-emerald-200 ring-1 ring-emerald-400/50',
    }
  }
  const attack = Number(item.attack_ev) || 0
  const defense = Number(item.defense_loss) || 0
  const maxRisk = maxDealInRisk(item)
  const uke = Number(item.effective_count) || 0

  const ignoreDefense =
    defense <= Math.max(2, attack * 0.12) &&
    (uke >= 2 || maxRisk < 0.08) &&
    attack > 0

  if (ignoreDefense) {
    return {
      key: 'attack',
      label: '极速进攻',
      tip: '进张/进攻期望突出，可暂时无视微小铳率',
      className: 'bg-rose-950/90 text-rose-100 ring-1 ring-rose-400/45',
    }
  }

  return {
    key: 'tactical',
    label: '战术避险',
    tip: '权衡赔付非对称：倾向放铳低损闲家，规避庄家/高副露大牌',
    className: 'bg-sky-950/90 text-sky-100 ring-1 ring-sky-400/45',
  }
}

const bestStrategy = computed(() => strategyTag(bestMeta.value))

const topSelfGang = computed(() => props.selfGangCandidates?.[0] || null)

const gangBeatsBestDiscard = computed(() => {
  const g = topSelfGang.value
  const d = bestMeta.value
  if (!g || d?.ev_score == null) return false
  return Number(g.ev_score) > Number(d.ev_score)
})

function gangLabel(g) {
  if (!g) return ''
  return g.action_type === 'bu_gang' ? '补杠' : '暗杠'
}

function toggleExpand(tile) {
  expandedTile.value = expandedTile.value === tile ? null : tile
}

function defenseRows(item) {
  const details = item?.defense_details || {}
  const seats = relativeOpponents(props.seatWind).map((s) => s.seat_wind)
  // 若无相对座次数据，退回 Object.keys
  const order = seats.some((s) => details[s] != null)
    ? seats
    : Object.keys(details)
  return order
    .filter((sw) => details[sw])
    .map((sw) => {
      const d = details[sw]
      return {
        seat_wind: sw,
        role: seatRoleMap.value[sw] || windLabel(sw),
        windName: windLabel(sw),
        ...d,
      }
    })
}
</script>

<template>
  <section
    class="w-full max-w-2xl overflow-hidden rounded-2xl border border-amber-400/40 bg-teal-950/55 shadow-xl backdrop-blur-sm"
    aria-label="切牌推荐结果"
  >
    <!-- EV 推演中：固定高度占位，避免取消后高度坍塌闪烁 -->
    <div
      v-if="loading"
      class="flex min-h-[7.5rem] flex-col items-center justify-center gap-2 border-b border-amber-400/20 bg-teal-950/40 px-4 py-6"
      aria-live="polite"
      aria-busy="true"
    >
      <div
        class="h-7 w-7 animate-spin rounded-full border-2 border-amber-400/25 border-t-amber-300"
      />
      <p class="text-center text-sm text-amber-100/90">
        正在推演切牌 EV…
      </p>
      <p class="text-center text-[11px] text-teal-200/75">
        也可直接点击手牌快速切出
      </p>
    </div>

    <!-- ========== 暗杠 / 补杠决策条 ========== -->
    <div
      v-if="selfGangCandidates.length"
      class="border-b border-violet-500/35 bg-violet-950/50"
      :class="compact ? 'px-3 py-2' : 'px-4 py-3 sm:px-6'"
    >
      <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-200/80" :class="compact ? 'mb-1' : 'mb-2'">
        开杠决策
        <span
          v-if="gangBeatsBestDiscard"
          class="ml-2 rounded bg-amber-400/20 px-1.5 py-0.5 text-[10px] font-bold normal-case tracking-normal text-amber-100"
        >EV 高于最优切牌</span>
      </p>
      <ul class="flex flex-col" :class="compact ? 'gap-1' : 'gap-2'">
        <li
          v-for="(g, gi) in selfGangCandidates"
          :key="`sg-${g.action_type}-${g.tile}-${gi}`"
        >
          <button
            type="button"
            class="flex w-full flex-wrap items-center justify-between gap-2 rounded-xl border border-violet-400/45 bg-violet-900/40 text-left transition hover:border-violet-300/70 hover:bg-violet-800/50 disabled:cursor-not-allowed disabled:opacity-50"
            :class="compact ? 'px-2 py-1.5' : 'px-3 py-2.5'"
            :disabled="!interactive"
            @click="interactive && emit('select-self-gang', g)"
          >
            <span class="text-sm font-semibold text-violet-50">
              执行{{ gangLabel(g) }}
              <span class="ml-1 text-amber-100">[{{ tileLabel(g.tile) }}]</span>
              <span v-if="bestAction?.action_type === g.action_type && bestAction?.tile === g.tile" class="ml-2 rounded bg-amber-400/25 px-1.5 py-0.5 text-[10px] text-amber-100">本巡首选</span>
            </span>
            <span class="flex items-center gap-2 text-xs">
              <span class="rounded bg-amber-500/25 px-1.5 py-0.5 font-bold text-amber-100">
                +{{ g.est_hu_bonus }} 胡
              </span>
              <span class="font-semibold tabular-nums text-violet-100">
                净 EV {{ formatEv(g.ev_score) }}
              </span>
            </span>
          </button>
          <p
            v-if="g.note && !compact"
            class="mt-1 px-1 text-[11px] text-violet-200/65"
          >
            {{ g.note }}
          </p>
        </li>
      </ul>
    </div>

    <!-- ========== 冠军位 ========== -->
    <div
      v-if="!loading || bestTile"
      class="ev-winner relative bg-gradient-to-br from-amber-300 via-yellow-400 to-amber-500"
      :class="compact ? 'px-3 py-3 sm:px-4' : 'px-5 py-8 sm:px-8 sm:py-10'"
    >
      <div
        class="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_rgba(255,255,255,0.35),_transparent_55%)]"
      />
      <p
        class="relative text-center font-medium uppercase tracking-[0.2em] text-amber-950/70"
        :class="compact ? 'mb-1 text-[10px]' : 'mb-2 text-xs'"
      >
        净 EV 推荐切牌
      </p>

      <div
        v-if="bestMeta"
        class="relative flex justify-center gap-2"
        :class="compact ? 'mb-1' : 'mb-2'"
      >
        <span
          v-if="canSelfWinHint"
          class="inline-flex items-center rounded-full bg-rose-700/90 px-3 py-1 text-xs font-bold text-amber-50 ring-1 ring-amber-200/60"
        >
          亦可宣告自摸
        </span>
        <span
          class="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold tracking-wide"
          :class="bestStrategy.className"
          :title="bestStrategy.tip"
        >
          {{ bestStrategy.label }}
        </span>
      </div>

      <div
        class="relative flex flex-col items-center sm:flex-row sm:justify-center"
        :class="compact ? 'gap-2 sm:gap-3' : 'gap-4 sm:gap-6'"
      >
        <button
          type="button"
          class="flex items-center justify-center rounded-xl border-2 shadow-lg transition"
          :class="[
            tileSuitClass(bestTile),
            compact ? 'h-12 w-9 sm:h-14 sm:w-10' : 'h-20 w-14 sm:h-24 sm:w-16',
            interactive
              ? 'cursor-pointer ring-2 ring-amber-950/30 hover:scale-105 active:scale-95'
              : 'cursor-default',
          ]"
          :disabled="!interactive"
          :title="interactive ? `确认打出 ${tileLabel(bestTile)}` : undefined"
          @click="interactive && emit('select-tile', bestTile)"
        >
          <span class="font-bold" :class="compact ? 'text-sm' : 'text-xl sm:text-2xl'">{{
            tileLabel(bestTile)
          }}</span>
        </button>

        <div class="w-full max-w-md text-center sm:text-left">
          <h2
            class="font-bold tracking-wide text-amber-950"
            :class="compact ? 'text-xl' : 'text-2xl sm:text-3xl'"
          >
            {{ bestAction?.action_type && bestAction.action_type !== 'discard' ? '不杠时打出：' : '打出：' }}{{ tileLabel(bestTile) }}
          </h2>
          <p v-if="!compact" class="mt-1 text-sm text-amber-950/70">
            编码 {{ bestTile }}
            <button
              v-if="interactive"
              type="button"
              class="ml-2 rounded-lg bg-amber-950/15 px-2 py-0.5 text-xs font-semibold text-amber-950 underline-offset-2 hover:bg-amber-950/25 hover:underline"
              @click="emit('select-tile', bestTile)"
            >
              确认切出
            </button>
          </p>

          <template v-if="bestMeta">
            <!-- Net EV 公式 -->
            <div
              class="rounded-xl border border-amber-950/15 bg-amber-950/10 text-amber-950"
              :class="compact ? 'mt-1 px-2 py-1.5 text-xs' : 'mt-4 px-3 py-3 text-sm'"
            >
              <p v-if="!compact" class="text-[11px] font-medium uppercase tracking-wider text-amber-950/55">
                得分拆解
              </p>
              <p class="font-semibold tabular-nums leading-relaxed" :class="compact ? 'flex flex-wrap items-center gap-x-1' : 'mt-1'">
                Net EV
                <span class="text-amber-950">{{ formatEv(bestMeta.ev_score) }}</span>
                <span class="mx-1 font-normal text-amber-950/50">=</span>
                进攻
                <span class="text-emerald-900">{{
                  formatEv(bestMeta.attack_ev ?? 0)
                }}</span>
                <span class="mx-1 font-normal text-amber-950/50">−</span>
                防守损
                <span class="text-rose-800">{{
                  formatEv(-(bestMeta.defense_loss ?? 0))
                }}</span>
              </p>
              <p v-if="!compact" class="mt-1 text-[11px] text-amber-950/55">
                另含向听×120 惩罚（已折入净 EV）；无包牌 · 庄全额 / 闲对闲半额
              </p>
            </div>

            <dl
              class="text-left text-amber-950"
              :class="compact ? 'mt-1.5 flex flex-wrap gap-1 text-[11px]' : 'mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm'"
            >
              <div :class="compact ? 'flex items-center gap-1 rounded-md bg-amber-950/10 px-1.5 py-1' : ''">
                <dt class="text-amber-950/60" :class="compact ? 'text-[11px]' : 'text-xs'">有效进张</dt>
                <dd class="font-semibold tabular-nums">
                  {{ bestMeta.effective_count }}
                </dd>
              </div>
              <div :class="compact ? 'flex items-center gap-1 rounded-md bg-amber-950/10 px-1.5 py-1' : ''">
                <dt class="text-amber-950/60" :class="compact ? 'text-[11px]' : 'text-xs'">最大放铳率</dt>
                <dd class="font-semibold tabular-nums">
                  {{ formatPct(maxDealInRisk(bestMeta)) }}
                </dd>
              </div>
              <div :class="compact ? 'flex items-center gap-1 rounded-md bg-amber-950/10 px-1.5 py-1' : ''">
                <dt class="text-amber-950/60" :class="compact ? 'text-[11px]' : 'text-xs'">预估结算胡</dt>
                <dd class="font-semibold tabular-nums">
                  {{ bestMeta.est_final_points }}
                  <span
                    v-if="bestMeta.is_hard_hu"
                    class="ml-1 text-[10px] font-bold text-amber-900/80"
                    >硬胡</span
                  >
                </dd>
              </div>
              <div :class="compact ? 'flex items-center gap-1 rounded-md bg-amber-950/10 px-1.5 py-1' : ''">
                <dt class="text-amber-950/60" :class="compact ? 'text-[11px]' : 'text-xs'">全场现物</dt>
                <dd class="font-semibold">
                  {{ bestMeta.is_safe_all ? '是' : '否' }}
                </dd>
              </div>
            </dl>
            <p
              v-if="bestStrategy.tip && !compact"
              class="mt-2 text-xs text-amber-950/65"
            >
              {{ bestStrategy.tip }}
            </p>
          </template>
        </div>
      </div>
    </div>

    <button
      v-if="compact && rankedCandidates.length"
      type="button"
      class="mobile-ev-toggle"
      :aria-expanded="mobileDetailsOpen"
      @click="mobileDetailsOpen = !mobileDetailsOpen"
    >{{ mobileDetailsOpen ? '收起候选' : `候选 ${rankedCandidates.length} ▴` }}</button>

    <!-- ========== 候选对比 ========== -->
    <div
      v-if="!loading || rankedCandidates.length"
      class="ev-candidates"
      :class="[{ 'mobile-ev-open': mobileDetailsOpen }, compact ? 'px-3 py-2' : 'px-4 py-5 sm:px-6 sm:py-6']"
    >
      <h3 class="mb-1 text-sm font-semibold tracking-wide text-amber-50">
        候选对比
      </h3>
      <p v-if="!compact" class="mb-3 text-xs text-teal-300/70">
        点击行展开三家听牌率 / 放铳率 / 点炮赔付（庄全额 · 闲半额）
      </p>

      <p
        v-if="rankedCandidates.length === 0"
        class="text-sm text-teal-300/70"
      >
        暂无候选切牌
      </p>

      <ul :class="compact ? 'space-y-1' : 'space-y-2'" role="list">
        <li
          v-for="(item, idx) in rankedCandidates"
          :key="`${item.tile}-${idx}`"
          class="overflow-hidden rounded-xl border transition"
          :class="
            item.tile === bestTile
              ? 'border-amber-400/50 bg-amber-500/10'
              : 'border-teal-700/40 bg-emerald-950/45'
          "
        >
          <button
            type="button"
            class="flex w-full items-center text-left"
            :class="compact ? 'gap-2 px-2 py-1.5' : 'gap-3 px-3 py-3 sm:px-4'"
            :aria-expanded="expandedTile === item.tile"
            @click="toggleExpand(item.tile)"
          >
            <span
              class="flex shrink-0 items-center justify-center rounded-md border text-xs font-bold"
              :class="[tileSuitClass(item.tile), compact ? 'h-7 w-6' : 'h-10 w-7']"
            >
              {{ tileLabel(item.tile) }}
            </span>

            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <p class="text-sm font-medium text-amber-50">
                  {{ tileLabel(item.tile) }}
                  <span class="text-xs text-teal-400/70">{{ item.tile }}</span>
                  <span
                    v-if="item.tile === bestTile"
                    class="ml-1 text-[10px] font-bold text-amber-300"
                    >推荐</span
                  >
                </p>
                <span
                  class="rounded-full px-2 py-0.5 text-[10px] font-bold"
                  :class="strategyTag(item).className"
                >
                  {{ strategyTag(item).label }}
                </span>
              </div>
              <p class="text-teal-200/85" :class="compact ? 'text-[11px]' : 'mt-0.5 text-xs'">
                净 EV
                <span class="tabular-nums text-amber-200">{{
                  formatEv(item.ev_score)
                }}</span>
                · 进张
                <span class="tabular-nums">{{ item.effective_count }}</span>
                · 最大铳率
                <span class="tabular-nums">{{
                  formatPct(maxDealInRisk(item))
                }}</span>
              </p>
            </div>

            <span
              class="shrink-0 text-teal-300/80 transition"
              :class="expandedTile === item.tile ? 'rotate-180' : ''"
              aria-hidden="true"
              >▾</span
            >
          </button>

          <!-- 展开抽屉 -->
          <div
            v-if="expandedTile === item.tile"
            class="border-t border-teal-800/50 bg-teal-950/50 px-3 py-3 sm:px-4"
          >
            <div
              class="mb-3 flex flex-wrap gap-3 text-xs text-teal-200/90"
            >
              <span
                >进攻
                <strong class="tabular-nums text-emerald-300">{{
                  formatEv(item.attack_ev ?? 0)
                }}</strong></span
              >
              <span
                >防守损
                <strong class="tabular-nums text-rose-300">{{
                  formatPlain(item.defense_loss ?? 0)
                }}</strong></span
              >
              <span
                >结算胡
                <strong class="tabular-nums">{{
                  item.est_final_points
                }}</strong></span
              >
            </div>

            <div
              v-if="defenseRows(item).length === 0"
              class="text-xs text-teal-400/70"
            >
              未录入对手公开信息时，防守明细为空（零放铳期望）。
            </div>

            <div v-else class="overflow-x-auto">
              <table
                class="w-full min-w-[28rem] border-collapse text-left text-xs sm:text-sm"
              >
                <thead>
                  <tr class="border-b border-teal-700/50 text-teal-300/80">
                    <th class="pb-2 pr-2 font-medium">座次</th>
                    <th class="pb-2 pr-2 font-medium tabular-nums">听牌率</th>
                    <th class="pb-2 pr-2 font-medium tabular-nums">放铳率</th>
                    <th class="pb-2 pr-2 font-medium tabular-nums">
                      点炮估分
                    </th>
                    <th class="pb-2 font-medium">自家赔付</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in defenseRows(item)"
                    :key="row.seat_wind"
                    class="border-b border-teal-800/40 text-amber-50/95 last:border-0"
                  >
                    <td class="py-2.5 pr-2">
                      <span class="font-medium">{{ row.role }}</span>
                      <span class="ml-1 text-teal-400/80"
                        >{{ row.windName }}风</span
                      >
                      <span
                        v-if="row.is_dealer"
                        class="ml-1 rounded bg-amber-500/20 px-1 py-0.5 text-[10px] font-bold text-amber-200"
                        >庄</span
                      >
                    </td>
                    <td class="py-2.5 pr-2 tabular-nums">
                      {{ formatPct(row.tenpai_prob) }}
                    </td>
                    <td class="py-2.5 pr-2 tabular-nums">
                      {{ formatPct(row.deal_in_rate) }}
                    </td>
                    <td class="py-2.5 pr-2 tabular-nums">
                      {{ formatPlain(row.est_ron_points) }}
                    </td>
                    <td class="py-2.5">
                      <span class="tabular-nums font-medium text-rose-200/95">
                        {{ formatPlain(row.loss_if_deal_in) }}
                      </span>
                      <span class="ml-1 text-[10px] text-teal-400/80">
                        {{ row.payment_label }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.mobile-ev-toggle { display:none; }
@media screen and (orientation: portrait) and (max-width: 768px) {
  .mobile-ev-toggle { display:block; flex:0 0 auto; padding:5px; color:#fef3c7; font-size:10px; font-weight:700; }
  .ev-candidates { display:none; }
  .ev-candidates.mobile-ev-open {
    display:block;
    position:absolute;
    z-index:30;
    left:0;
    right:0;
    bottom:calc(100% + 4px);
    max-height:min(50dvh,430px);
    overflow:auto;
    border:1px solid #d9b65c88;
    border-radius:12px;
    background:#052e2b;
    box-shadow:0 10px 25px #0009;
  }
}
</style>
