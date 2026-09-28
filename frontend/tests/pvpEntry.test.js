import assert from 'node:assert/strict'
import { test } from 'node:test'
import { nicknameError, roomIdError, pvpRoute, createVisitorId } from '../src/utils/pvpEntry.js'

test('nickname rejects empty, invisible and reserved AI variants', () => {
  for (const name of ['', '   ', '\u200b', 'AI 1号', 'aI2号', '牌友AI-3号', 'A I_4号', 'ＡＩ １号', 'ai四号', 'AI.2']) {
    assert.ok(nicknameError(name), name)
  }
  for (const name of ['顶龙牌友', ' 小西 ', 'Mai', 'AI研究员', 'AI10号']) assert.equal(nicknameError(name), '')
  assert.ok(nicknameError('龙'.repeat(7)))
  assert.equal(nicknameError('龙'.repeat(6)), '')
})

test('room entry uses exactly six digits and route safely extracts the ID', () => {
  for (const id of ['12345', '1234567', '12a456', '１２３４５６', '']) assert.ok(roomIdError(id))
  assert.equal(roomIdError(' 123456 '), '')
  assert.deepEqual(pvpRoute('#/pvp'), { roomId: '' })
  assert.deepEqual(pvpRoute('#/pvp/room/123456'), { roomId: '123456' })
  assert.equal(pvpRoute('#/pvp/room/12345'), null)
  assert.equal(pvpRoute('#/pvp/room/123456/evil'), null)
})

test('LAN previews can create a valid visitor UUID without HTTPS randomUUID', () => {
  const value = createVisitorId({ getRandomValues: bytes => { bytes.fill(123); return bytes } })
  assert.match(value, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
})
