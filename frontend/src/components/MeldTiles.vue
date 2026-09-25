<script setup>
import { computed } from 'vue'
import MahjongTile from './MahjongTile.vue'
import { tileLabel } from '../constants/tiles.js'
const props = defineProps({ meld: { type: Object, required: true }, dealerTile: String })
const claimedIndex = computed(() => props.meld.meld_type === 'chi' && props.meld.claimed_tile ? props.meld.tiles.indexOf(props.meld.claimed_tile) : -1)
</script>
<template>
  <span class="meld-tile-group relative inline-flex items-end pb-3 pt-2" aria-label="副露牌组" :aria-description="`${meld.meld_type === 'ming_gang' ? '明杠' : meld.meld_type === 'chi' ? '吃' : meld.meld_type === 'pong' ? '碰' : '副露'}：${meld.tiles.map(tileLabel).join('、')}`" data-meld-group :data-meld-type="meld.meld_type">
    <MahjongTile v-for="(tile,i) in meld.tiles" :key="i" :code="tile" :sideways="i === claimedIndex" :note="tile === 'P' && dealerTile && dealerTile !== 'P' ? '替' + tileLabel(dealerTile) : undefined" />
    <span v-if="meld.meld_type === 'ming_gang'" class="meld-kind-label absolute bottom-0 left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] font-bold text-amber-300">明杠</span>
  </span>
</template>
<style scoped>
.meld-tile-group { gap:4px; isolation:isolate; }
.meld-tile-group :deep(.mahjong-tile) { position:relative; flex:0 0 auto; margin-left:0; margin-right:0; z-index:1; }
.meld-tile-group :deep(.mahjong-tile.sideways) { width:var(--th); height:var(--tw); }
</style>
