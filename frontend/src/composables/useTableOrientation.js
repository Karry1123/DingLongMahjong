import { onMounted, onUnmounted } from 'vue'
import { orientation, keepAwake } from '../platform/index.js'

export function useTableOrientation(enabled = true) {
  onMounted(() => { if (enabled) { void orientation.enterTable(); void keepAwake.acquire() } })
  onUnmounted(() => { if (enabled) { void orientation.leaveTable(); void keepAwake.release() } })
}
