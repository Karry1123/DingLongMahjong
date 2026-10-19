<script setup>
const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'dev'
import { reactive, ref, watch } from 'vue'
import { isNative } from '../platform/index.js'
import { checkForUpdate } from '../utils/appUpdate.js'
const updateChecking = ref(false), updateResult = ref(''), availableUpdate = ref(null)
async function checkUpdate() {
  if (updateChecking.value) return
  updateChecking.value = true
  updateResult.value = ''
  availableUpdate.value = null
  try {
    availableUpdate.value = await checkForUpdate(appVersion)
    updateResult.value = availableUpdate.value ? `发现新版本 ${availableUpdate.value.version.replace(/^v?/, 'v')}` : `已是最新版本 v${appVersion}`
  } catch (error) { updateResult.value = `检查失败（${error.message}）` }
  finally { updateChecking.value = false }
}
import { useRouter } from 'vue-router'
import { auth, signOut } from '../stores/auth.js'
import { preferences } from '../stores/preferences.js'
import { updateProfile, changePassword } from '../services/authApi.js'
import { nicknameError } from '../utils/pvpEntry.js'
import { passwordError } from '../utils/authValidation.js'
const router = useRouter(), name = ref(auth.user?.display_name || ''), passwords = reactive({ current:'', next:'', confirm:'' }), error = ref(''), notice = ref(''), busy = ref(false)
watch(() => auth.user?.display_name, value => { name.value = value || '' })
async function run(fn) { busy.value = true; error.value = ''; notice.value = ''; try { await fn() } catch(e) { error.value = e.message } finally { busy.value = false } }
function profile() { error.value = nicknameError(name.value); if (!error.value) run(async () => { auth.user = { ...auth.user, ...await updateProfile(name.value.trim()) }; notice.value = '昵称已更新' }) }
function password() { error.value = passwordError(passwords.current) || passwordError(passwords.next) || (passwords.next !== passwords.confirm ? '两次新密码不一致' : ''); if (!error.value) run(async () => { await changePassword(passwords.current,passwords.next); Object.assign(passwords,{current:'',next:'',confirm:''}); notice.value = '密码已更新' }) }
async function logout() { await run(async () => { try { await signOut() } finally { await router.replace('/login') } }) }
</script>
<template><h1>设置</h1><p class="muted">@{{ auth.user?.account }}</p><form class="card stack" @submit.prevent="profile"><label>昵称<input v-model="name" autocomplete="nickname" maxlength="12" required /></label><button :disabled="busy">保存昵称</button></form><form class="card stack" @submit.prevent="password"><h2>修改密码</h2><label>当前密码<input v-model="passwords.current" type="password" autocomplete="current-password" maxlength="64" required /></label><label>新密码<input v-model="passwords.next" type="password" autocomplete="new-password" maxlength="64" required /></label><label>确认新密码<input v-model="passwords.confirm" type="password" autocomplete="new-password" maxlength="64" required /></label><button :disabled="busy">更新密码</button></form><section class="card stack"><label>音量 {{ preferences.volume }}%<input v-model.number="preferences.volume" type="range" min="0" max="100" /></label><label class="row">静音<input v-model="preferences.muted" type="checkbox" /></label></section><p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p><button :disabled="busy" @click="logout">退出登录</button><p class="muted version-line">顶龙麻将 v{{ appVersion }}</p><section v-if="isNative()" class="card stack"><button type="button" :disabled="updateChecking" @click="checkUpdate">{{ updateChecking ? '检查中…' : '检查更新' }}</button><p v-if="updateResult" role="status">{{ updateResult }} <a v-if="availableUpdate" :href="availableUpdate.url" target="_blank" rel="noopener">（下载）</a></p></section></template>
