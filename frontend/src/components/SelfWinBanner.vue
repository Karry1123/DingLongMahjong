<script setup>
import { computed } from 'vue'
import { huResultLabel } from '../utils/huLabel.js'
const props = defineProps({ info: { type:Object, required:true }, disabled:Boolean })
const emit = defineEmits(['declare', 'dismiss'])
const result = computed(() => huResultLabel(props.info))
</script>
<template>
  <div class="self-win-actions" aria-label="自摸操作" aria-live="polite">
    <button type="button" class="self-win-button" :disabled="disabled" @click="emit('declare')">自摸<span v-if="result"> ({{ result }})</span></button>
    <button type="button" class="self-win-pass" :disabled="disabled" @click="emit('dismiss')">暂不胡</button>
  </div>
</template>
<style scoped>
.self-win-actions { display:flex; justify-content:center; align-items:center; gap:8px; }
.self-win-actions button { min-height:44px; padding:8px 14px; border-radius:10px; white-space:nowrap; font-size:16px; font-weight:700; cursor:pointer; }
.self-win-button { background:#fbbf24; color:#422006; border:1px solid #fde68a; }
.self-win-pass { background:#063b32; color:#d1fae5; border:1px solid #5eead477; }
.self-win-actions button:disabled { cursor:default; opacity:.5; }
</style>
