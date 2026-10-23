<script setup>
import TileArtwork from './TileArtwork.vue'
import { computed } from 'vue'
import { tileLabel } from '../constants/tiles.js'
const props = defineProps({ code: { type: String, required: true }, faceDown: Boolean, sideways: Boolean, badge: String, note: String, large: Boolean })
const suited = computed(() => /^[1-9][mps]$/.test(props.code))
const number = computed(() => Number(props.code[0]))
const suitName = computed(() => ({ m: '万', p: '筒', s: '条' })[props.code[1]] || '')
</script>
<template>
  <span class="mahjong-tile" :class="{ sideways, large, marked: badge, 'face-down':faceDown }" :data-tile="code" :data-face-down="faceDown || undefined" :data-sideways="sideways || undefined" :aria-label="faceDown ? '牌背' : [tileLabel(code), badge, note].filter(Boolean).join(' · ')" :title="faceDown ? '牌背' : [tileLabel(code), note].filter(Boolean).join(' · ')">
    <span v-if="faceDown" class="tile-back-face" aria-hidden="true" />
    <span v-else class="tile-face" aria-hidden="true">
      <TileArtwork v-if="suited && code[1] !== 'm'" :code="code" />
      <span v-else-if="suited" class="characters" :class="`suit-${code[1]}`"><b>{{ '一二三四五六七八九'[number-1] }}</b><b>{{ suitName }}</b></span>
      <span v-else-if="code === 'P'" class="white-dragon" />
      <b v-else class="honor" :class="code === 'C' ? 'text-[rgb(var(--tile-zhong))]' : code === 'F' ? 'text-[rgb(var(--tile-fa))]' : 'text-[rgb(var(--tile-bai))]'">{{ tileLabel(code) }}</b>
    </span>
    <span v-if="badge && !faceDown" class="tile-badge">{{ badge }}</span>
    <span v-if="note && !faceDown" class="tile-note">{{ note }}</span>
  </span>
</template>
<style scoped>
.mahjong-tile { --tw:40px; --th:calc(var(--tw)*4/3); position:relative; display:inline-flex; flex:none; width:var(--tw); height:var(--th); aspect-ratio:3/4; vertical-align:bottom; margin-bottom:4px; border-radius:clamp(2px,calc(var(--tw)*.12),6px); background:rgb(var(--tile-face)); box-shadow:2px 3px 0px rgb(var(--tile-shadow)),3px 4px 2px rgb(var(--ink-950) / .25); }
.mahjong-tile.large { --tw:54px; --th:calc(var(--tw)*4/3); }
.tile-face { position:absolute; inset:0; box-sizing:border-box; display:flex; flex-direction:column; align-items:center; justify-content:center; width:100%; height:100%; padding:8% 4%; overflow:hidden; border:1px solid rgb(var(--tile-edge)); border-radius:clamp(2px,calc(var(--tw)*.12),6px); background:linear-gradient(140deg,rgb(var(--tile-face)),rgb(var(--tile-face-2))); color:rgb(var(--tile-ink)); }
.tile-back-face { position:absolute; inset:0; border:1px solid rgb(var(--tile-back-edge)); border-radius:inherit; background:repeating-linear-gradient(45deg,rgb(var(--paper) / .02) 0 2px,transparent 2px 5px),linear-gradient(145deg,rgb(var(--tile-back)),rgb(var(--tile-back-2))); box-shadow:inset 0 0 0 1px rgb(var(--gilt-300) / .35),inset 0 0 0 2px rgb(var(--tile-back-edge) / .2),inset 0 0 0 4px rgb(var(--ink-950) / .2); }
.sideways { width:var(--th); height:var(--tw); aspect-ratio:4/3; }
.sideways .tile-face { inset:auto; left:50%; top:50%; width:var(--tw); height:var(--th); transform:translate(-50%,-50%) rotate(90deg); }
.characters { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:0; width:100%; font-family:var(--font-display); font-size:calc(var(--tw)*.4); font-weight:700; line-height:.9; text-align:center; }
.suit-m { gap:calc(var(--tw)*.10); color:rgb(var(--tile-wan)); } .suit-p { color:rgb(var(--tile-tong)); } .suit-s { color:rgb(var(--tile-tiao)); }
.honor { max-width:100%; font-size:calc(var(--tw)*.56); line-height:1; font-family:var(--font-display); white-space:nowrap; }
.white-dragon { width:65%; height:70%; border:max(1px,calc(var(--tw)*.055)) double rgb(var(--tile-bai)); border-radius:3px; }
.marked .tile-face { outline:2px solid rgb(var(--highlight)); }
.tile-badge { position:absolute; right:-3px; top:-10px; z-index:2; padding:1px 4px; border-radius:4px; background:rgb(var(--highlight)); color:rgb(var(--bronze-900)); font-size:10px; font-weight:800; white-space:nowrap; }
.tile-note { position:absolute; bottom:-10px; left:50%; transform:translateX(-50%); z-index:2; padding:0 2px; border-radius:3px; background:rgb(var(--info) / .22); color:rgb(var(--info)); font-size:9px; white-space:nowrap; }
</style>
