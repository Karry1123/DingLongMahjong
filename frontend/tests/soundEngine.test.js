import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSoundEngine, spokenAction, voiceProfileForSeat } from '../src/utils/soundEngine.js'

test('tile names and seat profiles follow the relative PvE roles', () => {
  assert.equal(spokenAction('DISCARD', '9p'), '九筒')
  assert.equal(spokenAction('DISCARD', '3s'), '三条')
  assert.equal(spokenAction('DISCARD', '1m'), '一万')
  assert.equal(spokenAction('DISCARD', 'C'), '中')
  assert.equal(spokenAction('CHI'), '吃！')
  assert.equal(spokenAction('PONG'), '碰！')
  assert.equal(spokenAction('GANG'), '杠！')
  assert.equal(spokenAction('WIN'), '胡了！')
  assert.ok(voiceProfileForSeat('E', 'E').pitch > voiceProfileForSeat('E', 'S').pitch)
  assert.ok(voiceProfileForSeat('E', 'S').pitch > voiceProfileForSeat('E', 'N').pitch)
  assert.ok(voiceProfileForSeat('E', 'N').pitch > voiceProfileForSeat('E', 'W').pitch)
  assert.equal(voiceProfileForSeat('N', 'E').pitch, voiceProfileForSeat('E', 'S').pitch)
})

test('speech uses each role, keeps only the latest pending call, and obeys mute and volume', () => {
  const spoken = []
  let cancelled = 0
  class Utterance { constructor(text) { this.text = text } }
  const browser = {
    SpeechSynthesisUtterance: Utterance,
    speechSynthesis: {
      getVoices: () => [{ name: 'Chinese', lang: 'zh-CN' }],
      speak: (utterance) => spoken.push(utterance),
      cancel: () => { cancelled++ },
    },
  }
  const engine = createSoundEngine(browser)
  engine.setVolume(0.45)
  engine.playAction({ action: 'DISCARD', tile: '9p', seat: 'E', selfSeat: 'E' })
  assert.equal(spoken[0].text, '九筒')
  assert.equal(spoken[0].volume, 0.45)
  assert.equal(spoken[0].lang, 'zh-CN')
  engine.playAction({ action: 'CHI', seat: 'S', selfSeat: 'E' })
  engine.playAction({ action: 'PONG', seat: 'W', selfSeat: 'E' })
  assert.equal(spoken.length, 1)
  spoken[0].onend()
  assert.equal(spoken[1].text, '碰！')
  assert.equal(spoken[1].pitch, voiceProfileForSeat('E', 'W').pitch)
  engine.setVolume(0)
  engine.playAction({ action: 'GANG', seat: 'S', selfSeat: 'E' })
  assert.equal(spoken.length, 2)
  engine.setVolume(0.45)
  engine.setMuted(true)
  engine.playAction({ action: 'WIN', seat: 'N', selfSeat: 'E' })
  assert.equal(spoken.length, 2)
  assert.ok(cancelled >= 1)
  engine.stop()
})
