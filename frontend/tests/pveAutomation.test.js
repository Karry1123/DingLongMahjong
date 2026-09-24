import assert from 'node:assert/strict'
import { test, afterEach } from 'node:test'
import { nextTick, watch } from 'vue'
import { useGameSession } from '../src/composables/useGameSession.js'
import { usePvEAutomation } from '../src/composables/usePvEAutomation.js'
import { northDiscardDeal } from './pveFixture.js'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })
const waitFor = async (predicate, timeout = 2000) => {
  const until = Date.now() + timeout
  while (!predicate()) {
    assert.ok(Date.now() < until, 'AI did not advance before deadline')
    await new Promise((r) => setTimeout(r, 5))
  }
}
async function fixture(onAction) {
  globalThis.fetch = async (url) => ({ ok: true, json: async () => String(url).endsWith('/auto-deal')
    ? northDiscardDeal() : { action_phase: 'WAIT', need_self_action: false } })
  const s = useGameSession({ onAction })
  await s.startPveGame()
  return s
}

test('a fast AI recommendation waits for the full three-second thinking timer', async () => {
  const actions = []
  const s = await fixture((event) => actions.push(event))
  let observedLockedTurn = false
  const recommendations = []
  const durations = []
  let finishThinking
  const unwatch = watch(s.currentTurnSeat, () => { observedLockedTurn ||= s.loading.value }, { flush: 'sync' })
  const driver = usePvEAutomation(s, { sleep: (ms) => {
    durations.push(ms)
    return new Promise((resolve) => { finishThinking = resolve })
  }, recommend: async (payload) => {
    recommendations.push(payload.seat_wind)
    assert.equal(payload.hand_tiles.length + 3 * payload.melds.length, 14)
    assert.ok(payload.opponents.every((o) => !('hand_tiles' in o)))
    return { best_tile: payload.hand_tiles[0] }
  } })
  try {
    await s.discardTile('N', s.roundState.handTiles.indexOf('N'))
    assert.deepEqual(actions[0], { action: 'DISCARD', seat: 'E', tile: 'N', selfSeat: 'E' })
    await waitFor(() => recommendations.includes('S') && finishThinking)
    assert.ok(observedLockedTurn, 'regression must exercise a turn update under loading')
    assert.equal(durations[0], 3000)
    assert.equal(driver.thinkingSeat.value, 'S')
    assert.equal(s.roundState.opponents.find((o) => o.seat_wind === 'S').discards.length, 0)
    finishThinking()
    await waitFor(() => s.roundState.opponents.find((o) => o.seat_wind === 'S').discards.length > 0)
    assert.equal(actions.find((event) => event.seat === 'S' && event.action === 'DISCARD')?.selfSeat, 'E')
    assert.equal(recommendations.filter((seat) => seat === 'S').length, 1)
  } finally { unwatch(); driver.stop() }
})

test('a slow AI recommendation executes as soon as the result arrives after the timer', async () => {
  const s = await fixture()
  const durations = []
  let resolveDecision
  const driver = usePvEAutomation(s, { sleep: async (ms) => { durations.push(ms) }, recommend: () =>
    new Promise((resolve) => { resolveDecision = resolve }) })
  try {
    await s.discardTile('N', s.roundState.handTiles.indexOf('N'))
    await waitFor(() => resolveDecision)
    assert.equal(durations[0], 3000)
    assert.equal(s.roundState.opponents.find((o) => o.seat_wind === 'S').discards.length, 0)
    const tile = s.roundState.opponents.find((o) => o.seat_wind === 'S').hand_tiles[0]
    resolveDecision({ best_tile: tile })
    await waitFor(() => s.roundState.opponents.find((o) => o.seat_wind === 'S').discards.includes(tile))
  } finally { driver.stop() }
})

test('AI upgrades a one-pin pong, draws replacement, and never discards the fourth tile', async () => {
  const actions = []
  const s = await fixture((event) => actions.push(event))
  const south = s.roundState.opponents.find((o) => o.seat_wind === 'S')
  south.melds = [{ meld_type: 'pong', tiles: ['1p', '1p', '1p'] }]
  south.hand_tiles = ['1p', '3m', '9s', '2m', '5m', '8s', '2s', '5p', '7p', '4s', '9m']
  s.currentTurnSeat.value = 'S'
  s.currentPhase.value = 'WAITING'
  const wallBefore = s.wallTiles.value.length
  const replacement = s.wallTiles.value.at(-1)
  let requests = 0
  const driver = usePvEAutomation(s, { delayMs: () => 0, recommend: async () => {
    requests++
    if (requests === 1) return { best_tile: '1p', best_action: { action_type: 'bu_gang', tile: '1p' } }
    return new Promise(() => {})
  } })
  try {
    await waitFor(() => s.roundState.opponents.find((o) => o.seat_wind === 'S').melds[0].meld_type === 'ming_gang')
    await waitFor(() => s.roundState.opponents.find((o) => o.seat_wind === 'S').hand_tiles.includes(replacement))
    const upgraded = s.roundState.opponents.find((o) => o.seat_wind === 'S')
    assert.equal(upgraded.melds.length, 1)
    assert.deepEqual(upgraded.melds[0].tiles, ['1p', '1p', '1p', '1p'])
    assert.equal(s.wallTiles.value.length, wallBefore - 1)
    assert.equal(upgraded.discards.includes('1p'), false)
    assert.ok(actions.some((event) => event.action === 'GANG' && event.seat === 'S' && event.tile === '1p'))
  } finally { driver.stop() }
})

async function robKongFixture() {
  const s = await fixture()
  s.roundState.dealerTile = '9s'
  const south = s.roundState.opponents.find((o) => o.seat_wind === 'S')
  south.melds = [{ meld_type: 'pong', tiles: ['1p', '1p', '1p'] }]
  south.hand_tiles = ['1p', '3m', '9s', '2m', '5m', '8s', '2s', '5p', '7p', '4s', '9m']
  s.roundState.handTiles = ['1m','1m','1m','4m','4m','4m','5s','5s','5s','6p','6p','2p','3p']
  s.roundState.opponents.find((o) => o.seat_wind === 'W').hand_tiles =
    ['2m','2m','2m','3m','3m','3m','7s','7s','7s','8p','8p','2p','3p']
  s.roundState.opponents.find((o) => o.seat_wind === 'N').hand_tiles = Array(13).fill('F')
  s.currentTurnSeat.value = 'S'
  s.currentPhase.value = 'WAITING'
  return s
}

test('robbing-kong passes in seat order, then upgrades pong and draws exactly one tail tile', async () => {
  const s = await robKongFixture()
  const before = s.wallTiles.value.length
  const tail = s.wallTiles.value.at(-1)
  await s.executeOpponentMeld({ seat: 'S', meld_type: 'bu_gang', tile: '1p' })
  const south = () => s.roundState.opponents.find((o) => o.seat_wind === 'S')
  assert.deepEqual(s.pendingHuQueue.value, ['W', 'E'])
  assert.equal(s.currentHuSeat.value, 'W')
  assert.equal(south().hand_tiles.includes('1p'), false)
  assert.equal(south().melds[0].meld_type, 'pong')
  assert.equal(s.wallTiles.value.length, before)
  await s.passCall('1p', 'W')
  assert.equal(s.currentHuSeat.value, 'E')
  assert.equal(south().melds[0].meld_type, 'pong')
  assert.equal(s.wallTiles.value.length, before)
  await s.passCall('1p', 'E')
  assert.equal(s.isResponseWindow.value, false)
  assert.equal(south().melds[0].meld_type, 'ming_gang')
  assert.deepEqual(south().melds[0].tiles, ['1p','1p','1p','1p'])
  assert.equal(south().hand_tiles.length, 11)
  assert.equal(south().hand_tiles.at(-1), tail)
  assert.equal(s.wallTiles.value.length, before - 1)
  assert.equal(s.currentTurnSeat.value, 'S')
})

test('robbing-kong win cancels meld upgrade and replacement draw', async () => {
  const s = await robKongFixture()
  const before = s.wallTiles.value.length
  await s.executeOpponentMeld({ seat: 'S', meld_type: 'bu_gang', tile: '1p' })
  await s.passCall('1p', 'W')
  await s.declareSelfRon('1p', 'S')
  const south = s.roundState.opponents.find((o) => o.seat_wind === 'S')
  assert.equal(s.gameState.value, 'GAME_OVER')
  assert.equal(s.selfWinSettlement.value.win_type_label, '抢杠胡')
  assert.equal(south.melds[0].meld_type, 'pong')
  assert.equal(south.hand_tiles.length, 10)
  assert.equal(s.wallTiles.value.length, before)
})

test('self add-kong upgrades the existing meld and returns to discard after tail draw', async () => {
  const s = await fixture()
  s.roundState.dealerTile = '9s'
  s.roundState.melds = [{ meld_type: 'pong', tiles: ['1p','1p','1p'] }]
  s.roundState.handTiles = ['1p','3m','4m','5m','2s','3s','4s','7p','8p','9p','C']
  for (const o of s.roundState.opponents) o.hand_tiles = Array(13).fill('F')
  const before = s.wallTiles.value.length
  const tail = s.wallTiles.value.at(-1)
  await s.applySelfKong({ action_type: 'bu_gang', tile: '1p' })
  assert.equal(s.roundState.melds.length, 1)
  assert.deepEqual(s.roundState.melds[0].tiles, ['1p','1p','1p','1p'])
  assert.equal(s.roundState.melds[0].meld_type, 'ming_gang')
  assert.equal(s.roundState.handTiles.length, 11)
  assert.equal(s.roundState.handTiles.at(-1), tail)
  assert.equal(s.wallTiles.value.length, before - 1)
  assert.equal(s.currentPhase.value, 'MY_TURN_DISCARD')
})

async function westNineKongFixture() {
  const s = await fixture()
  s.roundState.dealerTile = '5p'
  s.roundState.handTiles = ['9s', '9s', '9s', '1s', '2s', '3s', '4s', '5s', '6s', '7s', '8s', 'E', 'F']
  for (const o of s.roundState.opponents) o.hand_tiles = []
  const west = s.roundState.opponents.find((o) => o.seat_wind === 'W')
  west.hand_tiles = ['9s', '1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '2p', '3p', '4p']
  s.currentTurnSeat.value = 'W'
  s.currentPhase.value = 'WAITING'
  return s
}

test('west nine-sou discard and self ming-kong send the original river snapshot', async () => {
  const s = await westNineKongFixture()
  const baseFetch = globalThis.fetch
  let meldRequest
  globalThis.fetch = async (url, options) => {
    if (String(url).endsWith('/game/step')) {
      const payload = JSON.parse(options.body)
      if (payload.event.event_type === 'MELD') meldRequest = payload
    }
    return baseFetch(url, options)
  }
  await s.opponentDiscardTile('W', '9s')
  assert.equal(s.lastDiscardSeat.value, 'W')
  assert.equal(s.roundState.opponents.find((o) => o.seat_wind === 'W').discards.at(-1), '9s')
  await s.applySelfMeld({ meld_type: 'ming_gang', tiles: ['9s','9s','9s','9s'], claimed_tile: '9s', provider_seat: 'W' })
  assert.equal(meldRequest.event.actor_seat, 'E')
  assert.equal(meldRequest.event.provider_seat, 'W')
  assert.equal(meldRequest.event.claimed_discard_index, 0)
  assert.equal(meldRequest.opponents.find((o) => o.seat_wind === 'W').discards.at(-1), '9s')
  assert.equal(meldRequest.hand_tiles.filter((tile) => tile === '9s').length, 3)
  assert.equal(s.roundState.melds[0].provider_seat, 'W')
  assert.equal(s.roundState.opponents.find((o) => o.seat_wind === 'W').discards.length, 0)
  assert.equal(s.errorMsg.value, '')
})

test('a stale provider validation response keeps the completed PvE meld without a raw red error', async () => {
  const s = await westNineKongFixture()
  const baseFetch = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    if (String(url).endsWith('/game/step') && JSON.parse(options.body).event.event_type === 'MELD') {
      return { ok: false, status: 400, json: async () => ({ detail: "供牌方 W 牌河末张不是 '9s'" }) }
    }
    return baseFetch(url, options)
  }
  await s.opponentDiscardTile('W', '9s')
  await s.applySelfMeld({ meld_type: 'ming_gang', tiles: ['9s','9s','9s','9s'], claimed_tile: '9s', provider_seat: 'W' })
  assert.equal(s.errorMsg.value, '')
  assert.match(s.lastStepResult.value.note, /当前全桌局面继续校验/)
  assert.equal(s.roundState.opponents.find((o) => o.seat_wind === 'W').discards.length, 0)
  assert.equal(s.currentPhase.value, 'MY_TURN_DISCARD')
})

test('three AI turns return control to the human, drawing exactly once per seat', async () => {
  const s = await fixture()
  const seen = []
  const before = s.wallTiles.value.length
  const driver = usePvEAutomation(s, { delayMs: () => 0, recommend: async (payload) => {
    seen.push(payload.seat_wind)
    const safe = payload.hand_tiles.find((tile) => !s.scanTableResponses(payload.seat_wind, tile).hasResponse)
    assert.ok(safe)
    return { best_tile: safe }
  } })
  try {
    await s.discardTile('N', s.roundState.handTiles.indexOf('N'))
    await waitFor(() => seen.length === 3 && s.currentTurnSeat.value === 'E' && !s.loading.value)
    assert.deepEqual(seen, ['S', 'W', 'N'])
    assert.equal(s.wallTiles.value.length, before - 4)
    assert.equal(s.roundState.handTiles.length, 14)
    assert.equal(driver.error.value, '')
  } finally { driver.stop() }
})

test('AI claims whiteboard chi and evaluates the post-chi hand without drawing', async () => {
  const actions = []
  const s = await fixture((event) => actions.push(event))
  s.roundState.dealerTile = '7m'
  s.roundState.handTiles = ['6m','1p','2p','4p','5p','7p','8p','1s','2s','4s','5s','7s','8s','E']
  for (const o of s.roundState.opponents) o.hand_tiles = ['C','F','N']
  s.roundState.opponents.find((o) => o.seat_wind === 'S').hand_tiles = ['P','8m','1m','2m','4m','9m','3p','6p','9p','3s','6s','9s','S']
  const before = s.wallTiles.value.length
  let evaluated = false
  let finishClaimThinking
  const durations = []
  const driver = usePvEAutomation(s, { sleep: (ms) => {
    durations.push(ms)
    return durations.length === 1 ? new Promise((resolve) => { finishClaimThinking = resolve }) : Promise.resolve()
  }, recommend: async (payload) => {
    assert.deepEqual(payload.melds[0].tiles, ['6m', 'P', '8m'])
    assert.equal(payload.hand_tiles.length, 11)
    assert.equal(s.wallTiles.value.length, before)
    evaluated = true
    driver.stop()
    return { best_tile: payload.hand_tiles[0] }
  } })
  try {
    await s.discardTile('6m', 0)
    await waitFor(() => finishClaimThinking)
    assert.equal(durations[0], 3000)
    assert.equal(driver.thinkingSeat.value, 'S')
    assert.equal(s.roundState.opponents.find((o) => o.seat_wind === 'S').melds.length, 0)
    finishClaimThinking()
    await waitFor(() => evaluated)
    assert.ok(actions.some((event) => event.action === 'CHI' && event.seat === 'S' && event.selfSeat === 'E'))
    assert.equal(s.roundState.discards.length, 0)
  } finally { driver.stop() }
})

test('south chi takes the latest seven-pin from self, preserving north historical seven-pin', async () => {
  const s = await fixture()
  s.roundState.dealerTile = '9s'
  s.roundState.handTiles = ['7p','1m','2m','3m','4m','5m','6m','7m','8m','9m','1s','3s','C']
  s.roundState.opponents.find((o) => o.seat_wind === 'S').hand_tiles =
    ['5p','6p','1m','2m','3m','4m','5m','6m','7m','1s','2s','3s','C']
  s.roundState.opponents.find((o) => o.seat_wind === 'N').hand_tiles =
    ['7p','1p','2p','3p','4p','5p','6p','8p','9p','1s','2s','3s','4s','F']
  s.currentTurnSeat.value = 'N'
  s.currentPhase.value = 'WAITING'
  await s.opponentDiscardTile('N', '7p')
  assert.deepEqual(s.roundState.opponents.find((o) => o.seat_wind === 'N').discards, ['7p'])
  assert.equal(s.currentTurnSeat.value, 'E')
  await s.discardTile('7p', s.roundState.handTiles.indexOf('7p'))
  assert.equal(s.lastDiscardSeat.value, 'E')
  assert.equal(s.lastStepResult.value._response_tile, '7p')
  const wallBeforeClaim = s.wallTiles.value.length
  await assert.rejects(s.executeOpponentMeld({ seat: 'S', meld_type: 'chi',
    tiles: ['5p','6p','7p'], claimed_tile: '7p', provider_seat: 'N' }), /供牌方.*不一致/)
  assert.deepEqual(s.roundState.discards, ['7p'])
  assert.deepEqual(s.roundState.opponents.find((o) => o.seat_wind === 'N').discards, ['7p'])
  s.roundState.discards = []
  await assert.rejects(s.executeOpponentMeld({ seat: 'S', meld_type: 'chi',
    tiles: ['5p','6p','7p'], claimed_tile: '7p', provider_seat: 'E' }), /牌河末张/)
  assert.deepEqual(s.roundState.opponents.find((o) => o.seat_wind === 'N').discards, ['7p'])
  s.roundState.discards = ['7p']
  await s.executeOpponentMeld({ seat: 'S', meld_type: 'chi',
    tiles: ['5p','6p','7p'], claimed_tile: '7p', provider_seat: 'E' })
  assert.deepEqual(s.roundState.discards, [])
  assert.deepEqual(s.roundState.opponents.find((o) => o.seat_wind === 'N').discards, ['7p'])
  const south = s.roundState.opponents.find((o) => o.seat_wind === 'S')
  assert.equal(south.melds[0].provider_seat, 'E')
  assert.equal(south.melds[0].claimed_tile, '7p')
  assert.equal(south.hand_tiles.length, 11)
  assert.equal(s.wallTiles.value.length, wallBeforeClaim)
  await assert.rejects(s.executeOpponentMeld({ seat: 'S', meld_type: 'chi',
    tiles: ['5p','6p','7p'], claimed_tile: '7p', provider_seat: 'E' }), /没有可副露的出牌响应窗口|没有待响应的出牌事件/)
})

test('AI south chi binds the response to self seven-pin after north discarded seven-pin', async () => {
  const s = await fixture()
  s.roundState.dealerTile = '9s'
  s.roundState.handTiles = ['7p','1m','2m','3m','4m','5m','6m','7m','8m','9m','1s','3s','C']
  const south = s.roundState.opponents.find((o) => o.seat_wind === 'S')
  south.hand_tiles = ['5p','6p','1m','2m','3m','4m','5m','6m','7m','1s','2s','3s','C']
  const north = s.roundState.opponents.find((o) => o.seat_wind === 'N')
  north.hand_tiles = ['7p','1p','2p','3p','4p','5p','6p','8p','9p','1s','2s','3s','4s','F']
  s.currentTurnSeat.value = 'N'
  s.currentPhase.value = 'WAITING'
  await s.opponentDiscardTile('N', '7p')
  assert.deepEqual(s.roundState.opponents.find((o) => o.seat_wind === 'N').discards, ['7p'])

  const driver = usePvEAutomation(s, { delayMs: () => 0, recommend: () => new Promise(() => {}) })
  try {
    await s.discardTile('7p', s.roundState.handTiles.indexOf('7p'))
    await waitFor(() => s.roundState.opponents.find((o) => o.seat_wind === 'S').melds.length === 1)
    const claimedBySouth = s.roundState.opponents.find((o) => o.seat_wind === 'S').melds[0]
    assert.deepEqual(s.roundState.discards, [])
    assert.deepEqual(s.roundState.opponents.find((o) => o.seat_wind === 'N').discards, ['7p'])
    assert.deepEqual(claimedBySouth.tiles, ['5p', '6p', '7p'])
    assert.equal(claimedBySouth.provider_seat, 'E')
    assert.equal(claimedBySouth.claimed_tile, '7p')
  } finally { driver.stop() }
})

test('a recommendation from the previous round cannot discard in the new round', async () => {
  const s = await fixture()
  let resolve, requested = false
  const driver = usePvEAutomation(s, { delayMs: () => 0, recommend: () => {
    requested = true
    return new Promise((r) => { resolve = r })
  } })
  try {
    await s.discardTile('N', s.roundState.handTiles.indexOf('N'))
    await waitFor(() => requested)
    await s.startPveGame()
    resolve({ best_tile: s.roundState.opponents.find((o) => o.seat_wind === 'S').hand_tiles[0] })
    await waitFor(() => !driver.busy.value)
    await nextTick()
    assert.equal(s.currentTurnSeat.value, 'E')
    assert.ok(s.roundState.opponents.every((o) => o.discards.length === 0))
  } finally { driver.stop() }
})
