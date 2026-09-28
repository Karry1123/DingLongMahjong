<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { nicknameError, roomIdError, pvpRoute, createVisitorId } from '../utils/pvpEntry.js'
import { roomRequest } from '../services/roomApi.js'
import { useRoomSocket } from '../composables/useRoomSocket.js'
import { ROOM_SEATS, countdownNumber } from '../utils/roomSeats.js'
import PvpGameTable from './PvpGameTable.vue'
import { selfTurnCueKey } from '../utils/pvpTurnCue.js'

const props = defineProps({ opening: Boolean, soundMuted: Boolean, soundVolume: Number })
const emit = defineEmits(['home', 'dissolved', 'opening', 'opening-end', 'sound', 'mute', 'volume', 'playing', 'fullscreen'])
const clockOffset = ref(0)
function readStorage(key, fallback = '') { try { return localStorage.getItem(key) || fallback } catch { return fallback } }
function saveStorage(key, value) { try { localStorage.setItem(key, value) } catch { /* Private browsing may disable storage. */ } }
let clientId
try { clientId = sessionStorage.getItem('dinglong.pvp.client'); if (!clientId) { clientId = createVisitorId(); sessionStorage.setItem('dinglong.pvp.client', clientId) } }
catch { clientId = createVisitorId() }
function readTabNickname() { try { return sessionStorage.getItem('dinglong.pvp.nickname') || readStorage('dinglong.pvp.nickname') } catch { return readStorage('dinglong.pvp.nickname') } }
const nickname = ref([...readTabNickname()].slice(0, 6).join(''))
const dialog = ref('nickname')
const capacity = ref(4)
const roomIdInput = ref(pvpRoute(location.hash)?.roomId || '')
const room = ref(null)
const error = ref('')
const busy = ref(false)
const connectionMessage = ref('')
const copied = ref(false)
const dialogElement = ref(null)
const nicknameConfirmed = ref(false)
const occupied = computed(() => room.value?.human_count || 0)
const seats = computed(() => ROOM_SEATS.map(seat => ({ ...seat, player: room.value?.players.find(p => p.seat === seat.seat) })))
const me = computed(() => room.value?.players.find(p => p.seat === room.value.my_seat))
const game = ref(null)
const playing = computed(() => room.value?.status === 'playing' && !!game.value)
watch(playing, value => emit('playing', value), { immediate: true })
const actionError = ref(0)
const countdown = ref(3)
let controller, disposed = false, countdownTimer, serverOffset = 0, openingGameId = '', lastSoundEvent = ''
let lastTurnCue = ''
const credentials = () => ({ client_id: clientId, nickname: nickname.value.trim() })
function stopCountdown() { clearInterval(countdownTimer); countdownTimer = null }
function returnToLobby(message) {
  emit('opening-end')
  openingGameId = ''; lastSoundEvent = ''
  lastTurnCue = ''
  stopCountdown(); room.value = null; game.value = null; dialog.value = ''; busy.value = false
  roomIdInput.value = ''; copied.value = false; connectionMessage.value = ''; error.value = message
  history.replaceState(null, '', `${location.pathname}${location.search}#/pvp`)
}
const { connected, connectRoom, send } = useRoomSocket({
  onState(message) {
    room.value = message.room
    game.value = message.game || null
    busy.value = false
    connectionMessage.value = ''
    serverOffset = message.server_time - Date.now()
    clockOffset.value = serverOffset
    const cue = selfTurnCueKey(game.value)
    if (cue && cue !== lastTurnCue) {
      lastTurnCue = cue
      emit('sound', {action:'TURN',seat:game.value.seat_wind,selfSeat:game.value.seat_wind})
    } else if (!cue) lastTurnCue = ''
    if (game.value?.phase === 'opening' && game.value.game_id !== openingGameId) {
      openingGameId = game.value.game_id
      emit('opening', { gameId: game.value.game_id, dealerTile: game.value.dealer_tile, revealUntil: game.value.opening_at + 3000 - serverOffset })
    }
    const event = game.value?.event
    const eventId = event ? `${game.value.game_id}:${event.id}` : ''
    if (eventId && eventId !== lastSoundEvent) {
      lastSoundEvent = eventId
      emit('sound', { ...event, selfSeat: game.value.seat_wind })
    }
    if (room.value.status === 'countdown') {
      const update = () => { countdown.value = countdownNumber(room.value.start_at, serverOffset) }
      update()
      if (!countdownTimer) countdownTimer = setInterval(update, 80)
    } else stopCountdown()
  },
  onClosed(message, dissolved) { returnToLobby(message); if (dissolved) emit('dissolved', message) },
  onError(message) { error.value = message; busy.value = false; actionError.value++ },
})
function chooseSeat(wind) { error.value = ''; if (!send({ type: 'seat', seat: wind })) error.value = '房间正在连接，请稍候' }
function toggleReady() { error.value = ''; if (!me.value?.ready) emit('fullscreen'); if (!send({ type: 'ready', ready: !me.value?.ready })) error.value = '房间正在连接，请稍候' }
function act(action) {
  error.value = ''
  if (!send({ type: 'game_action', game_id: game.value.game_id, revision: game.value.revision, action_id: action.action_id })) { error.value = '房间连接已中断'; actionError.value++ }
}
function confirmNext() { emit('fullscreen'); if (!send({ type:'next_hand', game_id:game.value.game_id })) error.value = '房间连接已中断' }
watch(() => props.opening, (value, previous) => {
  if (previous && !value && game.value?.phase === 'opening') send({ type:'opening_complete', game_id:game.value.game_id })
})

function showDialog(value) { error.value = ''; dialog.value = value }
function confirmNickname() {
  error.value = nicknameError(nickname.value)
  if (error.value) return
  nickname.value = nickname.value.trim()
  saveStorage('dinglong.pvp.nickname', nickname.value)
  try { sessionStorage.setItem('dinglong.pvp.nickname', nickname.value) } catch { /* Storage is optional. */ }
  nicknameConfirmed.value = true
  showDialog(roomIdInput.value && !room.value ? 'join' : '')
}
async function enterRoom() {
  error.value = nicknameError(nickname.value) || (dialog.value === 'join' ? roomIdError(roomIdInput.value) : '')
  if (error.value || busy.value) return
  const creating = dialog.value === 'create'
  busy.value = true
  controller = new AbortController()
  try {
    // Joining claims a seat only after the WebSocket is authenticated; a failed
    // upgrade must not leave a disconnected reservation occupying a human slot.
    const result = creating
      ? await roomRequest('', { ...credentials(), capacity: capacity.value }, controller.signal)
      : { room_id: roomIdInput.value.trim(), capacity: 4, human_count: 0, players: [], status: 'waiting', my_seat: null }
    if (disposed) {
      if (creating) void roomRequest(`/${result.room_id}/leave`, { client_id: clientId }).catch(() => {})
      return
    }
    room.value = result
    dialog.value = ''
    history.replaceState(null, '', `${location.pathname}${location.search}#/pvp/room/${result.room_id}`)
    connectionMessage.value = '正在连接牌桌…'
    connectRoom(result.room_id, credentials())
  } catch (e) { if (!disposed && e.name !== 'AbortError') error.value = e.message }
  finally { busy.value = false }
}
async function leaveRoom() {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try {
    if (send({ type: 'leave' })) return
    if (room.value) await roomRequest(`/${room.value.room_id}/leave`, { client_id: clientId })
    returnToLobby('你已离席，房间已解散')
  } catch (e) { error.value = e.message; busy.value = false }
}
function backHome() { if (room.value) showDialog('leave'); else emit('home') }
async function copyRoom() {
  try { await navigator.clipboard.writeText(room.value.room_id); copied.value = true }
  catch { connectionMessage.value = `房间号 ${room.value.room_id}，可手动选中复制` }
}
function dialogKeydown(event) {
  if (event.key === 'Escape' && !busy.value) { event.preventDefault(); if (dialog.value === 'nickname' && !nicknameConfirmed.value) backHome(); else showDialog('') }
  if (event.key !== 'Tab') return
  const elements = [...dialogElement.value.querySelectorAll('button:not(:disabled), input:not(:disabled)')]
  const first = elements[0], last = elements.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
watch(dialog, async value => { if (!value) return; await nextTick(); dialogElement.value?.querySelector('input, button')?.focus() })
onMounted(async () => {
  // A link can join an active waiting room; refreshing an occupied room dissolves it.
  await nextTick(); dialogElement.value?.querySelector('input')?.focus()
  if (roomIdInput.value && !nicknameError(nickname.value)) { nicknameConfirmed.value = true; dialog.value = 'join'; await enterRoom() }
})
onUnmounted(() => { disposed = true; stopCountdown(); controller?.abort(); emit('opening-end'); emit('playing', false) })
</script>

<template>
  <section class="pvp-lobby" :class="{ 'is-playing': playing }">
    <header v-if="!playing" class="lobby-header" :inert="dialog ? true : undefined">
      <button type="button" class="quiet-button" :disabled="busy" @click="backHome">← 返回首页</button>
      <span class="lobby-brand">顶龙麻将</span>
      <span class="fair-play">真人对战 · 公平博弈</span>
    </header>
    <div v-if="!room" class="lobby-entry" :inert="dialog ? true : undefined">
      <p class="lobby-eyebrow">以牌会友 · 四方入席</p>
      <h1>玩家对战</h1>
      <p class="lobby-description">2–4 人相约一桌，凭牌技较量。</p>
      <button class="nickname-chip quiet-button" type="button" @click="showDialog('nickname')">{{ nicknameConfirmed ? nickname : '设置昵称' }} <span aria-hidden="true">✎</span></button>
      <div class="room-entry-actions">
        <button type="button" class="entry-action" :disabled="!nicknameConfirmed || busy" @click="showDialog('create')"><span class="entry-glyph" aria-hidden="true">＋</span><strong>创建房间</strong><span>设定人数，邀好友入席</span></button>
        <button type="button" class="entry-action" :disabled="!nicknameConfirmed || busy" @click="showDialog('join')"><span class="entry-glyph" aria-hidden="true">↗</span><strong>加入房间</strong><span>输入房间号，赴一场牌约</span></button>
      </div>
      <p class="fair-notice">本模式关闭 EV 推荐与局势辅助提示</p>
    </div>
    <PvpGameTable v-else-if="room.status === 'playing' && game" :room="room" :game="game" :opening="props.opening" :sound-muted="props.soundMuted" :sound-volume="props.soundVolume" :action-error="actionError" :server-offset="clockOffset" :inert="dialog || props.opening ? true : undefined" @leave="showDialog('leave')" @action="act" @next="confirmNext" @mute="emit('mute')" @volume="emit('volume', $event)" />
    <div v-else class="waiting-room" :inert="dialog ? true : undefined">
      <div class="room-heading"><div><p class="lobby-eyebrow">牌友入席 · 静候开局</p><h1>房间 <span class="room-number">{{ room.room_id }}</span></h1></div><button type="button" class="quiet-button" @click="copyRoom">{{ copied ? '已复制房间号' : '复制房间号' }}</button></div>
      <div class="waiting-table" aria-label="房间等待桌面">
        <div class="table-center"><span class="table-seal" aria-hidden="true">顶龙</span><strong>{{ occupied < room.capacity ? '等待入席' : '静候准备' }}</strong><span aria-live="polite">真人 {{ occupied }} / {{ room.capacity }} 人</span></div>
        <div class="seat-list">
          <button v-for="item in seats" :key="item.seat" type="button" class="waiting-seat" :data-seat="item.wind" :class="[item.position, { occupied: item.player, 'my-seat': item.seat === room.my_seat, 'ai-seat': item.player?.is_ai }]" :disabled="!connected || !!(item.player && !item.player.is_ai)" :aria-label="`${item.label}风：${item.player?.nickname || '空位'}${!item.player || item.player.is_ai ? '，点击就坐' : ''}`" @click="chooseSeat(item.wind)">
            <span class="seat-wind">{{ item.label }} <small>{{ { E: 'East', S: 'South', W: 'West', N: 'North' }[item.wind] }}</small></span>
            <span class="seat-avatar" aria-hidden="true">{{ item.player ? [...item.player.nickname][0] : '待' }}</span>
            <strong>{{ item.player?.nickname || '空位' }}</strong>
            <span class="seat-meta">{{ item.player ? (item.player.is_host ? '房主' : item.player.is_ai ? 'AI 补位' : '牌友') : '点击就坐' }}{{ item.player && item.seat === room.my_seat ? ' · 你' : '' }}</span>
            <span class="ready-label" :aria-hidden="!item.player || undefined" :class="{ 'is-ready': item.player?.ready }">{{ item.player ? item.player.ready ? '✓ 已准备' : item.player.connected ? '未准备' : '连接中' : '' }}</span>
          </button>
        </div>
      </div>
      <div class="waiting-footer"><p>{{ occupied < room.capacity ? '分享房间号，邀请牌友入席。' : '牌友已到齐，全员准备后开局。' }}</p><div class="waiting-actions"><button type="button" class="primary-button ready-button" :disabled="!connected || busy" :aria-pressed="!!me?.ready" @click="toggleReady">{{ me?.ready ? '取消准备' : '准备' }}</button><button type="button" class="quiet-button" :disabled="busy" @click="showDialog('leave')">离开房间</button></div></div>
      <p class="fair-notice">真人对战 · 无 EV 辅助</p>
    </div>
    <p v-if="error && !dialog" class="lobby-error" role="alert">{{ error }}</p>
    <p v-if="connectionMessage" class="connection-status" role="status">{{ connectionMessage }}</p>
    <div v-if="room?.status === 'countdown'" class="countdown-overlay" role="status" aria-live="polite"><p>四方就绪 · 即将开局</p><Transition name="countdown" mode="out-in"><strong :key="countdown">{{ countdown || '入席' }}</strong></Transition><button type="button" class="quiet-button" @click="toggleReady">取消准备</button></div>

    <div v-if="dialog" class="lobby-overlay" @keydown="dialogKeydown">
      <section ref="dialogElement" class="lobby-dialog" role="dialog" aria-modal="true" aria-labelledby="pvp-dialog-title">
        <p class="lobby-eyebrow">顶龙麻将 · 真人牌桌</p>
        <h2 id="pvp-dialog-title">{{ { nickname: '请留个名号', create: '创建房间', join: '加入房间', leave: '离开房间？' }[dialog] }}</h2>
        <form v-if="dialog !== 'leave'" @submit.prevent="dialog === 'nickname' ? confirmNickname() : enterRoom()">
          <template v-if="dialog === 'nickname'">
            <label for="pvp-nickname">你的昵称</label>
            <input id="pvp-nickname" v-model="nickname" :disabled="busy" autocomplete="nickname" placeholder="输入昵称，与牌友相识" maxlength="6" :aria-invalid="!!error" aria-describedby="pvp-dialog-help pvp-dialog-error" @input="nickname = [...$event.target.value].slice(0, 6).join(''); error = ''" />
            <p id="pvp-dialog-help" class="dialog-help">最多 6 个字；AI 1号至 AI 4号为系统保留昵称。</p>
          </template>
          <template v-else-if="dialog === 'create'">
            <label>本局真人上限人数</label>
            <div class="capacity-options" role="group" aria-label="选择房间人数"><button v-for="count in [2, 3, 4]" :key="count" type="button" :aria-pressed="capacity === count" :disabled="busy" @click="capacity = count">{{ count }} 人</button></div>
            <p class="dialog-help">房间号创建后可分享给好友。</p>
          </template>
          <template v-else>
            <label for="pvp-room-id">六位房间号</label>
            <input id="pvp-room-id" v-model="roomIdInput" :disabled="busy" class="room-id-input" inputmode="numeric" autocomplete="off" maxlength="6" placeholder="输入 6 位数字" :aria-invalid="!!error" aria-describedby="pvp-dialog-error" @input="error = ''" />
          </template>
          <p id="pvp-dialog-error" class="dialog-error" role="alert">{{ error }}</p>
          <div class="dialog-actions"><button type="button" class="quiet-button" :disabled="busy" @click="dialog === 'nickname' && !nicknameConfirmed ? backHome() : showDialog('')">取消</button><button type="submit" class="primary-button" :disabled="busy">{{ busy ? '正在连接…' : dialog === 'nickname' ? '确认昵称' : dialog === 'create' ? '创建并入席' : '加入房间' }}</button></div>
        </form>
        <template v-else><p class="dialog-help">任一真人离席都会解散房间，全员返回主页。</p><p id="pvp-dialog-error" class="dialog-error" role="alert">{{ error }}</p><div class="dialog-actions"><button type="button" class="quiet-button" :disabled="busy" @click="showDialog('')">留在牌桌</button><button type="button" class="primary-button" :disabled="busy" @click="leaveRoom()">{{ busy ? '正在离席…' : '确认离开' }}</button></div></template>
      </section>
    </div>
  </section>
</template>

<style scoped>
.pvp-lobby { position:relative; flex:1; min-height:0; width:100%; height:100%; max-width:1000px; margin:auto; color:#f8ecd3; }
.lobby-header { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:16px; height:42px; padding-bottom:8px; border-bottom:1px solid #bdc7a42b; }
.lobby-brand { font:600 22px 'Songti SC',SimSun,serif; letter-spacing:.1em; }
.fair-play,.fair-notice { color:#a5beb0; font-size:12px; }
.quiet-button,.primary-button { border:1px solid #c4b47f55; border-radius:9px; padding:10px 16px; font-size:13px; background:#092d2855; color:#ecdfbf; transition:background .2s; }
button:hover:not(:disabled) { background:#3a6754; }
button:focus-visible,input:focus-visible { outline:2px solid #e7ca84; outline-offset:3px; }
button:disabled { opacity:.5; cursor:wait; }
.lobby-entry { text-align:center; padding:60px 0 32px; }
.lobby-eyebrow { font-size:11px; letter-spacing:.2em; color:#c8ae76; margin-bottom:12px; }
.lobby-entry h1 { font:600 36px/1.4 'Songti SC',SimSun,serif; }
.lobby-description { margin-top:12px; color:#b5cdc0; font-size:14px; }
.nickname-chip { margin-top:22px; max-width:100%; overflow-wrap:anywhere; }
.nickname-chip span { margin-left:12px; color:#c7ab73; }
.room-entry-actions { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px; max-width:640px; margin:32px auto 24px; }
.entry-action { display:flex; align-items:center; flex-direction:column; gap:15px; padding:34px 18px; border:1px solid #c8b57455; border-radius:20px; background:linear-gradient(130deg,#1b514440,#82703920); }
.entry-glyph { font-size:32px; color:#e1c584; }
.entry-action strong { font:600 23px 'Songti SC',SimSun,serif; }
.entry-action > span:last-child { color:#b7cabc; font-size:12px; }
.waiting-room { height:calc(100% - 50px); margin-top:8px; display:grid; grid-template-rows:48px minmax(0,1fr) 42px 16px; gap:8px; }
.room-heading { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:18px; }
.room-heading h1 { font-size:22px; }
.room-number { color:#f1d594; font-variant-numeric:tabular-nums; letter-spacing:.14em; user-select:all; }
.waiting-table { position:relative; margin-top:0; min-height:0; border:1px solid #c9b07377; border-radius:36px; padding:12px; background:radial-gradient(ellipse at center,#236253,#0b372e 75%); box-shadow:inset 0 0 0 8px #092d2840,0 18px 60px #001b1740; }
.table-center { position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); display:flex; align-items:center; flex-direction:column; gap:10px; width:140px; text-align:center; pointer-events:none; }
.table-seal { border:1px solid #d0ab68; border-radius:50%; width:68px; height:68px; display:grid; place-items:center; color:#e6c58b; font:24px serif; box-shadow:inset 0 0 0 4px #123f36; }
.table-center strong { color:#e9dcb6; letter-spacing:.16em; font-size:17px; }
.table-center > span:last-child { color:#b9d4c3; font-size:13px; }
.seat-list { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); height:100%; grid-template-rows:repeat(3,minmax(0,1fr)); gap:6px; align-items:center; }
.waiting-seat { box-sizing:border-box; display:flex; flex-direction:column; align-items:center; justify-self:center; gap:3px; width:min(100%,210px); height:140px; min-height:140px; max-height:140px; min-width:0; padding:9px 10px; overflow:hidden; border:1px dashed #91af9e5c; border-radius:16px; background:#092f2755; }
.waiting-seat > * { flex-shrink:0; }
.waiting-seat.left { grid-area:2 / 1; } .waiting-seat.right { grid-area:2 / 3; } .waiting-seat.top { grid-area:1 / 2; } .waiting-seat.bottom { grid-area:3 / 2; }
.waiting-seat:disabled { opacity:1; cursor:default; }
.seat-wind { height:20px; line-height:20px; color:#efcf8c; font:600 16px/20px serif; white-space:nowrap; } .seat-wind small { font:10px sans-serif; margin-left:4px; color:#9fb7a7; }
.ready-label { height:16px; line-height:16px; color:#a7b5ac; font-size:11px; white-space:nowrap; } .ready-label.is-ready { color:#84ddab; }
.seat-meta { height:16px; line-height:16px; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#a9c5b4; font-size:11px; }
.waiting-seat.ai-seat { border-color:#a7c8b766; background:#2c594344; }
.waiting-seat.occupied { border-style:solid; border-color:#a4bea35c; }
.waiting-seat.my-seat { border-color:#d5b66f; background:#90824b20; }
.seat-avatar { display:grid; place-items:center; width:34px; height:34px; border-radius:50%; color:#cfba84; background:#385d4d; font:20px serif; }
.waiting-seat strong { height:20px; line-height:20px; max-width:100%; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; font-size:14px; text-align:center; }
.waiting-seat > span:last-child { color:#a9c5b4; font-size:11px; }
.waiting-footer { display:flex; align-items:center; justify-content:space-between; gap:18px; margin:0; color:#bdcec0; font-size:13px; }
.waiting-actions { display:flex; flex-shrink:0; gap:12px; }
.ready-button { min-width:90px; }
.countdown-overlay { position:fixed; inset:0; z-index:145; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:32px; background:#001b17c9; backdrop-filter:blur(5px); text-align:center; }
.countdown-overlay p { color:#e8cb89; letter-spacing:.25em; font-size:16px; }
.countdown-overlay strong { display:grid; place-items:center; width:160px; height:160px; border:1px solid #d6b36688; border-radius:50%; color:#ffe5a6; font:700 100px/1 serif; text-shadow:0 0 35px #e6bf6470; }
.countdown-enter-active,.countdown-leave-active { transition:opacity .18s,transform .18s; }
.countdown-enter-from { opacity:0; transform:scale(1.25); } .countdown-leave-to { opacity:0; transform:scale(.85); }
.lobby-error,.dialog-error { color:#ffb3a6; font-size:12px; line-height:1.6; }
.lobby-error,.connection-status { text-align:center; margin-top:18px; }
.connection-status { color:#e4c78e; font-size:12px; }
.lobby-overlay { position:fixed; inset:0; z-index:150; display:flex; align-items:center; justify-content:center; padding:20px; background:#001c19bd; backdrop-filter:blur(7px); overflow:auto; }
.lobby-dialog { width:100%; max-width:420px; max-height:100%; overflow:auto; padding:30px; border:1px solid #d5b16a80; border-radius:22px; background:linear-gradient(145deg,#154236,#092b27); box-shadow:0 30px 100px #00110da0; }
.lobby-dialog h2 { font:600 26px 'Songti SC',SimSun,serif; margin-bottom:25px; }
.lobby-dialog label { display:block; color:#d8d8be; font-size:13px; margin-bottom:10px; }
.lobby-dialog input { width:100%; box-sizing:border-box; min-width:0; padding:13px 14px; border:1px solid #adb58a66; border-radius:10px; background:#001e1a88; color:#fff2d6; font-size:16px; }
.lobby-dialog input::placeholder { color:#8aa999; }
.lobby-dialog input[aria-invalid=true] { border-color:#e39380; }
.dialog-help { margin-top:12px; color:#9fbbab; font-size:12px; line-height:1.7; }
.dialog-error { margin-top:12px; min-height:20px; }
.dialog-actions { display:flex; justify-content:flex-end; gap:12px; margin-top:20px; }
.primary-button { background:#d7b56d; border-color:#d7b56d; color:#193e31; font-weight:600; }
.primary-button:hover:not(:disabled) { background:#ebcd8b; }
.capacity-options { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.capacity-options button { padding:17px 5px; border:1px solid #9bb59650; border-radius:10px; color:#bdcfbf; }
.capacity-options button[aria-pressed=true] { border-color:#e2c477; color:#ffe4a6; background:#af935430; }
.room-id-input { letter-spacing:.16em; font-variant-numeric:tabular-nums; }
.pvp-lobby.is-playing { max-width:none; }
.waiting-room .lobby-eyebrow { margin-bottom:2px; }
.connection-status,.lobby-error { position:absolute; z-index:130; bottom:0; left:50%; transform:translateX(-50%); padding:4px 10px; border-radius:8px; background:#123e32; }
@media(prefers-reduced-motion:reduce) { .countdown-enter-active,.countdown-leave-active { transition:none; } }
</style>
