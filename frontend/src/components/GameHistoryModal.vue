<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { tileLabel } from '../constants/tiles.js'
import { windLabel } from '../utils/seatLayout.js'
import { getGameRecord, listGameRecords } from '../services/api.js'
import { useOrientation } from '../composables/useOrientation.js'

const props = defineProps({ currentGameId: { type: String, default: '' } })
const emit = defineEmits(['close'])
const records = ref([])
const loading = ref(true)
const error = ref('')
const copiedId = ref('')
const activeRecord = ref(null)
const activeIndex = ref(0)
const loadingRecord = ref('')
const controller = new AbortController()
const { stageTransform } = useOrientation(1080, 560, 16, 1)

const orderedRecords = computed(() => {
  const rows = [...records.value]
  const current = rows.findIndex((row) => row.game_id === props.currentGameId)
  if (current > 0) rows.unshift(rows.splice(current, 1)[0])
  return rows
})
const activeStep = computed(() => activeRecord.value?.steps?.[activeIndex.value] || null)
const replaySeats = computed(() => {
  const record = activeRecord.value
  if (!record) return []
  const self = record.config?.seat_wind || 'E'
  const snapshot = activeStep.value?.snapshot?.self
  return ['E', 'S', 'W', 'N'].map((seat) => {
    const state = seat === self ? snapshot : snapshot?.opponents?.find((item) => item.seat_wind === seat)
    return {
      seat, isSelf: seat === self,
      hand: state?.handTiles || state?.hand_tiles || record.config?.initial_hands?.[seat] || [],
      melds: state?.melds || [], discards: state?.discards || [],
    }
  })
})

function signed(value) {
  const n = Number(value) || 0
  return `${n >= 0 ? '+' : ''}${n}`
}
function detailLabel(item) {
  if (typeof item === 'string') return item.replaceAll('明碰', '明刻')
  if (!item) return ''
  return item.label ? `${item.label.replaceAll('明碰', '明刻')}${item.hu == null ? '' : ` (+${item.hu}胡)`}` : ''
}
function scoreHint(score) {
  if (!score) return ''
  const items = [...(score.hu_items || []), ...(score.fan_items || [])].map(detailLabel).filter(Boolean)
  return items.length ? items.join(' · ') : `固有 ${score.hu || 0} 胡${score.fan ? ` · ${score.fan} 翻` : ''}`
}
function scoreMeta(score) {
  if (!score) return ''
  return `${score.hu || 0}胡${score.fan ? ` ${score.fan}翻` : ''}`
}
function timeLabel(timestamp) {
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}
async function copyId(gameId) {
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(gameId)
    else {
      const field = document.createElement('textarea')
      field.value = gameId
      document.body.appendChild(field)
      field.select()
      if (!document.execCommand('copy')) throw new Error('复制不可用')
      field.remove()
    }
    copiedId.value = gameId
  } catch { error.value = '复制失败，请手动选择牌谱编号' }
}
async function loadReplay(gameId) {
  loadingRecord.value = gameId
  error.value = ''
  try {
    activeRecord.value = await getGameRecord(gameId, { signal: controller.signal })
    activeIndex.value = 0
  } catch (cause) {
    if (!controller.signal.aborted) error.value = cause?.message || String(cause)
  } finally { loadingRecord.value = '' }
}
function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}
onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  try {
    const result = await listGameRecords({ signal: controller.signal })
    records.value = result.records || []
  } catch (cause) {
    if (!controller.signal.aborted) error.value = cause?.message || String(cause)
  } finally { loading.value = false }
})
onUnmounted(() => { controller.abort(); window.removeEventListener('keydown', onKeydown) })
</script>

<template>
  <Teleport to="body">
    <div class="history-backdrop" @click.self="emit('close')">
      <section class="history-modal" :style="{ transform: stageTransform }" role="dialog" aria-modal="true" aria-label="复盘历史">
        <header class="history-header">
          <div>
            <h2>{{ activeRecord ? `牌谱复盘 · ${activeRecord.game_id}` : '复盘历史' }}</h2>
            <p>{{ activeRecord ? '按时间顺序查看每步动作与四方牌面' : `本地最近 ${orderedRecords.length} 局 · 按结算时间排序` }}</p>
          </div>
          <div class="history-header-actions">
            <button v-if="activeRecord" type="button" @click="activeRecord = null">返回列表</button>
            <button type="button" aria-label="关闭复盘历史" @click="emit('close')">关闭</button>
          </div>
        </header>
        <p v-if="error" class="history-error" role="alert">{{ error }}</p>
        <div v-if="!activeRecord" class="history-list-viewport">
          <p v-if="loading" class="history-empty">正在读取牌谱…</p>
          <p v-else-if="!orderedRecords.length" class="history-empty">暂无已归档牌局</p>
          <div v-else class="history-list">
            <article v-for="record in orderedRecords" :key="record.game_id" class="history-row" :class="{ 'is-current': record.game_id === currentGameId }">
              <div class="history-identity">
                <div class="history-id-line"><strong>{{ record.game_id }}</strong><button type="button" :aria-label="`复制 ${record.game_id}`" :title="`复制 ${record.game_id}`" @click="copyId(record.game_id)">{{ copiedId === record.game_id ? '✓' : '⧉' }}</button></div>
                <small>{{ record.circle_index ? `第 ${record.circle_index} 圈` : '已归档' }} · {{ windLabel(record.round_wind) }}风局</small>
                <small>{{ timeLabel(record.timestamp) }}</small>
              </div>
              <div class="history-outcome">
                <span class="history-result-badge" :class="record.win_type === 'draw' ? 'is-draw' : record.winner_seat === record.self_seat ? 'is-self' : 'is-opponent'">{{ record.win_type === 'draw' ? '荒牌流局' : record.winner_name }}</span>
                <small v-if="record.win_type !== 'draw'">{{ record.points }}胡 {{ record.fan }}翻 · 得{{ tileLabel(record.win_tile) }}</small>
                <small v-if="record.is_lazi" class="history-lazi">辣子 100分</small>
              </div>
              <div class="history-scores">
                <div v-for="field in ['self_score', 'xiajia_score', 'duijia_score', 'shangjia_score']" :key="field" class="history-score" :title="scoreHint(record[field])">
                  <strong>{{ { self_score: '自家', xiajia_score: '下家', duijia_score: '对家', shangjia_score: '上家' }[field] }}</strong>
                  <b :class="record[field]?.net >= 0 ? 'score-positive' : 'score-negative'">{{ signed(record[field]?.net) }}分</b>
                  <small>{{ scoreMeta(record[field]) }}</small>
                  <small class="history-score-detail">{{ scoreHint(record[field]) }}</small>
                </div>
              </div>
              <div class="history-actions">
                <button type="button" @click="copyId(record.game_id)">{{ copiedId === record.game_id ? '已复制' : '复制编号' }}</button>
                <button type="button" :disabled="!!loadingRecord" @click="loadReplay(record.game_id)">{{ loadingRecord === record.game_id ? '载入中…' : '载入复盘' }}</button>
              </div>
            </article>
          </div>
        </div>
        <div v-else class="history-replay">
          <div class="history-replay-controls">
            <span>第 {{ activeIndex + 1 }} / {{ activeRecord.steps?.length || 0 }} 步 · {{ activeStep?.seat ? windLabel(activeStep.seat) + '风' : '' }} {{ activeStep?.action }} {{ tileLabel(activeStep?.tile) }}</span>
            <div><button type="button" :disabled="activeIndex <= 0" @click="activeIndex--">上一步</button><button type="button" :disabled="activeIndex >= (activeRecord.steps?.length || 1) - 1" @click="activeIndex++">下一步</button></div>
          </div>
          <input v-model.number="activeIndex" type="range" min="0" :max="Math.max(0, (activeRecord.steps?.length || 1) - 1)" aria-label="复盘步数" />
          <div class="history-replay-seats">
            <article v-for="seat in replaySeats" :key="seat.seat">
              <h3>{{ seat.isSelf ? '自家 · ' : '' }}{{ windLabel(seat.seat) }}风</h3>
              <p>手牌 <span v-for="(tile, i) in seat.hand" :key="i" class="history-replay-tile">{{ tileLabel(tile) }}</span></p>
              <p>副露 <span v-for="(meld, i) in seat.melds" :key="i" class="history-replay-meld">{{ (meld.tiles || []).map(tileLabel).join(' ') }}</span></p>
              <p>弃牌 {{ seat.discards.map(tileLabel).join(' ') || '—' }}</p>
            </article>
          </div>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.history-backdrop { position:fixed; inset:0; z-index:100; overflow:hidden; background:#001a16dc; backdrop-filter:blur(9px); }
.history-modal { box-sizing:border-box; position:absolute; top:50%; left:50%; display:flex; flex-direction:column; width:1080px; height:560px; overflow:hidden; border:1px solid #d9b65c99; border-radius:18px; background:linear-gradient(145deg,#082f2bef,#063b34f5); box-shadow:0 24px 70px #000a; color:#fef3c7; transform-origin:center center; }
.history-header { display:flex; align-items:center; justify-content:space-between; gap:12px; flex:none; padding:13px 18px; border-bottom:1px solid #d9b65c55; }
.history-header h2 { font-size:1.15rem; font-weight:800; }.history-header p { color:#a7cfc5; font-size:.75rem; }
.history-header-actions { display:flex; gap:6px; }.history-header-actions button,.history-actions button,.history-replay-controls button { border:1px solid #d9b65c88; border-radius:7px; padding:5px 8px; font-size:.75rem; white-space:nowrap; }.history-header-actions button:hover,.history-actions button:hover,.history-replay-controls button:hover { background:#6b501c; }
.history-list-viewport { min-height:0; overflow:auto; overscroll-behavior:contain; padding:10px; }.history-list { display:grid; gap:6px; min-width:990px; }.history-empty { padding:25px; text-align:center; color:#a7cfc5; }
.history-row { display:grid; grid-template-columns:155px 205px minmax(480px,1fr) 105px; align-items:center; gap:8px; min-height:78px; padding:7px 9px; border:1px solid #41786d; border-radius:11px; background:#0b3933c9; }.history-row.is-current { border-color:#fbbf24; }
.history-identity,.history-outcome,.history-score { display:flex; min-width:0; flex-direction:column; gap:2px; }.history-identity strong { color:#fde68a; font-size:.82rem; }.history-id-line { display:flex; align-items:center; gap:5px; }.history-id-line button { color:#fbbf24; font-size:1rem; line-height:1; }.history-identity small,.history-outcome small,.history-score small { overflow:hidden; color:#a8c8bf; font-size:.75rem; text-overflow:ellipsis; white-space:nowrap; }
.history-result-badge { overflow:hidden; width:max-content; max-width:100%; border-radius:999px; padding:2px 7px; background:#743a37; color:#ffe2df; font-size:.75rem; font-weight:700; text-overflow:ellipsis; white-space:nowrap; }.history-result-badge.is-self { background:#145f42; color:#bbf7d0; }.history-result-badge.is-draw { background:#475569; color:#e2e8f0; }.history-outcome .history-lazi { color:#fbbf24; font-weight:700; }
.history-scores { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:5px; min-width:0; }.history-score { border-left:1px solid #41786d; padding-left:6px; }.history-score strong { font-size:.75rem; }.history-score b { font-size:.88rem; line-height:1; }.score-positive { color:#86efac; }.score-negative { color:#fda4af; }.history-score .history-score-detail { color:#e3d5ae; }.history-actions { display:flex; flex-direction:column; gap:4px; }.history-actions button { padding:4px 5px; }.history-actions button:last-child { background:#b48b25; color:#112c22; font-weight:800; }.history-actions button:disabled { opacity:.5; }
.history-error { flex:none; padding:5px 18px; color:#fda4af; font-size:.8rem; }.history-replay { min-height:0; overflow:auto; padding:12px 18px; }.history-replay-controls { display:flex; justify-content:space-between; gap:10px; font-size:.8rem; }.history-replay-controls > div { display:flex; gap:5px; }.history-replay-controls button:disabled { opacity:.4; }.history-replay > input { width:100%; margin:12px 0; accent-color:#fbbf24; }.history-replay-seats { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }.history-replay-seats article { min-width:0; border:1px solid #41786d; border-radius:8px; padding:8px; background:#052e2b; }.history-replay-seats h3 { font-size:.8rem; font-weight:800; }.history-replay-seats p { margin-top:5px; color:#c9ddd3; font-size:.75rem; line-height:1.7; }.history-replay-tile { display:inline-block; margin:1px; border:1px solid #d8d4bb; border-radius:3px; padding:0 3px; background:#fffdf0; color:#183b39; }.history-replay-meld { display:inline-block; margin-right:5px; color:#fde68a; }
</style>
