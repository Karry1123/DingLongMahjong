import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSoundEngine, spokenAction, voiceProfileForSeat } from '../src/utils/soundEngine.js'

test('turn reminder plays a short two-tone Web Audio cue and obeys mute without speech or downloads',()=>{
  const tones=[],requests=[]
  class Context {
    currentTime=0;state='running';destination={}
    createOscillator(){return {frequency:{set value(v){tones.push(v)}},connect(){return this},start(){},stop(){}}}
    createGain(){return {gain:{setValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){return this}}}
    close(){}
  }
  const engine=createSoundEngine({AudioContext:Context,fetch:url=>requests.push(url)})
  engine.playAction({action:'TURN'})
  assert.deepEqual(tones,[660,880]);assert.deepEqual(requests,[])
  engine.setMuted(true);engine.playAction({action:'TURN'});assert.equal(tones.length,2)
  engine.stop(true)
})

function deferredClipEngine(fetch) {
  const played = []
  const spoken = []
  class Context {
    state = 'running'
    currentTime = 0
    destination = {}
    decodeAudioData() { return Promise.resolve({ duration: .5 }) }
    createBufferSource() { return { playbackRate: {}, connect() { return this }, start() { played.push(this.buffer) }, stop() {} } }
    createGain() { return { gain: {}, connect() { return this } } }
    close() {}
  }
  const engine = createSoundEngine({ AudioContext: Context, fetch,
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text } },
    speechSynthesis: { getVoices: () => [{lang:'zh-CN',name:'Huihui'}], speak: u => spoken.push(u.text), cancel() {} },
  })
  return { engine, played, spoken, play: () => engine.playAction({ action:'DISCARD', tile:'E', seat:'E', selfSeat:'E' }) }
}

test('opening cue fetches and decodes a data asset, caches it, and respects mute', async () => {
  const urls=[]
  const h=deferredClipEngine(async url=>{
    urls.push(url)
    return {ok:true,arrayBuffer:async()=>new Uint8Array([77,74,86,79,73,67,69,49,1]).buffer}
  })
  h.engine.unlock()
  assert.equal(await h.engine.playOpening(),true)
  assert.match(urls[0],/OPENING\.dat$/)
  assert.equal(await h.engine.playOpening(),true)
  assert.equal(urls.length,1)
  assert.equal(h.played.length,2)
  assert.deepEqual(h.spoken,[])
  h.engine.setMuted(true)
  assert.equal(await h.engine.playOpening(),false)
  h.engine.stop(true)
})

test('empty intercepted responses fall back without automatic retries, next action can retry', async () => {
  let requests = 0
  const h = deferredClipEngine(async () => {
    requests++
    return { ok:true, arrayBuffer:async () => requests === 1 ? new ArrayBuffer(0) : new Uint8Array([77,74,86,79,73,67,69,49,1]).buffer }
  })
  await h.play()
  assert.equal(requests, 1)
  assert.deepEqual(h.spoken, ['东风'])
  assert.equal(h.played.length, 0)
  await h.play()
  assert.equal(requests, 2)
  assert.equal(h.played.length, 1)
  h.engine.stop(true)
})

test('disposing while a fetch is pending prevents late playback or new requests', async () => {
  let release, requests = 0
  const gate = new Promise(resolve => { release = resolve })
  const h = deferredClipEngine(async () => {
    requests++
    await gate
    return { ok:true, arrayBuffer:async () => new Uint8Array([77,74,86,79,73,67,69,49,1]).buffer }
  })
  const pending = h.play()
  h.engine.stop(true)
  release()
  await pending
  await h.play()
  assert.equal(requests, 1)
  assert.deepEqual(h.played, [])
  assert.deepEqual(h.spoken, [])
})

test('tile names and seat profiles follow the relative PvE roles', () => {
  assert.equal(spokenAction('DISCARD', '9p'), '九筒')
  assert.equal(spokenAction('DISCARD', '3s'), '三条')
  assert.equal(spokenAction('DISCARD', '1m'), '一万')
  for (const [code, text] of Object.entries({ E:'东风', S:'南风', W:'西风', N:'北风', C:'红中', F:'发财', P:'白板' })) assert.equal(spokenAction('DISCARD', code), text)
  assert.equal(spokenAction('CHI'), '吃！')
  assert.equal(spokenAction('PONG'), '碰！')
  assert.equal(spokenAction('GANG'), '杠！')
  assert.equal(spokenAction('WIN'), '胡了！')
  assert.equal(spokenAction('WIN', null, true), '自摸！')
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

test('first user gesture primes speech and delayed Chinese voices are used', () => {
  const spoken = []
  const listeners = new Map()
  let voices = []
  class Utterance { constructor(text) { this.text = text } }
  const browser = {
    SpeechSynthesisUtterance: Utterance,
    speechSynthesis: {
      speak: (utterance) => spoken.push(utterance),
      cancel: () => {},
      resume: () => {},
      getVoices: () => voices,
      addEventListener: (event, cb) => listeners.set(event, cb),
      removeEventListener: (event) => listeners.delete(event),
    },
  }
  const engine = createSoundEngine(browser)
  engine.unlock()
  assert.equal(spoken.length, 1)
  assert.equal(spoken[0].volume, 0)
  engine.playAction({ action: 'DISCARD', tile: '9p', seat: 'S', selfSeat: 'E' })
  assert.equal(spoken.length, 1)
  voices = [{ name: 'Yunxi', lang: 'zh-CN' }]
  listeners.get('voiceschanged')()
  assert.equal(spoken[1].text, '九筒')
  assert.equal(spoken[1].voice, voices[0])
  engine.stop(true)
  assert.equal(listeners.size, 0)
})

test('missing speech API falls back without throwing', () => {
  let tones = 0
  class AudioContext {
    state = 'running'
    currentTime = 0
    destination = {}
    createOscillator() {
      return { frequency: {}, connect() { return this }, start() { tones++ }, stop() {} }
    }
    createGain() {
      return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() { return this } }
    }
    close() {}
  }
  const engine = createSoundEngine({ AudioContext })
  assert.doesNotThrow(() => {
    engine.unlock()
    engine.playAction({ action: 'PONG', seat: 'W', selfSeat: 'E' })
    engine.stop()
  })
  assert.equal(tones, 2)
})

for (const userAgent of ['MicroMessenger', 'Chrome']) {
test(`${userAgent} loads on demand via fetch and reuses decoded buffers without media elements`, async () => {
  const requested = []
  const sources = []
  const listeners = new Map()
  let spoken = 0
  let decoded = 0
  let bytesRead = 0
  class AudioContext {
    state = 'suspended'
    currentTime = 0
    sampleRate = 16000
    destination = {}
    resume() { this.state = 'running'; return Promise.resolve() }
    decodeAudioData(bytes) {
      assert.ok(bytes instanceof ArrayBuffer)
      decoded++
      return Promise.resolve({ duration: 0.4 })
    }
    createBuffer() { return { getChannelData: () => new Float32Array(400) } }
    createBufferSource() {
      const source = { playbackRate: { value: 1 }, connect() { return this }, start(time) { this.startedAt = time }, stop() {} }
      sources.push(source)
      return source
    }
    createBiquadFilter() { return { frequency: {}, Q: {}, connect() { return this } } }
    createGain() { return { gain: { value: 1 }, connect() { return this } } }
    close() {}
  }
  const browser = {
    navigator: { userAgent }, AudioContext,
    Audio: class { constructor() { assert.fail('Audio elements must never be used') } },
    document: {
      createElement() { assert.fail('Media elements must never be created') },
      addEventListener: (name, callback) => listeners.set(name, callback),
      removeEventListener: (name) => listeners.delete(name),
    },
    fetch: async (url, options) => { assert.equal(options.headers.Accept, 'application/octet-stream'); requested.push(url); return { ok: true, arrayBuffer: async () => { bytesRead++; return new Uint8Array([77,74,86,79,73,67,69,49,1,2,3,4]).buffer } } },
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text } },
    speechSynthesis: { getVoices: () => [{ name: 'Huihui', lang: 'zh-CN' }], speak: () => { spoken++ }, cancel() {} },
  }
  const engine = createSoundEngine(browser)
  listeners.get('WeixinJSBridgeReady')()
  await engine.unlock()
  assert.equal(requested.length, 0)
  assert.equal(decoded, 0)
  assert.equal(bytesRead, 0)
  await engine.playAction({ action: 'DISCARD', tile: '1m', seat: 'E', selfSeat: 'E' })
  assert.deepEqual(requested, ['/audio/data/1m.dat'])
  assert.equal(spoken, 0)
  assert.equal(sources.length, 3) // Two table taps and one spoken tile clip.
  assert.ok(sources[2].startedAt >= 0.14)
  await engine.unlock()
  engine.playAction({ action: 'DISCARD', tile: '1m', seat: 'E', selfSeat: 'E' })
  assert.equal(sources[5].buffer, sources[2].buffer)
  assert.equal(requested.length, 1)
  assert.equal(decoded, 1)
  engine.setMuted(true)
  await engine.playAction({ action: 'DISCARD', tile: '2p', seat: 'E', selfSeat: 'E' })
  engine.setMuted(false)
  engine.setVolume(0)
  await engine.playAction({ action: 'DISCARD', tile: '2p', seat: 'E', selfSeat: 'E' })
  assert.equal(requested.length, 1)
  engine.setVolume(.7)
  await engine.playAction({action:'WIN',isZimo:true,seat:'E',selfSeat:'E'})
  await engine.playAction({action:'WIN',isZimo:false,seat:'N',selfSeat:'E'})
  assert.deepEqual(requested.slice(-2),['/audio/data/ZIMO.dat','/audio/data/WIN.dat'])
  assert.equal(decoded,3)
  assert.equal(spoken,0)
  engine.stop(true)
  assert.equal(listeners.has('WeixinJSBridgeReady'), false)
})
}

test('concurrent requests for one tile are deduplicated and cached', async () => {
  let requests = 0
  let releaseOtherClips
  const otherClips = new Promise(resolve => { releaseOtherClips = resolve })
  const played = []
  class AudioContext {
    state = 'running'
    currentTime = 0
    sampleRate = 16000
    destination = {}
    decodeAudioData() { return Promise.resolve({ duration: 0.3 }) }
    createBuffer() { return { getChannelData: () => new Float32Array(400) } }
    createBufferSource() { return { playbackRate: { value: 1 }, connect() { return this }, start() { played.push(this.buffer) }, stop() {} } }
    createBiquadFilter() { return { frequency: {}, Q: {}, connect() { return this } } }
    createGain() { return { gain: { value: 1 }, connect() { return this } } }
  }
  const engine = createSoundEngine({
    navigator: { userAgent: 'MicroMessenger' }, AudioContext,
    fetch: async url => {
      requests++
      await otherClips
      return { ok: true, arrayBuffer: async () => new Uint8Array([77,74,86,79,73,67,69,49,1,2,3,4]).buffer }
    },
  })
  engine.unlock()
  assert.equal(requests, 0)
  const first = engine.playAction({ action: 'DISCARD', tile: '9p', seat: 'E', selfSeat: 'E' })
  const second = engine.playAction({ action: 'DISCARD', tile: '9p', seat: 'E', selfSeat: 'E' })
  assert.equal(requests, 1)
  releaseOtherClips()
  await Promise.all([first, second])
  assert.equal(played.length, 5) // Four synthesized taps and one latest announcement.
  await engine.playAction({ action: 'DISCARD', tile: '9p', seat: 'E', selfSeat: 'E' })
  assert.equal(requests, 1)
  assert.equal(played.length, 8)
  engine.stop(true)
})
