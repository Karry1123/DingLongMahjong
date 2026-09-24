import test from 'node:test'
import assert from 'node:assert/strict'
import { pveOpponentsForDealer, pveWindForPlayer, remapPveScores } from '../src/utils/pveSeatMapping.js'

test('a non-self dealer stays East and all winds follow fixed relative player identities', () => {
  assert.equal(pveWindForPlayer(2, 2), 'E')
  assert.equal(pveWindForPlayer(0, 2), 'W')
  assert.equal(pveWindForPlayer(1, 2), 'N')
  assert.equal(pveWindForPlayer(3, 2), 'S')
  assert.deepEqual(
    pveOpponentsForDealer(2).map(({ role, seat_wind }) => [role, seat_wind]),
    [['下家', 'N'], ['对家', 'E'], ['上家', 'S']],
  )
})

test('the first non-self dealer is the lower seat and cumulative totals follow players', () => {
  assert.equal(pveWindForPlayer(1, 1), 'E')
  assert.equal(pveWindForPlayer(0, 1), 'N')
  assert.deepEqual(
    remapPveScores({ E: 10, S: 20, W: 30, N: 40 }, 0, 1),
    { E: 20, S: 30, W: 40, N: 10 },
  )
})

test('starting a new circle returns the dealer to self without moving totals between players', () => {
  assert.deepEqual(
    remapPveScores({ E: 10, S: 20, W: 30, N: 40 }, 3, 0),
    { E: 20, S: 30, W: 40, N: 10 },
  )
})
