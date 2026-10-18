import { onMounted, onUnmounted } from 'vue'
import { orientation, keepAwake, statusBar } from '../platform/index.js'

export function useTableOrientation(enabled = true) {
  onMounted(() => { if (enabled) { void statusBar.enterTable(); void orientation.enterTable(); void keepAwake.acquire() } })
  onUnmounted(() => { if (enabled) { void statusBar.leaveTable(); void orientation.leaveTable(); void keepAwake.release() } })
}
