<script setup>
defineProps({ busy: Boolean })
defineEmits(['pve', 'pvp', 'sandbox', 'rules'])
const modes = [
  { key: 'pve', number: '壹', title: '人机对战', tag: 'PvE', subtitle: '与智能 AI 磨砺牌技，支持实时切牌 EV 推荐与局势推演。', detail: '智能陪练 · 磨砺牌技' },
  { key: 'pvp', number: '贰', title: '玩家对战', tag: 'PvP', subtitle: '真人大战（2–4人），关闭 EV 辅助与提示，凭真实水平博弈。', detail: '以牌会友 · 真人较量' },
  { key: 'sandbox', number: '叁', title: '全景沙盘', tag: 'Sandbox', subtitle: '自由摆牌、推演任意残局与算番验证。', detail: '自由推演 · 探索牌理' },
  { key: 'rules', number: '肆', title: '规则教学', tag: 'Guide', subtitle: '跟着示例牌逐页学习，从认牌、财神到算胡与四家结算。', detail: '图文入门 · 随时回看' },
]
</script>

<template>
  <div class="mode-selection">
    <header class="home-brand">
      <span class="brand-seal ui-seal" aria-hidden="true">顶龙</span>
      <p class="home-eyebrow">一桌风雅 · 四方相逢</p>
      <h1>顶龙麻将</h1>
      <p class="home-intro">磨砺牌技，以牌会友，落子自有章法。</p>
    </header>
    <nav class="mode-cards" aria-label="选择对局模式">
      <button v-for="mode in modes" :key="mode.key" type="button" class="ui-card mode-card" :class="[`mode-${mode.key}`, { 'ui-card--gilt ui-corner': mode.key === 'pve' }]" :disabled="busy" :data-mode="mode.key" @click="$emit(mode.key)">
        <span class="mode-number" aria-hidden="true">{{ mode.number }}</span>
        <span class="mode-content">
          <span class="mode-heading"><strong>{{ mode.title }}</strong><span class="mode-tag">{{ mode.tag }}</span></span>
          <span class="mode-description">{{ mode.subtitle }}</span>
          <span class="mode-detail">{{ mode.detail }}</span>
        </span>
        <span class="mode-arrow" aria-hidden="true">↗</span>
      </button>
    </nav>
  </div>
</template>

<style scoped>
.mode-selection { width:100%; max-width:760px; margin:auto; font-family:var(--font-body); font-size:var(--size-body); line-height:1.7; }
.home-brand { text-align:center; margin-bottom:var(--space-8); }
.brand-seal { font-weight:600; }
.home-eyebrow { margin:var(--space-4) 0 var(--space-2); color:rgb(var(--gilt-400)); font-size:var(--size-eyebrow); letter-spacing:var(--tracking-eyebrow); }
.home-brand h1 { margin:0; font:600 var(--size-display)/1.4 var(--font-display); letter-spacing:var(--tracking-action); color:rgb(var(--fg)); }
.home-intro { margin-top:var(--space-2); color:rgb(var(--fg-muted)); font-size:var(--size-body); }
.mode-cards { display:flex; flex-direction:column; gap:var(--space-4); text-align:left; }
.mode-card { width:100%; min-height:var(--control-min-height); display:flex; align-items:center; gap:var(--space-6); padding:var(--space-6); border:1px solid rgb(var(--line) / .16); border-radius:var(--r-lg); background:rgb(var(--bg-raised)); color:rgb(var(--fg)); text-align:left; box-shadow:none; transition:background-color var(--motion-fast),border-color var(--motion-fast); }
.mode-card.ui-card--gilt { background:linear-gradient(135deg,rgb(var(--accent-soft) / .14),transparent),rgb(var(--bg-raised)); }
.mode-card:hover { border-color:rgb(var(--accent-line) / .45); background:rgb(var(--bg-interactive)); }
.mode-card:focus-visible { outline:2px solid rgb(var(--accent)); outline-offset:var(--space-1); }
.mode-card:disabled { opacity:.45; cursor:wait; }
.mode-number { flex-shrink:0; font:var(--size-h1) var(--font-display); color:rgb(var(--gilt-400)); }
.mode-content { flex:1; min-width:0; }
.mode-heading { display:flex; align-items:center; flex-wrap:wrap; gap:var(--space-3); }
.mode-heading strong { font:600 var(--size-h2)/1.4 var(--font-display); }
.mode-tag { border:1px solid rgb(var(--line) / .16); border-radius:var(--r-xs); padding:var(--space-1) var(--space-2); color:rgb(var(--fg-muted)); font-size:var(--size-caption); }
.mode-description { display:block; margin-top:var(--space-2); color:rgb(var(--fg-muted)); font-size:var(--size-body); line-height:1.7; }
.mode-detail { display:block; margin-top:var(--space-2); font-size:var(--size-caption); color:rgb(var(--gilt-400)); }
.mode-arrow { color:rgb(var(--gilt-400)); font-size:var(--size-h2); flex-shrink:0; }
@media(prefers-reduced-motion:reduce) { .mode-card { transition:none; } }
</style>
