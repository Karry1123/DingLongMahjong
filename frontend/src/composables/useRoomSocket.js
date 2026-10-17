import { onUnmounted, ref } from 'vue'
import { socketUrl } from '../services/authenticatedFetch.js'
import { createRealtimeConnection } from '../utils/realtimeConnection.js'
export function useRoomSocket({ onState, onClosed, onError }, Socket = globalThis.WebSocket) {
 const connected = ref(false), status = ref('idle'); let connection
 function dispose() { connection?.stop(); connected.value = false }
 function connectRoom(id) {
  dispose()
  connection = createRealtimeConnection({ url: socketUrl(`/matches/${encodeURIComponent(id)}/ws`), Socket,
   onStatus(value) { status.value = value; connected.value = value === 'connected' },
   onMessage(message) {
    if (['state','room_state'].includes(message.type)) onState(message)
    else if (['room_closed','match_closed'].includes(message.type)) { dispose(); onClosed(message.message || '本桌已结束', true) }
    else if (message.type === 'error') onError(message.message || message.detail || '对局操作失败')
   },
   onTerminal(code) { if (code === 4401) onClosed('登录已失效，请重新登录'); else onClosed(code === 4409 ? '此账号已在另一窗口连接本桌' : '无权访问本桌') },
  }); connection.start()
 }
 onUnmounted(dispose)
 return { connected, status, connectRoom, send: message => connected.value && connection?.send(message), dispose }
}
