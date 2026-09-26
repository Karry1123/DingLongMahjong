import { ALL_TILES, relativeOpponents, tileLabel } from '../constants/tiles.js'

const CLIP_CODES = [...ALL_TILES, 'CHI', 'PONG', 'GANG', 'WIN']
const CLIP_SET = new Set(CLIP_CODES)
const CLIP_BASE = `${(import.meta.env?.BASE_URL || '/').replace(/\/?$/, '/')}audio/tiles/`

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

export function spokenAction(action, tile) {
  if (action === 'DISCARD') return tile ? tileLabel(tile) : ''
  return { CHI: '吃！', PONG: '碰！', GANG: '杠！', WIN: '胡了！' }[action] || ''
}

/** Predecoded clips for WeChat, browser speech elsewhere, and synthesized table cues. */
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
  const preferClips = /MicroMessenger/i.test(browser.navigator?.userAgent || '')
  const clipBuffers = new Map()
  const clipLoads = new Map()
  const activeSources = new Set()
  let preloadPromise = null
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

  function decodeClip(bytes) {
    return new Promise((resolve, reject) => {
      try {
        const result = context.decodeAudioData(bytes, resolve, reject)
        result?.then?.(resolve, reject)
      } catch (error) { reject(error) }
    })
  }

  function loadClip(code) {
    if (clipBuffers.has(code)) return Promise.resolve(true)
    if (clipLoads.has(code)) return clipLoads.get(code)
    const load = (async () => {
      try {
        const response = await browser.fetch(`${CLIP_BASE}${code}.wav`)
        if (!response.ok) return false
        clipBuffers.set(code, await decodeClip(await response.arrayBuffer()))
        return true
      } catch { return false }
    })()
    clipLoads.set(code, load)
    return load
  }

  function preloadClips() {
    if (preloadPromise) return preloadPromise
    if (!context?.decodeAudioData || !browser.fetch) return Promise.resolve()
    let next = 0
    preloadPromise = Promise.all(Array.from({ length: 4 }, async () => {
      while (next < CLIP_CODES.length) {
        const code = CLIP_CODES[next++]
        await loadClip(code)
      }
    }))
    return preloadPromise
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
    const AudioContext = browser.AudioContext || browser.webkitAudioContext
    if (!context && AudioContext) context = new AudioContext()
    if (context?.state === 'suspended') void Promise.resolve(context.resume()).catch(() => {})
  }
  function unlock() {
    unlockAudio()
    const clipsReady = preferClips ? preloadClips() : undefined
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
    return clipsReady
  }
  function onBridgeReady() {
    if (!preferClips) return
    unlockAudio()
    void preloadClips()
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
  function playAction({ action, tile, seat, selfSeat }) {
    if (muted || volume === 0) return
    const text = spokenAction(action, tile)
    if (!text) return
    tap(action === 'WIN')
    const profile = voiceProfileForSeat(selfSeat, seat)
    const code = action === 'DISCARD' ? tile : action
    if ((preferClips || !synth?.speak) && CLIP_SET.has(code) && context?.decodeAudioData && browser.fetch) {
      const sequence = ++clipSequence
      if (playClip(code, profile)) return
      void loadClip(code).then(() => {
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
      preloadPromise = null
    }
  }
  return { playAction, setVolume, setMuted, unlock, stop }
}
