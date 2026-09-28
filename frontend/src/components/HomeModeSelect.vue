<script setup>
defineProps({ busy: Boolean })
defineEmits(['pve', 'pvp', 'sandbox'])
const modes = [
  { key: 'pve', number: '壹', title: '人机对战', tag: 'PvE', subtitle: '与智能 AI 磨砺牌技，支持实时切牌 EV 推荐与局势推演。', detail: '智能陪练 · 磨砺牌技' },
  { key: 'pvp', number: '贰', title: '玩家对战', tag: 'PvP', subtitle: '真人大战（2–4人），关闭 EV 辅助与提示，凭真实水平博弈。', detail: '以牌会友 · 真人较量' },
  { key: 'sandbox', number: '叁', title: '全景沙盘', tag: 'Sandbox', subtitle: '自由摆牌、推演任意残局与算番验证。', detail: '自由推演 · 探索牌理' },
]
</script>

<template>
  <div class="mode-selection">
    <header class="home-brand">
      <span class="brand-seal" aria-hidden="true">顶龙</span>
      <p class="home-eyebrow">一桌风雅 · 四方相逢</p>
      <h1>顶龙麻将</h1>
      <p class="home-intro">磨砺牌技，以牌会友，落子自有章法。</p>
    </header>
    <nav class="mode-cards" aria-label="选择对局模式">
      <button v-for="mode in modes" :key="mode.key" type="button" class="mode-card" :class="`mode-${mode.key}`" :disabled="busy" :data-mode="mode.key" @click="$emit(mode.key)">
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
.mode-selection { width:100%; max-width:760px; margin:auto; }
.home-brand { text-align:center; margin-bottom:30px; }
.brand-seal { display:inline-flex; align-items:center; justify-content:center; width:42px; height:42px; border:1px solid #ce9c67; border-radius:8px; color:#f3d6a3; background:#8c3c2b66; font:600 15px/1.2 serif; box-shadow:inset 0 0 0 3px #092c27; }
.home-eyebrow { margin:16px 0 8px; color:#d5b980; font-size:11px; letter-spacing:.32em; }
.home-brand h1 { margin:0; font:600 44px/1.4 'Noto Serif SC','Songti SC',SimSun,serif; letter-spacing:.15em; color:#fff2d4; }
.home-intro { margin-top:9px; color:#b1c9bf; font-size:13px; }
.mode-cards { display:flex; flex-direction:column; gap:14px; text-align:left; }
.mode-card { width:100%; display:flex; align-items:center; gap:22px; padding:23px 28px; border:1px solid #a3b5a63b; border-radius:16px; background:linear-gradient(110deg,#123e35e6,#092d28e6); color:#f8ebd0; text-align:left; box-shadow:0 8px 30px #00191120; transition:background .2s,border-color .2s,transform .2s; }
.mode-pve { border-color:#d5b36b77; background:linear-gradient(110deg,#63512f40,#12392fe6); }
.mode-pvp { border-color:#63bb9a70; }
.mode-card:hover { border-color:#e1c88d; transform:translateY(-2px); background:#225445; }
.mode-card:focus-visible { outline:2px solid #f4d88e; outline-offset:4px; }
.mode-card:disabled { opacity:.55; cursor:wait; transform:none; }
.mode-number { flex-shrink:0; font:28px serif; color:#d7b16a; opacity:.85; }
.mode-content { flex:1; min-width:0; }
.mode-heading { display:flex; align-items:center; flex-wrap:wrap; gap:12px; }
.mode-heading strong { font:600 22px/1.4 'Songti SC',SimSun,serif; letter-spacing:.06em; }
.mode-tag { border:1px solid #c4caaa30; border-radius:5px; padding:2px 7px; color:#b8c6b3; font-size:10px; letter-spacing:.06em; }
.mode-description { display:block; margin-top:8px; color:#c3d3c9; font-size:13px; line-height:1.7; }
.mode-detail { display:block; margin-top:9px; font-size:10px; letter-spacing:.16em; color:#bea779; }
.mode-arrow { color:#d7bd86; font-size:24px; flex-shrink:0; }
@media(prefers-reduced-motion:reduce) { .mode-card { transition:none; } }
</style>
