import assert from 'node:assert/strict'
import { test } from 'node:test'
import { TimeBank } from '../src/utils/timeBank.js'
import { roomClockState } from '../src/utils/roomClock.js'

test('regular time rolls into reserve without a broadcast; action freezes the unused reserve',()=>{
  const bank=new TimeBank(),turn={E:{token:'1',kind:'discard',durationMs:10000}}
  bank.sync(turn,1000)
  const before=bank.snapshot(1000)
  assert.equal(roomClockState(before.clocks.E,before.banks.E,0,1000).seconds,10)
  assert.deepEqual(roomClockState(before.clocks.E,before.banks.E,0,11000),{seconds:30,bankSeconds:30,stage:'bank',paused:false})
  assert.equal(roomClockState(before.clocks.E,before.banks.E,0,13500).bankSeconds,28)
  bank.sync({},13500)
  assert.equal(bank.snapshot(30000).banks.E,27500)
  bank.sync({E:{...turn.E,token:'2'}},30000)
  assert.equal(bank.snapshot(30000).clocks.E.deadline,40000)
  assert.equal(bank.snapshot(40000).clocks.E.deadline,67500)
})

test('hung chi and network pauses consume neither base time nor reserve',()=>{
  const bank=new TimeBank(),response={S:{token:'chi',kind:'response',durationMs:6000,paused:true}}
  bank.sync(response,1000)
  bank.sync(response,25000)
  assert.equal(bank.snapshot(25000).banks.S,30000)
  bank.sync({S:{...response.S,paused:false}},25000)
  assert.equal(bank.snapshot(25000).clocks.S.deadline,31000)
  bank.sync(response,33500)
  assert.equal(bank.snapshot(50000).banks.S,27500)
  bank.sync({S:{...response.S,paused:false}},50000)
  assert.equal(bank.snapshot(50000).clocks.S.bank_deadline,77500)
  assert.deepEqual(bank.expired(77499),[])
  assert.deepEqual(bank.expired(77500),['S'])
})

test('exhausted reserve stays zero until the next hand and four seats are independent',()=>{
  const bank=new TimeBank(),action={E:{token:'1',kind:'discard',durationMs:10000}}
  bank.sync(action,0);bank.sync({},40000)
  assert.equal(bank.banks.E,0);assert.equal(bank.banks.S,30000)
  bank.sync({E:{...action.E,token:'2'}},60000)
  assert.deepEqual(bank.expired(70000),['E'])
  bank.reset()
  assert.deepEqual(bank.banks,{E:30000,S:30000,W:30000,N:30000})
})

test('server offsets and repeated bank snapshots never double deduct thinking time',()=>{
  const clock={kind:'discard',stage:'bank',regular_deadline:11000,bank_deadline:41000,deadline:41000,remaining_ms:28000,bank_remaining_ms:28000,paused:false}
  assert.equal(roomClockState(clock,28000,2000,11000).bankSeconds,28)
  assert.equal(roomClockState({...clock,remaining_ms:27000,bank_remaining_ms:27000},27000,2000,12000).bankSeconds,27)
  assert.equal(roomClockState(clock,28000,2000,39000).seconds,0)
})
