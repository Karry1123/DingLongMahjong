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
  <div class="pvp-response-wait" :class="{ 'is-bank': !seconds, 'is-critical': seconds && seconds < 3 }" role="status" aria-live="polite">
    <span>等待其余玩家决策中...</span><b v-if="seconds" data-public-response-seconds>{{ seconds }}s</b><small v-else>加时等待</small>
  </div>
</template>
<style scoped>
.pvp-response-wait { position:absolute; z-index:14; top:31%; left:50%; transform:translateX(-50%); display:flex; align-items:center; gap:12px; padding:10px 16px; border:1px solid rgb(var(--clock-run)); border-radius:14px; background:rgb(var(--ink-900) / .95); color:rgb(var(--clock-run)); white-space:nowrap; font-size:14px; box-shadow:0 8px 24px rgb(var(--ink-950) / .35); }
.pvp-response-wait.is-bank { border-color:rgb(var(--clock-bank)); color:rgb(var(--clock-bank)); background:rgb(var(--info) / .16); }
.pvp-response-wait.is-critical { border-color:rgb(var(--clock-urgent)); color:rgb(var(--clock-urgent)); background:rgb(var(--danger) / .16); }
.pvp-response-wait b { color:inherit; font-size:20px; min-width:28px; text-align:center; font-variant-numeric:tabular-nums; }.pvp-response-wait small { color:inherit; font-size:12px; }
</style>
