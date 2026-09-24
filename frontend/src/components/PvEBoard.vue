<script setup>
import { computed } from 'vue'
import { relativeOpponents, tileLabel } from '../constants/tiles.js'
import { windLabel } from '../utils/seatLayout.js'
import MahjongTile from './MahjongTile.vue'
import MeldTiles from './MeldTiles.vue'
import DiscardRiver from './DiscardRiver.vue'
const props = defineProps({
  seatWind: { type: String, default: 'E' }, currentTurnSeat: String, dealerSeat: String,
  dealerTile: String, opponents: { type: Array, default: () => [] },
  cumulativeScores: { type: Object, default: () => ({}) }, roundCount: { type: Number, default: 1 },
  aiStatus: String, aiAnnouncement: String, thinkingSeat: String,
})
const seats = computed(() => relativeOpponents(props.seatWind).map(({ seat_wind, role }, i) => {
  const opp = props.opponents.find(o => o.seat_wind === seat_wind) || {}
  return { seat: seat_wind, role, position: ['left','top','right'][i], handCount: opp.hand_tiles?.length ?? 13, melds: opp.melds || [], discards: opp.discards || [] }
}))
</script>
<template>
  <section class="pve-table" aria-label="四方牌桌">
    <header class="flex flex-wrap justify-between gap-2 text-sm text-teal-100">
      <span>第 {{ roundCount }} 圈 · 庄家 {{ windLabel(dealerSeat) }}风</span>
      <span class="text-amber-200">当前 {{ windLabel(currentTurnSeat) }}风行动</span>
    </header>
    <div class="table-compass">
      <article v-for="player in seats" :key="player.seat" :data-seat="player.seat" :data-position="player.position" class="opponent-seat" :class="[player.position, { active: player.seat === currentTurnSeat }]">
        <header class="seat-header flex justify-between gap-2 text-sm text-teal-50">
          <b>{{ player.role }} · {{ windLabel(player.seat) }}风 <span v-if="player.seat === dealerSeat" class="text-amber-300">庄</span></b>
          <span v-if="player.seat === thinkingSeat" class="thinking-indicator" role="status">思考中…</span>
          <span>{{ cumulativeScores[player.seat] || 0 }} 分</span>
        </header>
        <div class="seat-tiles">
          <div class="concealed-hand" :aria-label="`${player.role}暗手，已隐藏`"><span v-for="n in player.handCount" :key="n" class="tile-back" /></div>
          <div v-if="player.melds.length" class="meld-area flex flex-wrap gap-2" aria-label="副露"><MeldTiles v-for="(meld,i) in player.melds" :key="i" :meld="meld" :dealer-tile="dealerTile" /></div>
        </div>
        <DiscardRiver :tiles="player.discards" />
      </article>
      <div class="table-center" aria-label="本局财神">
        <span class="rounded-full border border-amber-300/60 bg-amber-400 px-4 py-1 text-sm font-black text-amber-950 shadow">得 · 财神</span>
        <MahjongTile v-if="dealerTile" :code="dealerTile" large class="my-3" />
        <p class="text-sm font-semibold text-amber-100">{{ dealerTile ? tileLabel(dealerTile) : '等待发牌' }}</p>
        <p v-if="dealerTile && dealerTile !== 'P'" class="mt-2 text-xs text-amber-100/80">白板承接 {{ tileLabel(dealerTile) }} 替身属性</p>
        <p class="mt-4 text-center text-xs text-teal-200" role="status">{{ aiAnnouncement || aiStatus || '三家 AI 托管 · 等待你的决策' }}</p>
      </div>
    </div>
  </section>
</template>
<style scoped>
.pve-table { padding:20px; border:1px solid #c9b26c55; border-radius:24px; background:radial-gradient(ellipse at center,#17604c99,#052e2c 85%); box-shadow:inset 0 0 50px #0003,0 12px 30px #0002; }
.table-compass { display:grid; grid-template-columns:493px minmax(0,1fr) 493px; grid-template-areas:'top top top' 'left center right'; align-items:start; gap:16px; margin-top:16px; }
.opponent-seat { min-width:0; padding:14px; border:1px solid #659d8955; border-radius:16px; background:#03272399; }
.opponent-seat.active { border-color:#fcd34d; box-shadow:0 0 18px #fbbf2420; }
/* 两侧：3×(4×35 + 3×3) + 2×8 组距 + 30 内边框 = 493px。
   对家：20×35 + 19×3 牌距 + 30 内边框 = 787px。 */
.top { grid-area:top; justify-self:center; width:min(100%,787px); padding:10px 14px; }
.left { grid-area:left; justify-self:start; width:min(100%,493px); align-self:start; }
.right { grid-area:right; justify-self:end; width:min(100%,493px); align-self:start; }
.seat-header { margin-bottom:8px; }
.thinking-indicator { margin-left:auto; color:#fde68a; font-size:12px; white-space:nowrap; animation:thinking-pulse 1s ease-in-out infinite alternate; }
@keyframes thinking-pulse { from { opacity:.45; } to { opacity:1; } }
.seat-tiles { display:flex; flex-direction:column; align-items:flex-start; gap:6px; }
.concealed-hand { display:flex; flex-wrap:wrap; gap:3px; }
.top .seat-header { margin-bottom:5px; }
.top .seat-tiles { flex-direction:row; align-items:flex-start; gap:10px; min-height:31px; }
.top .concealed-hand { flex:none; }
.top .meld-area { min-width:0; flex:1; }
.opponent-seat :deep(.mahjong-tile) { --tw:35px; --th:49px; --face-font:19px; --honor-font:26px; }
.opponent-seat :deep(.discard-river) { grid-template-columns:repeat(6,35px); gap:5px 4px; min-height:53px; }
.left :deep(.discard-river), .right :deep(.discard-river) { width:100%; grid-template-columns:repeat(auto-fill,35px); }
.opponent-seat :deep([aria-label="副露牌组"]) { gap:3px; padding-top:3px; padding-bottom:5px; }
.top :deep([aria-label="副露牌组"]) { padding-top:0; padding-bottom:3px; }
.table-center { grid-area:center; display:flex; flex-direction:column; align-items:center; padding:16px 4px; }
.tile-back { width:15px; height:23px; border:1px solid #7ab5a6; border-radius:3px; background:linear-gradient(130deg,#368a75,#115643); box-shadow:0 2px 0 #aec7b7; }
@media(max-width:1279px) { .table-compass { grid-template-columns:minmax(0,1fr) minmax(0,1fr); grid-template-areas:'top top' 'left right' 'center center'; } .table-center { border-top:1px solid #d4b96844; } }
@media(max-width:639px) { .pve-table { padding:12px; } .table-compass { grid-template-columns:minmax(0,1fr); grid-template-areas:'top' 'center' 'left' 'right'; } .opponent-seat { width:100%; justify-self:stretch; } }
</style>
