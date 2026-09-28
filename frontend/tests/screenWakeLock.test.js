import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createScreenWakeLock } from '../src/utils/screenWakeLock.js'
import { selfTurnCueKey } from '../src/utils/pvpTurnCue.js'

function browserFixture() {
  const document=new EventTarget(),browser=new EventTarget(),locks=[]
  document.visibilityState='visible';browser.document=document
  browser.navigator={wakeLock:{request:async(type)=>{
    assert.equal(type,'screen')
    const lock=new EventTarget();lock.released=false
    lock.release=async()=>{lock.released=true;lock.dispatchEvent(new Event('release'))}
    locks.push(lock);return lock
  }}}
  return {browser,locks}
}
const flush=()=>new Promise(resolve=>setImmediate(resolve))

test('wake lock acquires once, recovers on foreground/focus, and removes all listeners on disposal',async()=>{
  const {browser,locks}=browserFixture(),states=[]
  const wake=createScreenWakeLock(browser,state=>states.push(state));wake.start()
  await flush();assert.equal(locks.length,1);assert.equal(states.at(-1),'active')
  await Promise.all([wake.request(),wake.request()]);assert.equal(locks.length,1)
  browser.document.visibilityState='hidden';await locks[0].release()
  browser.document.dispatchEvent(new Event('visibilitychange'));await flush();assert.equal(locks.length,1)
  browser.document.visibilityState='visible';browser.document.dispatchEvent(new Event('visibilitychange'))
  browser.dispatchEvent(new Event('focus'));await flush();assert.equal(locks.length,2)
  await wake.stop();assert.equal(locks[1].released,true)
  browser.dispatchEvent(new Event('focus'));browser.document.dispatchEvent(new Event('pointerdown'));await flush()
  assert.equal(locks.length,2)
})

test('late acquisition after page disposal releases its sentinel; unsupported/denied APIs do not throw',async()=>{
  const {browser}=browserFixture();let resolve,released=false
  browser.navigator.wakeLock.request=()=>new Promise(r=>{resolve=r})
  const wake=createScreenWakeLock(browser),pending=wake.request()
  await wake.stop();resolve({release:async()=>{released=true}})
  assert.equal(await pending,false);assert.equal(released,true)
  assert.equal(await createScreenWakeLock({navigator:{},document:{visibilityState:'visible'}}).request(),false)
  browser.navigator.wakeLock.request=async()=>{throw new Error('Denied')}
  assert.equal(await createScreenWakeLock(browser).request(),false)
})

test('turn notification ignores heartbeats, opponent actions and suspended chi; a new turn gets a new cue',()=>{
  const game={game_id:'GM-1',phase:'discard',seat_wind:'E',actions:[{action_type:'discard'}],clocks:{E:{started_at:1000,paused:false}}}
  const first=selfTurnCueKey(game)
  game.revision=3;game.clocks.E.stage='bank';assert.equal(selfTurnCueKey(game),first)
  game.clocks.E.paused=true;assert.equal(selfTurnCueKey(game),'')
  game.clocks={S:{started_at:2000}};assert.equal(selfTurnCueKey(game),'')
  game.clocks.E={started_at:3000};assert.notEqual(selfTurnCueKey(game),first)
  game.phase='finished';assert.equal(selfTurnCueKey(game),'')
})
