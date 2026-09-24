<script setup>
import { computed } from 'vue'
import MahjongTile from './MahjongTile.vue'
import { tileLabel } from '../constants/tiles.js'
const props = defineProps({ meld: { type: Object, required: true }, dealerTile: String })
const claimedIndex = computed(() => props.meld.meld_type === 'chi' && props.meld.claimed_tile ? props.meld.tiles.indexOf(props.meld.claimed_tile) : -1)
</script>
<template>
  <span class="relative inline-flex items-end gap-1 pb-3 pt-2" aria-label="副露牌组" :data-meld-type="meld.meld_type">
    <MahjongTile v-for="(tile,i) in meld.tiles" :key="i" :code="tile" :sideways="i === claimedIndex" :note="tile === 'P' && dealerTile && dealerTile !== 'P' ? '替' + tileLabel(dealerTile) : undefined" />
    <span v-if="meld.meld_type === 'ming_gang'" class="absolute bottom-0 left-1/2 -translate-x-1/2 whitespace-nowrap text-[10px] font-bold text-amber-300">明杠</span>
  </span>
</template>
