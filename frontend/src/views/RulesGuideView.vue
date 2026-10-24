<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MahjongTile from '../components/MahjongTile.vue'
import { rulesGuide } from '../constants/rulesGuide.js'

const route = useRoute(), router = useRouter()
const heading = ref(null)
const directory = ref(null)
const pageIndex = computed(() => {
  const value = Number(route.query.page)
  return Number.isInteger(value) && value >= 1 && value <= rulesGuide.length ? value - 1 : 0
})
const page = computed(() => rulesGuide[pageIndex.value])
async function go(index) {
  if (index < 0 || index >= rulesGuide.length || index === pageIndex.value) return
  await router.push({ path: '/rules', query: { ...route.query, page: String(index + 1) } })
}
function onKey(event) {
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
    event.target instanceof Element && event.target.closest('input, textarea, select, button, a, summary, [contenteditable="true"]')) return
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault()
    void go(pageIndex.value + (event.key === 'ArrowRight' ? 1 : -1))
  }
}
watch(pageIndex, async () => {
  await nextTick()
  if (directory.value) directory.value.open = false
  heading.value?.focus({ preventScroll: true })
  heading.value?.scrollIntoView({ block: 'start' })
})
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <section class="rules-guide" aria-label="图文规则教学">
    <header class="guide-header">
      <RouterLink class="ui-btn ui-btn--ghost" to="/home">← 返回首页</RouterLink>
      <span class="ui-pill">新手图文课 · {{ rulesGuide.length }} 页</span>
      <h1>规则教学</h1>
      <p>认牌、行牌、算胡、结算。每次读一页，跟着牌例学。</p>
    </header>
    <div class="guide-layout">
      <details ref="directory" class="ui-card guide-directory">
        <summary>章节目录 · 第 {{ pageIndex + 1 }} 页 / {{ rulesGuide.length }} 页</summary>
        <nav aria-label="教学章节">
          <button v-for="(item, index) in rulesGuide" :key="item.title" type="button"
            class="ui-btn ui-btn--ghost" :aria-current="index === pageIndex ? 'page' : undefined"
            @click="go(index)"><span class="guide-number">{{ String(index + 1).padStart(2, '0') }}</span>{{ item.title }}</button>
        </nav>
      </details>
      <div class="guide-reader">
        <article class="ui-card guide-lesson" :data-guide-page="pageIndex + 1">
          <div class="guide-meta"><span class="ui-pill">{{ page.stage }}</span><span>对照规则 {{ page.source }}</span></div>
          <h2 ref="heading" tabindex="-1">{{ page.title }}</h2>
          <p class="guide-lead">{{ page.lead }}</p>
          <section class="guide-examples" aria-label="示例牌">
            <figure v-for="example in page.examples" :key="example.label">
              <figcaption>{{ example.label }}</figcaption>
              <div class="guide-tiles"><MahjongTile v-for="(tile, index) in example.tiles" :key="index" :code="tile.code" :face-down="tile.faceDown" :sideways="tile.sideways" /></div>
            </figure>
          </section>
          <section v-for="part in page.sections" :key="part.title" class="guide-section">
            <h3>{{ part.title }}</h3><p v-for="text in part.paragraphs" :key="text">{{ text }}</p>
          </section>
          <div v-if="page.table" class="guide-table-scroll" tabindex="0" role="region" aria-label="规则速查表，可横向滚动">
            <table><caption>{{ page.title }} · 速查</caption><thead><tr><th v-for="header in page.table.headers" :key="header" scope="col">{{ header }}</th></tr></thead>
              <tbody><tr v-for="(row, rowIndex) in page.table.rows" :key="rowIndex"><th scope="row">{{ row[0] }}</th><td v-for="(cell, cellIndex) in row.slice(1)" :key="cellIndex">{{ cell }}</td></tr></tbody>
            </table>
          </div>
          <aside class="guide-takeaway"><strong>记住这一点</strong><p>{{ page.takeaway }}</p></aside>
        </article>
        <nav class="guide-pagination" aria-label="教学翻页">
          <button type="button" class="ui-btn ui-btn--secondary" :disabled="pageIndex === 0" @click="go(pageIndex - 1)">← 上一页</button>
          <span class="guide-number" role="status" aria-live="polite">{{ pageIndex + 1 }} / {{ rulesGuide.length }}</span>
          <button v-if="pageIndex < rulesGuide.length - 1" type="button" class="ui-btn ui-btn--primary" @click="go(pageIndex + 1)">下一页 →</button>
          <RouterLink v-else class="ui-btn ui-btn--primary" to="/home">学完，回首页</RouterLink>
        </nav>
        <p class="guide-hint">可用键盘 ← → 翻页，或打开目录跳转。页码保存在网址中，刷新可接着读。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.rules-guide { font-family:var(--font-body); color:rgb(var(--fg)); line-height:1.8; min-width:0; }
.guide-header { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:var(--space-4); margin-bottom:var(--space-6); }
.guide-header h1 { width:100%; margin:0; font:600 var(--size-h1)/1.5 var(--font-display); }
.guide-header p { width:100%; margin:0; color:rgb(var(--fg-muted)); }
.guide-layout, .guide-reader { display:grid; gap:var(--space-4); min-width:0; }
.guide-directory { padding:var(--space-4); align-self:start; }
.guide-directory summary { min-height:44px; cursor:pointer; color:rgb(var(--accent)); }
.guide-directory nav { display:grid; gap:var(--space-2); margin-top:var(--space-3); }
.guide-directory button { justify-content:flex-start; text-align:left; gap:var(--space-3); white-space:normal; }
.guide-directory [aria-current="page"] { background:rgb(var(--bg-selected)); border-color:rgb(var(--accent)); color:rgb(var(--fg)); }
.guide-number { font-family:var(--font-num); font-variant-numeric:tabular-nums; white-space:nowrap; }
.guide-lesson { padding:var(--space-6); min-width:0; }
.guide-meta { display:flex; align-items:center; flex-wrap:wrap; gap:var(--space-3); font-size:var(--size-caption); color:rgb(var(--fg-muted)); }
.guide-lesson h2 { font:600 var(--size-h1)/1.5 var(--font-display); margin:var(--space-4) 0; scroll-margin-top:var(--space-6); }
.guide-lead { font-size:var(--size-body); color:rgb(var(--accent)); }
.guide-examples { display:grid; gap:var(--space-4); padding:var(--space-4); margin:var(--space-6) 0; background:rgb(var(--bg-sunken)); border:1px solid rgb(var(--line) / .16); border-radius:var(--r-md); }
.guide-examples figure { margin:0; min-width:0; }
.guide-examples figcaption { margin-bottom:var(--space-3); color:rgb(var(--fg-muted)); font-size:var(--size-caption); }
.guide-tiles { display:flex; flex-wrap:wrap; align-items:flex-end; gap:var(--space-2); padding-bottom:var(--space-2); }
.guide-section { margin:var(--space-6) 0; }
.guide-section h3 { font:600 var(--size-h2)/1.5 var(--font-display); margin-bottom:var(--space-3); }
.guide-section p { margin:var(--space-3) 0; overflow-wrap:anywhere; }
.guide-table-scroll { overflow-x:auto; margin:var(--space-6) 0; border:1px solid rgb(var(--line) / .16); border-radius:var(--r-sm); }
table { width:100%; border-collapse:collapse; font-size:var(--size-caption); }
caption { text-align:left; padding:var(--space-3); color:rgb(var(--accent)); }
th, td { padding:var(--space-3); text-align:left; border-bottom:1px solid rgb(var(--line) / .16); min-width:80px; }
thead { background:rgb(var(--bg-interactive)); }
.guide-takeaway { border-left:3px solid rgb(var(--accent)); padding:var(--space-4); background:rgb(var(--bg-sunken)); border-radius:var(--r-sm); }
.guide-takeaway strong { color:rgb(var(--accent)); }
.guide-takeaway p { margin:var(--space-2) 0 0; }
.guide-pagination { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:var(--space-2); }
.guide-pagination .ui-btn { min-width:100px; }
.rules-guide .ui-btn--primary { background:rgb(var(--btn-primary-bg)); color:rgb(var(--btn-primary-fg)); border-color:transparent; }
.rules-guide .ui-btn--primary:hover { background:rgb(var(--accent-hover)); }
.rules-guide .ui-btn--ghost { background:transparent; color:rgb(var(--accent)); border-color:rgb(var(--accent-line) / .45); }
.guide-hint { margin:0; color:rgb(var(--fg-muted)); font-size:var(--size-caption); }
.rules-guide :focus-visible { outline:2px solid rgb(var(--accent)); outline-offset:4px; }
@media (max-width:480px) { .guide-lesson { padding:var(--space-4); } .guide-tiles { gap:var(--space-1); } }
</style>
