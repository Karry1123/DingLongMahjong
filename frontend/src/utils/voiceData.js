// Transport envelope, not encryption. Keep media signatures out of network
// responses so download managers see data, not an independently playable file.
const MAGIC = [77, 74, 86, 79, 73, 67, 69, 49] // MJVOICE1
export function unpackVoiceData(bytes) {
  const source = new Uint8Array(bytes)
  if (source.length <= MAGIC.length || MAGIC.some((value, i) => source[i] !== value)) {
    throw new Error('Invalid voice data')
  }
  const audio = source.slice(MAGIC.length)
  for (let i = 0; i < audio.length; i++) audio[i] ^= 0xa5
  return audio.buffer
}
