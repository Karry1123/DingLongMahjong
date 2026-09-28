import { ref, watch, onScopeDispose } from 'vue'
import { calculateHuPoints } from '../services/api.js'

/** Recompute on a new win opportunity; never show a previous hand's score. */
export function useHuPreview(payload, calculate = calculateHuPoints) {
  const result = ref(null)
  const stop = watch(() => JSON.stringify(payload.value), async (key, _, onCleanup) => {
    result.value = null
    if (!payload.value) return
    const controller = new AbortController()
    let current = true
    onCleanup(() => { current = false; controller.abort() })
    try {
      const info = await calculate(JSON.parse(key), { signal: controller.signal })
      if (current) result.value = info
    } catch (error) {
      if (current && error?.name !== 'AbortError') console.warn('[hu preview]', error)
    }
  }, { immediate: true })
  onScopeDispose(stop)
  return result
}
