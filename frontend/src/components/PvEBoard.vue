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
  selfDiscards: { type: Array, default: () => [] },
  cumulativeScores: { type: Object, default: () => ({}) }, roundCount: { type: Number, default: 1 },
  wallCount: { type: Number, default: 0 },
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
        <DiscardRiver :tiles="player.discards" :layout="player.position" />
      </article>
      <div class="table-center" aria-label="本局财神">
        <div class="center-compass-hud">
          <span class="compass-title">得 · 财神</span>
          <MahjongTile v-if="dealerTile" :code="dealerTile" />
          <span class="compass-count">余牌 <strong>{{ wallCount }}</strong><small>{{ windLabel(currentTurnSeat) }}风行牌</small></span>
        </div>
        <p class="sr-only" role="status">{{ dealerTile ? tileLabel(dealerTile) : '等待发牌' }}；{{ aiAnnouncement || aiStatus || '等待你的决策' }}</p>
      </div>
      <div class="self-river" aria-label="自家牌河"><DiscardRiver :tiles="selfDiscards" layout="self" /></div>
    </div>
  </section>
</template>
<style scoped>
.pve-table { position:relative; padding:0; border:0; border-radius:0; background:radial-gradient(ellipse at center,#17604c99,#052e2c 85%); box-shadow:none; }
.table-compass { position:relative; width:100%; height:100%; margin:0; }
.opponent-seat { position:absolute; width:36%; height:260px; padding:0; border:0; border-radius:0; background:transparent; box-shadow:none; }
.opponent-seat.active .seat-header { color:#fde68a; text-shadow:0 0 12px #fbbf2466; }
.top { top:4px; left:50%; width:760px; height:190px; transform:translateX(-50%); }
.left { top:50%; left:0; transform:translateY(-50%); }
.right { top:50%; right:0; transform:translateY(-50%); }
.seat-header { height:18px; margin:0; font-size:12px; }
.thinking-indicator { margin-left:auto; color:#fde68a; font-size:12px; white-space:nowrap; animation:thinking-pulse 1s ease-in-out infinite alternate; }
@keyframes thinking-pulse { from { opacity:.45; } to { opacity:1; } }
.seat-tiles { display:flex; align-items:flex-start; gap:8px; }
.concealed-hand { display:flex; flex-wrap:nowrap; gap:2px; }
.top .seat-header { width:440px; margin:0 auto; }
.top .seat-tiles { justify-content:center; margin-top:5px; }
.top .meld-area { display:flex; flex-wrap:nowrap; gap:7px; }
.left .seat-header, .right .seat-header { position:absolute; top:-23px; width:250px; }
.right .seat-header { right:0; }
.left .seat-tiles, .right .seat-tiles { position:absolute; top:0; }
.left .seat-tiles { left:6px; }
.right .seat-tiles { right:6px; flex-direction:row-reverse; }
.left .concealed-hand, .right .concealed-hand { flex-direction:column; gap:1px; }
.left .meld-area, .right .meld-area { display:flex; flex-direction:column; flex-wrap:nowrap; gap:0; }
.opponent-seat :deep(.mahjong-tile) { --tw:26px; --th:35px; }
.opponent-seat :deep([aria-label="副露牌组"]) { gap:2px; padding-top:0; padding-bottom:2px; }
.opponent-seat > :deep(.discard-river) { position:absolute; display:grid; gap:3px 3px; min-height:0; }
.opponent-seat > :deep(.discard-river) .mahjong-tile { --tw:24px; --th:32px; margin-bottom:0; }
.top > :deep(.discard-river) { top:64px; left:50%; grid-template-columns:repeat(10,24px); transform:translateX(-50%); }
.left > :deep(.discard-river) { top:50%; right:0; grid-template-columns:repeat(4,24px); transform:translateY(-50%); }
.right > :deep(.discard-river) { top:50%; left:0; grid-template-columns:repeat(4,24px); transform:translateY(-50%); }
.table-center { position:absolute; z-index:2; top:50%; left:50%; transform:translate(-50%,-50%); }
.center-compass-hud { display:flex; align-items:center; justify-content:center; gap:6px; padding:7px 10px; border:1px solid #d4af5888; border-radius:13px; background:#043a32ee; color:#fef3c7; white-space:nowrap; box-shadow:0 10px 24px #001b1755; }
.compass-title { font-size:11px; font-weight:800; color:#fbbf24; }
.compass-count { display:flex; flex-direction:column; align-items:center; font-size:10px; line-height:1.1; }
.compass-count strong { font-size:16px; }
.compass-count small { font-size:8px; color:#b7d8cc; }
.center-compass-hud :deep(.mahjong-tile) { --tw:25px; --th:calc(var(--tw)*4/3); margin:0; }
.self-river { position:absolute; top:calc(50% + 58px); left:50%; transform:translateX(-50%); }
.self-river :deep(.discard-river) { display:grid; grid-template-columns:repeat(8,24px); gap:3px; min-height:0; }
.self-river :deep(.mahjong-tile) { --tw:24px; --th:32px; margin-bottom:0; }
.tile-back { width:14px; height:18px; border:1px solid #7ab5a6; border-radius:3px; background:linear-gradient(130deg,#368a75,#115643); box-shadow:0 2px 0 #aec7b7; }
</style>
