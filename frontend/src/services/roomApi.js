import { fetchWithWakeNotice } from './api.js'
import { resolveApiBase } from './apiBase.js'

const base = resolveApiBase(import.meta.env?.VITE_API_BASE_URL || '')
export async function roomRequest(path, payload, signal) {
  const response = await fetchWithWakeNotice(roomHttpUrl(path), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal,
  }, { timeoutMs: 15000 })
  const data = await response.json()
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : '房间请求失败，请稍后重试')
    error.status = response.status
    throw error
  }
  return data
}

export function roomHttpUrl(path = '', apiBase = base, origin = location.origin) {
  return new URL(`${resolveApiBase(apiBase, origin)}/api/rooms${path}`, origin).href
}

export function roomSocketUrl(roomId, apiBase = base, origin = location.origin) {
  const url = new URL(roomHttpUrl(`/${roomId}/ws`, apiBase, origin))
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.href
}
