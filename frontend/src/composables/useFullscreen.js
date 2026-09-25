import { onMounted, onUnmounted, ref } from 'vue'

const CHANGE_EVENTS = ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange']

function fullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement
}

export function useFullscreen() {
  const isFullscreen = ref(false)
  const fullscreenError = ref('')
  const fullscreenAvailable = typeof document !== 'undefined' && !!(
    document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen ||
    document.documentElement.mozRequestFullScreen || document.documentElement.msRequestFullscreen
  )

  function syncFullscreen() {
    isFullscreen.value = !!fullscreenElement()
    document.documentElement.classList.toggle('game-fullscreen-scroll-lock', isFullscreen.value)
    document.body?.classList.toggle('game-fullscreen-scroll-lock', isFullscreen.value)
  }

  // The browser API must be called before the first await to retain the click's user activation.
  async function enterFullscreen() {
    fullscreenError.value = ''
    if (typeof document === 'undefined') return false
    if (fullscreenElement()) { syncFullscreen(); return true }
    const element = document.documentElement
    const request = element.requestFullscreen || element.webkitRequestFullscreen ||
      element.mozRequestFullScreen || element.msRequestFullscreen
    if (!request) {
      fullscreenError.value = '当前浏览器不支持网页全屏'
      return false
    }
    try {
      await request.call(element)
      syncFullscreen()
      return isFullscreen.value
    } catch (error) {
      fullscreenError.value = error?.message || '当前浏览器无法进入全屏'
      syncFullscreen()
      return false
    }
  }

  async function exitFullscreen() {
    fullscreenError.value = ''
    if (typeof document === 'undefined') return false
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
    return fullscreenElement() ? exitFullscreen() : enterFullscreen()
  }

  onMounted(() => {
    syncFullscreen()
    CHANGE_EVENTS.forEach((event) => document.addEventListener(event, syncFullscreen))
  })
  onUnmounted(() => {
    CHANGE_EVENTS.forEach((event) => document.removeEventListener(event, syncFullscreen))
    document.documentElement.classList.remove('game-fullscreen-scroll-lock')
    document.body?.classList.remove('game-fullscreen-scroll-lock')
  })

  return { isFullscreen, fullscreenAvailable, fullscreenError, enterFullscreen, exitFullscreen, toggleFullscreen }
}
