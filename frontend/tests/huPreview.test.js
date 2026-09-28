import assert from 'node:assert/strict'
import { test } from 'node:test'
import { effectScope, ref, nextTick, createSSRApp } from 'vue'
import { createServer } from 'vite'
import { renderToString } from 'vue/server-renderer'
import { useHuPreview } from '../src/composables/useHuPreview.js'

test('a pending score cannot leak into the next win opportunity or survive dismissing it', async () => {
  const scope = effectScope(), payload = ref({ win_tile:'1m', is_zimo:true })
  const requests = []
  const result = scope.run(() => useHuPreview(payload, (body, options) => new Promise(resolve => requests.push({body,options,resolve}))))
  assert.equal(requests.length,1)
  payload.value = { win_tile:'2m', is_zimo:false, round_wind:'S' }
  await nextTick()
  assert.equal(requests[0].options.signal.aborted,true)
  requests[0].resolve({ final_hu:100 })
  await nextTick()
  assert.equal(result.value,null)
  requests[1].resolve({ final_hu:40, is_lazi:false })
  await nextTick()
  assert.equal(result.value.final_hu,40)
  payload.value = null
  await nextTick()
  assert.equal(result.value,null)
  scope.stop()
})

test('self draw and ron show one final result, with no breakdown or tooltip', async () => {
  const vite = await createServer({ server:{middlewareMode:true, hmr:false}, appType:'custom' })
  try {
    const Self = (await vite.ssrLoadModule('/src/components/SelfWinBanner.vue')).default
    const Prompt = (await vite.ssrLoadModule('/src/components/ActionPrompt.vue')).default
    for (const [info,label] of [[{final_hu:40},'40胡'],[{final_hu:100,is_lazi:true},'辣子']]) {
      const self = await renderToString(createSSRApp(Self,{info:{...info,base_hu:10,fan:4,details:{fans:{门清:1}}}}))
      const ron = await renderToString(createSSRApp(Prompt,{inline:true,dock:true,huInfo:info,callDecision:{available_actions:[{action_type:'hu',tiles:['8m']}]}}))
      for (const html of [self,ron]) {
        assert.match(html,new RegExp(`\\(${label}\\)`))
        assert.doesNotMatch(html,/Tooltip|tooltip|算胡明细|底胡|翻数|牌型胡|H_final/)
        const button = html.match(/<button\b[^>]*(?:self-win-button|data-action="hu")[\s\S]*?<\/button>/)?.[0]
        assert.ok(button)
        assert.doesNotMatch(button,/title=/)
      }
      assert.doesNotMatch(self,/role="dialog"/)
    }
  } finally { await vite.close() }
})
