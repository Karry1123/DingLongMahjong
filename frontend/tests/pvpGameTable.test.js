import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSSRApp } from 'vue'
import { createServer } from 'vite'
import { renderToString } from 'vue/server-renderer'

test('PvP pauses chi controls, shows server clock, and gates the next hand by human confirmations', async () => {
  const vite = await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'})
  try {
    const Table = (await vite.ssrLoadModule('/src/components/PvpGameTable.vue')).default
    const players = [...'ESWN'].map((seat_wind,i)=>({seat_wind,nickname:`牌友${i}`,is_ai:i>=2,hand_count:13,melds:[],discards:[]}))
    const game = {game_id:'test',revision:1,seat_wind:'S',dealer_seat:'E',dealer_tile:'9s',current_turn:'E',wall_count:70,hand_tiles:['3m','4m'],players,phase:'response',actions:[{action_id:'chi',action_type:'chi',tiles:['3m','4m','5m']},{action_id:'pass',action_type:'pass',tiles:[]}],clocks:{S:{paused:true,remaining_ms:6000,deadline:null,kind:'response'}}}
    const render = () => renderToString(createSSRApp(Table,{room:{room_id:'123456'},game}))
    let html = await render()
    assert.match(html, /class="pve-game-main"/)
    assert.match(html, /class="[^"]*\bpve-table\b/)
    assert.match(html, /pve-self-hand pvp-own-hand/)
    assert.match(html, /牌友0 · 东风/)
    assert.doesNotMatch(html, /pve-ev-slot/)
    assert.match(html,/等待抢断 · <b[^>]*>6<\/b>秒/)
    assert.equal((html.match(/data-bank-wind=/g)||[]).length,4)
    assert.match(html,/<button[^>]*data-action="chi"[^>]*disabled/)
    assert.doesNotMatch(html,/<button[^>]*data-action="pass"[^>]*disabled/)
    assert.doesNotMatch(html,/荐|进张|铳率|向听/)
    game.clocks.S={paused:false,deadline:Date.now()+6000,kind:'response'}
    html=await render()
    assert.doesNotMatch(html,/<button[^>]*data-action="chi"[^>]*disabled/)
    game.clocks.W={paused:false,deadline:Date.now()+6000,kind:'response'}
    game.seat_wind='E';game.actions=[];game.response_wait={deadline:Date.now()+6000,remaining_ms:6000}
    html=await render()
    assert.match(html,/等待其余玩家决策中/)
    assert.match(html,/data-public-response-seconds/)
    assert.doesNotMatch(html,/data-clock-wind="[SWN]"/)
    assert.doesNotMatch(html,/thinking-indicator/)
    assert.match(html,/加时已隐藏/)
    game.seat_wind='S'
    game.phase='finished';game.actions=[];game.clocks={};game.result={kind:'draw'};game.next_ready=['E'];game.circle_complete=false
    html=await render()
    assert.match(html,/role="dialog"/);assert.match(html,/开始下一局/);assert.match(html,/\(1\/2\)/)
    game.next_ready.push('S');game.circle_complete=true
    html=await render()
    assert.match(html,/等待中/);assert.match(html,/\(2\/2\)/);assert.match(html,/<button[^>]*next-round-button[^>]*disabled/)
    game.next_ready=[]
    assert.match(await render(),/开始下一圈/)
  } finally { await vite.close() }
})
