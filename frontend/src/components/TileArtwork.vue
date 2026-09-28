<script setup>
import { computed } from 'vue'
const props = defineProps({ code: { type: String, required: true } })
const suit = computed(() => props.code[1])
const n = computed(() => Number(props.code[0]))
const green = '#146b46', red = '#b52c35', blue = '#214e87'
const layouts = {
  1:[[36,48]], 2:[[36,26],[36,70]], 3:[[20,23],[36,48],[52,73]],
  4:[[20,26],[52,26],[20,70],[52,70]],
  5:[[20,23],[52,23],[36,48],[20,73],[52,73]],
  6:[[20,22],[52,22],[20,48],[52,48],[20,74],[52,74]],
  7:[[20,18],[36,29],[52,40],[20,59],[52,59],[20,79],[52,79]],
  8:[[20,17],[52,17],[20,38],[52,38],[20,59],[52,59],[20,80],[52,80]],
  9:[[17,23],[36,23],[55,23],[17,48],[36,48],[55,48],[17,73],[36,73],[55,73]],
}
function color(n,i) { return n === 5 && i === 2 ? red : n === 7 && i < 3 ? red : [blue,green,red][Math.floor(i / (n === 9 ? 3 : 2)) % 3] }
</script>
<template>
  <svg class="tile-artwork" viewBox="0 0 72 96" aria-hidden="true" focusable="false" :data-artwork="code">
            <g v-if="suit === 's' && n === 1" stroke-linecap="round" stroke-linejoin="round">
              <path d="M35 61 Q10 75 14 86 Q30 82 41 62 M39 61 Q25 87 35 88 L47 60 M44 61 Q44 86 55 84 L50 56" :fill="green" :stroke="green" stroke-width="2" />
              <path d="M20 79 L34 67 M37 79 L42 65 M50 76 L48 64" stroke="#d6b955" stroke-width="2" />
              <path d="M27 30 C16 44 21 62 39 65 C54 65 59 51 50 40 C46 36 44 30 48 24 C52 17 45 12 39 16 C33 20 34 30 27 30Z" :fill="green" />
              <path d="M28 37 C18 50 31 61 43 55 C49 51 39 40 28 37Z" :fill="blue" stroke="#fffdf1" stroke-width="1.5" />
              <path d="M27 43 L40 52 M26 48 L35 54" stroke="#fffdf1" stroke-width="1.5" />
              <path d="M48 21 L57 24 L48 27 M39 16 L36 10 L43 13" :fill="red" />
              <circle cx="44" cy="21" r="1.8" fill="#fffdf1" /><circle cx="44.4" cy="21" r=".9" fill="#18352d" />
              <path d="M32 64 L28 71 M41 65 L39 72 M20 73 H48" :stroke="red" stroke-width="2" />
            </g>
            <g v-else v-for="([x,y],i) in layouts[n]" :key="i" :transform="`translate(${x} ${y})`">
              <g v-if="suit === 'p'" :stroke="n === 1 ? green : color(n,i)" fill="none">
                <circle :r="n === 1 ? 25 : n === 9 ? 7.5 : 9" :stroke-width="n === 1 ? 3 : 2" />
                <circle :r="n === 1 ? 19 : n === 9 ? 4.5 : 6" :stroke-width="n === 1 ? 2 : 1" :stroke="n === 1 ? blue : color(n,i)" />
                <g v-if="n === 1" :stroke="blue"><path v-for="a in 12" :key="a" d="M0 -16 L0 -22" :transform="`rotate(${a*30})`" stroke-width="2" /></g>
                <path v-if="n === 1" d="M0 -11 Q5 -15 6 -6 Q15 -5 11 0 Q15 5 6 6 Q5 15 0 11 Q-5 15 -6 6 Q-15 5 -11 0 Q-15 -5 -6 -6 Q-5 -15 0 -11Z" :fill="red" stroke="none" />
                <circle :r="n === 1 ? 3 : 2" :fill="n === 1 ? '#fffdf1' : color(n,i)" stroke="none" />
              </g>
              <g v-else :stroke="n === 5 && i === 2 || n === 7 && i < 3 || n === 9 && i < 3 ? red : green" stroke-linecap="round">
                <path d="M-3 -7 Q-1 0 -3 7 M3 -7 Q1 0 3 7" fill="none" stroke-width="2.6" />
                <path d="M-4 -8 H4 M-4 0 H4 M-4 8 H4" stroke-width="2.5" />
              </g>
            </g>
  </svg>
</template>
<style scoped>
.tile-artwork { display:block; width:100%; height:100%; min-width:0; min-height:0; flex:1; }
</style>
