<script setup>
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { ALL_TILES, SEAT_WINDS, tileLabel, tileSuitClass } from '../constants/tiles.js'
import { cloudWakeMessage, getRecommendDecision, isAbortError } from '../services/api.js'
import MahjongTile from './MahjongTile.vue'

defineEmits(['home', 'advanced'])
const settings = reactive({ dealerTile: 'P', seatWind: 'E', isDealer: true })
try {
  const saved = JSON.parse(localStorage.getItem('sandbox-reference-settings') || '{}')
  if (ALL_TILES.includes(saved.dealerTile)) settings.dealerTile = saved.dealerTile
  if (SEAT_WINDS.some(w => w.code === saved.seatWind)) settings.seatWind = saved.seatWind
  if (typeof saved.isDealer === 'boolean') settings.isDealer = saved.isDealer
} catch { /* Settings remain usable when storage is unavailable. */ }
watch(settings, value => {
  try { localStorage.setItem('sandbox-reference-settings', JSON.stringify(value)) } catch { /* private browsing */ }
})

const state = reactive({ hand: [], melds: [], discards: [], seen: [], tracking: false })
const history = ref([])
const target = ref('hand')
const editing = ref(false)
const selectingMeld = ref(false)
const selected = ref([])
const seenOpen = ref(false)
const result = ref(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const slots = computed(() => state.hand.length + state.melds.length * 3)
const full = computed(() => slots.value === 14)
const bestTile = computed(() => result.value?.best_tile || result.value?.candidates?.[0]?.tile)
const bestCandidate = computed(() => result.value?.candidates?.find(c => c.tile === bestTile.value))
const effectiveCount = computed(() => bestCandidate.value?.effective_count ?? result.value?.effective_count ?? 0)
const shantenLabel = computed(() => {
  const value = result.value?.shanten
  return value == null ? '向听未知' : value < 0 ? '已成和牌型' : value === 0 ? '听牌' : `${value} 向听`
})
const counts = computed(() => {
  const map = {}
  for (const tile of [...state.hand, ...state.melds.flatMap(m => m.tiles), ...state.discards, ...state.seen]) map[tile] = (map[tile] || 0) + 1
  return map
})
const keyboardTitle = computed(() => target.value === 'joker' ? '点一张设为财神' : target.value === 'seen' ? '点键盘记录场上已见牌' : full.value ? '点手牌打出，或切换改手牌' : state.tracking && !editing.value && slots.value === 13 ? '点键盘摸入一张' : `点键盘录手牌 · 还差 ${14 - slots.value} 张`)
const selectedTiles = computed(() => selected.value.map(i => state.hand[i]).sort((a, b) => ALL_TILES.indexOf(a) - ALL_TILES.indexOf(b)))
const meldType = computed(() => {
  const tiles = selectedTiles.value
  if (tiles.length === 4 && tiles.every(t => t === tiles[0])) return 'ming_gang'
  if (tiles.length !== 3) return null
  if (tiles.every(t => t === tiles[0])) return 'pong'
  if (/^[1-7][mps]$/.test(tiles[0]) && tiles.every((t, i) => t === `${Number(tiles[0][0]) + i}${tiles[0][1]}`)) return 'chi'
  return null
})

function snapshot() {
  history.value.push(JSON.parse(JSON.stringify(state)))
  if (history.value.length > 100) history.value.shift()
  notice.value = ''
}
function cancelMeld() { selectingMeld.value = false; selected.value = [] }
function undo() {
  if (!history.value.length) return
  Object.assign(state, history.value.pop())
  cancelMeld()
  editing.value = false
  target.value = 'hand'
  notice.value = '已撤销上一步'
}
function reset() {
  snapshot()
  Object.assign(state, { hand: [], melds: [], discards: [], seen: [], tracking: false })
  cancelMeld()
  target.value = 'hand'
  editing.value = false
  notice.value = '已清空牌局，设置已保留；可撤销'
}
function keyDisabled(tile) {
  return target.value !== 'joker' && ((counts.value[tile] || 0) >= 4 || selectingMeld.value || (target.value === 'hand' && full.value))
}
function addTile(tile) {
  if (keyDisabled(tile)) return
  if (target.value === 'joker') {
    settings.dealerTile = tile
    target.value = 'hand'
    return
  }
  snapshot()
  if (target.value === 'seen') state.seen.push(tile)
  else {
    state.hand.push(tile)
    if (full.value) { state.tracking = true; editing.value = false }
  }
}
function handClick(index) {
  if (selectingMeld.value) {
    selected.value = selected.value.includes(index) ? selected.value.filter(i => i !== index) : [...selected.value, index].slice(-4)
    return
  }
  if (state.tracking && !editing.value && !full.value) return
  snapshot()
  const [tile] = state.hand.splice(index, 1)
  if (state.tracking && !editing.value) state.discards.push(tile)
}
function removePublic(list, index) { snapshot(); state[list].splice(index, 1) }
function startMeld() {
  selectingMeld.value = true
  selected.value = []
  target.value = 'hand'
}
function confirmMeld() {
  if (!meldType.value || state.melds.length >= 4) return
  const tiles = [...selectedTiles.value]
  const type = meldType.value
  snapshot()
  state.hand = state.hand.filter((_, i) => !selected.value.includes(i))
  state.melds.push({ meld_type: type, tiles })
  cancelMeld()
  editing.value = false
  notice.value = type === 'ming_gang' ? '已标记杠牌，请补摸一张' : '已标记副露，继续录牌或打出'
}
function restoreMeld(index) {
  // Undoing a kong after its replacement draw would create 15 slots.
  const meld = state.melds[index]
  if (slots.value + meld.tiles.length - 3 > 14) {
    notice.value = '请先用“改手牌”移除补摸牌，再还原杠牌'
    return
  }
  snapshot()
  state.hand.push(...meld.tiles)
  state.melds.splice(index, 1)
  cancelMeld()
}

let controller, timer, epoch = 0
function invalidate() {
  epoch++
  clearTimeout(timer)
  controller?.abort()
  result.value = null
  busy.value = false
  error.value = ''
}
async function recommend() {
  invalidate()
  if (!full.value) return
  const requestEpoch = epoch
  controller = new AbortController()
  busy.value = true
  try {
    const response = await getRecommendDecision({
      hand_tiles: [...state.hand], melds: state.melds.map(m => ({ ...m, tiles: [...m.tiles] })),
      discards: [...state.discards], discarded_tiles: [...state.seen],
      dealer_tile: settings.dealerTile, seat_wind: settings.seatWind, is_dealer: settings.isDealer,
    }, { signal: controller.signal })
    if (requestEpoch === epoch) result.value = response
  } catch (e) {
    if (requestEpoch === epoch && !isAbortError(e)) error.value = e.message || '推荐暂不可用，请重试'
  } finally {
    if (requestEpoch === epoch) busy.value = false
  }
}
watch(() => JSON.stringify([state.hand, state.melds, state.discards, state.seen, settings]), () => {
  invalidate()
  if (full.value) {
    busy.value = true
    timer = setTimeout(recommend, 180)
  }
}, { flush: 'sync' })
onUnmounted(invalidate)
</script>

<template>
  <main class="sandbox-reference" data-mode="sandbox" data-game-mode="SANDBOX">
    <header class="reference-header">
      <button class="ui-btn ui-btn--ghost" @click="$emit('home')">← 首页</button>
      <h1>实战参考</h1>
      <button class="ui-btn ui-btn--ghost" @click="reset">重置</button>
    </header>
    <div class="reference-settings" aria-label="牌局设置">
      <button class="ui-btn ui-btn--secondary" :aria-pressed="target === 'joker'" @click="cancelMeld(); target = target === 'joker' ? 'hand' : 'joker'">财神 {{ tileLabel(settings.dealerTile) }}</button>
      <label>门风 <select v-model="settings.seatWind" class="ui-compact-select" aria-label="自家门风"><option v-for="wind in SEAT_WINDS" :key="wind.code" :value="wind.code">{{ wind.label }}</option></select></label>
      <label class="reference-dealer"><input v-model="settings.isDealer" type="checkbox">庄家</label>
    </div>

    <section class="ui-card reference-table" aria-label="自家手牌与推荐">
      <div class="reference-row"><h2>我的手牌 <span class="ui-num">{{ state.hand.length }}/{{ 14 - state.melds.length * 3 }}</span></h2><span class="ui-pill">{{ selectingMeld ? '选择副露' : editing ? '修正中' : full ? '待打' : state.tracking ? '待摸' : '录入中' }}</span></div>
      <p class="reference-hint">{{ selectingMeld ? '选同牌 3 / 4 张，或同花色顺子 3 张' : editing || !state.tracking ? '点手牌移除 · 点键盘加入' : full ? '点任意手牌打出 · 金框为推荐' : '点下方键盘摸一张 · 修正请点改手牌' }}</p>
      <div class="reference-hand">
        <button v-for="(tile, index) in state.hand" :key="index" class="ui-tile-touch" :class="{ 'is-selected': selected.includes(index) }" :aria-label="`${tileLabel(tile)}，${selectingMeld ? '选择副露' : editing || !state.tracking ? '移除' : '打出'}${tile === bestTile ? '，推荐' : ''}`" :aria-pressed="selectingMeld ? selected.includes(index) : undefined" :disabled="state.tracking && !editing && !full && !selectingMeld" @click="handClick(index)">
          <MahjongTile :code="tile" :badge="tile === bestTile ? '荐' : tile === settings.dealerTile ? '财' : ''" />
        </button>
        <p v-if="!state.hand.length" class="reference-empty">按现实手牌逐张点入，无需录对手</p>
      </div>
      <p class="reference-summary" role="status" aria-live="polite">
        <template v-if="busy">{{ cloudWakeMessage || '正在推荐…' }}</template>
        <template v-else-if="result">{{ result.can_self_win ? '可自摸和牌 · ' : '' }}{{ bestTile ? `建议打${tileLabel(bestTile)} · ` : '' }}{{ shantenLabel }} · 有效进张 {{ effectiveCount }} 张</template>
        <template v-else>{{ full ? '推荐暂不可用，可重试' : slots === 13 ? '再录入摸到的一张，立即推荐' : '录满 14 个牌型位，自动推荐' }}</template>
      </p>
      <div v-if="error" class="reference-row"><p role="alert">{{ error }}</p><button class="ui-btn ui-btn--ghost" @click="recommend">重试</button></div>
      <details v-if="result?.candidates?.length" class="reference-candidates"><summary>展开候选出牌（{{ result.candidates.length }}）</summary><ol><li v-for="candidate in result.candidates" :key="candidate.tile">打{{ tileLabel(candidate.tile) }} · 有效进张 {{ candidate.effective_count }} 张</li></ol></details>
      <div v-if="state.melds.length" class="reference-melds"><button v-for="(meld, i) in state.melds" :key="i" class="ui-btn ui-btn--secondary" :disabled="selectingMeld" @click="restoreMeld(i)">{{ { chi: '吃', pong: '碰', ming_gang: '杠' }[meld.meld_type] }} {{ meld.tiles.map(tileLabel).join(' ') }} · 还原</button></div>
    </section>

    <div class="reference-tools">
      <button class="ui-btn ui-btn--secondary" :disabled="!history.length" @click="undo">撤销上一步</button>
      <button class="ui-btn ui-btn--ghost" :aria-pressed="editing" @click="cancelMeld(); target = 'hand'; editing = !editing">{{ editing ? '完成修改' : '改手牌' }}</button>
      <button class="ui-btn ui-btn--ghost" :disabled="state.hand.length < 3 || state.melds.length >= 4" @click="selectingMeld ? cancelMeld() : startMeld()">{{ selectingMeld ? '取消副露' : '吃碰杠' }}</button>
    </div>
    <div v-if="selectingMeld" class="reference-row"><span>已选 {{ selected.length }} 张</span><button class="ui-btn ui-btn--primary" :disabled="!meldType" @click="confirmMeld">确认{{ { chi: '吃', pong: '碰', ming_gang: '杠' }[meldType] || '副露' }}</button></div>
    <p v-if="notice" class="reference-hint" role="status">{{ notice }}</p>

    <section class="reference-keyboard" aria-label="牌面键盘">
      <div class="reference-row"><h2>{{ keyboardTitle }}</h2><button v-if="target !== 'hand'" class="ui-btn ui-btn--ghost" @click="target = 'hand'">回到手牌</button></div>
      <div class="reference-keys"><button v-for="tile in ALL_TILES" :key="tile" class="ui-tile-key" :class="tileSuitClass(tile)" :disabled="keyDisabled(tile)" :data-key-tile="tile" :aria-label="`${tileLabel(tile)}${target === 'joker' ? '设为财神' : target === 'seen' ? '记录已见' : '加入手牌'}`" @click="addTile(tile)">{{ tileLabel(tile) }}</button></div>
    </section>

    <details class="ui-card reference-public" :open="seenOpen" @toggle="seenOpen = $event.target.open; !seenOpen && target === 'seen' && (target = 'hand')">
      <summary>场上已见牌 · {{ state.seen.length }} 张（可选）</summary>
      <p class="reference-hint">仅录其他已见废牌；自己的出牌会自动记录。点下方牌可移除。</p>
      <button class="ui-btn ui-btn--secondary" :aria-pressed="target === 'seen'" @click="cancelMeld(); target = target === 'seen' ? 'hand' : 'seen'">{{ target === 'seen' ? '结束已见牌录入' : '用键盘录已见牌' }}</button>
      <div class="reference-public-tiles"><button v-for="(tile, i) in state.seen" :key="i" class="ui-tile-key" :class="tileSuitClass(tile)" :aria-label="`移除已见${tileLabel(tile)}`" @click="removePublic('seen', i)">{{ tileLabel(tile) }}</button></div>
    </details>
    <details class="reference-river"><summary>我的牌河 · {{ state.discards.length }} 张</summary><div class="reference-public-tiles"><button v-for="(tile, i) in state.discards" :key="i" class="ui-tile-key" :class="tileSuitClass(tile)" :aria-label="`移除牌河${tileLabel(tile)}`" @click="removePublic('discards', i)">{{ tileLabel(tile) }}</button></div><p class="reference-hint">误打请用撤销；点此处只移除记录。</p></details>
    <footer class="reference-footer"><p>仅依据已录信息估算，未录对手信息也可使用。</p><button class="ui-btn ui-btn--ghost" @click="$emit('advanced')">高级：全景推演 ↗</button></footer>
  </main>
</template>

<style scoped>
.sandbox-reference { max-width:640px; min-height:100dvh; margin:auto; padding:max(12px, env(safe-area-inset-top)) max(12px, env(safe-area-inset-right)) max(24px, env(safe-area-inset-bottom)) max(12px, env(safe-area-inset-left)); color:rgb(var(--fg)); font-family:var(--font-body); }
.reference-header, .reference-row, .reference-settings, .reference-tools { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.reference-header h1 { font:600 22px var(--font-display); }
.reference-settings { margin:8px 0 12px; flex-wrap:wrap; font-size:14px; }
.reference-settings label { display:flex; align-items:center; gap:6px; }
.reference-dealer { min-height:44px; padding:0 8px; cursor:pointer; }
.reference-dealer input { width:20px; height:20px; accent-color:rgb(var(--accent)); }
.reference-table { background:rgb(var(--table-felt-deep)); padding:12px; }
h2 { font-size:14px; font-weight:600; margin:0; }
.reference-hint, .reference-footer { color:rgb(var(--fg-muted)); font-size:12px; line-height:1.6; }
.reference-hint { margin:8px 0; }
.reference-hand { display:grid; grid-template-columns:repeat(7, minmax(44px, 1fr)); gap:10px 0; padding:12px 0 8px; min-height:136px; align-content:start; }
.reference-hand :deep(.mahjong-tile) { --tw:32px; }
.reference-empty { grid-column:1 / -1; align-self:center; color:rgb(var(--fg-muted)); font-size:14px; }
.reference-summary { min-height:40px; margin:8px 0 0; font-size:14px; line-height:1.6; }
.reference-candidates { margin-top:8px; font-size:14px; }
summary { cursor:pointer; min-height:44px; padding:12px 0; font-size:14px; }
summary:focus-visible, input:focus-visible { outline:2px solid rgb(var(--accent)); outline-offset:2px; }
.reference-candidates li { padding:6px 0; }
.reference-melds { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
.reference-tools { margin:8px 0; }
.reference-tools .ui-btn, .reference-header .ui-btn, .reference-settings .ui-btn { padding:8px 10px; font-size:14px; }
.reference-keyboard { margin:8px 0 16px; }
.reference-keyboard .reference-row { min-height:44px; }
.reference-keys { display:grid; grid-template-columns:repeat(7, minmax(44px, 1fr)); gap:4px; }
.reference-public { padding:0 12px 8px; margin-top:12px; }
.reference-public-tiles { display:flex; flex-wrap:wrap; gap:4px; margin-top:8px; }
.reference-public-tiles .ui-tile-key { width:44px; }
.reference-river { padding:0 12px; }
.reference-footer { padding-top:12px; text-align:center; }
@media (max-width:359px) { .reference-hand, .reference-keys { grid-template-columns:repeat(6, minmax(44px, 1fr)); } }
</style>
