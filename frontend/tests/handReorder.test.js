import assert from 'node:assert/strict'
import { test, afterEach } from 'node:test'
import { useGameSession } from '../src/composables/useGameSession.js'
import { reconcileHandOrder, sortAroundSpecialTiles } from '../src/utils/tileSorter.js'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

function fixture(autoSort) {
  const s=useGameSession()
  Object.assign(s.roundState,{seatWind:'E',dealerTile:'9p',handTiles:['9p','1m','2m','3m','2p','P','4p','5s','5s','7s','8s','N','N'],
    melds:[],discards:[],opponents:['S','W','N'].map(seat_wind=>({seat_wind,hand_tiles:[],melds:[],discards:[]}))})
  s.gameState.value='PLAYING';s.tableLocked.value=true;s.autoSortEnabled.value=autoSort
  s.currentTurnSeat.value='E';s.currentPhase.value='WAITING'
  globalThis.fetch=async (_url,options)=>{
    const body=JSON.parse(options.body), event=body.event
    return {ok:true,json:async()=>({action_phase:event?.event_type==='DISCARD'?'WAIT':'DISCARD',need_self_action:event?.event_type!=='DISCARD',
      updated_state:{hand_tiles:[...s.roundState.handTiles].reverse(),melds:s.roundState.melds}})}
  }
  return s
}

test('API order reconciliation handles duplicate copies, removals and appended draws',()=>{
  assert.deepEqual(reconcileHandOrder(['2p','9p','P','4p','4p'],['4p','P','9p','2p','C']),['2p','9p','P','4p','C'])
  assert.deepEqual(sortAroundSpecialTiles(['3m','1m','9p','4p','2p','P','8s','6s','C'],'9p','C'),['1m','3m','2p','9p','4p','6s','P','8s','C'])
})

for (const autoSort of [true,false]) test(`custom gods and ordinary order survive draw/discard/chi/pong/kong (auto=${autoSort})`,async()=>{
  const s=fixture(autoSort)
  s.moveSelfTileInHand(0,5)
  if(!autoSort)s.moveSelfTileInHand(7,1)
  const arranged=[...s.roundState.handTiles]
  await s.selfDrawTile('C')
  assert.deepEqual(s.roundState.handTiles,[...arranged,'C'])
  await s.discardTile('C',13)
  assert.deepEqual(s.roundState.handTiles,arranged)
  s.currentTurnSeat.value='E';s.currentPhase.value='WAITING'
  await s.selfDrawTile('F',{fromWall:true})
  assert.deepEqual(s.roundState.handTiles,[...arranged,'F'])
  await s.discardTile('F',13)
  assert.deepEqual(s.roundState.handTiles,arranged)
  const claim=async(meld_type,tiles,claimed_tile,provider_seat)=>{
    s.lastDiscardSeat.value=provider_seat;s.currentPhase.value='WAIT_RESPONSE'
    s.lastStepResult.value={_response_tile:claimed_tile,action_phase:'CALL',need_self_action:true}
    s.roundState.opponents.find(p=>p.seat_wind===provider_seat).discards.push(claimed_tile)
    await s.applySelfMeld({meld_type,tiles,claimed_tile,provider_seat})
  }
  await claim('chi',['1m','2m','3m'],'3m','N')
  let expected=arranged.filter(t=>!['1m','2m'].includes(t))
  assert.deepEqual(s.roundState.handTiles,expected)
  await s.discardTile('N',s.roundState.handTiles.lastIndexOf('N'))
  expected.splice(expected.lastIndexOf('N'),1)
  await claim('pong',['5s','5s','5s'],'5s','S')
  expected=expected.filter(t=>t!=='5s')
  assert.deepEqual(s.roundState.handTiles,expected)
  assert.equal(s.handLayoutPinned.value.E,true)
  // Explicit tidy may order ordinary segments but must never extract placed gods/proxies.
  const godIndex=expected.indexOf('9p'),proxyIndex=expected.indexOf('P')
  s.manualSortHand()
  assert.equal(s.roundState.handTiles.indexOf('9p'),godIndex)
  assert.equal(s.roundState.handTiles.indexOf('P'),proxyIndex)
  const k=fixture(autoSort)
  k.roundState.handTiles=['9p','2p','P','4p','1m','1m','1m','1m','5s','6s','7s','N','N','C']
  k.moveSelfTileInHand(0,3)
  const kongExpected=k.roundState.handTiles.filter(t=>t!=='1m')
  await k.applySelfKong({meld_type:'an_gang',tile:'1m'})
  assert.deepEqual(k.roundState.handTiles,kongExpected)
  const exposed=fixture(autoSort)
  exposed.roundState.handTiles=['9p','2p','P','4p','1m','1m','1m','5s','6s','7s','8s','N','N']
  exposed.moveSelfTileInHand(0,3)
  const exposedExpected=exposed.roundState.handTiles.filter(t=>t!=='1m')
  exposed.lastDiscardSeat.value='S';exposed.currentPhase.value='WAIT_RESPONSE'
  exposed.lastStepResult.value={_response_tile:'1m',action_phase:'CALL',need_self_action:true}
  exposed.roundState.opponents[0].discards=['1m']
  await exposed.applySelfMeld({meld_type:'ming_gang',tiles:Array(4).fill('1m'),claimed_tile:'1m',provider_seat:'S'})
  assert.deepEqual(exposed.roundState.handTiles,exposedExpected)
  exposed.lastStepResult.value=null
  await exposed.selfDrawTile('F')
  assert.deepEqual(exposed.roundState.handTiles,[...exposedExpected,'F'])
})

test('auto sort off preserves every tile even before any manual drag; fast wall draw keeps layout pinned',async()=>{
  const s=fixture(false),before=[...s.roundState.handTiles]
  s.sortSeatClosedHand('E',{keepDrawn:false})
  assert.deepEqual(s.roundState.handTiles,before)
  await s.selfDrawTile('C')
  assert.deepEqual(s.roundState.handTiles,[...before,'C'])
  await s.discardTile('C',13)
  assert.deepEqual(s.roundState.handTiles,before)
  s.moveSelfTileInHand(0,5)
  const pinned=[...s.roundState.handTiles]
  s.wallTiles.value=['F'];s.godViewWallMode.value=true
  s.applyGodViewSelfDrawFast()
  assert.deepEqual(s.roundState.handTiles,[...pinned,'F'])
  assert.equal(s.handLayoutPinned.value.E,true)
})

test('PvE moves any tile by insertion and preserves the chosen order', () => {
  const session = useGameSession()
  session.roundState.seatWind = 'E'
  session.roundState.dealerTile = '9p'
  session.roundState.handTiles = ['9p', '1m', '2m', '3m', '4m', '5m']

  session.moveSelfTileInHand(0, 4)
  assert.deepEqual(session.roundState.handTiles, ['1m', '2m', '3m', '9p', '4m', '5m'])
  assert.equal(session.handLayoutPinned.value.E, true)
  session.applyHandSort()
  assert.deepEqual(session.roundState.handTiles, ['1m', '2m', '3m', '9p', '4m', '5m'])

  session.autoSortEnabled.value=false

  session.moveSelfTileInHand(4, 1)
  assert.deepEqual(session.roundState.handTiles, ['1m', '4m', '2m', '3m', '9p', '5m'])
  session.latestDrawnTile.value = '5m'
  session.latestDrawnBySeat.value.E = '5m'
  session.moveSelfTileInHand(5, 2)
  assert.deepEqual(session.roundState.handTiles, ['1m', '4m', '5m', '2m', '3m', '9p'])
  assert.equal(session.latestDrawnTile.value, '5m')
  session.applyHandSort({ keepDrawn: true })
  assert.deepEqual(session.roundState.handTiles, ['1m', '4m', '5m', '2m', '3m', '9p'])
})

test('auto sort restricts both reorder entry points to gods and proxies, then sorts ordinary tiles around anchors',()=>{
  const s=useGameSession()
  s.roundState.dealerTile='9p'
  s.roundState.handTiles=['9p','1m','2p','4p','7s','N','P']
  s.moveSelfTileInHand(0,3)
  assert.deepEqual(s.roundState.handTiles,['1m','2p','9p','4p','7s','N','P'])
  const before=[...s.roundState.handTiles]
  s.moveSelfTileInHand(1,5)
  assert.deepEqual(s.roundState.handTiles,before)
  assert.throws(()=>s.moveJokerInHand('E',1,5))
  // A previously drawn ordinary tile joins the main hand and must be sorted normally.
  s.roundState.handTiles.push('3p')
  s.applyHandSort()
  assert.deepEqual(s.roundState.handTiles,['1m','2p','3p','9p','4p','7s','N','P'])
  s.moveSelfTileInHand(7,5)
  s.roundState.handTiles.splice(s.roundState.handTiles.indexOf('2p'),1)
  s.applyHandSort()
  assert.deepEqual(s.roundState.handTiles,['1m','3p','9p','4p','P','7s','N'])
  s.autoSortEnabled.value=false
  s.moveSelfTileInHand(5,0)
  assert.equal(s.roundState.handTiles[0],'7s')
  s.autoSortEnabled.value=true
  const hand=s.roundState.handTiles
  assert.deepEqual(hand.filter(t=>!['9p','P'].includes(t)),['1m','3p','4p','7s','N'])
  assert.ok(hand.indexOf('9p')>hand.indexOf('3p'))
  assert.ok(hand.indexOf('9p')<hand.indexOf('4p'))
})
