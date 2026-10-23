<script setup>
import { ref } from 'vue'
import { isNative } from '../platform/index.js'
import { appUpdate, installAppUpdate } from '../services/appUpdates.js'
const dismissed = ref('')
</script>

<template>
  <aside v-if="isNative() && appUpdate.action === 'apk' && appUpdate.info?.version !== dismissed" class="update-banner ui-toast" role="status">
    <div class="update-text"><b>需要安装新版本 {{ appUpdate.info.version }}</b><span>{{ appUpdate.error || appUpdate.message }}</span><span v-if="appUpdate.downloading">下载中 {{ appUpdate.progress == null ? '…' : appUpdate.progress + '%' }}</span></div>
    <div class="update-actions"><button type="button" class="ui-btn ui-btn--secondary" :disabled="appUpdate.downloading" @click="dismissed = appUpdate.info.version">稍后</button><button type="button" class="primary ui-btn ui-btn--secondary" :disabled="appUpdate.downloading" @click="installAppUpdate">立即更新</button></div>
  </aside>
</template>

<style scoped>
.update-banner { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:var(--space-2) var(--space-3); margin:var(--space-2) var(--space-4) 0; }
.update-text { display:flex; flex-direction:column; gap:var(--space-1); font-size:var(--size-body); }
.update-text span { color:rgb(var(--fg-muted)); font-size:var(--size-caption); }
.update-actions { display:flex; gap:var(--space-2); }
.update-actions button { padding:var(--space-3) var(--space-4); font:inherit; }
</style>
