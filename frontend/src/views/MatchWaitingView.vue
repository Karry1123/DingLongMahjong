<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { auth } from '../stores/auth.js'
import { countdownNumber } from '../utils/roomSeats.js'
import { waitingSeats } from '../utils/matchSeats.js'
const props = defineProps({ match: Object, connection: String, busy: Boolean })
const emit = defineEmits(['start','leave'])
const router = useRouter(), now = ref(Date.now()); let timer
const offset = ref(0)
const countdown = computed(() => countdownNumber(props.match?.start_at, offset.value, now.value))
watch(() => props.match?.server_time, value => { if (value) offset.value = value - Date.now() }, { immediate: true })
onMounted(() => { timer = setInterval(() => { now.value = Date.now() },100) })
onUnmounted(() => clearInterval(timer))
const host = computed(() => props.match?.host_id === auth.user?.id)
const seats = computed(() => waitingSeats(props.match))
const unlocked = computed(() => ['inviting','waiting'].includes(props.match?.status))
</script>
<template><h1>好友牌桌</h1><p class="muted" role="status">{{ connection === 'connected' ? '好友接受邀请后自动准备' : '正在连接，等待服务端同步…' }}</p><div class="seat-grid"><article v-for="seat in seats" :key="seat.seat" class="card seat-card" :class="{ 'ui-corner': match?.members?.some(member => member.seat === seat.seat && member.user_id === match.host_id) }"><span class="seat-label">{{ ['东','南','西','北'][seat.seat-1] }}席</span><b>{{ seat.name }}</b><p>{{ seat.label }}</p></article></div><section v-if="match?.status === 'countdown'" class="card countdown-card" role="status" aria-live="polite"><h2>四方就绪</h2><strong>{{ countdown || '等待服务端开局' }}</strong><p>空位已由 AI 补齐</p></section><template v-if="host && unlocked"><button :disabled="busy || connection !== 'connected' || match.members.length < 2" class="primary" @click="emit('start')">按当前人数开始</button><button :disabled="busy" @click="router.push({ path:'/invite', query: { match:match.id } })">补邀好友</button><small>至少 2 位真人可开始，空位由 AI 补齐。</small></template><p v-if="['cancelled','aborted','finished'].includes(match?.status)" class="card">本桌已结束，请返回首页。</p><button :disabled="busy" @click="emit('leave')">{{ host ? '离开并结束本桌' : '离开牌桌' }}</button></template>
