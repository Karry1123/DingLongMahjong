import { test } from 'node:test'
import assert from 'node:assert/strict'
import { gameStatusHint, createGameStatusTracker } from '../src/utils/gameStatusHint.js'
const chi=tiles=>({meld_type:'chi',tiles})
const pong=tile=>({meld_type:'pong',tiles:Array(3).fill(tile)})
const input=(wall=82)=>({wallCount:wall,roundId:'round-a',seatWind:'E',dealerTile:'9p',opponents:[{seat_wind:'N',melds:[],discards:[]}]})

test('all depth boundaries use the requested base copy; three total melds advance opening to middle', () => {
  for (const [wall,text] of [[82,'牌局平稳'],[66,'牌局平稳'],[65,'牌局步入中盘'],[41,'牌局步入中盘'],[40,'局势进入白热化'],[20,'局势进入白热化'],[19,'海底绝张'],[0,'海底绝张']])
    assert.ok(gameStatusHint({wallCount:wall}).text.startsWith(text))
  assert.match(gameStatusHint({wallCount:70,selfMelds:[{}],opponents:[{melds:[{},{}]}]}).text,/步入中盘/)
})

test('new high-value exposures name the relative opponent, dragons, own wind and terminal triplets', () => {
  for (const [tile,label] of [['C','中'],['F','发'],['P','白'],['N','北'],['1m','一万'],['9s','九条']]) {
    const tracker=createGameStatusTracker(), s=input()
    tracker.update(s);s.opponents[0].melds=[pong(tile)]
    const hint=tracker.update(s)
    assert.match(hint.text,/上家大番/);assert.ok(hint.text.includes(label));assert.equal(hint.level,'high')
  }
  const tracker=createGameStatusTracker(),s=input()
  tracker.update(s);s.opponents[0].melds=[pong('E')]
  assert.match(tracker.update(s).text,/牌局平稳/) // No invented round-wind fan.
})

test('warning lasts two rounds of draws, then stays expired despite duplicate model responses', () => {
  const tracker=createGameStatusTracker(),s=input(60)
  tracker.update(s);s.opponents[0].melds=[pong('C')]
  assert.match(tracker.update(s).text,/大番/)
  s.wallCount=53;assert.match(tracker.update(s).text,/大番/)
  s.wallCount=52;assert.match(tracker.update(s).text,/步入中盘/)
  for(let i=0;i<10;i++)assert.match(tracker.update(s).text,/步入中盘/)
  s.wallCount=39;assert.match(tracker.update(s).text,/白热化/)
  s.wallCount=19;assert.match(tracker.update(s).text,/海底绝张/)
})

test('an upgrade to kong is a new event and renews the bounded warning', () => {
  const tracker=createGameStatusTracker(),s=input(60)
  tracker.update(s);s.opponents[0].melds=[pong('C')];tracker.update(s)
  s.wallCount=52;tracker.update(s)
  s.opponents[0].melds=[{meld_type:'ming_gang',tiles:Array(4).fill('C')}]
  assert.match(tracker.update(s).text,/大番/)
  s.wallCount=44;assert.match(tracker.update(s).text,/步入中盘/)
})

test('two/three exposed sets and a genuine probability jump trigger distinct temporary alerts', () => {
  const tracker=createGameStatusTracker(),s=input(57)
  tracker.update(s);s.opponents[0].melds=[chi(['1s','2s','3s']),chi(['4s','5s','6s'])]
  assert.match(tracker.update(s).text,/上家2副露.*谨防听牌/)
  s.wallCount=49;assert.match(tracker.update(s).text,/步入中盘/)
  s.opponents[0].melds.push(chi(['7p','8p','9p']))
  assert.match(tracker.update(s).text,/3副露.*谨防听牌/)
  const model=createGameStatusTracker(),m=input(57)
  m.threats=[{seat_wind:'N',probability:.2}];model.update(m)
  m.threats[0].probability=.3;assert.match(model.update(m).text,/步入中盘/)
  m.threats[0].probability=.55;assert.match(model.update(m).text,/上家听牌骤增/)
  m.wallCount=49;assert.match(model.update(m).text,/步入中盘/)
})
test('the first model sample is not mislabeled as a jump from an imaginary zero baseline', () => {
  const tracker=createGameStatusTracker(),s=input(35)
  tracker.update(s);s.threats=[{seat_wind:'N',probability:.55}]
  assert.match(tracker.update(s).text,/白热化/)
  s.threats[0].probability=.85
  assert.match(tracker.update(s).text,/听牌骤增/)
})

test('fresh middle discards trigger once and publicly repeated safe tiles do not', () => {
  const tracker=createGameStatusTracker(),s=input(57)
  tracker.update(s);s.opponents[0].discards=['4m','5p']
  assert.match(tracker.update(s).text,/上家连切生张.*谨防放铳/)
  s.wallCount=49;assert.match(tracker.update(s).text,/步入中盘/)
  const safe=createGameStatusTracker(),m=input(57)
  safe.update(m);m.opponents[0].discards=['4m','5p'];m.selfDiscards=['4m']
  assert.match(safe.update(m).text,/步入中盘/)
})

test('danger takes priority over base; high danger takes priority over a smaller new event', () => {
  const tracker=createGameStatusTracker(),s=input(18)
  s.opponents[0].is_dealer=true
  tracker.update(s);s.opponents[0].melds=[pong('C')]
  assert.match(tracker.update(s).text,/上家庄家大番/)
  s.opponents.push({seat_wind:'S',melds:[chi(['1p','2p','3p']),chi(['4p','5p','6p'])]})
  assert.match(tracker.update(s).text,/上家庄家/)
})

test('meld reordering does not renew; a new round and exit clear every previous warning', () => {
  const tracker=createGameStatusTracker(),s=input(60)
  tracker.update(s);s.opponents[0].melds=[pong('C'),chi(['1s','2s','3s'])];tracker.update(s)
  s.wallCount=56;s.opponents[0].melds.reverse();tracker.update(s)
  s.wallCount=52;assert.match(tracker.update(s).text,/步入中盘/)
  s.opponents[0].melds.push(pong('F'));assert.match(tracker.update(s).text,/3副露/)
  s.roundId='round-b';s.wallCount=82;s.opponents[0].melds=[]
  assert.match(tracker.update(s).text,/牌局平稳/)
  s.opponents[0].melds=[pong('C')];tracker.update(s)
  tracker.update({...s,playing:false});s.opponents[0].melds=[]
  assert.match(tracker.update(s).text,/牌局平稳/)
})


test('all base and opponent alerts fit within 16 characters including punctuation', () => {
  const hints=[82,57,35,18].map(wallCount=>gameStatusHint({wallCount}).text)
  for (const seat of ['N','W','S']) for (const is_dealer of [false,true]) {
    for (const tile of ['C','F','P',seat,'1m','9s']) {
      const tracker=createGameStatusTracker(),s=input(57)
      s.opponents[0].seat_wind=seat;s.opponents[0].is_dealer=is_dealer
      tracker.update(s);s.opponents[0].melds=[pong(tile)]
      hints.push(tracker.update(s).text)
    }
    for (const event of ['meld','fresh','model']) {
      const tracker=createGameStatusTracker(),s=input(57)
      s.opponents[0].seat_wind=seat;s.opponents[0].is_dealer=is_dealer
      s.threats=[{seat_wind:seat,probability:.2}];tracker.update(s)
      if(event==='meld')s.opponents[0].melds=Array(3).fill(chi(['2s','3s','4s']))
      if(event==='fresh')s.opponents[0].discards=['4m','5p']
      if(event==='model')s.threats[0].probability=.7
      hints.push(tracker.update(s).text)
    }
  }
  for(const text of hints){assert.ok([...text].length<=16,text);assert.doesNotMatch(text,/\r|\n/)}
})
