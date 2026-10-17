import assert from 'node:assert/strict'
import { test } from 'node:test'
import { nicknameError } from '../src/utils/pvpEntry.js'

test('nickname rejects empty, invisible and reserved AI variants', () => {
  for (const name of ['', '   ', '\u200b', 'AI 1号', 'aI2号', '牌友AI-3号', 'A I_4号', 'ＡＩ １号', 'ai四号', 'AI.2']) {
    assert.ok(nicknameError(name), name)
  }
  for (const name of ['顶龙牌友', ' 小西 ', 'Mai', 'AI研究员', 'AI10号']) assert.equal(nicknameError(name), '')
  assert.ok(nicknameError('龙'.repeat(7)))
  assert.equal(nicknameError('龙'.repeat(6)), '')
})

