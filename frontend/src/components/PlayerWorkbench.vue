<script setup>
defineProps({ pve: Boolean, showRecommendation: { type: Boolean, default: true } })
</script>

<template>
  <section aria-label="自家操作工作台" :class="pve ? 'pve-workbench grid scroll-mt-4 grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(22rem,1fr)]' : 'flex flex-col gap-6'">
    <slot name="heading" />
    <div class="min-w-0" :class="pve ? 'pve-self-controls space-y-3' : 'space-y-4'" aria-label="自家手牌与副露">
      <slot />
    </div>
    <aside v-if="showRecommendation" class="min-w-0" :class="pve ? 'pve-ev-slot' : ''" aria-label="实时决策看板">
      <slot name="recommendation" />
    </aside>
  </section>
</template>
