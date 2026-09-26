import { computed, onMounted, onUnmounted, ref } from 'vue'

const STAGE_WIDTH = 1280
const STAGE_HEIGHT = 720

/** Keep the PvE stage at one logical landscape size on every screen. */
export function useOrientation(stageWidth = STAGE_WIDTH, stageHeight = STAGE_HEIGHT, inset = 0, maxScale = Infinity) {
  const viewportWidth = ref(typeof window === 'undefined' ? STAGE_WIDTH : window.innerWidth)
  const viewportHeight = ref(typeof window === 'undefined' ? STAGE_HEIGHT : window.innerHeight)
  const isPortrait = computed(() => viewportHeight.value > viewportWidth.value)
  const stageTransform = computed(() => {
    const width = Math.max(1, viewportWidth.value - inset * 2)
    const height = Math.max(1, viewportHeight.value - inset * 2)
    const scale = isPortrait.value
      ? Math.min(maxScale, width / stageHeight, height / stageWidth)
      : Math.min(maxScale, width / stageWidth, height / stageHeight)
    // The bottom of the landscape board must land on the phone's right edge.
    return `translate(-50%, -50%) ${isPortrait.value ? 'rotate(-90deg) ' : ''}scale(${scale})`
  })

  function updateViewport() {
    viewportWidth.value = window.innerWidth
    viewportHeight.value = window.innerHeight
  }
  onMounted(() => {
    updateViewport()
    window.addEventListener('resize', updateViewport, { passive: true })
    window.addEventListener('orientationchange', updateViewport, { passive: true })
  })
  onUnmounted(() => {
    window.removeEventListener('resize', updateViewport)
    window.removeEventListener('orientationchange', updateViewport)
  })
  return { isPortrait, stageTransform }
}
