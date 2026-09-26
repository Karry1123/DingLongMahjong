import assert from 'node:assert/strict'
import { test } from 'node:test'
import { useGameSession } from '../src/composables/useGameSession.js'

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
