import * as session from '../platform/secureSession.js'
const liveConnections = new Set()
let appPaused = false
export function pauseRealtimeConnections() { appPaused = true; for (const connection of liveConnections) connection.pause() }
export function resumeRealtimeConnections() { appPaused = false; for (const connection of liveConnections) connection.resume() }
export function createRealtimeConnection({ url, onMessage, onStatus = () => {}, onTerminal = () => {}, Socket = globalThis.WebSocket, schedule = setTimeout, cancel = clearTimeout }) {
 let socket, retry, heartbeat, handshake, stopped = true, attempt = 0, paused = false
 function clearTimers() { cancel(retry); cancel(handshake); clearInterval(heartbeat) }
 function connect() {
  if (stopped || paused) return
  onStatus(attempt ? 'reconnecting' : 'connecting')
  const current = new Socket(url); socket = current
  let lastMessage = Date.now()
  handshake = schedule(() => current.close(), 12000)
  current.onopen = () => { if (socket === current && !stopped) current.send(JSON.stringify({ type: 'authenticate', token: session.get() })) }
  current.onmessage = event => {
   if (socket !== current || stopped) return
   let data; try { data = JSON.parse(event.data) } catch { return }
   lastMessage = Date.now()
   if (['authenticated','state','room_state'].includes(data.type)) {
    cancel(handshake); attempt = 0; onStatus(data.type === 'authenticated' ? 'syncing' : 'connected')
    if (!heartbeat) heartbeat = setInterval(() => { if (Date.now() - lastMessage > 30000) current.close(); else if (current.readyState === 1) current.send(JSON.stringify({ type:'ping' })) },10000)
   }
   onMessage(data)
  }
  current.onclose = event => {
   if (socket !== current || stopped) return
   socket = null; clearTimers(); heartbeat = null
   if ([4401,4403,4409].includes(event.code)) { stopped = true; liveConnections.delete(control); onStatus('closed'); onTerminal(event.code); return }
   onStatus('reconnecting'); retry = schedule(connect, Math.min(1000 * 2 ** attempt++, 15000))
  }
  current.onerror = () => { if (socket === current) current.close() }
 }
 const control = {
  start() { if (!stopped) return; stopped = false; liveConnections.add(control); if (appPaused) control.pause(); else connect() },
  send(data) { if (stopped || paused || socket?.readyState !== 1) return false; socket.send(JSON.stringify(data)); return true },
  pause() { if (stopped || paused) return; paused = true; clearTimers(); heartbeat = null; const previous = socket; socket = null; previous?.close(); onStatus('idle') },
  resume() { if (stopped || !paused) return; paused = false; connect() },
  stop() { stopped = true; paused = false; liveConnections.delete(control); clearTimers(); heartbeat = null; const previous = socket; socket = null; previous?.close(); onStatus('idle') },
 }
 return control
}
