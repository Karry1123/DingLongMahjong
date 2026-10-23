<script setup>
const props = defineProps({ enableEV: { type: Boolean, default: true }, busy: Boolean })
const emit = defineEmits(['close', 'start', 'update:enableEV'])
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="人机对战设置" @click.self="emit('close')">
    <section class="w-full max-w-md rounded-2xl border border-accent-line/45 bg-ink-800 p-5 text-left text-fog-100 shadow-2xl">
      <header class="relative flex items-center justify-between">
        <h2 class="text-xl font-bold">顶龙麻将 · 人机对战设置</h2>
        <span class="ui-huiwen pve-start-huiwen" aria-hidden="true" />
        <button type="button" class="rounded-lg px-2 py-1 text-fog-300 hover:bg-ink-700" aria-label="关闭设置" @click="emit('close')">✕</button>
      </header>
      <label class="mt-5 flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-line/50 bg-ink-800/50 p-4">
        <span><b class="block">EV 决策辅助</b><small class="mt-1 block leading-5 text-fog-300">开启后展示切牌与副露建议；关闭后进行纯实战盲打训练。</small></span>
        <input class="peer sr-only" type="checkbox" :checked="enableEV" @change="emit('update:enableEV', $event.target.checked)" />
        <span class="relative h-7 w-12 shrink-0 rounded-full bg-ink-700 transition peer-checked:bg-gilt-500 peer-focus-visible:ring-2 peer-focus-visible:ring-accent-line after:absolute after:left-1 after:top-1 after:h-5 after:w-5 after:rounded-full after:bg-paper after:transition after:content-[''] peer-checked:after:translate-x-5" aria-hidden="true" />
      </label>
      <p class="mt-3 text-xs text-fog-300">AI 风格：平衡型</p>
      <button type="button" class="mt-5 w-full rounded-xl bg-gilt-500 px-4 py-3 font-bold text-fg-on-accent hover:bg-gilt-400 disabled:opacity-60" :disabled="busy" @click="emit('start')">{{ busy ? '正在发牌…' : '开始对战' }}</button>
    </section>
  </div>
</template>

<style scoped>
.pve-start-huiwen { position:absolute; top:calc(100% + 4px); left:0; right:0; height:12px; pointer-events:none; }
</style>
