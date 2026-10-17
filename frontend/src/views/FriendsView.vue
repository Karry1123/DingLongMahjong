<script setup>
import { onMounted, ref } from 'vue'
import { friends, refreshFriends } from '../stores/friends.js'
import { searchUsers, requestFriend, removeFriend } from '../services/socialApi.js'
import { accountError } from '../utils/authValidation.js'
const account = ref(''), results = ref(null), error = ref(''), notice = ref(''), busy = ref(false)
onMounted(() => refreshFriends().catch(e => { error.value = e.message }))
async function run(fn) { if (busy.value) return; busy.value = true; error.value = ''; try { await fn() } catch(e) { error.value = e.message } finally { busy.value = false } }
function search() { error.value = accountError(account.value); if (!error.value) run(async () => { results.value = (await searchUsers(account.value)).items }) }
function apply(person) { run(async () => { const result = await requestFriend(person.id); notice.value = result.status === 'accepted' ? '已成为好友' : '申请已发送'; await refreshFriends(); results.value = (await searchUsers(account.value)).items }) }
function remove(person) { if (window.confirm(`移除好友 ${person.display_name}？`)) run(async () => { await removeFriend(person.id); await refreshFriends() }) }
const relations = { self:'这是你自己', friend:'已是好友', outgoing:'申请已发送', incoming:'对方已申请，加为好友' }
</script>
<template><div class="row"><h1>我的好友</h1><RouterLink to="/friends/requests">申请 {{ friends.incoming.length || '' }} →</RouterLink></div><form class="card stack" @submit.prevent="search"><label for="search-account">通过完整账号找好友<input id="search-account" v-model="account" autocomplete="off" maxlength="24" placeholder="输入完整账号" /></label><button :disabled="busy">查找账号</button><p v-if="results && !results.length">没有找到该账号</p><article v-for="person in results" :key="person.id" class="stack"><b>{{ person.display_name }} <small>@{{ person.account }}</small></b><button v-if="['none','incoming'].includes(person.relationship)" class="primary" :disabled="busy" @click.prevent="apply(person)">{{ relations[person.relationship] || '申请加好友' }}</button><span v-else>{{ relations[person.relationship] }}</span></article></form><p class="muted">{{ friends.items.length }} 位牌友</p><p v-if="!friends.items.length">还没有好友，用完整账号认识第一位牌友。</p><article v-for="person in friends.items" :key="person.id" class="card friend-row"><div><b>{{ person.display_name }}</b><small>@{{ person.account }}</small><small>{{ person.in_match ? '对局中' : person.online ? '在线' : '离线' }}</small></div><div class="stack"><RouterLink class="link-button" :aria-disabled="person.in_match" :to="person.in_match ? '/friends' : { path:'/invite', query: { friend:person.id } }">邀请</RouterLink><button :disabled="busy" @click="remove(person)">移除</button></div></article><p v-if="notice" role="status">{{ notice }}</p><p v-if="error" class="error" role="alert">{{ error }}</p></template>
