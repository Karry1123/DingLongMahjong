<script setup>
const props = defineProps({ enableEV: { type: Boolean, default: true }, busy: Boolean })
const emit = defineEmits(['close', 'start', 'update:enableEV'])
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="人机对战设置" @click.self="emit('close')">
    <section class="w-full max-w-md rounded-2xl border border-amber-400/45 bg-teal-950 p-5 text-left text-amber-50 shadow-2xl">
      <header class="flex items-center justify-between">
        <h2 class="text-xl font-bold">人机对战设置</h2>
        <button type="button" class="rounded-lg px-2 py-1 text-teal-200 hover:bg-teal-800" aria-label="关闭设置" @click="emit('close')">✕</button>
      </header>
      <label class="mt-5 flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-teal-600/50 bg-teal-900/50 p-4">
        <span><b class="block">EV 决策辅助</b><small class="mt-1 block leading-5 text-teal-200">开启后展示切牌与副露建议；关闭后进行纯实战盲打训练。</small></span>
        <input class="peer sr-only" type="checkbox" :checked="enableEV" @change="emit('update:enableEV', $event.target.checked)" />
        <span class="relative h-7 w-12 shrink-0 rounded-full bg-slate-600 transition peer-checked:bg-amber-400 peer-focus-visible:ring-2 peer-focus-visible:ring-amber-200 after:absolute after:left-1 after:top-1 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition after:content-[''] peer-checked:after:translate-x-5" aria-hidden="true" />
      </label>
      <p class="mt-3 text-xs text-teal-300">AI 风格：平衡型</p>
      <button type="button" class="mt-5 w-full rounded-xl bg-amber-400 px-4 py-3 font-bold text-emerald-950 hover:bg-amber-300 disabled:opacity-60" :disabled="busy" @click="emit('start')">{{ busy ? '正在发牌…' : '开始对战' }}</button>
    </section>
  </div>
</template>
