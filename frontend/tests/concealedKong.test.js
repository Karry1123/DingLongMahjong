import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSSRApp } from 'vue'
import { createServer } from 'vite'
import { renderToString } from 'vue/server-renderer'

test('PvE, Sandbox and both PvP perspectives render a fixed back/face/back/back kong', async () => {
  const vite = await createServer({server:{middlewareMode:true,hmr:false},appType:'custom'})
  try {
    const meld={meld_type:'an_gang',tiles:['1m','1m','1m','1m']}
    const players=[...'ESWN'].map(seat_wind=>({seat_wind,nickname:seat_wind,is_ai:seat_wind==='N',hand_count:10,melds:seat_wind==='E'?[meld]:[],discards:[]}))
    const cases=[
      ['MeldTiles',{meld}],
      ['MeldBar',{modelValue:[meld],readOnly:true}],
      ['GodViewTable',{seatWind:'E',selfMelds:[meld]}],
      ['PvEBoard',{seatWind:'S',opponents:players}],
      ...['E','S'].map(seat_wind=>['PvpGameTable',{room:{room_id:'123456'},game:{game_id:'kong',seat_wind,players,hand_tiles:[],actions:[],phase:'discard',dealer_seat:'E',dealer_tile:'9s',wall_count:81,current_turn:'E'}}]),
    ]
    for(const [name,props] of cases){
      const Component=(await vite.ssrLoadModule(`/src/components/${name}.vue`)).default
      const html=await renderToString(createSSRApp(Component,props))
      assert.equal((html.match(/data-face-down="true"/g)||[]).length,3,name)
      const tiles=[...html.matchAll(/<span class="mahjong-tile[^>]*data-tile="1m"[^>]*>/g)].map(m=>m[0])
      assert.equal(tiles.length,4,name)
      assert.deepEqual(tiles.map(t=>t.includes('data-face-down="true"')),[true,false,true,true],name)
    }
    const Component=(await vite.ssrLoadModule('/src/components/MeldTiles.vue')).default
    const ordinary=await renderToString(createSSRApp(Component,{meld:{meld_type:'ming_gang',tiles:['1m','1m','1m','1m']}}))
    assert.doesNotMatch(ordinary,/data-face-down/)
  } finally { await vite.close() }
})
