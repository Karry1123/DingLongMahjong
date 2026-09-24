import assert from 'node:assert/strict'
import { test, before, after } from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { useGameSession } from '../src/composables/useGameSession.js'
import { buildPendingHuQueue } from '../src/utils/callDetector.js'

let vite, Table
const originalFetch = globalThis.fetch
before(async () => {
  globalThis.fetch = async (url, init) => {
    const body = JSON.parse(init?.body || '{}')
    const data = String(url).endsWith('/settle')
      ? { winner_seat: body.winner_seat, win_type: 'ron', points: 20, net_by_seat: {}, transfers: [] }
      : { action_phase: 'WAIT', need_self_action: false }
    return { ok: true, json: async () => data }
  }
  vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  Table = (await vite.ssrLoadModule('/src/components/GodViewTable.vue')).default
})
after(async () => { globalThis.fetch = originalFetch; await vite?.close() })

async function fixture(selfSeat = 'N') {
  const s = useGameSession({ seatWind: selfSeat, dealerTile: '5s' })
  const hands = {
    N: ['1m','2m','3m','4m','5m','6m','1p','2p','3p','4p','5p','6p','C'],
    E: ['7m','8m','9m','7p','8p','9p','1s','2s','3s','4s','5s','6s','C'],
  }
  s.roundState.handTiles = hands[selfSeat]
  const other = selfSeat === 'N' ? 'E' : 'N'
  s.roundState.opponents.find((o) => o.seat_wind === other).hand_tiles = hands[other]
  s.roundState.opponents.find((o) => o.seat_wind === 'W').hand_tiles = ['C']
  s.tableLocked.value = true
  s.gameState.value = 'PLAYING'
  s.currentTurnSeat.value = 'W'
  await s.opponentDiscardTile('W', 'C')
  return s
}

async function header(s) {
  return renderToString(createSSRApp(Table, {
    seatWind: 'N', tableLocked: true, responseWindow: s.isResponseWindow.value,
    catchWinSeats: s.catchWinSeats.value, lastDiscardSeat: 'W', lastDiscardedTile: 'C',
  }))
}

test('west discard: only north can win; passing unlocks east and undo restores north', async () => {
  const s = await fixture()
  assert.deepEqual(s.pendingHuQueue.value, ['N', 'E'])
  assert.deepEqual(s.catchWinSeats.value, ['N'])
  let html = await header(s)
  assert.match(html, /北风 捉铳和牌/)
  assert.doesNotMatch(html, /东风 捉铳和牌/)
  await assert.rejects(s.declareOpponentWin({ seat: 'E', winType: 'catch_win', winTile: 'C', discarderSeat: 'W' }), /尚未轮到/)
  await assert.rejects(s.executeOpponentMeld({ seat: 'E', meld_type: 'pong', tiles: ['C','C','C'] }), /顺位胡牌/)
  await s.passCall('C')
  assert.equal(s.currentTurnSeat.value, 'W')
  assert.deepEqual(s.catchWinSeats.value, ['E'])
  assert.equal(s.lastStepResult.value.call_decision, null)
  html = await header(s)
  assert.match(html, /东风 捉铳和牌/)
  assert.doesNotMatch(html, /北风 捉铳和牌/)
  await assert.rejects(s.declareSelfRon('C', 'W'), /尚未轮到/)
  s.undoLastStep()
  assert.deepEqual(s.pendingHuQueue.value, ['N', 'E'])
})

test('east accepts after north passes: settlement clears all rights', async () => {
  const s = await fixture()
  await s.passAllCalls('C')
  await s.declareOpponentWin({ seat: 'E', winType: 'catch_win', winTile: 'C', discarderSeat: 'W' })
  assert.equal(s.gameState.value, 'GAME_OVER')
  assert.equal(s.selfWinSettlement.value.winner_seat, 'E')
  assert.deepEqual(s.catchWinSeats.value, [])
  assert.deepEqual(s.lastStepResult.value.pending_hu_queue, [])
})

test('all hu passes resume ordinary meld response without drawing early', async () => {
  const s = await fixture()
  s.lastStepResult.value._table_responses.push({ seat: 'S', types: ['pong'] })
  await s.passAllCalls('C')
  await s.passAllCalls('C')
  assert.deepEqual(s.catchWinSeats.value, [])
  assert.equal(s.isResponseWindow.value, true)
  assert.equal(s.currentTurnSeat.value, 'W')
  await s.passAllCalls('C')
  assert.equal(s.isResponseWindow.value, false)
  assert.equal(s.currentTurnSeat.value, 'N')
})

test('queue order wraps and removes duplicate/provider candidates', () => {
  assert.deepEqual(buildPendingHuQueue('W', ['E', 'W', 'N', 'S', 'N']), ['N','E','S'])
  assert.deepEqual(buildPendingHuQueue('N', ['W','E','S']), ['E','S','W'])
})

test('north accepts immediately and east cannot settle again', async () => {
  const s = await fixture()
  await s.declareSelfRon('C', 'W')
  assert.equal(s.selfWinSettlement.value.winner_seat, 'N')
  assert.equal(s.gameState.value, 'GAME_OVER')
  assert.deepEqual(s.pendingHuQueue.value, [])
  assert.equal(await s.declareOpponentWin({ seat: 'E', winType: 'catch_win', winTile: 'C', discarderSeat: 'W' }), false)
  assert.equal(s.selfWinSettlement.value.winner_seat, 'N')
})

test('all pass with no meld response advances only after the second pass', async () => {
  const s = await fixture()
  await s.passAllCalls('C')
  assert.equal(s.currentTurnSeat.value, 'W')
  await s.passAllCalls('C')
  assert.equal(s.currentTurnSeat.value, 'N')
  assert.equal(s.isResponseWindow.value, false)
  assert.deepEqual(s.catchWinSeats.value, [])
})

test('self is second: self action panel stays locked until first seat passes', async () => {
  const s = await fixture('E')
  assert.equal(s.lastStepResult.value.call_decision, null)
  await assert.rejects(s.passCall('C'), /尚未轮到/)
  await s.passAllCalls('C')
  assert.equal(s.currentHuSeat.value, 'E')
  assert.equal(s.lastStepResult.value.need_self_action, true)
  assert.deepEqual(s.lastStepResult.value.call_decision.available_actions.map((a) => a.action_type), ['hu', 'pass'])
})
