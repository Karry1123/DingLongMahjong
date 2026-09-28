import assert from 'node:assert/strict'
import { test } from 'node:test'
import { useGameSession } from '../src/composables/useGameSession.js'
import { northDiscardDeal } from './pveFixture.js'

test('each dealt PvE round waits for its opening before entering play, and cancellation cannot revive it', async () => {
  const original=globalThis.fetch
  globalThis.fetch=async url=>({ok:true,json:async()=>String(url).endsWith('/auto-deal')?northDiscardDeal():{action_phase:'WAIT'}})
  try {
    let release, openings=0
    const s=useGameSession({onPveOpening:()=>{openings++;return new Promise(resolve=>{release=resolve})}})
    const start=s.startPveGame()
    await new Promise(resolve=>setTimeout(resolve,0))
    assert.equal(s.pveOpening.value,true)
    assert.equal(s.gameState.value,'SETUP')
    assert.equal(s.tableLocked.value,false)
    assert.equal(s.wallTiles.value.length,82)
    release(true); await start
    assert.equal(s.pveOpening.value,false)
    assert.equal(s.gameState.value,'PLAYING')
    const next=s.startNextRound(null,false,{isDraw:true})
    await new Promise(resolve=>setTimeout(resolve,0))
    assert.equal(openings,2)
    assert.equal(s.pveOpening.value,true)
    assert.equal(s.gameState.value,'SETUP')
    s.gameMode.value='SANDBOX'
    release(false); assert.equal(await next,false)
    assert.equal(s.pveOpening.value,false)
    assert.equal(s.gameState.value,'SETUP')
  } finally {globalThis.fetch=original}
})
