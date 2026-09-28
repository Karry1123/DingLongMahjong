<script setup>
import { ref } from 'vue'
import MahjongTile from './MahjongTile.vue'
import { createSoundEngine, HONOR_VOICES } from '../utils/soundEngine.js'
import { onUnmounted } from 'vue'
const size = ref(72)
const sound = createSoundEngine()
onUnmounted(() => sound.stop(true))
async function listen(code) { await sound.unlock(); sound.playAction({ action:'DISCARD', tile:code, seat:'E', selfSeat:'E' }) }
</script>
<template>
  <main class="design-preview">
    <a href="?">← 返回麻将</a>
    <p class="eyebrow">牌面设计 · 已实装</p>
    <h1>竹影与圆纹</h1>
    <p>一条用鸟雀与舒展尾羽；二至九条用竹节。筒子用同心圆、中心花芯与传统点阵。与正式游戏共享同一套 SVG 牌面。</p>
    <label>预览牌宽 {{ size }}px <input v-model="size" type="range" min="28" max="100" /></label>
    <section v-for="suit in ['s','p']" :key="suit">
      <h2>{{ suit === 's' ? '条子 · 鸟雀与竹节' : '筒子 · 同心圆饼纹' }}</h2>
      <div class="design-row" :style="{ '--preview-width':size+'px' }">
        <figure v-for="n in 9" :key="n">
          <MahjongTile class="draft-tile" :code="`${n}${suit}`" :style="{ '--tw':size+'px' }" />
          <figcaption>{{ '一二三四五六七八九'[n-1] }}{{ suit === 's' ? '条' : '筒' }}</figcaption>
        </figure>
      </div>
    </section>
    <section><h2>万子字距 · 当前调整</h2><div class="design-row"><MahjongTile v-for="n in 9" :key="n" :code="`${n}m`" large /></div></section>
    <section><h2>字牌语音试听</h2><div class="design-row"><button v-for="(voice,code) in HONOR_VOICES" :key="code" @click="listen(code)">{{ voice.text }} ▶</button></div></section>
    <p class="reference">设计参考：<a href="https://mahjong-europe.org/portal/images/docs/Riichi-rules-2016-EN.pdf">EMA 牌种图例</a> · <a href="https://www.themahjongtileset.co.uk/tile-set-galleries/tile-set-diversity-2-0/">传统牌具藏品</a>。图案为原创 SVG，未复制藏品图片。</p>
  </main>
</template>
<style scoped>
.design-preview { min-height:100vh; padding:32px clamp(16px,5vw,80px); background:#103f35; color:#f5edd8; font-family:serif; }
h1 { font-size:40px; margin:8px 0 16px; } h2 { font-size:21px; margin:30px 0 16px; } p { max-width:850px; line-height:1.8; } a { color:#e5c986; text-decoration:underline; } .eyebrow { margin-top:28px; color:#cfb477; letter-spacing:3px; }
label { display:flex; align-items:center; gap:20px; margin:24px 0; } .design-row { display:flex; flex-wrap:wrap; gap:18px; align-items:start; } figure { margin:0; text-align:center; } .draft-tile { display:block;  } figcaption { font-size:13px; margin-top:12px; color:#d6c9ac; } button { padding:10px 16px; border:1px solid #bca572; border-radius:8px; } button:hover { background:#25594a; } .reference { margin-top:40px; font-size:13px; }
</style>
