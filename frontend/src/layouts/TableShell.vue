<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useTableOrientation } from '../composables/useTableOrientation.js'
import { useOrientation } from '../composables/useOrientation.js'
const props = defineProps({ active: Boolean, leaving: Boolean, entry: Boolean, overlay: Boolean })
useTableOrientation(!props.overlay)
const { stageTransform } = useOrientation(props.overlay ? 1080 : 1280, props.overlay ? 560 : 720, props.overlay ? 16 : 0, props.overlay ? 1 : Infinity)
onMounted(() => { if (props.overlay) return; document.documentElement.classList.add('game-stage-scroll-lock'); document.body.classList.add('game-stage-scroll-lock') })
onUnmounted(() => { if (props.overlay) return; document.documentElement.classList.remove('game-stage-scroll-lock'); document.body.classList.remove('game-stage-scroll-lock') })
</script>
<template><slot v-if="overlay" :stage-transform="stageTransform" /><div v-else class="viewport-wrapper viewport-container game-viewport" :class="{ 'is-stage-active': active, 'is-sandbox-leaving': leaving }"><div class="game-stage app-shell min-h-screen bg-gradient-to-br from-ink-950 via-ink-900 to-ink-800 px-4 py-8 sm:px-6 sm:py-10" :style="{ transform: stageTransform }" :class="{ 'pve-stage-shell': active, 'is-stage-active': active, 'is-entry-stage': entry }"><slot /><span v-if="active || entry" class="stage-cloud stage-cloud--top ui-yunwen" aria-hidden="true" /><span v-if="active || entry" class="stage-cloud stage-cloud--bottom ui-yunwen" aria-hidden="true" /></div></div></template>
