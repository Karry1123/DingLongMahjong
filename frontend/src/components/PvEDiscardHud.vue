<script setup>
import { computed, ref } from 'vue'
import { tileLabel, tileSuitClass } from '../constants/tiles.js'

const props = defineProps({
  bestTile: { type: String, default: '' },
  candidates: { type: Array, default: () => [] },
  interactive: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits({ 'select-tile': (tile) => typeof tile === 'string' && tile.length > 0 })
const expanded = ref(false)

const ranked = computed(() => {
  const seen = new Set()
  const rows = []
  for (const row of props.candidates) {
    if (!row?.tile || seen.has(row.tile)) continue
    seen.add(row.tile)
    rows.push(row)
  }
  rows.sort((a, b) => Number(b.ev_score ?? -Infinity) - Number(a.ev_score ?? -Infinity))
  const best = rows.findIndex((row) => row.tile === props.bestTile)
  if (best > 0) rows.unshift(rows.splice(best, 1)[0])
  if (best < 0 && props.bestTile) rows.unshift({ tile: props.bestTile })
  return rows.slice(0, 5)
})
const leading = computed(() => ranked.value.slice(0, 2))
const remaining = computed(() => ranked.value.slice(2))

function maxRisk(row) {
  return Math.max(0, ...Object.values(row?.deal_in_risks || {}).map((risk) => Number(risk) || 0))
}
function choose(tile) {
  if (props.interactive) emit('select-tile', tile)
}
</script>

<template>
  <section class="pve-discard-hud" aria-label="极简切牌推荐">
    <div class="hud-leading">
      <button
        v-for="(row, index) in leading"
        :key="row.tile"
        type="button"
        class="hud-tile"
        :class="index === 0 ? 'hud-best' : ''"
        :disabled="!interactive"
        :title="`打出 ${tileLabel(row.tile)}`"
        @click="choose(row.tile)"
      >
        <span class="hud-rank">{{ index === 0 ? '荐' : '次' }}</span>
        <span class="hud-face" :class="tileSuitClass(row.tile)">{{ tileLabel(row.tile) }}</span>
        <span class="hud-metrics"><b>进张 {{ row.effective_count ?? '—' }}</b><small>铳率 {{ (maxRisk(row) * 100).toFixed(1) }}%</small></span>
      </button>
      <span v-if="loading && !leading.length" class="hud-wait">计算中…</span>
      <span v-else-if="!leading.length" class="hud-wait">等待切牌</span>
      <button
        v-if="remaining.length"
        type="button"
        class="hud-more"
        :aria-expanded="expanded"
        aria-label="更多切牌候选"
        @click="expanded = !expanded"
      >{{ expanded ? '收起 ▴' : '展开 ▾' }}</button>
    </div>
    <div v-if="expanded && remaining.length" class="hud-drawer" role="list" aria-label="更多切牌候选">
      <button v-for="row in remaining" :key="row.tile" type="button" role="listitem" :disabled="!interactive" @click="choose(row.tile)">
        <span :class="tileSuitClass(row.tile)">{{ tileLabel(row.tile) }}</span>
        <b>进张 {{ row.effective_count ?? '—' }}</b>
        <small>铳率 {{ (maxRisk(row) * 100).toFixed(1) }}%</small>
      </button>
    </div>
  </section>
</template>

<style scoped>
.pve-discard-hud { position:relative; z-index:50; width:min(100%,370px); min-height:70px; padding:5px; border:1px solid rgba(255,215,0,.35); border-radius:14px; background:#042c28f2; box-shadow:0 12px 28px rgba(0,0,0,.45),0 4px 10px rgba(0,0,0,.3); color:#fff; }
.hud-leading { display:flex; align-items:stretch; gap:5px; min-height:60px; }
.hud-tile { flex:1 1 0; min-width:0; display:flex; align-items:center; gap:4px; padding:4px; border:1px solid #3d806d; border-radius:9px; background:#075044; text-align:left; }
.hud-tile:disabled { opacity:.7; cursor:default; }
.hud-best { border-color:#fbbf24; background:#785510bb; }
.hud-rank { align-self:flex-start; font-size:10px; font-weight:800; color:#fde68a; }
.hud-face { flex:0 0 auto; display:flex; align-items:center; justify-content:center; width:26px; height:35px; border:1px solid #e5e7eb; border-radius:4px; font-size:13px; font-weight:800; }
.hud-metrics { min-width:0; display:flex; flex-direction:column; gap:2px; white-space:nowrap; font-size:10px; }
.hud-metrics b { color:#86efac; }
.hud-metrics small { color:#fda4af; font-size:10px; }
.hud-more { flex:0 0 38px; border:1px solid #c9b26c66; border-radius:8px; color:#fde68a; font-size:10px; font-weight:700; }
.hud-wait { align-self:center; flex:1; text-align:center; color:#cbd5d1; font-size:12px; }
.hud-drawer { position:absolute; z-index:51; right:0; top:calc(100% + 6px); display:grid; gap:3px; width:min(100%,300px); padding:5px; border:1px solid rgba(255,215,0,.35); border-radius:10px; background:#042c28fa; box-shadow:0 12px 28px rgba(0,0,0,.45),0 4px 10px rgba(0,0,0,.3); animation:hud-drop .18s ease-out both; }
@keyframes hud-drop { from { opacity:0; transform:translateY(-7px); } to { opacity:1; transform:translateY(0); } }
.hud-drawer button { display:flex; align-items:center; gap:8px; min-height:35px; padding:3px 6px; border-radius:5px; background:#0b433d; text-align:left; }
.hud-drawer button > span { min-width:28px; text-align:center; border-radius:3px; font-size:12px; font-weight:700; }
.hud-drawer b { color:#86efac; font-size:11px; }
.hud-drawer small { margin-left:auto; color:#fda4af; font-size:10px; }
@media (orientation:landscape) and (min-width:640px) {
  .hud-drawer { right:0; top:calc(100% + 6px); bottom:auto; width:100%; max-height:min(210px,calc(100dvh - 180px)); overflow:auto; padding:4px; gap:2px; }
  .hud-drawer button { min-height:30px; padding:2px 4px; }
}
@media (prefers-reduced-motion:reduce) { .hud-drawer { animation:none; } }
@media (max-height:600px) and (orientation:landscape) {
  .pve-discard-hud { width:100%; min-height:58px; padding:2px; border-radius:8px; }
  .hud-leading { min-height:52px; gap:2px; }
  .hud-tile { position:relative; gap:2px; padding:9px 2px 2px; border-radius:5px; }
  .hud-rank { position:absolute; top:0; left:2px; font-size:8px; }
  .hud-face { width:19px; height:27px; font-size:10px; }
  .hud-metrics, .hud-metrics small { font-size:8px; }
  .hud-more { flex-basis:25px; font-size:8px; }
}
</style>
