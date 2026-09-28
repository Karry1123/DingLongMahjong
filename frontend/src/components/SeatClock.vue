<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { roomClockState } from '../utils/roomClock.js'
const props = defineProps({ wind:String, clock:Object, bankMs:{type:Number,default:30000}, privateBank:Boolean, serverOffset:{type:Number,default:0} })
const now = ref(Date.now())
let interval
onMounted(() => { interval = setInterval(() => { now.value = Date.now() }, 100) })
onUnmounted(() => clearInterval(interval))
const state = computed(() => roomClockState(props.clock, props.bankMs, props.serverOffset, now.value))
const label = computed(() => state.value.paused ? '等待抢断' : state.value.stage === 'bank' ? '加时' : props.clock?.kind === 'win' ? '和牌' : props.clock?.kind === 'response' ? '响应' : '出牌')
</script>
<template>
  <div class="seat-time" :data-seat-timer="wind" :class="{ 'is-active':clock && !state.paused, 'is-bank':state.stage === 'bank', 'is-critical':clock && !state.paused && state.seconds < 3, 'is-paused':state.paused }" :aria-label="`${wind}风${clock ? `${label}${state.seconds}秒，` : ''}${privateBank ? '加时已隐藏' : `剩余加时${state.bankSeconds}秒`}`">
    <span v-if="clock" class="operation-clock" :data-clock-wind="wind" :data-paused="state.paused" :data-timer-stage="state.stage">{{ label }} · <b>{{ state.seconds }}</b>秒</span>
    <span v-else class="operation-clock waiting-clock">静候行牌</span>
    <span class="time-bank" :data-bank-wind="wind">加时: <b>{{ privateBank ? '—' : state.bankSeconds }}</b>{{ privateBank ? '' : 's' }}</span>
  </div>
</template>
<style scoped>
.seat-time { display:flex; flex-direction:column; align-items:center; justify-content:center; flex-shrink:0; min-width:90px; height:38px; padding:2px 6px; border:1px solid #8eb5a54d; border-radius:8px; background:#06372ddd; color:#add0bd; font-variant-numeric:tabular-nums; white-space:nowrap; line-height:1.1; }
.operation-clock { font-size:11px; }.operation-clock b { display:inline-block; min-width:23px; font-size:20px; color:inherit; text-align:center; }
.waiting-clock { font-size:10px; opacity:.65; margin-bottom:3px; }
.time-bank { font-size:11px; }.time-bank b { font-weight:700; }
.is-active { border-color:#e8c972; color:#ffe2a0; box-shadow:0 0 10px #e5bd422b; }.is-active .operation-clock b { animation:clock-pulse 1s ease-in-out infinite; }
.is-bank { border-color:#5cc8ed; color:#b8edff; background:#123e48ee; }.is-paused { border-style:dashed; color:#bacbbf; }
.is-critical { border-color:#fb7185; color:#ffd1d8; background:#542c32e8; }.is-critical .operation-clock b { animation-duration:.5s; }
@keyframes clock-pulse { 50% { opacity:.6; transform:scale(1.08); } }
@media(prefers-reduced-motion:reduce) { .is-active .operation-clock b { animation:none; } }
</style>
