<script setup>
import tokenSource from '../styles/tokens.css?raw'
import layerSource from '../styles/z-index.css?raw'
const colors = [...tokenSource.matchAll(/--([\w-]+):\s*([^;]+);/g)].filter(([, , value]) => /^\d+ \d+ \d+$/.test(value) || /^var\(--(?!font)[\w-]+\)$/.test(value)).map(([, name]) => name)
const values = [...(tokenSource + layerSource).matchAll(/--([\w-]+):\s*([^;]+);/g)].filter(([, name]) => !colors.includes(name)).map(([, name, value]) => ({ name, value }))
const alpha = { 'bg-overlay': .78, 'accent-soft': .14, 'accent-line': .45, line: .16, 'line-strong': .34, 'ok-soft': .16, 'danger-soft': .16, 'info-soft': .16, 'clock-track': .08 }
</script>

<template>
  <main class="ui-preview">
    <h1>顶龙麻将 · Design system / P1</h1>
    <p>Foundation preview · ?preview=design</p>
    <section><h2>Color tokens</h2><div class="ui-swatches">
      <figure v-for="name in colors" :key="name"><div :style="{ background: `rgb(var(--${name}) / ${alpha[name] ?? 1})` }" /><figcaption>{{ name }}<span v-if="alpha[name]"> · {{ alpha[name] * 100 }}%</span></figcaption></figure>
    </div></section>
    <section><h2>Type specimens</h2>
      <p class="ui-display">墨绿 · 温玉 · 鎏金</p><h1>标题一 · 顶龙麻将</h1><h2>标题二 · 入席开局</h2>
      <p>正文 Noto Sans SC · 与好友共聚一桌。ABCDEFGHIJKLMNOPQRSTUVWXYZ</p><p class="ui-num">0123456789 · 88:88</p>
      <p class="ui-caption">注释 Caption · 牌局进行中</p><p class="ui-eyebrow">顶龙麻将 · EYEBROW</p>
      <dl class="ui-token-values"><template v-for="item in values" :key="item.name"><dt>{{ item.name }}</dt><dd>{{ item.value }}</dd></template></dl>
    </section>
    <section><h2>Patterns</h2><p>Decorative samples (section 4 placement and opacity).</p>
      <div class="ui-huiwen" aria-hidden="true" />
      <div class="ui-pattern-grid"><div class="ui-huiwen-frame">回纹边框</div><div class="ui-yunwen">云纹</div><div class="ui-guijia">龟甲纹</div><div class="ui-corner">角线</div><span class="ui-seal">顶龙</span><div class="ui-ruyi" aria-label="如意纹" /></div>
    </section>
    <section><h2>Components</h2><div class="ui-examples">
      <button class="ui-btn ui-btn--primary">开始</button><button class="ui-btn ui-btn--secondary">邀请</button><button class="ui-btn ui-btn--ghost">返回</button><button class="ui-btn ui-btn--danger">解散</button>
      <button class="ui-btn ui-btn--action">碰</button><button class="ui-btn ui-btn--action is-hu">胡</button><button class="ui-btn ui-btn--action is-pass">过</button>
      <button class="ui-btn ui-btn--secondary" disabled>禁用</button>
      <span class="ui-pill">等待</span><span class="ui-pill ui-pill--ok">已准备</span><span class="ui-pill ui-pill--warn">待确认</span><span class="ui-pill ui-pill--danger">离线</span>
      <span class="ui-wind">东</span><span class="ui-wind is-dealer">东</span>
      <span class="ui-clock" style="--value: .7">12</span><span class="ui-clock is-urgent" style="--value: .15">3</span><span class="ui-clock is-bank" style="--value: .8">30</span>
    </div><div class="ui-card">普通卡片 · 无阴影</div><div class="ui-card ui-card--gilt ui-corner">强调卡片 · 金色角线</div>
    <div class="ui-toast" role="status">消息已更新</div>
    <div class="ui-modal-backdrop ui-preview-modal"><article class="ui-modal" role="dialog" aria-labelledby="preview-modal-title"><header class="ui-modal__head"><h3 id="preview-modal-title">弹窗预览</h3><div class="ui-huiwen" aria-hidden="true" /></header><div class="ui-modal__body">玉温金润，入席开局。</div><footer class="ui-modal__foot"><button class="ui-btn ui-btn--secondary">关闭</button></footer></article></div>
    </section>
  </main>
</template>

<style scoped>
.ui-preview { background: rgb(var(--bg)); color: rgb(var(--fg)); min-height: 100dvh; padding: 32px; font-size: var(--size-body); line-height: 1.6; }
section { margin-block: 32px; } h1 { font-size: var(--size-h1); } h2 { font-size: var(--size-h2); } .ui-display { font-size: var(--size-display); } .ui-caption { font-size: var(--size-caption); } .ui-eyebrow { font-size: var(--size-eyebrow); letter-spacing: var(--tracking-eyebrow); }
.ui-swatches { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; } figure { margin: 0; } figure > div { height: 64px; border: 1px solid rgb(var(--line) / .16); border-radius: var(--r-sm); } figcaption { font-size: var(--size-caption); overflow-wrap: anywhere; }
.ui-examples, .ui-pattern-grid { display: flex; align-items: center; flex-wrap: wrap; gap: 16px; margin-block: 16px; } .ui-pattern-grid > div { width: 160px; min-height: 96px; display: grid; place-items: center; } .ui-card, .ui-toast { margin-block: 16px; }
.ui-token-values { display: grid; grid-template-columns: minmax(140px, 1fr) 2fr; gap: 8px; overflow-wrap: anywhere; } .ui-token-values dd { margin: 0; }
.ui-preview-modal { position: relative; min-height: 280px; padding: 24px; }
</style>
