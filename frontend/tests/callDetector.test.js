import assert from 'node:assert/strict'
import { test } from 'node:test'
import { detectTableResponses, shouldEnterResponseWindow } from '../src/utils/callDetector.js'

test('discarded god tile never opens a local call or ron window', () => {
  for (const providerSeat of ['E', 'S', 'W', 'N']) {
    const result = detectTableResponses({
      providerSeat,
      discardedTile: '5m',
      dealerTile: '5m',
      selfSeat: 'E',
      getSeat: () => ({ hand: ['5m', '5m', '3m', '4m'], melds: [] }),
    })
    assert.deepEqual(result.options, [])
    assert.deepEqual(result.catchWinSeats, [])
    assert.equal(result.untracked, false)
    assert.equal(shouldEnterResponseWindow(result, { godView: false }), false)
  }
})
