// Run with a local backend on :8000. Exercises the real step API through a PvE meld.
import assert from 'node:assert/strict'
import { useGameSession } from '../src/composables/useGameSession.js'
import { northDiscardDeal } from '../tests/pveFixture.js'

const baseFetch = globalThis.fetch
const apiUrl = process.env.API_URL || 'http://127.0.0.1:8000'
const meldRequests = []
globalThis.fetch = async (url, options) => {
  const path = String(url)
  if (path.endsWith('/game/auto-deal')) return Response.json(northDiscardDeal())
  const response = await baseFetch(`${apiUrl}${path}`, options)
  if (path.endsWith('/game/step') && JSON.parse(options?.body || '{}').event?.event_type === 'MELD') {
    meldRequests.push({ status: response.status, request: JSON.parse(options.body) })
  }
  return response
}

try {
  const session = useGameSession()
  await session.startPveGame()
  session.roundState.dealerTile = '5p'
  session.roundState.handTiles = ['9s', '9s', '9s', '1s', '2s', '3s', '4s', '5s', '6s', '7s', '8s', 'E', 'F']
  for (const opponent of session.roundState.opponents) opponent.hand_tiles = []
  session.roundState.opponents.find((o) => o.seat_wind === 'W').hand_tiles =
    ['9s', '1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '2p', '3p', '4p']
  session.currentTurnSeat.value = 'W'
  session.currentPhase.value = 'WAITING'

  await session.opponentDiscardTile('W', '9s')
  const wallBeforeKong = session.wallTiles.value.length
  await session.applySelfMeld({
    meld_type: 'ming_gang', tiles: ['9s', '9s', '9s', '9s'],
    claimed_tile: '9s', provider_seat: 'W',
  })

  assert.equal(meldRequests.length, 1)
  assert.equal(meldRequests[0].status, 200)
  assert.equal(meldRequests[0].request.event.provider_seat, 'W')
  assert.equal(meldRequests[0].request.opponents.find((o) => o.seat_wind === 'W').discards.at(-1), '9s')
  assert.equal(session.roundState.opponents.find((o) => o.seat_wind === 'W').discards.length, 0)
  assert.equal(session.roundState.melds[0].provider_seat, 'W')
  assert.equal(session.roundState.handTiles.length, 11)
  assert.equal(session.wallTiles.value.length, wallBeforeKong - 1)
  assert.equal(session.currentPhase.value, 'MY_TURN_DISCARD')
  assert.equal(session.errorMsg.value, '')
  console.log('W 打出九条 → 自家明杠 → 岭上补牌：步进 API 200，牌河与暗手一致')
} finally {
  globalThis.fetch = baseFetch
}
