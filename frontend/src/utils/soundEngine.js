import { ALL_TILES, relativeOpponents, tileLabel } from '../constants/tiles.js'
import { unpackVoiceData } from './voiceData.js'

export const HONOR_VOICES = Object.freeze({
  E: { text: '东风', file: 'dongfeng' }, S: { text: '南风', file: 'nanfeng' },
  W: { text: '西风', file: 'xifeng' }, N: { text: '北风', file: 'beifeng' },
  C: { text: '红中', file: 'hongzhong' }, F: { text: '发财', file: 'facai' },
  P: { text: '白板', file: 'baiban' },
})

const CLIP_CODES = [...ALL_TILES, 'CHI', 'PONG', 'GANG', 'WIN', 'ZIMO', 'OPENING']
const CLIP_SET = new Set(CLIP_CODES)
const CLIP_BASE = `${(import.meta.env?.BASE_URL || '/').replace(/\/?$/, '/')}audio/data/`

const PROFILES = Object.freeze({
  self: { pitch: 1.55, rate: 1.12, voice: /xiaoxiao|xiaoyi|huihui|female|女/i },
  下家: { pitch: 1.13, rate: 1.1, voice: /yunxi|yunyang|male|男/i },
  对家: { pitch: 0.72, rate: 0.88, voice: /yunjian|male|男/i },
  上家: { pitch: 1.02, rate: 0.94, voice: /xiaoxiao|huihui|female|女/i },
})

export function voiceProfileForSeat(selfSeat, seat) {
  const role = seat === selfSeat ? 'self' : relativeOpponents(selfSeat).find((item) => item.seat_wind === seat)?.role
  return PROFILES[role] || PROFILES.self
}

export function spokenAction(action, tile, isZimo = false) {
  if (action === 'DISCARD') return tile ? (HONOR_VOICES[tile]?.text || tileLabel(tile)) : ''
  if (action === 'WIN' && isZimo) return '自摸！'
  return { CHI: '吃！', PONG: '碰！', GANG: '杠！', WIN: '胡了！' }[action] || ''
}

/** Fetch/decode clips without media elements; speech is a compatibility fallback. */
export function createSoundEngine(browser = globalThis) {
  let volume = 0.7
  let muted = false
  let context = null
  let clickBuffer = null
  let speaking = false
  let activeUtterance = null
  let pending = null
  let speechTimeout = null
  let voiceWaitTimer = null
  let voiceWaitExpired = false
  let primingUtterance = null
  let speechUnlocked = false
  const preferClips = !!((browser.AudioContext || browser.webkitAudioContext) && browser.fetch)
  const clipBuffers = new Map()
  const clipLoads = new Map()
  const activeSources = new Set()
  let disposed = false
  let clipSequence = 0
  let nextClipTime = 0
  const synth = browser.speechSynthesis
  let voices = []

  function refreshVoices() {
    try { voices = synth?.getVoices?.() || [] } catch { voices = [] }
    if (voices.length) {
      clearTimeout(voiceWaitTimer)
      voiceWaitTimer = null
      pump()
    }
  }
  synth?.addEventListener?.('voiceschanged', refreshVoices)
  refreshVoices()

  function stopClips() {
    clipSequence++
    nextClipTime = 0
    for (const source of activeSources) {
      try { source.stop() } catch { /* Already ended. */ }
    }
    activeSources.clear()
  }

  function decodeClip(bytes, audioContext) {
    return new Promise((resolve, reject) => {
      try {
        const result = audioContext.decodeAudioData(bytes, resolve, reject)
        result?.then?.(resolve, reject)
      } catch (error) { reject(error) }
    })
  }

  function loadClip(code) {
    if (clipBuffers.has(code)) return Promise.resolve(true)
    if (clipLoads.has(code)) return clipLoads.get(code)
    const audioContext = context
    const load = (async () => {
      try {
        // A data asset, never a media URL/element or a blob URL. Only requested
        // from playAction, after the corresponding action actually occurs.
        const response = await browser.fetch(`${CLIP_BASE}${HONOR_VOICES[code]?.file || code}.dat`, {
          headers: { Accept: 'application/octet-stream' },
        })
        if (!response.ok) return false
        const bytes = await response.arrayBuffer()
        if (!bytes.byteLength || disposed) return false
        const buffer = await decodeClip(unpackVoiceData(bytes), audioContext)
        if (disposed) return false
        clipBuffers.set(code, buffer)
        return true
      } catch { return false }
    })()
    clipLoads.set(code, load)
    // Share concurrent requests, but allow a later real action to retry failures.
    void load.then(() => { if (clipLoads.get(code) === load) clipLoads.delete(code) })
    return load
  }

  function playClip(code, profile) {
    const buffer = clipBuffers.get(code)
    if (!buffer || !context || muted || volume === 0) return false
    try {
      unlockAudio()
      const source = context.createBufferSource()
      const gain = context.createGain()
      source.buffer = buffer
      source.playbackRate.value = profile.rate
      gain.gain.value = volume
      source.connect(gain).connect(context.destination)
      const startAt = Math.max(context.currentTime + 0.14, nextClipTime)
      nextClipTime = startAt + buffer.duration / profile.rate + 0.04
      source.onended = () => activeSources.delete(source)
      activeSources.add(source)
      source.start(startAt)
      return true
    } catch { return false }
  }

  function setVolume(value) {
    volume = Math.min(1, Math.max(0, Number(value) || 0))
    if (volume === 0) {
      stopClips()
      pending = null
      clearTimeout(speechTimeout)
      activeUtterance = null
      speaking = false
      primingUtterance = null
      synth?.cancel?.()
    }
    return volume
  }
  function setMuted(value) {
    muted = !!value
    if (muted) {
      stopClips()
      pending = null
      clearTimeout(speechTimeout)
      synth?.cancel?.()
      speaking = false
      activeUtterance = null
      primingUtterance = null
    }
    return muted
  }
  function unlockAudio() {
    if (disposed) return
    const AudioContext = browser.AudioContext || browser.webkitAudioContext
    if (!context && AudioContext) context = new AudioContext()
    if (context?.state === 'suspended') void Promise.resolve(context.resume()).catch(() => {})
  }
  function unlock() {
    unlockAudio()
    // iOS / WebView requires speak() itself to run in the first user gesture.
    if (!preferClips && !speechUnlocked && synth?.speak && browser.SpeechSynthesisUtterance && !muted && volume > 0) {
      try {
        primingUtterance = new browser.SpeechSynthesisUtterance('。')
        primingUtterance.lang = 'zh-CN'
        primingUtterance.volume = 0
        primingUtterance.onend = () => { primingUtterance = null }
        primingUtterance.onerror = () => { primingUtterance = null }
        synth.speak(primingUtterance)
        synth.resume?.()
        speechUnlocked = true
      } catch { primingUtterance = null }
    }
  }
  function onBridgeReady() {
    if (!preferClips) return
    unlockAudio()
  }
  browser.document?.addEventListener?.('WeixinJSBridgeReady', onBridgeReady)
  function fallbackCue() {
    // A distinct two-tone cue still announces an action on devices without TTS.
    try {
      unlockAudio()
      if (!context) return
      const now = context.currentTime
      for (const [offset, frequency] of [[0, 660], [0.13, 880]]) {
        const oscillator = context.createOscillator()
        const gain = context.createGain()
        oscillator.frequency.value = frequency
        gain.gain.setValueAtTime(Math.max(0.001, volume * 0.12), now + offset)
        gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.11)
        oscillator.connect(gain).connect(context.destination)
        oscillator.start(now + offset)
        oscillator.stop(now + offset + 0.12)
      }
    } catch { /* No audio output is available on this device. */ }
  }
  function tap(win = false) {
    if (muted || volume === 0) return
    try {
      unlockAudio()
      if (!context) return
      const now = context.currentTime
      if (!win) {
        if (!clickBuffer) {
          clickBuffer = context.createBuffer(1, Math.ceil(context.sampleRate * 0.025), context.sampleRate)
          const samples = clickBuffer.getChannelData(0)
          for (let i = 0; i < samples.length; i++) samples[i] = (Math.random() * 2 - 1) * (1 - i / samples.length)
        }
        for (const offset of [0, 0.065]) {
          const source = context.createBufferSource()
          const filter = context.createBiquadFilter()
          const gain = context.createGain()
          source.buffer = clickBuffer
          filter.type = 'bandpass'
          filter.frequency.value = offset ? 1250 : 1850
          filter.Q.value = 0.8
          gain.gain.value = volume * (offset ? 0.16 : 0.24)
          source.connect(filter).connect(gain).connect(context.destination)
          source.start(now + offset)
        }
        return
      }
      for (const [offset, frequency] of [[0, 440], [0.1, 660], [0.2, 880]]) {
        const oscillator = context.createOscillator()
        const gain = context.createGain()
        oscillator.type = 'sine'
        oscillator.frequency.setValueAtTime(frequency, now + offset)
        oscillator.frequency.exponentialRampToValueAtTime(frequency * 0.68, now + offset + 0.07)
        gain.gain.setValueAtTime(Math.max(0.001, volume * 0.09), now + offset)
        gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.09)
        oscillator.connect(gain).connect(context.destination)
        oscillator.start(now + offset)
        oscillator.stop(now + offset + 0.1)
      }
    } catch { /* AudioContext can be unavailable or blocked; speech remains usable. */ }
  }
  function pump() {
    if (speaking || !pending || muted || volume === 0) return
    if (!synth?.speak || !browser.SpeechSynthesisUtterance) {
      pending = null
      fallbackCue()
      return
    }
    if (!voices.length && !voiceWaitExpired) {
      if (!voiceWaitTimer) voiceWaitTimer = setTimeout(() => { voiceWaitExpired = true; voiceWaitTimer = null; pump() }, 700)
      return
    }
    const { text, profile } = pending
    pending = null
    const utterance = new browser.SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    utterance.pitch = profile.pitch
    utterance.rate = profile.rate
    utterance.volume = volume
    const chinese = voices.filter((voice) => /^zh(?:-|_)/i.test(voice.lang))
    utterance.voice = chinese.find((voice) => profile.voice.test(voice.name)) || chinese[0] || null
    if (primingUtterance) {
      try { synth.cancel() } catch { /* Ignore a stale primer. */ }
      primingUtterance = null
    }
    speaking = true
    activeUtterance = utterance
    const done = () => {
      if (activeUtterance !== utterance) return
      activeUtterance = null
      speaking = false
      clearTimeout(speechTimeout)
      pump()
    }
    utterance.onend = done
    utterance.onerror = () => { fallbackCue(); done() }
    // Some browsers never deliver onend after a tab loses focus.
    speechTimeout = setTimeout(() => { synth.cancel(); fallbackCue(); done() }, 3500)
    try { synth.speak(utterance); synth.resume?.() } catch { fallbackCue(); done() }
  }
  function playAction({ action, tile, seat, selfSeat, isZimo = false }) {
    if (disposed || muted || volume === 0) return
    if (action === 'TURN') { fallbackCue(); return }
    const text = spokenAction(action, tile, isZimo)
    if (!text) return
    tap(action === 'WIN')
    const profile = voiceProfileForSeat(selfSeat, seat)
    const code = action === 'DISCARD' ? tile : action === 'WIN' && isZimo ? 'ZIMO' : action
    if ((preferClips || !synth?.speak) && CLIP_SET.has(code) && context?.decodeAudioData && browser.fetch) {
      const sequence = ++clipSequence
      if (playClip(code, profile)) return
      return loadClip(code).then(() => {
        if (sequence !== clipSequence || muted || volume === 0) return
        if (!playClip(code, profile)) {
          pending = { text, profile }
          pump()
        }
      })
      return
    }
    pending = { text, profile }
    pump()
  }
  function stop(dispose = false) {
    pending = null
    clearTimeout(speechTimeout)
    clearTimeout(voiceWaitTimer)
    voiceWaitTimer = null
    voiceWaitExpired = false
    if (dispose) synth?.removeEventListener?.('voiceschanged', refreshVoices)
    if (dispose) browser.document?.removeEventListener?.('WeixinJSBridgeReady', onBridgeReady)
    stopClips()
    synth?.cancel?.()
    speaking = false
    activeUtterance = null
    primingUtterance = null
    speechUnlocked = false
    if (dispose) {
      void context?.close?.()
      context = null
      clickBuffer = null
      clipBuffers.clear()
      clipLoads.clear()
      disposed = true
    }
  }
  async function playOpening() {
    if (disposed || muted || volume === 0) return false
    unlockAudio()
    if (!context) return false
    const sequence = clipSequence
    const loaded = await loadClip('OPENING')
    if (disposed || muted || volume === 0 || sequence !== clipSequence) return false
    if (!loaded) { fallbackCue(); return false }
    return playClip('OPENING', { rate:1, pitch:1 })
  }
  return { playAction, playOpening, setVolume, setMuted, unlock, stop }
}
