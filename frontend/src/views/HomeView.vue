<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth } from '../stores/auth.js'
import { invitations, refreshInvitations, respondInvitation } from '../stores/invitations.js'
import { legacyNotice } from '../router/guards.js'
const router = useRouter(), route = useRoute(), error = ref(''), busy = ref('')
onMounted(() => refreshInvitations().catch(e => { error.value = e.message }))
async function respond(id, accept) { busy.value = id; try { const match = await respondInvitation(id,accept); if (match) { if (auth.user) auth.user.active_match_id = match.id; await router.push(`/matches/${match.id}/waiting`) } } catch(e) { error.value = e.message } finally { busy.value = '' } }
</script>
<style scoped>
.rules-entry { grid-column:1 / -1; display:block; padding:var(--space-6); color:rgb(var(--fg)); font-family:var(--font-body); }
.rules-entry h2 { margin:var(--space-3) 0; font:600 var(--size-h2)/1.5 var(--font-display); }
.rules-entry p { color:rgb(var(--fg-muted)); line-height:1.7; }
.rules-entry:hover { border-color:rgb(var(--accent)); }
.rules-entry:focus-visible { outline:2px solid rgb(var(--accent)); outline-offset:4px; }
</style>
<template><p v-if="route.query.upgraded" class="card" role="status">{{ legacyNotice }}</p><p class="eyebrow">{{ auth.user?.display_name }}，你好</p><h1>今日，与好友入席</h1><RouterLink class="card hero ui-card--gilt ui-corner" to="/invite"><span class="hero-cloud ui-yunwen" aria-hidden="true"></span><span class="hero-mark ui-seal" aria-hidden="true">四方</span><h2>邀请好友对战</h2><p>邀一至三位牌友，空位由 AI 陪伴。</p><span class="primary link-button">邀请好友 ↗</span></RouterLink><RouterLink v-if="auth.user?.active_match_id" class="card row" :to="`/matches/${auth.user.active_match_id}/waiting`">返回进行中的牌桌 →</RouterLink><h2>收到的邀请</h2><p v-if="!invitations.items.length" class="muted">暂时没有新牌约，先邀请好友吧。</p><article v-for="invite in invitations.items" :key="invite.id" class="card stack"><b>{{ invite.inviter.display_name }} 邀你对战</b><p>{{ invite.members_count }} 人已入席 · {{ new Date(invite.expires_at).toLocaleTimeString() }} 前有效</p><div class="row"><button :disabled="!!busy" @click="respond(invite.id,false)">婉拒</button><button class="primary" :disabled="!!busy" @click="respond(invite.id,true)">接受并准备</button></div></article><div class="secondary-grid"><RouterLink class="card" to="/pve">人机练习 →</RouterLink><RouterLink class="card" to="/sandbox">全景沙盘 →</RouterLink><RouterLink class="ui-card rules-entry" data-mode="rules" to="/rules"><span class="ui-pill">肆 · Guide</span><h2>规则教学 →</h2><p>图文入门，逐页学会财神、吃碰杠与四家结算。</p></RouterLink></div><p v-if="error" class="error" role="alert">{{ error }}</p></template>
