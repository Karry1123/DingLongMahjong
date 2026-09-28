<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import MahjongTile from './MahjongTile.vue'
import { tileLabel } from '../constants/tiles.js'
const props = defineProps({ dealerTile: { type:String, required:true } })
const emit = defineEmits(['complete'])
const overlay = ref(null), phase = ref('reveal'), destination = ref(null)
let revealTimer, flightTimer
const ruleHint = computed(() => props.dealerTile === 'P'
  ? '白板自身为百搭，本局没有额外替身牌。'
  : `白板替代${tileLabel(props.dealerTile)}的固定牌面；财神可作百搭，不能用于吃牌或开杠。`)
const flyerStyle = computed(() => destination.value ? {
  left:`${destination.value.x}px`, top:`${destination.value.y}px`,
  transform:`translate(-50%, -50%) scale(${destination.value.scale})`,
} : {})
function locateSlot() {
  const stage = overlay.value?.closest('.game-stage')
  const tile = stage?.querySelector('[data-god-slot] .mahjong-tile')
  if (!stage || !tile) return
  const s=stage.getBoundingClientRect(), t=tile.getBoundingClientRect()
  // Invert the stage's rotation and scale, including portrait's -90° rotation.
  const m=new DOMMatrix(getComputedStyle(stage).transform), det=m.a*m.d-m.b*m.c
  if (Math.abs(det)<1e-8) return
  const dx=(t.left+t.right-s.left-s.right)/2, dy=(t.top+t.bottom-s.top-s.bottom)/2
  const scale=Math.sqrt(Math.abs(det)), portrait=Math.abs(m.b)>Math.abs(m.a)
  destination.value={x:stage.offsetWidth/2+(m.d*dx-m.c*dy)/det,
    y:stage.offsetHeight/2+(-m.b*dx+m.a*dy)/det,
    scale:(portrait?t.height:t.width)/scale/140}
}
function onResize() { if (phase.value==='flight') locateSlot() }
onMounted(() => {
  revealTimer=setTimeout(() => {
    locateSlot(); phase.value='flight'
    flightTimer=setTimeout(() => emit('complete'),600)
  },3000)
  window.addEventListener('resize',onResize)
})
onUnmounted(() => {
  clearTimeout(revealTimer); clearTimeout(flightTimer)
  window.removeEventListener('resize',onResize)
})
</script>
<template>
  <div ref="overlay" class="god-opening" :class="`god-opening-${phase}`" :data-opening-phase="phase" role="dialog" aria-modal="true" aria-label="顶龙麻将 · 财神登场">
    <div class="god-opening-mask" /><div class="god-opening-halo" />
    <div class="god-opening-flyer" :style="flyerStyle"><MahjongTile :code="dealerTile" /></div>
    <div class="god-opening-copy"><p>顶龙麻将</p><h2>本局财神 / 得</h2>
      <strong>{{ tileLabel(dealerTile) }}</strong><p class="god-opening-rule">{{ ruleHint }}</p><small>定牌后，开启第一巡</small>
    </div>
  </div>
</template>
<style scoped>
.god-opening { position:absolute; inset:0; z-index:2000; isolation:isolate; overflow:hidden; color:#fff6d5; }
.god-opening-mask { position:absolute; inset:0; background:#001c19dc; backdrop-filter:blur(5px); transition:opacity .6s ease-in-out; }
.god-opening-halo { position:absolute; left:50%; top:39%; width:400px; height:400px; transform:translate(-50%,-50%); border-radius:50%; background:radial-gradient(circle,#f6ce6655,transparent 66%); animation:god-glow 1.5s ease-in-out infinite alternate; transition:opacity .6s ease-in-out; }
.god-opening-flyer { position:absolute; left:50%; top:37%; width:140px; height:186.667px; transform:translate(-50%,-50%); transition:all .6s ease-in-out; filter:drop-shadow(0 0 22px #fbbf2480); }
.god-opening-flyer :deep(.mahjong-tile) { --tw:140px; --th:186.667px; width:100%; height:100%; margin:0; }
.god-opening-copy { position:absolute; top:54%; left:50%; width:620px; max-width:90%; transform:translateX(-50%); text-align:center; transition:opacity .6s ease-in-out; }
.god-opening-copy > p:first-child { color:#fbbf24; font-size:13px; letter-spacing:.3em; }
.god-opening-copy h2 { margin:8px 0; font-size:32px; font-weight:800; letter-spacing:.12em; }
.god-opening-copy strong { display:block; font-size:20px; color:#fde68a; }
.god-opening-rule { margin:12px auto; max-width:520px; font-size:16px; line-height:1.6; color:#d5e8de; }
.god-opening-copy small { font-size:12px; color:#b8cbbf; }
.god-opening-flight .god-opening-mask, .god-opening-flight .god-opening-copy, .god-opening-flight .god-opening-halo { opacity:0; }
.god-opening-flight .god-opening-flyer { filter:none; }
@keyframes god-glow { to { opacity:.55; } }
@media(prefers-reduced-motion:reduce) { .god-opening-halo { animation:none; } .god-opening-flyer { transition:none; } }
</style>
