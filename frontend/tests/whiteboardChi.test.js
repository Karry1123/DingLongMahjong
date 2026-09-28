import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { chiCombosFor, detectTableResponses, isLegalClaimMeld } from '../src/utils/callDetector.js'
import { useGameSession } from '../src/composables/useGameSession.js'

test('multiple pin chi choices include the fixed whiteboard substitute, never a wildcard', () => {
  assert.deepEqual(chiCombosFor(['P','7p','9p'], '8p', '6p'), [['P','7p','8p'],['7p','8p','9p']])
  assert.deepEqual(chiCombosFor(['P','9p'], '8p', '7p'), [['P','8p','9p']])
  assert.deepEqual(chiCombosFor(['P','6p'], '8p', '7p'), [['6p','P','8p']])
  for (const dealer of ['5p','P','E']) assert.deepEqual(chiCombosFor(['P','9p'], '8p', dealer), [])
  assert.deepEqual(chiCombosFor(['7p','9p'], '8p', '8p'), [])
})

test('whiteboard pong and kong require real matching tiles; jokers cannot fill them', () => {
  const options = (hand, disc, dealer) => detectTableResponses({
    providerSeat:'N', discardedTile:disc, dealerTile:dealer, selfSeat:'E',
    getSeat:seat=>({hand:seat==='E'?hand:['1m'],melds:[]}),
  }).options.find(row=>row.seat==='E')?.types || []
  assert.deepEqual(options(['P','P','P'], 'P', '6p'), ['pong','ming_gang'])
  assert.deepEqual(options(['P','P'], 'P', '6p'), ['pong'])
  assert.deepEqual(options(['9p','P'], '9p', '6p'), [])
  assert.deepEqual(options(['9p','9p','P'], '9p', '6p'), ['pong'])
  assert.deepEqual(options(['P','P','P'], 'P', 'P'), [])
  assert.equal(isLegalClaimMeld({meldType:'chi',tiles:['P','7p','8p'],claimedTile:'8p',dealerTile:'6p'}), true)
  for (const [meldType,tiles,claimedTile,dealerTile] of [
    ['chi',['P','6p','8p'],'8p','5p'],
    ['chi',['7p','8p','9p'],'8p','8p'],
    ['pong',['9p','P','9p'],'9p','6p'],
    ['ming_gang',['9p','9p','P','9p'],'9p','6p'],
  ]) assert.equal(isLegalClaimMeld({meldType,tiles,claimedTile,dealerTile}), false)
})

test('white discard and white in hand both preserve physical codes', () => {
  assert.deepEqual(chiCombosFor(['7s','9s'], 'P', '8s'), [['7s','P','9s']])
  assert.deepEqual(chiCombosFor(['6s','7s','9s'], 'P', '8s'), [['6s','7s','P'],['7s','P','9s']])
  assert.deepEqual(chiCombosFor(['7s','P'], '9s', '8s'), [['7s','P','9s']])
  assert.deepEqual(chiCombosFor(['7s','8s'], '9s', '8s'), [])
  for (const dealer of ['P','E']) assert.deepEqual(chiCombosFor(['7s','9s'], 'P', dealer), [])
  assert.deepEqual(chiCombosFor(['9s'], 'P', '8s'), [])
})

test('south discard opens west chi only and panel renders actual combination', async () => {
  const detection = detectTableResponses({ providerSeat: 'S', discardedTile: 'P', dealerTile: '8s',
    selfSeat: 'S', godView: true, getSeat: () => ({ hand: ['7s','9s'], melds: [] }) })
  assert.deepEqual(detection.options.filter((o) => o.types.includes('chi')).map((o) => o.seat), ['W'])
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const Panel = (await vite.ssrLoadModule('/src/components/OpponentPanel.vue')).default
    const html = await renderToString(createSSRApp(Panel, {
      seatWind: 'S', dealerTile: '8s', tableLocked: true, responseWindow: true,
      lastDiscardSeat: 'S', lastDiscardedTile: 'P',
      modelValue: [{ seat_wind: 'W', role: '下家', hand_tiles: ['7s','9s'], melds: [], discards: [] }],
    }))
    assert.match(html, /下家吃 七条·白\(替八条\)·九条/)
    assert.doesNotMatch(html, /下家吃 六条七条白/)
  } finally { await vite.close() }
})

test('7m substitute: self discard waits, blocks drawing, and south claims physical P', async () => {
  for (const [dealer, hand, expected] of [
    ['7m', ['P', '8m'], ['6m', 'P', '8m']],
    ['7m', ['5m', 'P'], ['5m', '6m', 'P']],
    ['8m', ['P', '9m'], ['7m', 'P', '9m']],
  ]) assert.deepEqual(chiCombosFor(hand, dealer === '8m' ? '7m' : '6m', dealer), [expected])

  const s = useGameSession({ seatWind: 'E', dealerTile: '7m' })
  s.roundState.handTiles = ['6m','1p','2p','4p','5p','7p','8p','1s','2s','4s','5s','7s','8s','E']
  for (const o of s.roundState.opponents) o.hand_tiles = ['C','F','N']
  const south = s.roundState.opponents.find((o) => o.seat_wind === 'S')
  south.hand_tiles = ['P','8m','1m','2m','4m','9m','3p','6p','9p','3s','6s','9s','S']
  s.tableLocked.value = true
  s.gameState.value = 'PLAYING'
  s.currentTurnSeat.value = 'E'
  s.currentPhase.value = 'MY_TURN_DISCARD'
  s.godViewWallMode.value = true
  s.wallTiles.value = ['N','W']
  await s.discardTile('6m', 0)
  assert.equal(s.currentPhase.value, 'WAIT_RESPONSE')
  assert.equal(s.isResponseWindow.value, true)
  assert.deepEqual(s.lastStepResult.value._table_responses, [
    { seat: 'S', types: ['chi'], chiCombos: [['6m','P','8m']] },
  ])
  await s.ensureGodViewDrawForSeat('S')
  assert.deepEqual(s.wallTiles.value, ['N','W'])
  assert.equal(s.currentTurnSeat.value, 'E')

  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const Table = (await vite.ssrLoadModule('/src/components/GodViewTable.vue')).default
    const Panel = (await vite.ssrLoadModule('/src/components/OpponentPanel.vue')).default
    const props = { seatWind: 'E', dealerTile: '7m', tableLocked: true, responseWindow: true,
      lastDiscardSeat: 'E', lastDiscardedTile: '6m' }
    const html = await renderToString(createSSRApp(Table, { ...props,
      tableResponses: s.lastStepResult.value._table_responses }))
    assert.match(html, /等待副露响应/)
    assert.match(html, /自家/)
    assert.match(html, /六万/)
    assert.match(html, /下家可吃/)
    const panel = await renderToString(createSSRApp(Panel, { ...props, modelValue: s.roundState.opponents }))
    assert.match(panel, /下家吃 六万·白\(替七万\)·八万/)
    await s.executeOpponentMeld({ seat: 'S', meld_type: 'chi', tiles: ['6m','P','8m'],
      provider_seat: 'E', claimed_tile: '6m' })
    const updated = s.roundState.opponents.find((o) => o.seat_wind === 'S')
    assert.deepEqual(updated.melds, [{ meld_type: 'chi', tiles: ['6m','P','8m'], claimed_tile: '6m', provider_seat: 'E' }])
    assert.equal(updated.hand_tiles.includes('P'), false)
    assert.equal(updated.hand_tiles.includes('8m'), false)
    assert.deepEqual(s.roundState.discards, [])
    assert.equal(s.currentTurnSeat.value, 'S')
    assert.deepEqual(s.wallTiles.value, ['N','W'])
    const meldHtml = await renderToString(createSSRApp(Table, { ...props, opponents: s.roundState.opponents }))
    assert.match(meldHtml, /白\(替七万\)/)
  } finally { await vite.close() }
})
