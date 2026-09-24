<script setup>
import { computed } from 'vue'
import { relativeOpponents } from '../constants/tiles.js'

const props = defineProps({ roundCount: Number, scores: { type: Object, default: () => ({}) }, seatWind: { type: String, default: 'E' } })
const emit = defineEmits(['continue', 'exit'])
const rows = computed(() => [
  { role: '自家', seat: props.seatWind },
  ...relativeOpponents(props.seatWind).map(({ role, seat_wind }) => ({ role, seat: seat_wind })),
].map(({ role, seat }) => ({ role, score: Number(props.scores[seat] || 0) }))
  .sort((a, b) => b.score - a.score))
const signedScore = (score) => `${score > 0 ? '+' : ''}${score}`
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="本圈对局总结">
      <section class="w-full max-w-lg rounded-3xl border border-amber-300/50 bg-emerald-950 p-6 text-amber-50 shadow-2xl">
        <div class="text-xs font-bold uppercase tracking-[0.2em] text-amber-300">第 {{ roundCount }} 圈结束</div>
        <h2 class="mt-2 text-2xl font-bold">本圈对局总结</h2>
        <p class="mt-1 text-sm text-teal-100/70">四位玩家均已坐庄，累计积分继续保留。</p>
        <ol class="mt-5 space-y-2">
          <li v-for="(row, index) in rows" :key="row.seat" class="flex items-center justify-between rounded-xl border border-teal-800/70 bg-slate-900/40 px-4 py-3">
            <span><b class="mr-3 text-amber-300">{{ index + 1 }}</b>{{ row.role }}</span><strong class="tabular-nums" :class="row.score > 0 ? 'text-emerald-300' : row.score < 0 ? 'text-rose-300' : ''">{{ signedScore(row.score) }} 分</strong>
          </li>
        </ol>
        <div class="mt-6 flex flex-wrap justify-end gap-3">
          <button class="rounded-xl border border-slate-500 px-4 py-2 text-sm text-slate-100 hover:bg-slate-800" @click="emit('exit')">终止对局（返回主页）</button>
          <button class="rounded-xl bg-amber-400 px-4 py-2 text-sm font-bold text-emerald-950 hover:bg-amber-300" @click="emit('continue')">继续对战（开启新一圈）</button>
        </div>
      </section>
    </div>
  </Teleport>
</template>
