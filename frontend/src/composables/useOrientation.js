import { computed, onMounted, onUnmounted, ref } from 'vue'

const STAGE_WIDTH = 1280
const STAGE_HEIGHT = 720

/** Fit the whole logical stage inside the physical safe rectangle, before rotation. */
export function tableViewportLayout(viewportWidth, viewportHeight, stageWidth = STAGE_WIDTH, stageHeight = STAGE_HEIGHT, inset = 0, maxScale = Infinity, safe = {}) {
  const top = safe.top || 0, right = safe.right || 0, bottom = safe.bottom || 0, left = safe.left || 0
  const width = Math.max(1, viewportWidth - left - right - inset * 2)
  const height = Math.max(1, viewportHeight - top - bottom - inset * 2)
  const portrait = viewportHeight > viewportWidth
  const scale = Math.min(maxScale, width / (portrait ? stageHeight : stageWidth), height / (portrait ? stageWidth : stageHeight))
  return { scale, portrait, x: (left - right) / 2, y: (top - bottom) / 2,
    transform: `translate(-50%, -50%) translate(${(left - right) / 2}px, ${(top - bottom) / 2}px) ${portrait ? 'rotate(-90deg) ' : ''}scale(${scale})` }
}

export function useOrientation(stageWidth = STAGE_WIDTH, stageHeight = STAGE_HEIGHT, inset = 0, maxScale = Infinity) {
  const viewportWidth = ref(typeof window === 'undefined' ? STAGE_WIDTH : window.innerWidth)
  const viewportHeight = ref(typeof window === 'undefined' ? STAGE_HEIGHT : window.innerHeight)
  const safeArea = ref({})
  let probe
  const isPortrait = computed(() => viewportHeight.value > viewportWidth.value)
  const stageTransform = computed(() => tableViewportLayout(viewportWidth.value, viewportHeight.value, stageWidth, stageHeight, inset, maxScale, safeArea.value).transform)

  function updateViewport() {
    viewportWidth.value = window.innerWidth
    viewportHeight.value = window.innerHeight
    if (probe) {
      const style = window.getComputedStyle(probe)
      safeArea.value = Object.fromEntries(['top', 'right', 'bottom', 'left'].map(side => [side, parseFloat(style.getPropertyValue(`padding-${side}`)) || 0]))
    }
  }
  onMounted(() => {
    // Resolve env() in physical pixels; subtracting it after scale/rotation clips edges.
    probe = document.createElement('div')
    probe.style.cssText = 'position:fixed;visibility:hidden;pointer-events:none;padding:env(safe-area-inset-top, 0px) env(safe-area-inset-right, 0px) env(safe-area-inset-bottom, 0px) env(safe-area-inset-left, 0px)'
    document.body.appendChild(probe)
    updateViewport()
    window.addEventListener('resize', updateViewport, { passive: true })
    window.addEventListener('orientationchange', updateViewport, { passive: true })
  })
  onUnmounted(() => {
    probe?.remove()
    window.removeEventListener('resize', updateViewport)
    window.removeEventListener('orientationchange', updateViewport)
  })
  return { isPortrait, stageTransform }
}
