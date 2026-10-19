<script setup>
import { onMounted, ref } from 'vue'
import { isNative, lifecycle } from '../platform/index.js'
import { checkForUpdate } from '../utils/appUpdate.js'

const current = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : '0.0.0'
const update = ref(null), dismissed = ref(''), checking = ref(false)
const DISMISS_KEY = 'dl.update.dismissed'
try { dismissed.value = localStorage.getItem(DISMISS_KEY) || '' } catch { /* storage unavailable */ }

async function check() {
  if (checking.value) return
  checking.value = true
  try {
    update.value = await checkForUpdate(current)
  } catch { /* offline or rate limited: stay quiet, retry on next resume */ } finally { checking.value = false }
}
function dismiss() { dismissed.value = update.value?.version || ''; try { localStorage.setItem(DISMISS_KEY, dismissed.value) } catch { /* ignore */ } }
function download() { window.open(update.value.url, '_blank') }
const megabytes = size => (size / 1048576).toFixed(1)

onMounted(() => { if (!isNative()) return; void check(); lifecycle.onResume(() => void check()) })
</script>

<template>
  <aside v-if="isNative() && update && update.version !== dismissed" class="update-banner" role="status">
    <div class="update-text"><b>新版本 {{ update.version }}</b><span>当前 v{{ current }} · 安装包 {{ megabytes(update.size) }} MB</span></div>
    <div class="update-actions"><button type="button" @click="dismiss">稍后</button><button type="button" class="primary" @click="download">下载更新</button></div>
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
