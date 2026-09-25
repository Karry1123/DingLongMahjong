<script setup>
import MahjongTile from './MahjongTile.vue'
defineProps({
  tiles: { type: Array, default: () => [] },
  compact: Boolean,
  layout: { type: String, default: '' },
})
</script>
<template>
  <TransitionGroup name="river" tag="div" class="discard-river" :class="[{ compact }, layout && `river--${layout}`]" :data-layout="layout || undefined" aria-label="弃牌">
    <MahjongTile v-for="(tile,i) in tiles" :key="`${i}-${tile}`" :code="tile" />
  </TransitionGroup>
</template>
<style scoped>
.discard-river { display:grid; grid-template-columns:repeat(6,40px); gap:6px 4px; min-height:60px; align-content:start; }
.discard-river.compact { width:100%; grid-template-columns:repeat(auto-fill,33px); gap:4px 3px; min-height:49px; }
.compact :deep(.mahjong-tile) { --tw:33px; --th:47px; --face-font:18px; --honor-font:25px; }
.river-enter-active { transition:transform .22s,opacity .22s; }
.river-enter-from { transform:translateY(-10px); opacity:0; }
@media (max-width:768px) and (orientation:portrait) { .river-enter-from { transform:none; } }
@media(prefers-reduced-motion:reduce) { .river-enter-active { transition:none; } }
</style>
