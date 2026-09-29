<script setup>
import { computed, ref, watch } from 'vue'
import MahjongTile from './MahjongTile.vue'
import PvEBoard from './PvEBoard.vue'
import PlayerWorkbench from './PlayerWorkbench.vue'
import HandBar from './HandBar.vue'
import MeldBar from './MeldBar.vue'
import SeatClock from './SeatClock.vue'
import GameOverModal from './GameOverModal.vue'
import PvpResponseWait from './PvpResponseWait.vue'
import { sortHandTiles, reconcileHandOrder, sortAroundSpecialTiles, captureSpecialAnchors, moveTileInList } from '../utils/tileSorter.js'
import { useFullscreen } from '../composables/useFullscreen.js'
import { ROOM_SEATS, relativeRoomSeats } from '../utils/roomSeats.js'
import { gameStatusHint } from '../utils/gameStatusHint.js'
import { huResultLabel } from '../utils/huLabel.js'
const props = defineProps({ room: { type: Object, required: true }, game: { type: Object, required: true }, opening:Boolean, soundMuted:Boolean, soundVolume:Number, actionError:Number, serverOffset:{type:Number,default:0} })
const emit = defineEmits(['leave', 'action', 'next', 'mute', 'volume'])
const ownPaused = computed(() => !!props.game.clocks?.[props.game.seat_wind]?.paused)
const humans = computed(() => props.game.players.filter(p => !p.is_ai))
const nextCount = computed(() => humans.value.filter(p => props.game.next_ready?.includes(p.seat_wind)).length)
const nextConfirmed = computed(() => props.game.next_ready?.includes(props.game.seat_wind))
const pending = ref(false)
watch(() => `${props.game.game_id}:${props.game.revision}:${props.actionError}`, () => { pending.value = false })
// State belongs to physical winds; only these display coordinates rotate.
const seats = computed(() => relativeRoomSeats(props.game.seat_wind).map(seat => ({ ...seat, player: props.game.players.find(p => p.seat_wind === seat.wind) })))
const myWind = computed(() => ROOM_SEATS.find(s => s.wind === props.game.seat_wind)?.label)
const actions = computed(() => props.game.actions || [])
const canDiscard = computed(() => !props.opening && !pending.value && props.game.phase === 'discard' && props.game.current_turn === props.game.seat_wind)
const buttons = computed(() => actions.value.filter(a => a.action_type !== 'discard'))
const progressHint = computed(() => {
  if (props.game.phase === 'finished') return '本局结束，四方以牌会友。'
  return gameStatusHint({ wallCount:props.game.wall_count, selfMelds:props.game.players.find(p => p.seat_wind === props.game.seat_wind)?.melds || [], opponents:props.game.players.filter(p => p.seat_wind !== props.game.seat_wind) }).text
})
function act(action) { if (pending.value || props.opening) return; pending.value = true; emit('action', action) }
function discard(tile) { const action = actions.value.find(a => a.action_type === 'discard' && a.tiles[0] === tile); if (canDiscard.value && action) act(action) }
function actionLabel(action) { const label = { chi:'吃',pong:'碰',ming_gang:'明杠',an_gang:'暗杠',bu_gang:'补杠',hu:'胡',self_draw_win:'自摸',pass:'过牌' }[action.action_type]; return action.hu_info ? `${label} (${huResultLabel(action.hu_info)})` : label }
const { isFullscreen, fullscreenAvailable, toggleFullscreen } = useFullscreen({mobileFallback:true,autoEnter:true})
const self = computed(() => props.game.players.find(p => p.seat_wind === props.game.seat_wind) || {})
const opponents = computed(() => props.game.players.filter(p => p.seat_wind !== props.game.seat_wind))
const timeBanks = computed(() => Object.fromEntries([...'ESWN'].map(wind=>[wind,wind===props.game.seat_wind || props.game.phase==='discard' && wind===props.game.current_turn ? props.game.time_banks?.[wind] ?? 30000 : null])))
const visibleClocks = computed(() => Object.fromEntries(Object.entries(props.game.clocks || {}).filter(([wind])=>props.game.phase!=='response'||wind===props.game.seat_wind)))
const hand = ref([])
const autoSort = ref(true)
const anchors = ref(null)
watch(() => `${props.game.game_id}:${props.game.hand_tiles.join(',')}:${props.game.drawn_tile || ''}`, (_, previous) => {
  if (!previous || !previous.startsWith(`${props.game.game_id}:`)) { anchors.value = null; hand.value = [] }
  hand.value = reconcileHandOrder(hand.value, props.game.hand_tiles)
  if (autoSort.value) sortHand()
}, { immediate:true })
function sortHand() {
  hand.value = anchors.value
    ? sortAroundSpecialTiles(hand.value, props.game.dealer_tile, props.game.drawn_tile, anchors.value)
    : sortHandTiles(hand.value, props.game.dealer_tile, props.game.drawn_tile)
}
watch(autoSort, value => { if (value) sortHand() })
function moveHand({ fromIndex, toIndex }) {
  hand.value = moveTileInList(hand.value, fromIndex, toIndex)
  anchors.value = captureSpecialAnchors(hand.value, props.game.dealer_tile, props.game.drawn_tile)
}
</script>
<template>
  <section class="pvp-game-table pve-session-view" :data-game-id="game.game_id" :data-self-wind="game.seat_wind" :data-phase="game.phase" aria-label="玩家对战牌桌" :inert="opening ? true : undefined">
    <main class="pve-game-main">
      <section class="pvp-topbar rounded-2xl border border-amber-300/30 text-amber-100" aria-label="轮次状态">
        <div class="pvp-game-header">
          <span>第 {{ game.circle_number || 1 }} 圈 · 第 {{ game.hand_number || 1 }} 局 · 庄家 {{ game.players.find(p => p.seat_wind === game.dealer_seat)?.nickname }} · {{ {E:'东',S:'南',W:'西',N:'北'}[game.dealer_seat] }}风</span>
          <span class="score-strip">累计：<span v-for="player in game.players" :key="player.seat_wind">{{ player.nickname }} {{ game.scores?.[player.seat_wind] || 0 }}</span></span>
          <span class="game-id">{{ room.room_id }}</span>
          <button type="button" :aria-pressed="soundMuted" @click="emit('mute')">{{ soundMuted ? '🔇 静音' : '🔊 音效' }}</button>
          <label class="pvp-volume">音量 <input type="range" min="0" max="100" step="5" :value="soundVolume" aria-label="音效音量" @input="emit('volume', Number($event.target.value))" /></label>
          <button type="button" :disabled="!fullscreenAvailable" :aria-pressed="isFullscreen" @click="toggleFullscreen">{{ isFullscreen ? '退出全屏' : '⛶ 全屏' }}</button>
          <button type="button" @click="emit('leave')">返回主页</button>
        </div>
      </section>
      <PvEBoard show-roles :seat-wind="game.seat_wind" :current-turn-seat="game.current_turn" :dealer-seat="game.dealer_seat" :dealer-tile="game.dealer_tile" :opponents="opponents" :self-discards="self.discards || []" :cumulative-scores="game.scores" :round-count="game.circle_number" :wall-count="game.wall_count" :table-waiting="game.phase === 'response'" :clocks="visibleClocks" :time-banks="timeBanks" :server-offset="serverOffset" />
      <PvpResponseWait v-if="game.phase === 'response' && !actions.length" :wait="game.response_wait" :server-offset="serverOffset" />
      <div class="game-status-hint pve-situation-hud pvp-progress-hint" role="status"><Transition name="situation-hint" mode="out-in"><span :key="progressHint">{{ progressHint }}</span></Transition></div>
      <PlayerWorkbench pve :show-recommendation="false">
        <HandBar class="pve-self-hand pvp-own-hand" :data-hand-wind="game.seat_wind" data-position="bottom" v-model="hand" v-model:auto-sort="autoSort" wall-driven :capacity="14 - (self.melds?.length || 0) * 3" :dealer-tile="game.dealer_tile" :latest-drawn-tile="game.drawn_tile || ''" :discard-mode="canDiscard" :disabled="!canDiscard" :turn-focused="canDiscard" :layout-pinned="!!anchors" @discard-tile="discard" @move-joker="moveHand" @reorder-tile="moveHand" @manual-sort="sortHand" />
        <MeldBar v-if="self.melds?.length" :model-value="self.melds" :dealer-tile="game.dealer_tile" :data-meld-wind="game.seat_wind" data-position="bottom" compact read-only />
      </PlayerWorkbench>
      <SeatClock class="pve-self-clock" :wind="game.seat_wind" :clock="game.clocks?.[game.seat_wind]" :bank-ms="timeBanks[game.seat_wind]" :server-offset="serverOffset" />
      <div class="self-player-caption player-caption" data-position="bottom" :data-wind="game.seat_wind"><b>{{ self.nickname }} · 自家 · {{ myWind }}风</b><small v-if="self.is_host">房主</small><b v-if="game.seat_wind === game.dealer_seat">庄</b></div>
      <div v-if="buttons.length && !opening" class="pvp-action-controls" aria-label="合法行牌操作"><p v-if="ownPaused" class="claim-paused">等待其他玩家碰杠或胡牌，吃牌倒计时已挂起。</p><button v-for="action in buttons" :key="action.action_id" type="button" :data-action="action.action_type" :disabled="pending || ownPaused && action.action_type !== 'pass'" @click="act(action)"><strong>{{ actionLabel(action) }}</strong><span v-if="['chi','pong','ming_gang','an_gang','bu_gang'].includes(action.action_type)" class="action-tiles"><MahjongTile v-for="(tile,index) in action.tiles" :key="index" :code="tile" /></span></button></div>
    </main>
    <GameOverModal v-if="game.result" pvp :info="game.result" :seat-wind="game.seat_wind" :dealer-seat="game.dealer_seat" :players="game.players" :opponents="opponents" :cumulative-scores="game.scores" :is-round-over="game.circle_complete" :next-confirmed="nextConfirmed" :next-count="nextCount" :human-count="humans.length" @next-round="emit('next')" @leave="emit('leave')" />
  </section>
</template>
<style scoped>
.pvp-game-header { justify-content:space-between; color:#f4dfac; white-space:nowrap; }
.score-strip { display:flex; gap:8px; font-size:10px; }
.game-id { color:#90b2a0; font-size:9px; }
.pvp-game-header button { border:1px solid #c6b37866; padding:3px 8px; border-radius:16px; font-size:11px; }
.pvp-volume { display:flex; align-items:center; gap:5px; font-size:11px; }.pvp-volume input { width:65px; accent-color:#edcc78; }
.self-player-caption { position:absolute; z-index:12; bottom:3px; left:12px; display:flex; align-items:center; gap:6px; color:#d7c794; font-size:10px; white-space:nowrap; }
.self-player-caption small { font-size:8px; padding:0 3px; border:1px solid #d4af5866; border-radius:3px; }
.player-clock { color:#f5d68b; font-variant-numeric:tabular-nums; }
.pvp-action-controls { position:absolute; z-index:100; left:50%; bottom:104px; transform:translateX(-50%); display:flex; justify-content:center; flex-wrap:wrap; gap:8px; width:700px; max-height:250px; overflow:auto; padding:10px; border:1px solid #cbb57188; border-radius:16px; background:#063b32f5; }
.pvp-action-controls button { padding:10px 18px; border:1px solid #cbb57188; border-radius:10px; background:#174e40; display:flex; flex-direction:column; align-items:center; gap:6px; font-size:16px; min-width:100px; }.pvp-action-controls button:disabled { opacity:.6; }
.action-tiles { display:flex; gap:3px; }.action-tiles :deep(.mahjong-tile) { --tw:23px; --th:31px; }
.claim-paused { width:100%; text-align:center; font-size:12px; color:#d7c795; }

</style>
