<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { roomActionSeconds } from '../utils/roomClock.js'
const props=defineProps({wait:Object,serverOffset:{type:Number,default:0}})
const now=ref(Date.now());let timer
onMounted(()=>{timer=setInterval(()=>{now.value=Date.now()},100)})
onUnmounted(()=>clearInterval(timer))
const seconds=computed(()=>roomActionSeconds(props.wait,props.serverOffset,now.value))
</script>
<template>
  <div class="pvp-response-wait" role="status" aria-live="polite">
    <span>等待其余玩家决策中...</span><b v-if="seconds" data-public-response-seconds>{{ seconds }}s</b><small v-else>加时等待</small>
  </div>
</template>
<style scoped>
.pvp-response-wait { position:absolute; z-index:14; top:31%; left:50%; transform:translateX(-50%); display:flex; align-items:center; gap:12px; padding:10px 16px; border:1px solid #d4af5888; border-radius:14px; background:#063b32f2; color:#f4e1b0; white-space:nowrap; font-size:14px; box-shadow:0 8px 24px #001b1755; }
.pvp-response-wait b { color:#fde68a; font-size:20px; min-width:28px; text-align:center; font-variant-numeric:tabular-nums; }.pvp-response-wait small { color:#b7d8cc; font-size:12px; }
</style>
