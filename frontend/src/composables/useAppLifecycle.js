import { onMounted, onUnmounted, ref } from 'vue'
import { lifecycle, statusBar } from '../platform/index.js'
import { auth, restoreAuth } from '../stores/auth.js'
import { activeMatch, refreshMatch } from '../stores/activeMatch.js'
import { resumeRealtimeConnections, pauseRealtimeConnections } from '../utils/realtimeConnection.js'

export function useAppLifecycle() {
  const error = ref('')
  let stopResume, stopPause, pending, disposed = false, paused = false
  function resume() {
    paused = false
    if (pending || disposed) return pending
    pending = (async () => {
      error.value = ''
      await statusBar.dark()
      if (!auth.token) { if (!disposed && !paused) resumeRealtimeConnections(); return }
      const token = auth.token
      try {
        auth.restored = false
        await restoreAuth()
        if (disposed || token !== auth.token) return
        const id = auth.user?.active_match_id || activeMatch.match?.id
        if (id) await refreshMatch(id)
      } catch (failure) { error.value = failure.message }
      finally { if (!disposed && !paused) resumeRealtimeConnections() }
    })().finally(() => { pending = null })
    return pending
  }
  onMounted(() => { stopResume = lifecycle.onResume(resume); stopPause = lifecycle.onPause(() => { paused = true; pauseRealtimeConnections() }) })
  onUnmounted(() => { disposed = true; stopResume?.(); stopPause?.() })
  return { error }
}
