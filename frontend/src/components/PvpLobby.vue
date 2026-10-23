<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { registerBackDismiss } from '../platform/androidBack.js'
import { auth, clearAuth } from '../stores/auth.js'
import { activeMatch, applySnapshot, clearActiveMatch, refreshMatch } from '../stores/activeMatch.js'
import { leaveMatch, startMatch } from '../services/matchApi.js'
import { useRoomSocket } from '../composables/useRoomSocket.js'
import { selfTurnCueKey } from '../utils/pvpTurnCue.js'
import MatchWaitingView from '../views/MatchWaitingView.vue'
import PvpGameTable from './PvpGameTable.vue'
import TableShell from '../layouts/TableShell.vue'
import GodOpeningCeremony from './GodOpeningCeremony.vue'
const props = defineProps({ soundMuted:Boolean, soundVolume:Number })
const emit = defineEmits(['sound','mute','volume','fullscreen','playing','opening-end','opening'])
const route = useRoute(), router = useRouter(), id = route.params.id
const match = computed(() => activeMatch.match), game = computed(() => activeMatch.game)
const error = ref(''), busy = ref(false), opening = ref(null), actionError = ref(0), serverOffset = ref(0), leaveDialog = ref(false)
const stopBackDismiss = registerBackDismiss(() => { if (!leaveDialog.value) return false; leaveDialog.value = false; return true })
onUnmounted(stopBackDismiss)
let openingId = '', soundId = '', lastCue = '', hasLeft = false, dead = false
const playing = computed(() => !!game.value && match.value?.status === 'playing')
const { connected, status, connectRoom, send, dispose } = useRoomSocket({
 onState(message) {
  applySnapshot(message); busy.value = false
  serverOffset.value = (message.server_time || match.value?.server_time || Date.now()) - Date.now()
  if (auth.user) auth.user.active_match_id = ['finished','cancelled','aborted'].includes(match.value?.status) ? null : id
  if (game.value?.phase === 'opening' && openingId !== game.value.game_id) {
   openingId = game.value.game_id
   opening.value = { id:openingId, tile:game.value.dealer_tile, until:game.value.opening_at + 3000 - serverOffset.value }
   emit('opening')
  } else if (game.value?.phase !== 'opening') opening.value = null
  const cue = selfTurnCueKey(game.value)
  if (cue && cue !== lastCue) emit('sound',{ action:'TURN',seat:game.value.seat_wind,selfSeat:game.value.seat_wind })
  lastCue = cue
  const event = game.value?.event, key = event ? `${game.value.game_id}:${event.id}` : ''
  if (key && key !== soundId) { soundId = key; emit('sound',{ ...event,selfSeat:game.value.seat_wind }) }
  if (match.value?.status === 'playing' && route.params.phase !== 'play') void router.replace(`/matches/${id}/play`)
 },
 onClosed(message) { error.value = message; hasLeft = true; clearActiveMatch(); if (message.includes('登录')) { clearAuth(); void router.replace('/login') } else { if (auth.user) auth.user.active_match_id = null } },
 onError(message) { error.value = message; actionError.value++; busy.value = false },
})
watch(status, value => { activeMatch.connection = value }, { immediate:true })
watch(playing, value => emit('playing',value), { immediate:true })
async function start() { busy.value = true; error.value = ''; try { const { match:updated } = await startMatch(id); activeMatch.match = updated } catch(e) { error.value = e.message } finally { busy.value = false } }
function act(action) { if (!send({ type:'game_action', game_id:game.value.game_id, revision:game.value.revision, action_id:action.action_id })) { error.value = '连接恢复后才能操作'; actionError.value++ } }
function next() { if (!send({ type:'next_hand', game_id:game.value.game_id })) error.value = '连接恢复后才能操作' }
function openingComplete() { opening.value = null; if (game.value?.phase === 'opening') send({type:'opening_complete',game_id:game.value.game_id}); emit('opening-end') }
async function leave() { if (hasLeft || ['finished','cancelled','aborted'].includes(match.value?.status)) { dispose(); await router.push('/home'); return } busy.value = true; try { await leaveMatch(id); hasLeft = true; dispose(); if (auth.user) auth.user.active_match_id = null; clearActiveMatch(); await router.push('/home') } catch(e) { error.value = e.message } finally { busy.value = false } }
onBeforeRouteLeave(async to => {
 if (['finished','cancelled','aborted'].includes(match.value?.status)) return true
 if (to.path.startsWith(`/matches/${id}/`) || to.path === '/invite' && to.query.match === id || hasLeft || !auth.token) return true
 if (!window.confirm('离开会结束本桌对战，确定离开？')) return false
 try { await leaveMatch(id); hasLeft = true; if (auth.user) auth.user.active_match_id = null; return true } catch(e) { error.value = e.message; return false }
})
onMounted(async () => { clearActiveMatch(); try { await refreshMatch(id); if (!dead && !['finished','cancelled','aborted'].includes(activeMatch.match?.status)) connectRoom(id) } catch(e) { error.value = e.message; if ([403,404].includes(e.status)) hasLeft = true } })
onUnmounted(() => { dead = true; dispose(); emit('playing',false); emit('opening-end') })
</script>
<template><TableShell v-if="playing" active><GodOpeningCeremony v-if="opening" :key="opening.id" :dealer-tile="opening.tile" :reveal-until="opening.until" @complete="openingComplete" /><PvpGameTable :room="match" :game="game" :opening="!!opening" :reconnecting="!connected" :sound-muted="props.soundMuted" :sound-volume="props.soundVolume" :server-offset="serverOffset" :action-error="actionError" @action="act" @next="next" @leave="leaveDialog = true" @mute="emit('mute')" @volume="emit('volume',$event)" /><p v-if="error" class="table-error" role="alert">{{ error }}</p><div v-if="leaveDialog" class="pvp-dissolved-overlay"><section class="pvp-dissolved-dialog" role="dialog" aria-modal="true" aria-labelledby="leave-title"><h2 id="leave-title">离开会结束本桌</h2><p>全体牌友的本次对战将结束，确定离开？</p><div class="row"><button autofocus :disabled="busy" @click="leaveDialog = false">留在牌桌</button><button :disabled="busy" @click="leave">确认离开</button></div></section></div></TableShell><section v-else class="stack"><MatchWaitingView :match="match" :connection="status" :busy="busy" @start="start" @leave="leaveDialog = true" /><p v-if="error" class="error" role="alert">{{ error }}</p><section v-if="leaveDialog" class="card stack" role="dialog" aria-modal="true" aria-labelledby="waiting-leave"><h2 id="waiting-leave">确认离开牌桌？</h2><p>房主离开会结束本桌。</p><button :disabled="busy" @click="leave">确认离开</button><button @click="leaveDialog = false">继续等待</button></section></section></template>
<style scoped>.table-error { position:absolute;bottom:20px;left:20px;z-index:150;background:rgb(var(--bg-raised));color:rgb(var(--danger));padding:var(--space-3);border-radius:var(--r-md); }</style>
