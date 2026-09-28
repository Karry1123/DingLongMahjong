import { onUnmounted, ref } from 'vue'
import { roomSocketUrl } from '../services/roomApi.js'

/** A disconnection ends the room; never silently reconnect a dissolved match. */
export function useRoomSocket({ onState, onClosed, onError }, Socket = globalThis.WebSocket) {
  const connected = ref(false)
  let socket, heartbeat, handshakeTimer, lastPong = 0, disposed = false, ended = false
  function clearTimers() { clearInterval(heartbeat); clearTimeout(handshakeTimer) }
  function finish(message, dissolved = false) {
    if (ended || disposed) return
    ended = true; connected.value = false; clearTimers()
    const current = socket; socket = null
    current?.close()
    onClosed(message, dissolved)
  }
  function connectRoom(roomId, credentials) {
    ended = false
    const current = new Socket(roomSocketUrl(roomId))
    socket = current
    handshakeTimer = setTimeout(() => finish('连接房间超时，请重新创建或加入'), 12000)
    current.onopen = () => { if (socket === current) current.send(JSON.stringify({ type: 'join', ...credentials })) }
    current.onmessage = event => {
      if (disposed || socket !== current) return
      let message
      try { message = JSON.parse(event.data) } catch { return }
      lastPong = Date.now()
      if (message.type === 'room_state') {
        clearTimeout(handshakeTimer)
        if (!connected.value) {
          connected.value = true
          heartbeat = setInterval(() => {
            if (Date.now() - lastPong > 25000) { finish('连接已中断，房间已解散', true); return }
            send({ type: 'ping' })
          }, 10000)
        }
        onState(message)
      } else if (message.type === 'room_closed') finish(message.message, true)
      else if (message.type === 'error') { if (!connected.value) finish(message.message); else onError(message.message) }
    }
    current.onclose = () => { if (socket === current) finish('连接已断开，房间已解散', connected.value) }
    current.onerror = () => { if (socket === current) finish('房间连接失败，请检查网络后重新加入', connected.value) }
  }
  function send(message) {
    if (!connected.value || socket?.readyState !== Socket.OPEN) return false
    socket.send(JSON.stringify(message))
    return true
  }
  function dispose() { disposed = true; clearTimers(); socket?.close(); socket = null; connected.value = false }
  onUnmounted(dispose)
  return { connected, connectRoom, send, dispose }
}
