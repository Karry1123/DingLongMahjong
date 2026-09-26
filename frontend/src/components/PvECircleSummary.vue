<script setup>
import { computed } from 'vue'
import { relativeOpponents } from '../constants/tiles.js'
import { useOrientation } from '../composables/useOrientation.js'

const props = defineProps({ roundCount: Number, scores: { type: Object, default: () => ({}) }, seatWind: { type: String, default: 'E' } })
const emit = defineEmits(['back', 'continue', 'exit'])
const { stageTransform } = useOrientation(1080, 560, 16, 1)
const rows = computed(() => [
  { role: '自家', seat: props.seatWind },
  ...relativeOpponents(props.seatWind).map(({ role, seat_wind }) => ({ role, seat: seat_wind })),
].map(({ role, seat }) => ({ role, score: Number(props.scores[seat] || 0) }))
  .sort((a, b) => b.score - a.score))
const signedScore = (score) => `${score > 0 ? '+' : ''}${score}`
</script>

<template>
  <Teleport to="body">
    <div class="circle-backdrop" role="dialog" aria-modal="true" aria-label="本圈对局总结">
      <section class="circle-panel" :style="{ transform: stageTransform }">
        <div class="circle-intro">
          <span class="circle-kicker">第 {{ roundCount }} 圈结束</span>
          <h2>本圈对局总结</h2>
          <p>四位玩家均已坐庄。本圈积分已计入累计战绩，继续对战将开启新一圈。</p>
          <div class="circle-medal" aria-hidden="true">圈</div>
        </div>
        <div class="circle-ranking">
          <h3>累计积分排名</h3>
          <ol>
            <li v-for="(row, index) in rows" :key="row.seat">
              <span><b>{{ index + 1 }}</b>{{ row.role }}</span>
              <strong class="tabular-nums" :class="row.score > 0 ? 'positive' : row.score < 0 ? 'negative' : ''">{{ signedScore(row.score) }} 分</strong>
            </li>
          </ol>
        </div>
        <div class="circle-actions">
          <button type="button" class="circle-back" @click="emit('back')">返回本局结算</button>
          <button type="button" class="circle-exit" @click="emit('exit')">终止对局（返回主页）</button>
          <button type="button" class="circle-continue" @click="emit('continue')">继续对战（开启新一圈）</button>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.circle-backdrop { position:fixed; inset:0; z-index:70; overflow:hidden; background:#020f0dd9; backdrop-filter:blur(8px); }
.circle-panel { box-sizing:border-box; position:absolute; top:50%; left:50%; display:grid; grid-template-columns:42% minmax(0,1fr); grid-template-rows:minmax(0,1fr) auto; column-gap:30px; width:1080px; height:560px; overflow:hidden; border:1px solid #fbbf2488; border-radius:20px; padding:30px; background:linear-gradient(145deg,#0b4035,#062b29 65%,#07201f); color:#fffbeb; box-shadow:0 25px 80px #000b; transform-origin:center center; }
.circle-intro { position:relative; min-width:0; padding:24px 18px 0 0; }
.circle-kicker { color:#fbbf24; font-size:15px; font-weight:800; letter-spacing:.14em; }
.circle-intro h2 { margin-top:14px; font-size:36px; font-weight:900; line-height:1.2; }
.circle-intro p { max-width:330px; margin-top:18px; color:#bde1d5; font-size:16px; line-height:1.7; }
.circle-medal { position:absolute; bottom:24px; left:50px; display:grid; place-items:center; width:126px; height:126px; border:2px solid #fbbf2477; border-radius:50%; background:radial-gradient(circle,#b7862c55,#57411c22 70%); color:#fcd34d; font-size:56px; font-weight:900; box-shadow:0 0 50px #fbbf241f; }
.circle-ranking { display:flex; min-width:0; flex-direction:column; }
.circle-ranking h3 { margin:0 0 13px; color:#e1f7ef; font-size:18px; font-weight:800; }
.circle-ranking ol { display:grid; grid-template-rows:repeat(4,minmax(0,1fr)); gap:9px; flex:1; min-height:0; }
.circle-ranking li { display:flex; align-items:center; justify-content:space-between; gap:12px; min-width:0; border:1px solid #357a65; border-radius:12px; padding:11px 18px; background:#082e2acc; font-size:18px; }
.circle-ranking li:first-child { border-color:#fbbf24aa; background:#69501855; }
.circle-ranking li span { display:flex; align-items:center; gap:16px; }
.circle-ranking li b { display:grid; flex:none; place-items:center; width:30px; height:30px; border-radius:50%; background:#fbbf2430; color:#fde68a; }
.circle-ranking li strong { white-space:nowrap; font-size:22px; }
.circle-ranking li strong.positive { color:#86efac; }
.circle-ranking li strong.negative { color:#fda4af; }
.circle-actions { display:flex; grid-column:1/-1; align-items:center; gap:12px; padding-top:20px; }
.circle-actions button { min-height:48px; border-radius:10px; padding:10px 18px; font-size:15px; font-weight:800; white-space:nowrap; }
.circle-back,.circle-exit { border:1px solid #7bd4b384; color:#d1fae5; }
.circle-exit { margin-left:auto; border-color:#94a3b877; color:#e2e8f0; }
.circle-continue { background:#fbbf24; color:#18362c; }
.circle-actions button:hover { filter:brightness(1.15); }
</style>
