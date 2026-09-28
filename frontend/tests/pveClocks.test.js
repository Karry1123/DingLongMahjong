import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRenderer, h, nextTick, reactive, ref } from 'vue'
import { usePvEClocks } from '../src/composables/usePvEClocks.js'

const renderer = createRenderer({
  createElement: () => ({}), insert: () => {}, remove: () => {}, patchProp: () => {},
  setElementText: () => {}, createText: () => ({}), createComment: () => ({}),
  setText: () => {}, setComment: () => {}, parentNode: () => null, nextSibling: () => null,
})
function fixture(options={}) {
  const calls=[], s={
    gameMode:ref('PVE'),gameState:ref('PLAYING'),gameRoundId:ref('hand-1'),pveOpening:ref(false),loading:ref(false),
    roundState:reactive({seatWind:'E',handTiles:['1m','2m','3m','4m','5m','6m','7m','8m','9m','1p','2p','3p','E','N'],melds:[],discards:[],
      opponents:['S','W','N'].map(seat_wind=>({seat_wind,hand_tiles:Array(13).fill('2p'),melds:[],discards:[]}))}),
    currentTurnSeat:ref('E'),lastDiscardSeat:ref('N'),isResponseWindow:ref(false),lastStepResult:ref(null),
    currentHuSeat:ref(null),pendingHuQueue:ref([]),wallTiles:ref(Array(70).fill('9p')),latestDrawnBySeat:ref({E:'N'}),
    discardTile:async(tile,index)=>{calls.push(['discard',tile,index]);s.roundState.handTiles.splice(index,1)},
    passCall:async(tile,seat)=>{calls.push(['pass',tile,seat]);s.isResponseWindow.value=false},
    declareSelfRon:async(tile,provider)=>{calls.push(['hu',tile,provider]);s.gameState.value='GAME_OVER'},
  }
  let clock
  const app=renderer.createApp({setup(){clock=usePvEClocks(s,options);return()=>h('div')}})
  app.mount({})
  return {s,calls,clock,stop:()=>app.unmount()}
}
const tick=()=>new Promise(resolve=>setTimeout(resolve,130))

test('PvE only auto-discards after base and bank expire; next hand resets all reserves',async()=>{
  const original=Date.now;let now=1000;Date.now=()=>now
  const f=fixture()
  try{
    now=11000;await tick()
    assert.equal(f.clock.clocks.value.E.stage,'bank');assert.equal(f.calls.length,0)
    now=13500;await tick();assert.equal(f.clock.timeBanks.value.E,27500)
    now=41000;await tick()
    assert.deepEqual(f.calls,[['discard','N',13]])
    assert.equal(f.clock.timeBanks.value.E,0);assert.equal(f.clock.timeBanks.value.S,30000)
    f.s.gameRoundId.value='hand-2';await nextTick()
    assert.deepEqual(f.clock.timeBanks.value,{E:30000,S:30000,W:30000,N:30000})
  }finally{f.stop();Date.now=original}
})

test('PvE response with hu uses six seconds then reserve, and passed hu does not reopen a clock',async()=>{
  const original=Date.now;let now=1000;Date.now=()=>now
  const f=fixture()
  try{
    f.s.lastStepResult.value={_response_tile:'3p',_table_responses:[{seat:'E',types:['catch_win']},{seat:'S',types:['chi']}]}
    f.s.pendingHuQueue.value=['E'];f.s.currentHuSeat.value='E';f.s.isResponseWindow.value=true
    assert.equal(f.clock.clocks.value.E.kind,'win');assert.equal(f.clock.clocks.value.S.paused,true)
    now=7000;await tick();assert.equal(f.clock.clocks.value.E.stage,'bank');assert.equal(f.calls.length,0)
    now=37000;await tick();assert.deepEqual(f.calls,[['hu','3p','N']])
    f.s.gameState.value='PLAYING';f.s.pendingHuQueue.value=[];f.s.currentHuSeat.value=null
    assert.equal(f.clock.clocks.value.E,undefined);assert.equal(f.clock.clocks.value.S.paused,false)
    assert.equal(f.clock.timeBanks.value.S,30000)
  }finally{f.stop();Date.now=original}
})

test('PvE chi clock waits for pong and resumes without charging its bank',async()=>{
  const original=Date.now;let now=1000;Date.now=()=>now
  const f=fixture()
  try{
    f.s.lastStepResult.value={_response_tile:'3p',_table_responses:[{seat:'E',types:['chi']},{seat:'W',types:['pong']}]}
    f.s.isResponseWindow.value=true
    assert.equal(f.clock.clocks.value.E.paused,true)
    now=25000;await tick();assert.equal(f.clock.timeBanks.value.E,30000)
    f.s.lastStepResult.value._table_responses=f.s.lastStepResult.value._table_responses.filter(row=>row.seat==='E')
    assert.equal(f.clock.clocks.value.E.regular_deadline,31000)
    now=61000;await tick();assert.deepEqual(f.calls,[['pass','3p','E']])
  }finally{f.stop();Date.now=original}
})
