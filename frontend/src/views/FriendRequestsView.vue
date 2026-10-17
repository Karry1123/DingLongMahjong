<script setup>
import { onMounted, ref } from 'vue'
import { friends, refreshFriends, respondRequest } from '../stores/friends.js'
const error = ref(''), busy = ref(false)
onMounted(() => refreshFriends().catch(e => { error.value = e.message }))
async function respond(id,accept) { busy.value = true; try { await respondRequest(id,accept) } catch(e) { error.value = e.message } finally { busy.value = false } }
</script>
<template><RouterLink to="/friends">← 好友</RouterLink><h1>好友申请</h1><h2>收到的申请</h2><p v-if="!friends.incoming.length" class="muted">暂无待处理申请</p><article v-for="item in friends.incoming" :key="item.id" class="card stack"><b>{{ item.from.display_name }} · @{{ item.from.account }}</b><div class="row"><button :disabled="busy" @click="respond(item.id,false)">拒绝</button><button class="primary" :disabled="busy" @click="respond(item.id,true)">同意</button></div></article><h2>发出的申请</h2><article v-for="item in friends.outgoing" :key="item.id" class="card row"><span>{{ item.to.display_name }} · 等待同意</span><button :disabled="busy" @click="respond(item.id,false)">撤回</button></article><p v-if="error" class="error" role="alert">{{ error }}</p></template>
