import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
import { unpackVoiceData } from '../src/utils/voiceData.js'
import { ALL_TILES } from '../src/constants/tiles.js'
import { HONOR_VOICES } from '../src/utils/soundEngine.js'

test('all packaged voices restore their exact source bytes, including double-word honors', async () => {
  execFileSync(process.execPath, ['scripts/prepare-voice-data.mjs'])
  for (const code of [...ALL_TILES, 'CHI', 'PONG', 'GANG', 'WIN', 'OPENING']) {
    const name = HONOR_VOICES[code]?.file || code
    const data = await readFile(new URL(`../public/audio/data/${name}.dat`, import.meta.url))
    const wav = await readFile(new URL(`../public/audio/tiles/${name}.wav`, import.meta.url))
    assert.equal(data.subarray(0, 8).toString(), 'MJVOICE1')
    assert.deepEqual(Buffer.from(unpackVoiceData(Uint8Array.from(data).buffer)), wav)
  }
})

test('empty, intercepted and obsolete responses cannot be decoded as voices', () => {
  for (const bytes of [new ArrayBuffer(0), new TextEncoder().encode('<html>Error</html>').buffer, new TextEncoder().encode('RIFFoldwav').buffer]) {
    assert.throws(() => unpackVoiceData(bytes), /Invalid voice data/)
  }
})
