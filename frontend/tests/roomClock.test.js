import assert from 'node:assert/strict'
import { test } from 'node:test'
import { roomActionSeconds } from '../src/utils/roomClock.js'

test('server offset, stale render ticks, suspended claims and expiry render bounded clock seconds', () => {
  const clock={paused:false,deadline:11000,remaining_ms:10000}
  assert.equal(roomActionSeconds(clock,0,900),10)
  assert.equal(roomActionSeconds(clock,0,1000),10)
  assert.equal(roomActionSeconds(clock,2000,4000),5)
  assert.equal(roomActionSeconds(clock,0,11000),0)
  assert.equal(roomActionSeconds(clock,0,12000),0)
  const chi={paused:true,deadline:null,remaining_ms:6000}
  assert.equal(roomActionSeconds(chi,2000,50000),6)
  chi.paused=false;chi.deadline=56000
  assert.equal(roomActionSeconds(chi,0,49900),6)
  assert.equal(roomActionSeconds(chi,0,55001),1)
})
