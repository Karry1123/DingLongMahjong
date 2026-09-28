import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ROOM_SEATS, countdownNumber, relativeRoomSeats } from '../src/utils/roomSeats.js'
import { roomSocketUrl, roomHttpUrl } from '../src/services/roomApi.js'
import { resolveApiBase } from '../src/services/apiBase.js'

test('physical wind positions stay fixed for all viewers', () => {
  assert.deepEqual(ROOM_SEATS.map(s => [s.wind, s.position]), [['E', 'left'], ['S', 'bottom'], ['W', 'right'], ['N', 'top']])
})
test('all four self perspectives rotate hands, rivers and melds without changing physical winds', () => {
  const expected = { E:{bottom:'E',top:'W',left:'N',right:'S'}, S:{bottom:'S',top:'N',left:'E',right:'W'}, W:{bottom:'W',top:'E',left:'S',right:'N'}, N:{bottom:'N',top:'S',left:'W',right:'E'} }
  for (const wind of 'ESWN') {
    const seats = relativeRoomSeats(wind)
    assert.deepEqual(Object.fromEntries(seats.map(s=>[s.position,s.wind])), expected[wind])
    assert.equal(seats.find(s=>s.isSelf).position, 'bottom')
    assert.equal(seats.find(s=>s.position==='left').role, '上家')
    assert.equal(seats.find(s=>s.position==='right').role, '下家')
  }
  assert.throws(()=>relativeRoomSeats('invalid'))
})
test('countdown follows the server deadline even when the local clock differs', () => {
  const deadline = 20000, offset = 10000
  assert.equal(countdownNumber(deadline, offset, 7000), 3)
  assert.equal(countdownNumber(deadline, offset, 8000), 2)
  assert.equal(countdownNumber(deadline, offset, 9000), 1)
  assert.equal(countdownNumber(deadline, offset, 11000), 0)
})
test('WebSocket endpoint follows relative proxy or remote HTTPS API configuration', () => {
  assert.equal(roomSocketUrl('123456', '', 'http://localhost:5178'), 'ws://localhost:5178/api/rooms/123456/ws')
  assert.equal(roomSocketUrl('123456', 'https://backend.example', 'https://frontend.example'), 'wss://backend.example/api/rooms/123456/ws')
})

test('LAN and hotspot clients share the current HTTP and WebSocket proxy origin', () => {
  for (const origin of ['http://172.20.10.2:5173','http://192.168.1.25:5181','http://10.35.246.104:5173']) {
    assert.equal(roomHttpUrl('', '', origin),`${origin}/api/rooms`)
    assert.equal(roomSocketUrl('123456', '', origin),`${origin.replace('http:','ws:')}/api/rooms/123456/ws`)
  }
  assert.equal(roomSocketUrl('123456','/','https://192.168.1.25:5173'),'wss://192.168.1.25:5173/api/rooms/123456/ws')
})

test('explicit loopback backend configurations follow the browser host, while deployed APIs stay explicit', () => {
  const origin='http://172.20.10.2:5173'
  for(const base of ['http://localhost:8000','http://127.0.0.1:8000/','http://[::1]:8000']) {
    assert.equal(roomHttpUrl('',base,origin),'http://172.20.10.2:8000/api/rooms')
    assert.equal(roomSocketUrl('123456',base,origin),'ws://172.20.10.2:8000/api/rooms/123456/ws')
  }
  assert.equal(resolveApiBase('https://backend.example/',origin),'https://backend.example')
  assert.equal(resolveApiBase('http://127.0.0.1:8000','http://localhost:5173'),'http://127.0.0.1:8000')
})
