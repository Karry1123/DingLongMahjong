import * as session from '../platform/secureSession.js'
import { resolveApiBase } from './apiBase.js'
let onUnauthorized = () => { if (globalThis.location && !/^#\/(login|register)(?:[?]|$)/.test(location.hash)) location.hash = '/login' }
export function setUnauthorizedHandler(handler) { onUnauthorized = handler }
export function apiUrl(path, base = import.meta.env?.VITE_API_BASE_URL || '', origin = globalThis.location?.origin || 'http://localhost') {
  return new URL(`${resolveApiBase(base, origin)}/api${path}`, origin).href
}
export function socketUrl(path, base, origin) { const url = new URL(apiUrl(path, base, origin)); url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'; return url.href }
export async function authenticatedFetch(path, { method = 'GET', body, auth = true, signal } = {}, fetcher = globalThis.fetch) {
  const token = session.get()
  const response = await fetcher(apiUrl(path), { method, signal, headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(auth && token ? { Authorization: `Bearer ${token}` } : {}) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  const data = response.status === 204 ? null : await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 401 && auth) { try { await session.clear() } catch { /* In-memory session is already cleared. */ } onUnauthorized() }
    throw Object.assign(new Error(typeof data?.detail === 'string' ? data.detail : '请求失败，请稍后重试'), { status: response.status, code: data?.code })
  }
  return data
}
export const post = (path, body) => authenticatedFetch(path, { method: 'POST', body })
