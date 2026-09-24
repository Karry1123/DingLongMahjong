<script setup>
defineProps({ pve: Boolean })
</script>

<template>
  <section aria-label="自家操作工作台" :class="pve ? 'grid scroll-mt-4 grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(22rem,1fr)]' : 'flex flex-col gap-6'">
    <div class="min-w-0" :class="pve ? 'space-y-3' : 'space-y-4'" aria-label="自家手牌与副露">
      <slot />
    </div>
    <aside class="min-w-0" :class="pve ? 'lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto' : ''" aria-label="实时 EV 推荐">
      <slot name="recommendation" />
    </aside>
  </section>
</template>
