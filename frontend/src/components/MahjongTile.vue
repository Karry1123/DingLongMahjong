<script setup>
import { computed } from 'vue'
import { tileLabel } from '../constants/tiles.js'
const props = defineProps({ code: { type: String, required: true }, sideways: Boolean, badge: String, note: String, large: Boolean })
const suited = computed(() => /^[1-9][mps]$/.test(props.code))
const number = computed(() => Number(props.code[0]))
const suitName = computed(() => ({ m: '万', p: '筒', s: '条' })[props.code[1]] || '')
</script>
<template>
  <span class="mahjong-tile" :class="{ sideways, large, marked: badge }" :data-tile="code" :data-sideways="sideways || undefined" :aria-label="[tileLabel(code), badge, note].filter(Boolean).join(' · ')" :title="[tileLabel(code), note].filter(Boolean).join(' · ')">
    <span class="tile-face" aria-hidden="true">
      <span v-if="suited" class="characters" :class="`suit-${code[1]}`"><b>{{ '一二三四五六七八九'[number-1] }}</b><b>{{ suitName }}</b></span>
      <span v-else-if="code === 'P'" class="white-dragon" />
      <b v-else class="honor" :class="code === 'C' ? 'text-red-700' : code === 'F' ? 'text-emerald-700' : ''">{{ tileLabel(code) }}</b>
    </span>
    <span v-if="badge" class="tile-badge">{{ badge }}</span>
    <span v-if="note" class="tile-note">{{ note }}</span>
  </span>
</template>
<style scoped>
.mahjong-tile { --tw:40px; --th:calc(var(--tw)*4/3); position:relative; display:inline-flex; flex:none; width:var(--tw); height:var(--th); aspect-ratio:3/4; vertical-align:bottom; margin-bottom:4px; border-radius:clamp(2px,calc(var(--tw)*.12),6px); background:#fffef6; box-shadow:2px 3px 0px #b2cbb5,3px 4px 2px rgba(0,0,0,0.25); }
.mahjong-tile.large { --tw:54px; --th:calc(var(--tw)*4/3); }
.tile-face { position:absolute; inset:0; box-sizing:border-box; display:flex; flex-direction:column; align-items:center; justify-content:center; width:100%; height:100%; padding:8% 4%; overflow:hidden; border:1px solid #cabfa3; border-radius:clamp(2px,calc(var(--tw)*.12),6px); background:linear-gradient(140deg,#fffef6,#ece9d8); color:#173d42; }
.sideways { width:var(--th); height:var(--tw); aspect-ratio:4/3; }
.sideways .tile-face { inset:auto; left:50%; top:50%; width:var(--tw); height:var(--th); transform:translate(-50%,-50%) rotate(90deg); }
.characters { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:0; width:100%; font-family:serif; font-size:calc(var(--tw)*.4); font-weight:700; line-height:.9; text-align:center; }
.suit-m { color:#b4232d; } .suit-p { color:#185a91; } .suit-s { color:#177247; }
.honor { max-width:100%; font-size:calc(var(--tw)*.56); line-height:1; font-family:serif; white-space:nowrap; }
.white-dragon { width:65%; height:70%; border:max(1px,calc(var(--tw)*.055)) double #225c91; border-radius:3px; }
.marked .tile-face { outline:2px solid #fbbf24; }
.tile-badge { position:absolute; right:-3px; top:-10px; z-index:2; padding:1px 4px; border-radius:4px; background:#fbbf24; color:#422006; font-size:10px; font-weight:800; white-space:nowrap; }
.tile-note { position:absolute; bottom:-10px; left:50%; transform:translateX(-50%); z-index:2; padding:0 2px; border-radius:3px; background:#bae6fd; color:#0c4a6e; font-size:9px; white-space:nowrap; }
</style>
