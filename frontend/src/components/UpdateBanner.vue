<script setup>
import { ref } from 'vue'
import { isNative } from '../platform/index.js'
import { appUpdate, installAppUpdate } from '../services/appUpdates.js'
const dismissed = ref('')
</script>

<template>
  <aside v-if="isNative() && appUpdate.action === 'apk' && appUpdate.info?.version !== dismissed" class="update-banner" role="status">
    <div class="update-text"><b>需要安装新版本 {{ appUpdate.info.version }}</b><span>{{ appUpdate.error || appUpdate.message }}</span><span v-if="appUpdate.downloading">下载中 {{ appUpdate.progress == null ? '…' : appUpdate.progress + '%' }}</span></div>
    <div class="update-actions"><button type="button" :disabled="appUpdate.downloading" @click="dismissed = appUpdate.info.version">稍后</button><button type="button" class="primary" :disabled="appUpdate.downloading" @click="installAppUpdate">立即更新</button></div>
  </aside>
</template>

<style scoped>
.update-banner { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; margin: 8px 16px 0; padding: 12px 14px; border-radius: 16px; border: 1px solid rgba(199,165,85,.45); background: #10382F; color: #F4F0E5; }
.update-text { display: flex; flex-direction: column; gap: 2px; font-size: 14px; }
.update-text span { color: #B4C8BF; font-size: 13px; }
.update-actions { display: flex; gap: 8px; }
.update-actions button { min-height: 44px; padding: 0 14px; border-radius: 12px; border: 1px solid rgba(180,200,191,.4); background: transparent; color: #F4F0E5; font-size: 15px; }
.update-actions .primary { background: #C7A555; color: #06221D; border-color: #C7A555; font-weight: 600; }
</style>
