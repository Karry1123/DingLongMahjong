import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

test('chi previews, EV and recommendation match the physical combination regardless of tile order', async () => {
  const vite = await createServer({ server: { middlewareMode:true }, appType:'custom' })
  try {
    const Prompt = (await vite.ssrLoadModule('/src/components/ActionPrompt.vue')).default
    const regular = {action_type:'chi',tiles:['7p','8p','9p'],provider_seat:'N'}
    const white = {action_type:'chi',tiles:['P','7p','8p'],provider_seat:'N'}
    const props = {inline:true,dock:true,discardedTile:'8p',dealerTile:'6p',providerSeat:'N',callDecision:{
      available_actions:[regular,white,{...white,tiles:['8p','7p','P']},{action_type:'pass',tiles:[],provider_seat:'N'}],
      recommended_action:{...white,tiles:['8p','P','7p']},
      candidates:[{action:{...white,tiles:['P','7p']},net_ev:25},{action:regular,net_ev:10}],
    }}
    const html = await renderToString(createSSRApp(Prompt,props))
    const buttons = [...html.matchAll(/<button\b[^>]*data-action="chi"[\s\S]*?<\/button>/g)].map(row=>row[0])
    assert.equal(buttons.length,2)
    assert.match(buttons[0], /data-tile="P"/)
    assert.match(buttons[0], /白替六筒/)
    assert.match(buttons[0], /action-recommend-badge/)
    assert.doesNotMatch(buttons[1], /action-recommend-badge/)
    for (const button of buttons) {
      assert.equal((button.match(/action-preview-tile/g)||[]).length,3)
      assert.equal((button.match(/action-claimed-tile/g)||[]).length,1)
      assert.match(button, /供牌 八筒/)
    }
    const disabledEV = await renderToString(createSSRApp(Prompt,{...props,showRecommendation:false}))
    assert.doesNotMatch(disabledEV,/action-recommend-badge/)
    const fallback = await renderToString(createSSRApp(Prompt,{...props,callDecision:{available_actions:[regular,white]}}))
    assert.doesNotMatch(fallback,/action-recommend-badge/)
    const claims = await renderToString(createSSRApp(Prompt,{
      inline:true,dock:true,discardedTile:'P',dealerTile:'6p',providerSeat:'N',
      callDecision:{available_actions:[
        {action_type:'pong',tiles:['P','P','P'],provider_seat:'N'},
        {action_type:'ming_gang',tiles:['P','P','P','P'],provider_seat:'N'},
      ]},
    }))
    for (const [type,count] of [['pong',3],['ming_gang',4]]) {
      const button=claims.match(new RegExp(`<button\\b[^>]*data-action="${type}"[\\s\\S]*?<\\/button>`))[0]
      assert.equal((button.match(/action-preview-tile/g)||[]).length,count)
      assert.equal((button.match(/action-claimed-tile/g)||[]).length,1)
      assert.match(button,/白替六筒/)
    }
  } finally { await vite.close() }
})
