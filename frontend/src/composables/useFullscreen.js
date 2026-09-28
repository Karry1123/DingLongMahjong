import { onMounted, onUnmounted, ref } from 'vue'

const CHANGE_EVENTS = ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange']

function fullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement
}

export function useFullscreen(options = {}) {
  const isFullscreen = ref(false)
  const immersive = ref(false)
  let disposed = false, generation = 0
  const fullscreenError = ref('')
  const fullscreenAvailable = typeof document !== 'undefined' && !!(
    document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen ||
    document.documentElement.mozRequestFullScreen || document.documentElement.msRequestFullscreen || options.mobileFallback
  )

  function syncFullscreen() {
    if (disposed) return
    isFullscreen.value = !!fullscreenElement() || immersive.value
    document.documentElement.classList.toggle('game-fullscreen-scroll-lock', isFullscreen.value)
    document.body?.classList.toggle('game-fullscreen-scroll-lock', isFullscreen.value)
  }

  function setImmersive(value) {
    immersive.value = value
    document.documentElement.classList.toggle('pvp-immersive-fullscreen', value)
    document.body?.classList.toggle('pvp-immersive-fullscreen', value)
    syncFullscreen()
  }
  function preventPageScroll(event) {
    if (immersive.value && event.cancelable && !event.target?.closest?.('input,textarea,.landscape-winner-hand')) event.preventDefault()
  }
  const mobile = () => typeof window !== 'undefined' && (window.matchMedia?.('(pointer: coarse)').matches || navigator.maxTouchPoints > 0 || /MicroMessenger|Android|iPhone|iPad/i.test(navigator.userAgent))

  // The browser API must be called before the first await to retain the click's user activation.
  async function enterFullscreen() {
    const attempt = ++generation
    fullscreenError.value = ''
    if (typeof document === 'undefined') return false
    if (fullscreenElement()) { syncFullscreen(); return true }
    const element = document.documentElement
    const request = element.requestFullscreen || element.webkitRequestFullscreen ||
      element.mozRequestFullScreen || element.msRequestFullscreen
    if (!request) {
      if (options.mobileFallback) { setImmersive(true); return true }
      fullscreenError.value = '当前浏览器不支持网页全屏'
      return false
    }
    try {
      await request.call(element)
      if (disposed || attempt !== generation) return false
      syncFullscreen()
      if (!isFullscreen.value && options.mobileFallback) setImmersive(true)
      return isFullscreen.value
    } catch (error) {
      if (disposed || attempt !== generation) return false
      if (options.mobileFallback) { setImmersive(true); fullscreenError.value = ''; return true }
      fullscreenError.value = error?.message || '当前浏览器无法进入全屏'
      syncFullscreen()
      return false
    }
  }

  async function exitFullscreen() {
    generation++
    fullscreenError.value = ''
    if (typeof document === 'undefined') return false
    if (immersive.value) setImmersive(false)
    if (!fullscreenElement()) { syncFullscreen(); return true }
    const exit = document.exitFullscreen || document.webkitExitFullscreen ||
      document.mozCancelFullScreen || document.msExitFullscreen
    if (!exit) return false
    try {
      await exit.call(document)
      syncFullscreen()
      return !isFullscreen.value
    } catch (error) {
      fullscreenError.value = error?.message || '当前浏览器无法退出全屏'
      syncFullscreen()
      return false
    }
  }

  function toggleFullscreen() {
    return fullscreenElement() || immersive.value ? exitFullscreen() : enterFullscreen()
  }

  onMounted(() => {
    syncFullscreen()
    CHANGE_EVENTS.forEach((event) => document.addEventListener(event, syncFullscreen))
    if (options.mobileFallback) document.addEventListener('touchmove', preventPageScroll, { passive:false })
    if (options.autoEnter && mobile()) void enterFullscreen()
  })
  onUnmounted(() => {
    generation++; disposed = true
    if (immersive.value) { document.documentElement.classList.remove('pvp-immersive-fullscreen'); document.body?.classList.remove('pvp-immersive-fullscreen') }
    document.removeEventListener('touchmove', preventPageScroll)
    CHANGE_EVENTS.forEach((event) => document.removeEventListener(event, syncFullscreen))
    document.documentElement.classList.remove('game-fullscreen-scroll-lock')
    document.body?.classList.remove('game-fullscreen-scroll-lock')
  })

  return { isFullscreen, immersive, fullscreenAvailable, fullscreenError, enterFullscreen, exitFullscreen, toggleFullscreen }
}
