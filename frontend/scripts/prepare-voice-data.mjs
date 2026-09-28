// Build-time packaging only. No browser requests or runtime preloading.
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { ALL_TILES } from '../src/constants/tiles.js'
import { HONOR_VOICES } from '../src/utils/soundEngine.js'

const source = new URL('../public/audio/tiles/', import.meta.url)
const target = new URL('../public/audio/data/', import.meta.url)
await mkdir(target, { recursive: true })
for (const code of [...ALL_TILES, 'CHI', 'PONG', 'GANG', 'WIN', 'OPENING']) {
  const name = HONOR_VOICES[code]?.file || code
  const audio = await readFile(new URL(`${name}.wav`, source))
  for (let i = 0; i < audio.length; i++) audio[i] ^= 0xa5
  await writeFile(new URL(`${name}.dat`, target), Buffer.concat([Buffer.from('MJVOICE1'), audio]))
}
console.log('Prepared 39 audio data assets (application/octet-stream).')
