<script setup>
import { registerBackDismiss } from '../platform/androidBack.js'
import { onMounted, onUnmounted, ref } from 'vue'
import { getMatchHistory } from '../services/matchApi.js'
import GameHistoryModal from '../components/GameHistoryModal.vue'
const items = ref([]), cursor = ref(null), error = ref(''), loading = ref(false), showPve = ref(false)
async function load(more = false) { loading.value = true; try { const data = await getMatchHistory(more ? cursor.value : ''); items.value = more ? [...items.value,...data.items] : data.items; cursor.value = data.next_cursor; error.value = '' } catch(e) { error.value = e.message } finally { loading.value = false } }
onMounted(() => load())
onUnmounted(registerBackDismiss(() => { if (!showPve.value) return false; showPve.value = false; return true }))
</script>
<template><h1>我的牌谱</h1><button class="card row" @click="showPve = true">人机练习牌谱 <span>复盘 →</span></button><h2>好友对战摘要</h2><p v-if="!items.length && !loading" class="muted">暂无已结束的对战</p><article v-for="item in items" :key="item.match_id" class="card stack"><b>{{ new Date(item.finished_at).toLocaleString() }} · {{ item.hands }} 局</b><div v-for="member in item.members" :key="member.seat" class="row"><span>{{ member.display_name }}</span><span>{{ member.score > 0 ? '+' : '' }}{{ member.score }}</span></div></article><p v-if="error" class="error" role="alert">{{ error }}</p><button v-if="error || cursor" :disabled="loading" @click="load(!!cursor)">{{ loading ? '读取中…' : cursor ? '加载更多' : '重试' }}</button><p v-else-if="loading" role="status">正在读取…</p><GameHistoryModal v-if="showPve" @close="showPve = false" /></template>
