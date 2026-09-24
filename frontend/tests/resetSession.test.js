import assert from 'node:assert/strict'
import { test, after } from 'node:test'
import { useGameSession } from '../src/composables/useGameSession.js'
import { ALL_TILES } from '../src/constants/tiles.js'

const originalFetch = globalThis.fetch
after(() => { globalThis.fetch = originalFetch })
const response = (data) => ({ ok: true, json: async () => data })
let dealIndex = 0
function deal(dealerSeat = 'E') {
  const deck = ALL_TILES.flatMap((t) => Array(4).fill(t))
  const shift = ++dealIndex % deck.length
  deck.push(...deck.splice(0, shift))
  const dealer_tile = deck.pop()
  const hands = Object.fromEntries(['E','S','W','N'].map((s) => [s, deck.splice(0, s === dealerSeat ? 14 : 13)]))
  return { dealer_seat: dealerSeat, first_turn_seat: dealerSeat, dealer_tile, hands, wall_tiles: deck, wall_count: deck.length }
}
function installFetch(override = () => null) {
  globalThis.fetch = async (url, options) => override(url, options) || response(
    String(url).endsWith('/auto-deal') ? deal(JSON.parse(options?.body || '{}').dealer_seat || 'E') : { action_phase: 'WAIT', need_self_action: false })
}
function assertClean(s) {
  assert.equal(s.gameState.value, 'PLAYING')
  assert.equal(s.tableLocked.value, true)
  assert.equal(s.currentTurnSeat.value, 'E')
  assert.equal(s.lastDiscardSeat.value, null)
  assert.equal(s.selfWinSettlement.value, null)
  assert.equal(s.lastStepResult.value, null)
  assert.deepEqual(s.pendingHuQueue.value, [])
  assert.equal(s.isResponseWindow.value, false)
  assert.equal(s.wallTiles.value.length, 82)
  assert.equal(s.godViewWallMode.value, true)
  assert.equal(s.historyStack.value.length, 0)
  assert.equal(s.loading.value, false)
  assert.equal(s.resetInProgress.value, false)
  const players = [{ seat_wind: s.roundState.seatWind, hand_tiles: s.roundState.handTiles,
    melds: s.roundState.melds, discards: s.roundState.discards }, ...s.roundState.opponents]
  const all = [s.roundState.dealerTile, ...s.wallTiles.value]
  for (const player of players) {
    assert.equal(player.hand_tiles.length, player.seat_wind === 'E' ? 14 : 13)
    assert.deepEqual(player.melds, [])
    assert.deepEqual(player.discards, [])
    all.push(...player.hand_tiles)
  }
  assert.equal(all.length, 136)
  for (const t of ALL_TILES) assert.equal(all.filter((x) => x === t).length, 4)
  assert.ok(Object.values(s.latestDrawnBySeat.value).every((t) => t === null))
  assert.ok(Object.values(s.handLayoutPinned.value).every((p) => !p))
}

test('reset clears progressed/finished round, redeals and separates score lifecycle', async () => {
  installFetch()
  const s = useGameSession({ seatWind: 'S' })
  s.roundState.melds = [{ meld_type: 'pong', tiles: ['C','C','C'] }]
  s.roundState.discards = ['1m','2m','3m']
  s.roundState.opponents[0].melds = [{ meld_type: 'chi', tiles: ['1s','2s','3s'] }]
  s.roundState.opponents[0].discards = ['9m']
  s.currentTurnSeat.value = 'W'
  s.lastDiscardSeat.value = 'N'
  s.lastStepResult.value = { pending_hu_queue: ['E'], can_self_win: true }
  s.selfWinSettlement.value = { winner_seat: 'S' }
  s.gameState.value = 'GAME_OVER'
  s.currentPhase.value = 'WAIT_RESPONSE'
  s.wallTiles.value = ['1m']
  s.handLayoutPinned.value.E = true
  s.cumulativeScores.value.S = 100
  s.roundHistory.value = [{ roundIndex: 1 }]
  s.roundIndex.value = 1
  const signal = s.beginRecommendFetch()
  await s.resetGame()
  assert.ok(signal.aborted)
  assertClean(s)
  assert.equal(s.cumulativeScores.value.S, 100)
  assert.equal(s.roundHistory.value.length, 1)
  await s.resetGame({ clearHistory: true })
  assertClean(s)
  assert.deepEqual(s.cumulativeScores.value, { E: 0, S: 0, W: 0, N: 0 })
  assert.deepEqual(s.roundHistory.value, [])
  assert.equal(s.roundIndex.value, 0)
})

test('PVE rotates player identities, keeps the dealer East, and waits for the final-hand review before circle summary', async () => {
  installFetch()
  const s = useGameSession()
  await s.startPveGame()
  assert.equal(s.gameMode.value, 'PVE')
  assert.equal(s.dealerSeat.value, 'E')
  assert.equal(s.dealerPlayerId.value, 0)
  assert.equal(s.roundState.seatWind, 'E')
  assert.equal(s.roundState.handTiles.length, 14)

  await s.declareDraw()
  await s.startNextPveRound(null, false, { isDraw: true })
  assert.equal(s.dealerSeat.value, 'E')
  assert.equal(s.dealerPlayerId.value, 1)
  assert.equal(s.roundState.seatWind, 'N')
  assert.equal(s.roundState.opponents.find((o) => o.role === '下家').seat_wind, 'E')
  assert.equal(s.roundState.handTiles.length, 13)
  await s.declareDraw()
  await s.startNextPveRound(null, false, { isDraw: true })
  assert.equal(s.dealerPlayerId.value, 2)
  assert.equal(s.roundState.seatWind, 'W')
  await s.declareDraw()
  await s.startNextPveRound(null, false, { isDraw: true })
  assert.equal(s.dealerPlayerId.value, 3)
  assert.equal(s.roundState.seatWind, 'S')
  await s.declareDraw()
  assert.equal(s.pveRoundOverPending.value, true)
  assert.equal(s.showGameOverModal.value, true)
  assert.equal(s.showRoundSummaryModal.value, false)

  s.cumulativeScores.value.S = 30
  s.showGameOverModal.value = false
  s.showRoundSummaryModal.value = true
  await s.continuePveCircle()
  assert.equal(s.roundCount.value, 2)
  assert.equal(s.dealerSeat.value, 'E')
  assert.equal(s.dealerPlayerId.value, 0)
  assert.equal(s.cumulativeScores.value.E, 30)
  assert.equal(s.showGameOverModal.value, false)
  assert.equal(s.showRoundSummaryModal.value, false)
  assert.deepEqual(s.dealerRotationHistory.value, [0])
})

test('late step and settlement responses cannot overwrite reset even if transport ignores abort', async () => {
  for (const operation of ['step', 'settle']) {
    installFetch()
    const s = useGameSession({ seatWind: 'S' })
    await s.resetGame()
    let resolve, oldSignal
    installFetch((url, opts) => {
      if (String(url).endsWith('/' + operation)) {
        oldSignal = opts.signal
        return new Promise((r) => { resolve = r })
      }
    })
    const pending = operation === 'step'
      ? s.dispatchStep({ actor_seat: 'E', event_type: 'PASS' })
      : s.declareTableWin({ winnerSeat: 'E', winType: 'zimo', points: 128 })
    assert.ok(resolve)
    await s.resetGame()
    assert.ok(oldSignal.aborted)
    const snapshot = JSON.stringify(s.roundState)
    resolve(response({ action_phase: 'CALL', need_self_action: true,
      winner_seat: 'E', points: 128, net_by_seat: { E: 300, S: -100, W: -100, N: -100 } }))
    await pending
    assertClean(s)
    assert.equal(JSON.stringify(s.roundState), snapshot)
    assert.equal(s.cumulativeScores.value.E, 0)
  }
})

test('failed redeal leaves clean setup and supports retry', async () => {
  globalThis.fetch = async () => { throw new Error('offline') }
  const s = useGameSession()
  await assert.rejects(s.resetGame(), /offline/)
  assert.equal(s.gameState.value, 'SETUP')
  assert.equal(s.loading.value, false)
  assert.equal(s.selfWinSettlement.value, null)
  assert.equal(s.wallTiles.value.length, 0)
  installFetch()
  await s.resetGame()
  assertClean(s)
})
