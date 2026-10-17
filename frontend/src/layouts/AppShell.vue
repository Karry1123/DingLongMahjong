<script setup>
import { haptics } from '../platform/index.js'
import UpdateBanner from '../components/UpdateBanner.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const tabs = [['/home','⌂','首页'],['/friends','♧','好友'],['/records','▤','牌谱'],['/settings','⚙','设置']]
</script>
<template><div class="mobile-app"><header v-if="route.params.phase !== 'play'" class="mobile-brand"><RouterLink to="/home">顶龙麻将</RouterLink><span>以牌会友</span></header><UpdateBanner v-if="route.params.phase !== 'play'" /><main :class="{ 'mobile-content': route.params.phase !== 'play' }"><slot /></main><nav v-if="!route.meta.public && route.params.phase !== 'play'" class="bottom-tabs" aria-label="主导航"><RouterLink v-for="[path,icon,label] in tabs" :key="path" :to="path" @click="haptics.selection()" :class="{ selected: route.path.startsWith(path) }"><span aria-hidden="true">{{ icon }}</span>{{ label }}</RouterLink></nav></div></template>
