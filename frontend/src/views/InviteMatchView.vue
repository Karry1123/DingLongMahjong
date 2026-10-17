<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { friends, refreshFriends } from '../stores/friends.js'
import { auth } from '../stores/auth.js'
import { activeMatch, refreshMatch } from '../stores/activeMatch.js'
import { createMatch, inviteFriends } from '../services/matchApi.js'
const route = useRoute(), router = useRouter(), selected = ref([]), error = ref(''), busy = ref(false)
const supplement = computed(() => route.query.match)
const excluded = computed(() => supplement.value ? [...(activeMatch.match?.members || []).map(m => m.user_id), ...(activeMatch.match?.invitations || []).filter(i => i.status === 'pending').map(i => i.invitee.id)] : [])
const max = computed(() => supplement.value ? Math.max(0,4 - (activeMatch.match?.members.length || 1) - (activeMatch.match?.invitations || []).filter(i => i.status === 'pending').length) : 3)
onMounted(async () => { try { await refreshFriends(); if (supplement.value) await refreshMatch(supplement.value); if (route.query.friend && friends.items.some(f => f.id === route.query.friend && !f.in_match)) selected.value = [route.query.friend] } catch(e) { error.value = e.message } })
async function submit() { if (busy.value || !selected.value.length || selected.value.length > max.value) return; busy.value = true; try { const { match } = await (supplement.value ? inviteFriends(supplement.value,selected.value) : createMatch(selected.value)); activeMatch.match = match; if (auth.user) auth.user.active_match_id = match.id; await router.push(`/matches/${match.id}/waiting`) } catch(e) { error.value = e.message } finally { busy.value = false } }
</script>
<template><h1>{{ supplement ? '补邀好友' : '邀请好友对战' }}</h1><p class="muted">选择 1–{{ max }} 位好友，接受即准备。</p><p v-if="!friends.items.length" class="card">还没有好友。<RouterLink to="/friends">去添加好友 →</RouterLink></p><form class="stack with-fixed-action" @submit.prevent="submit"><label v-for="friend in friends.items" :key="friend.id" class="card friend-row"><span><b>{{ friend.display_name }}</b><small>@{{ friend.account }} · {{ friend.in_match ? '对局中' : friend.online ? '在线' : '离线' }}</small></span><input v-model="selected" type="checkbox" :value="friend.id" :disabled="friend.in_match || excluded.includes(friend.id) || selected.length >= max && !selected.includes(friend.id)" /></label><p v-if="error" class="error" role="alert">{{ error }}</p><div class="fixed-action"><button class="primary" :disabled="busy || !selected.length || selected.length > max">{{ busy ? '正在邀请…' : `邀请并准备（${selected.length}）` }}</button></div></form></template>
