import { onUnmounted, ref, watch } from 'vue'
import { auth, clearAuth } from '../stores/auth.js'
import { refreshFriends } from '../stores/friends.js'
import { refreshInvitations } from '../stores/invitations.js'
import { activeMatch, refreshMatch } from '../stores/activeMatch.js'
import { socketUrl } from '../services/authenticatedFetch.js'
import { createRealtimeConnection } from '../utils/realtimeConnection.js'
export function useSocialSocket() {
 const status = ref('idle'), error = ref(''); let connection
 const run = promise => promise.catch(e => { error.value = e.message })
 const stop = watch(() => auth.token, token => {
  connection?.stop(); connection = null
  if (!token) return
  connection = createRealtimeConnection({ url: socketUrl('/realtime/ws'), onStatus: value => { status.value = value }, onTerminal: code => { if (code === 4401) clearAuth() },
   onMessage(message) {
    if (message.type === 'authenticated') { run(refreshFriends()); run(refreshInvitations()); if (activeMatch.match) run(refreshMatch(activeMatch.match.id)); }
    if (['friend_request','friend_update'].includes(message.type)) run(refreshFriends())
    if (['invitation','invitation_update'].includes(message.type)) run(refreshInvitations())
    if (['match_update','invitation_update'].includes(message.type) && activeMatch.match?.id === message.match_id) run(refreshMatch(message.match_id))
   },
  }); connection.start()
 }, { immediate: true })
 onUnmounted(() => { stop(); connection?.stop() })
 return { status, error }
}
